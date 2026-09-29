#!/home/yoshi/ClaudeWS/wikiSystem/_venv/bin/python
"""全テーマ共通メニュー（wikilib.themes.common_menu_html）の出し分けと escape。

編集・新規は editable（閲覧者のそのページの編集の権限）で出し分け、編集には
いつも Alt+E の目印（data-hotkey="edit"）を付ける（theme.edit_hotkey は 2026-09-29 に廃止）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_sys"))

from wikilib.themes import common_menu_html  # noqa: E402


def menu(editable, page="Foo"):
    return str(common_menu_html("/w", "/w/.login", "/w", page, editable))


class CommonMenuTest(unittest.TestCase):
    def test_editable(self):
        h = menu(True)
        for word in ("ログイン", "トップ", "編集", "新規", "new-page-dialog"):
            self.assertIn(word, h)
        self.assertIn('data-hotkey="edit"', h)
        self.assertIn('action="/w/Foo"', h)
        self.assertTrue(h.startswith('<span class="common-menu">'))

    def test_new_page_dialog(self):
        # 送り先の入口URLはダイアログ自身が持つ（テーマの.contentに頼らない）
        h = menu(True)
        self.assertIn('<dialog class="new-page-dialog" data-base-url="/w">', h)
        # × は検証なしで閉じられる（入力欄が required のため）
        self.assertRegex(h, r'class="new-page-x"[^>]*formnovalidate')

    def test_not_editable(self):
        h = menu(False)
        self.assertIn("ログイン", h)
        self.assertIn("トップ", h)
        for word in ("編集", "新規", "dialog", "data-hotkey", "<form"):
            self.assertNotIn(word, h)

    def test_page_name_is_escaped(self):
        h = menu(True, 'a"<b>&日本語')
        self.assertIn('action="/w/a&quot;&lt;b&gt;&amp;日本語"', h)
        self.assertNotIn('<b>', h)


if __name__ == "__main__":
    unittest.main()
