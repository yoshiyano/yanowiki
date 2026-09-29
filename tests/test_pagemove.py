#!/usr/bin/env python3
"""ページの実体が動くときの後始末（wikilib.pagemove）のテスト。

`X.txt` と フォルダ `X/` は同居できない。`resolve_page_ref` はフォルダが
あれば必ずその中の `index` を読むので、`X.txt` を残したまま `X/` を作ると
中身はあるのに読めないページになる（`pagedb.shadowed_pages`）。そのため
下位ページを作るときは `X` を `X/index` へ動かし、下位が無くなったら
`X` へ戻す。この行き来を受け持つのがこのモジュールである。

見ているのは**紐づくものが取り残されないこと**。実体パス（subpath）が
変わると、添付・バックアップ・書きかけ・DBの行も一緒に動かないと参照が
切れる。1つでも取り残すと、画面には何も出ないまま静かに失われる。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pagemove.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import pagedb  # noqa: E402
from wikilib.backup import backed_up_subpaths  # noqa: E402
from wikilib.draft import draft_origin_path, draft_path  # noqa: E402
from wikilib.pagemove import (  # noqa: E402
    convert_folder_to_page, convert_page_to_folder, ensure_folder_path,
    folder_has_only_index,
)
from wikilib.pagesave import save_page  # noqa: E402
from wikilib.paths import resolve_page_ref  # noqa: E402


class PageMoveTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pagemove-")
        self.farm = os.path.join(self.work, "wikidata", "testwiki")
        self.wiki_dir = os.path.join(self.farm, "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, subpath, text="* 本文\n"):
        """平文を自分で置いてから記録する（取り込みと同じ経路）。"""
        path = os.path.join(self.wiki_dir, subpath + ".txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        save_page(self.wiki_dir, {}, subpath, ".txt", text, write=False)

    def save(self, subpath, text="* 本文\n"):
        """編集画面から保存したのと同じ経路（書き出しもsave_pageに任せる）。"""
        save_page(self.wiki_dir, {}, subpath, ".txt", text)

    def attach(self, subpath, name="logo.png"):
        directory = os.path.join(self.farm, "attach", subpath)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), "w") as f:
            f.write("x")

    def draft(self, subpath):
        """書きかけと、その元になった本文の目印を預ける。"""
        for locate in (draft_path, draft_origin_path):
            path = locate(self.wiki_dir, subpath)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("かきかけ")

    def has_draft(self, subpath):
        return (os.path.isfile(draft_path(self.wiki_dir, subpath)),
                os.path.isfile(draft_origin_path(self.wiki_dir, subpath)))

    def has_attach(self, subpath, name="logo.png"):
        return os.path.isfile(os.path.join(self.farm, "attach", subpath, name))


class TestConvertPageToFolder(PageMoveTestBase):
    """`X.txt` → `X/index.txt`。下位ページを作れるようにするための引っ越し。"""

    def test_本文が入口へ移る(self):
        self.put("Tech")
        self.assertTrue(convert_page_to_folder(self.wiki_dir, {}, "Tech"))
        self.assertTrue(os.path.isfile(os.path.join(self.wiki_dir, "Tech", "index.txt")))
        self.assertFalse(os.path.isfile(os.path.join(self.wiki_dir, "Tech.txt")))

    def test_DBの実体パスも付け替わる(self):
        self.put("Tech")
        convert_page_to_folder(self.wiki_dir, {}, "Tech")
        self.assertEqual(pagedb.all_subpaths(self.wiki_dir), ["Tech/index"])

    def test_添付も一緒に動く(self):
        # attach/Tech → attach/Tech/index。自分の下へ動かす形になる
        self.put("Tech")
        self.attach("Tech")
        convert_page_to_folder(self.wiki_dir, {}, "Tech")
        self.assertTrue(self.has_attach("Tech/index"))

    def test_書きかけも一緒に動く(self):
        # .draft だけでなく .draft.origin も動かす。origin が古い名前に残ると
        # 再開時の「預けてから更新されていないか」の判定が基準を失う
        self.put("Tech")
        self.draft("Tech")
        convert_page_to_folder(self.wiki_dir, {}, "Tech")
        self.assertEqual(self.has_draft("Tech"), (False, False))
        self.assertEqual(self.has_draft("Tech/index"), (True, True))

    def test_変更の記録も引き継ぐ(self):
        self.put("Tech")
        self.assertEqual(backed_up_subpaths(self.wiki_dir), ["Tech"])
        convert_page_to_folder(self.wiki_dir, {}, "Tech")
        self.assertEqual(backed_up_subpaths(self.wiki_dir), ["Tech/index"])

    def test_ページが無ければ何もしない(self):
        self.assertFalse(convert_page_to_folder(self.wiki_dir, {}, "Tech"))


class TestConvertFolderToPage(PageMoveTestBase):
    """`X/index.txt` → `X.txt`。下位が無くなったフォルダを畳む、逆向き。"""

    def test_入口だけになったら畳める(self):
        self.put("Tech/index")
        self.assertTrue(folder_has_only_index(self.wiki_dir, "Tech"))
        self.assertTrue(convert_folder_to_page(self.wiki_dir, {}, "Tech"))
        self.assertTrue(os.path.isfile(os.path.join(self.wiki_dir, "Tech.txt")))
        self.assertFalse(os.path.isdir(os.path.join(self.wiki_dir, "Tech")))

    def test_下位が残っていれば畳まない(self):
        self.put("Tech/index")
        self.put("Tech/Foo")
        self.assertFalse(convert_folder_to_page(self.wiki_dir, {}, "Tech"))

    def test_添付と書きかけも戻る(self):
        self.put("Tech/index")
        self.attach("Tech/index")
        self.draft("Tech/index")
        convert_folder_to_page(self.wiki_dir, {}, "Tech")
        self.assertTrue(self.has_attach("Tech"))
        self.assertEqual(self.has_draft("Tech"), (True, True))

    def test_行きと帰りで元に戻る(self):
        self.put("Tech")
        self.attach("Tech")
        convert_page_to_folder(self.wiki_dir, {}, "Tech")
        convert_folder_to_page(self.wiki_dir, {}, "Tech")
        self.assertEqual(pagedb.all_subpaths(self.wiki_dir), ["Tech"])
        self.assertTrue(self.has_attach("Tech"))


class TestEnsureFolderPath(PageMoveTestBase):
    """下位ページを作る前に、途中の階層をフォルダにしておく。"""

    def test_途中のページを入口へ移す(self):
        self.put("Tech")
        moved = ensure_folder_path(self.wiki_dir, {}, "Tech/ChangeLog/2026-01-01")
        self.assertEqual(moved, ["Tech"])
        self.assertTrue(os.path.isfile(os.path.join(self.wiki_dir, "Tech", "index.txt")))

    def test_すでにフォルダなら触らない(self):
        self.put("Tech/index")
        self.assertEqual(ensure_folder_path(self.wiki_dir, {}, "Tech/Foo"), [])

    def test_何段でも遡ってフォルダにする(self):
        self.put("Tech")
        self.put("Tech/ChangeLog")   # ここも下位を持つのでフォルダになる
        ensure_folder_path(self.wiki_dir, {}, "Tech/ChangeLog/2026-01-01")
        self.assertTrue(os.path.isfile(
            os.path.join(self.wiki_dir, "Tech", "ChangeLog", "index.txt")))


class TestSaveDoesNotShadow(PageMoveTestBase):
    """**保存そのものが**この決まりを守る（呼ぶ側に覚えさせない）。

    `A` があるところへ `A/B` を書くと、OSから見れば `A.txt` とフォルダ `A/` が
    並ぶだけでエラーにもならない。だがwikiでは `A` が読めなくなる
    （`resolve_page_ref` はフォルダがあれば必ず `A/index` を読む）。
    Wiki設計者の指示、2026-09-05。"""

    def test_下位ページを保存しても親は読めるまま(self):
        self.save("A", "* Aのページ\n")
        self.save("A/B", "* Bのページ\n")
        ref = resolve_page_ref(self.wiki_dir, "A")
        self.assertTrue(ref.exists)
        self.assertEqual(ref.subpath, "A/index")
        self.assertEqual(ref.body, "* Aのページ\n")

    def test_読めなくなったページが残らない(self):
        self.save("A")
        self.save("A/B")
        self.assertEqual(pagedb.shadowed_pages(self.wiki_dir), [])

    def test_下位ページ自身も読める(self):
        self.save("A")
        self.save("A/B")
        self.assertTrue(resolve_page_ref(self.wiki_dir, "A/B").exists)

    def test_取り込みでは実体を動かさない(self):
        # すでに置かれているファイルを後から記録するだけの経路（pagesync）。
        # 平文の置きかたは利用者が決めたものなので、こちらからは動かさない
        self.save("A")
        path = os.path.join(self.wiki_dir, "A", "B.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("* 直接置いた\n")
        save_page(self.wiki_dir, {}, "A/B", ".txt", "* 直接置いた\n", write=False)
        self.assertTrue(os.path.isfile(os.path.join(self.wiki_dir, "A.txt")))
        self.assertEqual(pagedb.shadowed_pages(self.wiki_dir), ["A"])


if __name__ == "__main__":
    unittest.main()
