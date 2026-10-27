#!/usr/bin/env python3
"""編集画面のサイドバーのページ一覧: 名前の切り替え（自動・ファイル名・タイトル）の試験。

切り替えの動き（並べ替え・再描画・控え）はブラウザ側（`treeview.js`・`editor.js`）の
もので、ここでは見ない。サーバーが渡すもの——切り替えのボタン・トップページ行の
`pinned`・行ごとの `listname`——だけを確かめる。

実行:
    _venv/bin/python3 -m unittest tests.test_pagelist_listmode
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.editor import build_page_list_html  # noqa: E402
from wikilib.pagetree import TOP_PAGE_LABEL, build_page_tree, with_top_page_row  # noqa: E402


class PageListBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pagelist-listmode-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        self.put("index.md", "# トップ\n")
        self.put("Apple.md", "# りんご\n")
        self.put("banana.txt", "*バナナ\n")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, name, text):
        with open(os.path.join(self.wiki_dir, name), "w", encoding="utf-8") as f:
            f.write(text)

    def html(self, config=None):
        return build_page_list_html("/=testwiki/.edit", self.wiki_dir, "index", config or {})

    def embedded_tree(self, html):
        m = re.search(r'<script type="application/json" class="edit-pages-tree">(.*?)</script>',
                      html, re.S)
        return json.loads(m.group(1).replace("\\u003c", "<"))


class TestTopRow(PageListBase):

    def test_トップページの行は先頭に固定する印を持つ(self):
        tree = with_top_page_row(build_page_tree(self.wiki_dir))
        top = tree["children"][0]
        self.assertEqual(top["name"], TOP_PAGE_LABEL)
        self.assertTrue(top["pinned"])

    def test_ほかの行は印を持たない(self):
        tree = with_top_page_row(build_page_tree(self.wiki_dir))
        self.assertFalse(any(c.get("pinned") for c in tree["children"][1:]))


class TestListModeButtons(PageListBase):

    def test_切り替えは3つで初めは自動が押されている(self):
        """3つは、自動・ファイル名・タイトル（この順）。"""
        html = self.html()
        buttons = re.findall(r'<button [^>]*class="ep-listmode-btn"[^>]*>', html)
        self.assertEqual([re.search(r'data-mode="(\w+)"', b).group(1) for b in buttons],
                         ["auto", "fname", "title"])
        pressed = [re.search(r'data-mode="(\w+)"', b).group(1)
                   for b in buttons if 'aria-pressed="true"' in b]
        self.assertEqual(pressed, ["auto"])

    def test_木のデータは書きかたごとのlistnameを持つ(self):
        """「自動」はこれを見る。切り替えても、サーバーが渡す木は変わらない。"""
        tree = self.embedded_tree(self.html())
        pages = {c["name"]: c for c in tree["children"] if c["kind"] == "page"}
        self.assertEqual(pages["Apple"]["listname"], "title")    # Markdown
        self.assertEqual(pages["banana"]["listname"], "fname")   # PukiWiki記法

    def test_サーバーが渡す並びはファイル名順のまま(self):
        """表示名での並べ替えはブラウザ側。木の並びまで変えると、ほかの画面（ダイアログ・
        バックアップ管理）の順も変わってしまう。"""
        tree = self.embedded_tree(self.html())
        names = [c["name"] for c in tree["children"] if c["kind"] == "page"]
        self.assertEqual(names, [TOP_PAGE_LABEL, "Apple", "banana"])


if __name__ == "__main__":
    unittest.main()
