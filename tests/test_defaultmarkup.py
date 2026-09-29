#!/usr/bin/env python3
"""新しく作るページの記法（`edit.defaultwiki`）のテスト。

**すでにあるページの記法は拡張子で決まる**ので、この設定が効くのは
「まだ無いページ」を指したときだけである。そこを取り違えると、
`.txt` のページを `.md` として書き戻して同じ名前のページが2つできる、
といった壊れかたをするため、両方を固定してある。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_defaultmarkup.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.paths import default_markup_ext, resolve_page_ref  # noqa: E402
from wikilib.wikiconfig import default_markup  # noqa: E402


class TestDefaultMarkupSetting(unittest.TestCase):
    """設定の読みかた（wikiconfig.default_markup）。"""

    def test_書かれていなければpukiwiki(self):
        self.assertEqual(default_markup({}), "pukiwiki")
        self.assertEqual(default_markup(None), "pukiwiki")
        self.assertEqual(default_markup({"edit": {}}), "pukiwiki")

    def test_設定した記法になる(self):
        self.assertEqual(default_markup({"edit": {"defaultwiki": "markdown"}}), "markdown")
        self.assertEqual(default_markup({"edit": {"defaultwiki": "pukiwiki"}}), "pukiwiki")

    def test_大文字や前後の空白は気にしない(self):
        self.assertEqual(default_markup({"edit": {"defaultwiki": " Markdown "}}), "markdown")
        self.assertEqual(default_markup({"edit": {"defaultwiki": "PUKIWIKI"}}), "pukiwiki")

    def test_読めない値は既定に戻す(self):
        # 書き損じで新しいページが作れなくなるより、既定に戻って動き続けるほうが安全
        for value in ("html", "", "md", 1, [], None, True):
            with self.subTest(value=value):
                self.assertEqual(default_markup({"edit": {"defaultwiki": value}}), "pukiwiki")


class TestDefaultMarkupExt(unittest.TestCase):
    """記法から拡張子を決める（paths.default_markup_ext）。"""

    def test_記法ごとの拡張子(self):
        self.assertEqual(default_markup_ext("pukiwiki"), ".txt")
        self.assertEqual(default_markup_ext("markdown"), ".md")

    def test_渡さない場合と読めない値は既定(self):
        self.assertEqual(default_markup_ext(), ".txt")
        self.assertEqual(default_markup_ext(None), ".txt")
        self.assertEqual(default_markup_ext("nosuch"), ".txt")


class TestResolvePageRef(unittest.TestCase):
    """まだ無いページと、すでにあるページの見分け。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="wikitest-")
        self.wiki_dir = os.path.join(self.work, "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def write(self, name, ext):
        with open(os.path.join(self.wiki_dir, name + ext), "w", encoding="utf-8") as f:
            f.write("中身\n")

    def test_まだ無いページは設定の記法になる(self):
        self.assertEqual(resolve_page_ref(self.wiki_dir, "New", "markdown").ext, ".md")
        self.assertEqual(resolve_page_ref(self.wiki_dir, "New", "pukiwiki").ext, ".txt")

    def test_まだ無いページで渡さなければ既定(self):
        self.assertEqual(resolve_page_ref(self.wiki_dir, "New").ext, ".txt")

    def test_すでにあるページは設定に関係なくファイル側で決まる(self):
        # ここが設定に引きずられると、.txt のページを .md として書き戻して
        # 同じ名前のページが2つできてしまう
        self.write("Old", ".txt")
        self.assertEqual(resolve_page_ref(self.wiki_dir, "Old", "markdown").ext, ".txt")
        self.write("Newer", ".md")
        self.assertEqual(resolve_page_ref(self.wiki_dir, "Newer", "pukiwiki").ext, ".md")

    def test_Wikiの外は設定に関わらずNone(self):
        self.assertIsNone(resolve_page_ref(self.wiki_dir, "../../etc/passwd", "markdown"))


if __name__ == "__main__":
    unittest.main()
