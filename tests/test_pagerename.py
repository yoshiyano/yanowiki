#!/usr/bin/env python3
"""ページの名前と置き場所を変える（wikilib.pagerename）のテスト。

見ているのは**移し先の決まり**である。移し先はページ選択の木から選ぶので、
「木に出ているのに、押すと断られる」ことがあってはならない
（Wiki設計者の報告、2026-09-05）。

もう1つ、`X.txt` と フォルダ `X/` は同居できないという制約がある。
`resolve_page_ref` はフォルダがあれば必ずその中の `index` を読むため、
`X.txt` を残したまま `X/` を作ると、中身はあるのに読めないページになる
（`pagedb.shadowed_pages`）。まだ下位を持たないページを移し先に選んだときは、
そのページ自身を `X/index` へ引っ越させてからフォルダにする。ここが
抜けると**移し先に選んだページが消えたように見える**ので、実際にファイルを
動かして確かめる。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pagerename.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import pagedb, privilege_records  # noqa: E402
from unittest import mock  # noqa: E402
from wikilib.pagerename import check_folder, check_name, rename_page  # noqa: E402
from wikilib.pagesave import save_page  # noqa: E402
from wikilib.paths import resolve_page_ref  # noqa: E402


class RenameTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="rename-")
        self.farm = os.path.join(self.work, "wikidata", "testwiki")
        self.wiki_dir = os.path.join(self.farm, "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, subpath, text=""):
        """ページを1枚置く（DBにも取り込む）。"""
        path = os.path.join(self.wiki_dir, subpath + ".txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        save_page(self.wiki_dir, {}, subpath, ".txt", text, write=False)

    def attach(self, subpath, name):
        """そのページの添付を1つ置く。"""
        directory = os.path.join(self.farm, "attach", subpath)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), "w") as f:
            f.write("x")

    def body_at(self, pagepath):
        """そのページパスで**読める**中身。読めなければ None。"""
        ref = resolve_page_ref(self.wiki_dir, pagepath)
        return ref.body if ref is not None and ref.exists else None

    def exists(self, relpath):
        return os.path.exists(os.path.join(self.wiki_dir, relpath))


class TestCheckName(unittest.TestCase):
    """新しい名前として使えるか。"""

    def test_ふつうの名前は通る(self):
        self.assertIsNone(check_name("演習課題2"))

    def test_空は断る(self):
        self.assertIsNotNone(check_name(""))

    def test_区切りは名前に書けない(self):
        # 置き場所は「フォルダも変更する」で選ぶもので、名前に混ぜない
        self.assertIsNotNone(check_name("講義/第07回"))

    def test_拡張子の形で終わる名前は断る(self):
        # リンクに書いたとき添付ファイルと見分けが付かなくなる
        self.assertIsNotNone(check_name("メモ.txt"))

    def test_システムの目印で始まる名前は断る(self):
        self.assertIsNotNone(check_name(".attach"))
        self.assertIsNotNone(check_name("=other"))


class TestCheckFolder(RenameTestBase):
    """移し先として選べる場所。**木に出るものは、すべて通らなければならない。**"""

    def test_いちばん上はいつでも選べる(self):
        self.assertIsNone(check_folder(self.wiki_dir, ""))

    def test_下位ページを持つ場所は選べる(self):
        self.put("講義/第07回")
        self.assertIsNone(check_folder(self.wiki_dir, "講義"))

    def test_まだ下位を持たないページも選べる(self):
        # ここが 2026-09-05 まで断られていた。木には出るのに押すと
        # 「はまだありません」と言われ、選びようが無かった
        self.put("講義/第07回")
        self.assertIsNone(check_folder(self.wiki_dir, "講義/第07回"))

    def test_ページの無い場所は断る(self):
        self.put("講義/第07回")
        self.assertIsNotNone(check_folder(self.wiki_dir, "存在しない場所"))

    def test_システムの目印で始まる場所は断る(self):
        self.assertIsNotNone(check_folder(self.wiki_dir, ".attach"))


class TestMoveIntoLeafPage(RenameTestBase):
    """まだ下位を持たないページへ移す。**そこが新しくフォルダになる。**"""

    def prepare(self):
        self.put("演習課題１", "* 演習課題1\n")
        self.put("講義/第07回", "* 第7回\n[[演習課題１]]へ\n")
        self.attach("講義/第07回", "fig.png")

    def test_移せる(self):
        self.prepare()
        ok, _message, pagepath = rename_page(
            self.wiki_dir, {}, "演習課題１", "演習課題１", "講義/第07回")
        self.assertTrue(ok)
        self.assertEqual(pagepath, "講義/第07回/演習課題１")
        self.assertTrue(self.exists("講義/第07回/演習課題１.txt"))

    def test_移し先のページは読めるまま(self):
        # 実体は X/index へ動くが、ページパスは X のままなのでURLは変わらない
        self.prepare()
        rename_page(self.wiki_dir, {}, "演習課題１", "演習課題１", "講義/第07回")
        self.assertTrue(self.exists("講義/第07回/index.txt"))
        self.assertFalse(self.exists("講義/第07回.txt"))
        self.assertIsNotNone(self.body_at("講義/第07回"))

    def test_移し先の添付も一緒に付け替える(self):
        self.prepare()
        rename_page(self.wiki_dir, {}, "演習課題１", "演習課題１", "講義/第07回")
        self.assertTrue(os.path.exists(
            os.path.join(self.farm, "attach", "講義/第07回", "index", "fig.png")))

    def test_DBの実体パスも入口に付け替わる(self):
        self.prepare()
        rename_page(self.wiki_dir, {}, "演習課題１", "演習課題１", "講義/第07回")
        self.assertEqual(pagedb.all_subpaths(self.wiki_dir),
                         ["講義/第07回/index", "講義/第07回/演習課題１"])

    def test_移し先からのリンクは直る(self):
        # 元は `[[演習課題１]]`（裸＝ルートからの絶対）。指し先が動いただけで
        # 参照元は動いていないので、絶対のまま新しい場所を指す
        self.prepare()
        rename_page(self.wiki_dir, {}, "演習課題１", "演習課題１", "講義/第07回")
        self.assertIn("[[講義/第07回/演習課題１]]", self.body_at("講義/第07回"))

    def test_フォルダを移しても同じように入口ができる(self):
        self.put("資料/index", "* 資料\n")
        self.put("資料/補足", "* 補足\n")
        self.put("講義/第07回", "* 第7回\n")
        ok, _message, _pagepath = rename_page(
            self.wiki_dir, {}, "資料/index", "資料", "講義/第07回")
        self.assertTrue(ok)
        self.assertTrue(self.exists("講義/第07回/index.txt"))
        self.assertTrue(self.exists("講義/第07回/資料/補足.txt"))


class TestMoveIntoExistingFolder(RenameTestBase):
    """すでにフォルダになっている場所へ移す。作り替えは起きない。"""

    def test_入口は作り替えない(self):
        self.put("演習課題１", "* 演習課題1\n")
        self.put("講義/第07回", "* 第7回\n")
        ok, _message, _pagepath = rename_page(
            self.wiki_dir, {}, "演習課題１", "演習課題１", "講義")
        self.assertTrue(ok)
        self.assertTrue(self.exists("講義/演習課題１.txt"))
        self.assertTrue(self.exists("講義/第07回.txt"))   # そのまま
        self.assertFalse(self.exists("講義/index.txt"))


class TestRefuse(RenameTestBase):
    """断るべきもの。"""

    def test_無い場所へは移せない(self):
        self.put("演習課題１")
        ok, message, _pagepath = rename_page(
            self.wiki_dir, {}, "演習課題１", "演習課題１", "存在しない場所")
        self.assertFalse(ok)
        self.assertIn("はまだありません", message)
        self.assertTrue(self.exists("演習課題１.txt"))

    def test_自分の中へは移せない(self):
        self.put("講義/第07回")
        ok, message, _pagepath = rename_page(
            self.wiki_dir, {}, "講義/第07回", "第07回", "講義/第07回")
        self.assertFalse(ok)
        self.assertIn("自分の中へ", message)

    def test_名前も置き場所も変わらなければ断る(self):
        self.put("講義/第07回")
        ok, _message, _pagepath = rename_page(
            self.wiki_dir, {}, "講義/第07回", "第07回", "講義")
        self.assertFalse(ok)

    def test_すでに使われている名前は断る(self):
        self.put("講義/第07回")
        self.put("講義/第08回")
        ok, message, _pagepath = rename_page(
            self.wiki_dir, {}, "講義/第07回", "第08回", "講義")
        self.assertFalse(ok)
        self.assertIn("すでに使われています", message)


class TestPrivilegesFollowRename(RenameTestBase):
    """アクセス制限の記録（`config/privileges`・`config/privileges.plugin`）も
    新しい名前へ付け替わる。付け替わらないと、新しい名前のページが誰でも読める。"""

    PLUGIN_HEADER = "# プラグインの記録\n"

    def setUp(self):
        super().setUp()
        self.put("Tech/index")
        self.put("Tech/Foo")
        self.put("Tech/Foo/Kid")
        self.put("Other")

    def system(self, *lines):
        entries = [privilege_records.parse_line(line) for line in lines]
        self.assertTrue(privilege_records.save(self.wiki_dir, entries))

    def plugin(self, *lines):
        path = privilege_records.plugin_path_of(self.wiki_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.PLUGIN_HEADER + "".join(line + "\n" for line in lines))

    def pages(self, entries):
        return sorted((e["page"], e["kind"], ",".join(e["who"])) for e in entries)

    def test_ページと配下の行が付け替わる(self):
        self.system("Tech/Foo:R:alice:1", "Tech/Foo/Kid:W:bob:2", "Tech/Foo/*:R:carol:3",
                    "Tech*:R:dave:4", "*/Foo:R:erin:5", "Other:R:frank:6")
        ok, message, _ = rename_page(self.wiki_dir, {}, "Tech/Foo", "Bar")
        self.assertTrue(ok, message)
        self.assertEqual(self.pages(privilege_records.load(self.wiki_dir)), [
            ("*/Foo", "R", "erin"),       # 後方一致は書き換えない
            ("Other", "R", "frank"),
            ("Tech*", "R", "dave"),       # `/` の無い前方一致も書き換えない
            ("Tech/Bar", "R", "alice"),
            ("Tech/Bar/*", "R", "carol"),
            ("Tech/Bar/Kid", "W", "bob"),
        ])

    def test_フォルダを動かすとフォルダの前方一致も付け替わる(self):
        self.system("Tech/*:R:alice:1", "Tech:W:bob:2")
        ok, message, _ = rename_page(self.wiki_dir, {}, "Tech/index", "Docs")
        self.assertTrue(ok, message)
        self.assertEqual(self.pages(privilege_records.load(self.wiki_dir)),
                         [("Docs", "W", "bob"), ("Docs/*", "R", "alice")])

    def test_プラグインの記録も付け替わり_移し先の残り物は消える(self):
        self.plugin("Tech/Foo:R:alice:1", "Tech/Bar:R:zed:0", "Other:W:bob:2")
        ok, message, _ = rename_page(self.wiki_dir, {}, "Tech/Foo", "Bar")
        self.assertTrue(ok, message)
        self.assertEqual(self.pages(privilege_records.load_plugin(self.wiki_dir)),
                         [("Other", "W", "bob"), ("Tech/Bar", "R", "alice")])
        with open(privilege_records.plugin_path_of(self.wiki_dir), encoding="utf-8") as f:
            self.assertTrue(f.read().startswith(self.PLUGIN_HEADER))

    def test_移し先に手で書いた行があれば断る(self):
        self.system("Tech/Foo:R:alice:1", "Tech/Bar:R:bob:2")
        ok, message, _ = rename_page(self.wiki_dir, {}, "Tech/Foo", "Bar")
        self.assertFalse(ok)
        self.assertIn("アクセス制限", message)
        self.assertTrue(os.path.exists(os.path.join(self.wiki_dir, "Tech/Foo.txt")))
        self.assertEqual(len(privilege_records.load(self.wiki_dir)), 2)

    def test_種類が違えば移し先の行と並ぶ(self):
        self.system("Tech/Foo:R:alice:1", "Tech/Bar:W:bob:2")
        ok, message, _ = rename_page(self.wiki_dir, {}, "Tech/Foo", "Bar")
        self.assertTrue(ok, message)
        self.assertEqual(self.pages(privilege_records.load(self.wiki_dir)),
                         [("Tech/Bar", "R", "alice"), ("Tech/Bar", "W", "bob")])

    def test_動かせなければ記録も元のまま(self):
        self.system("Tech/Foo:R:alice:1")
        self.plugin("Tech/Foo:W:bob:2")
        real = os.replace

        def fail(src, dst):
            if str(dst).endswith(".txt"):  # ページの実体だけを失敗させる
                raise OSError
            return real(src, dst)
        with mock.patch("wikilib.pagerename.os.replace", side_effect=fail):
            ok, _, _ = rename_page(self.wiki_dir, {}, "Tech/Foo", "Bar")
        self.assertFalse(ok)
        self.assertEqual(self.pages(privilege_records.load(self.wiki_dir)),
                         [("Tech/Foo", "R", "alice")])
        self.assertEqual(self.pages(privilege_records.load_plugin(self.wiki_dir)),
                         [("Tech/Foo", "W", "bob")])

    def test_動かしている間も新しい名前は制限されている(self):
        # 実体を動かした時点で、新旧どちらの名前にも行がある
        self.system("Tech/Foo:R:alice:1")
        seen = []
        real = os.replace

        def spy(src, dst):
            # os は共有なので、記録ファイルの書き込み（.tmp → 本体）にも呼ばれる
            if str(dst).endswith(".txt"):
                seen.append(self.pages(privilege_records.load(self.wiki_dir)))
            return real(src, dst)
        with mock.patch("wikilib.pagerename.os.replace", side_effect=spy):
            ok, message, _ = rename_page(self.wiki_dir, {}, "Tech/Foo", "Bar")
        self.assertTrue(ok, message)
        self.assertIn(("Tech/Bar", "R", "alice"), seen[0])
        self.assertIn(("Tech/Foo", "R", "alice"), seen[0])


if __name__ == "__main__":
    unittest.main()
