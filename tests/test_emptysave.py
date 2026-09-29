#!/usr/bin/env python3
"""**本文が空の保存＝ページの削除**、という約束のまわりの守り。

Wiki設計者の報告（2026-09-10）。iPhoneで本文を編集して保存したら、**削除として
扱われた**。添付ファイルが残っていたため削除は踏みとどまり、事なきを得た。

原因は2つ重なっていた。

1. 保存の送信を横取りするJavaScriptが、**画面が低いときに黙って効かなく
   なっていた**（`.edit-buttons` がタブの行へ移されて `.page-editor` の外に
   出るため、そこから探していた `.edit-actions` が見つからない）
2. そのとき送られるフォームに、**空の `source` が最初から入っていた**ので、
   サーバーには「本文を空にして保存した」＝消す指示として届いた

このテストが見ているのは**2つ目の側**——サーバーとフォームの組み立て。
1つ目は実ブラウザでないと出ないので、`Tech/ChangeLog/2026-09-10` に確認の
記録を残してある。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_emptysave.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import draft  # noqa: E402


class TestEmptyDraft(unittest.TestCase):
    """**空の書きかけは預からない。**

    預かっても守れるものが無いのに、保存のときに「消す指示」として読まれ
    かねない（`editor.posted_source`）。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="emptysave-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def test_中身があれば預かる(self):
        self.assertTrue(draft.save_draft(self.wiki_dir, "Page", "書きかけです"))
        self.assertEqual(draft.load_draft(self.wiki_dir, "Page"), "書きかけです")

    def test_空は預からない(self):
        draft.save_draft(self.wiki_dir, "Page", "")
        self.assertIsNone(draft.load_draft(self.wiki_dir, "Page"))
        self.assertFalse(draft.has_draft(self.wiki_dir, "Page"))

    def test_空白だけも預からない(self):
        draft.save_draft(self.wiki_dir, "Page", "   \n\t\n  ")
        self.assertIsNone(draft.load_draft(self.wiki_dir, "Page"))

    def test_空を渡すと預かってあるものを消す(self):
        # 書いていたものを全部消した、という状態。**危険な形では残さない**
        draft.save_draft(self.wiki_dir, "Page", "書きかけです")
        draft.save_draft(self.wiki_dir, "Page", "")
        self.assertIsNone(draft.load_draft(self.wiki_dir, "Page"))

    def test_空でも成功として返す(self):
        # 画面側は「預かってもらえたか」で送りかたを変える。ここで偽を返すと
        # 「預かれませんでした」と出てしまう
        self.assertTrue(draft.save_draft(self.wiki_dir, "Page", ""))


class TestActionsFormHtml(unittest.TestCase):
    """保存ボタンのフォームに、**空の hidden を置かない**。

    JavaScriptが横取りできなかった場合、ブラウザはこのフォームをそのまま
    送る。`source` が空のまま入っていると、それだけで削除の指示になる。
    値を詰めるのは `editor.js` の `fill()` で、**無ければその場で作る**ので、
    HTMLに置いておく必要はない。"""

    def test_空のsourceを置いていない(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "_sys", "wikilib", "editor.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        head = source.split('<form class="edit-actions"')[1].split("</form>")[0]
        for name in ("source", "from_draft", "origin", "markup"):
            self.assertNotIn(f'name="{name}"', head,
                             f"{name} の hidden がフォームに残っている")

    def test_保存ボタンは残っている(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "_sys", "wikilib", "editor.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        head = source.split('<form class="edit-actions"')[1].split("</form>")[0]
        self.assertIn('value="save"', head)


class TestJsFindsActions(unittest.TestCase):
    """`.edit-actions` は**文書全体から**探す。

    画面が低いとき、`editor.js` 自身が `.edit-buttons`（このフォームの
    入れもの）をタブの行へ移すことがあり、そのとき `.page-editor` の外へ
    出る。入れものの中だけを探していたため null になり、**保存の横取りが
    黙って効かなくなっていた**。"""

    def js(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "_sys", "editor", "editor.js")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_文書全体から探している(self):
        self.assertIn('var actionForm = document.querySelector(".edit-actions")', self.js())

    def test_見つからなければ何もしない(self):
        # 見つからないまま addEventListener を呼ぶと例外で止まり、そこから
        # 下の処理（離脱の確認など）も動かなくなる
        body = self.js().split('var actionForm = document.querySelector(".edit-actions")')[1]
        self.assertIn("if (!actionForm) return;", body[:120])

    def test_空のときは本文をそのまま送る(self):
        # 空の保存は「消す」指示。預かってあるファイル任せにしない
        self.assertIn("var empty = !source.value.trim();", self.js())

    def test_空の保存は確認する(self):
        self.assertIn("このページを削除します", self.js())


if __name__ == "__main__":
    unittest.main()
