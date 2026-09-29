#!/usr/bin/env python3
"""ac プラグイン（折りたたみ）のテスト。

本家（kanateko氏の ac.inc.php）の書きかた（見出し・h・open・alt・all・end・
インライン）が通ること、`<details>`／チェックボックスの形で出ることを見る。
開閉の動き（`h` の見出し・全て開く）は plugin/ac.js の受け持ちで、ブラウザで確かめた。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_ac.py     （このファイルだけ）
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib.paths import farm_plugin_dir  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import parse_source  # noqa: E402


class TestAc(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="ac-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "t", "wiki")
        os.makedirs(self.wiki_dir)
        bottle.request.bind({})

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def render(self, text, ext=".txt"):
        context = PluginContext(config={}, farm="t", wiki_dir=self.wiki_dir, page="Top",
                                base_url="", ext=ext)
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        html = md.renderer.render(parse_source(md, text, ext, env), md.options, env)
        self.used = context.used_plugins
        return html

    def test_見出しを書く(self):
        html = self.render("#ac(設定手順は以下の通り。){{\n- 手順1\n}}")
        self.assertRegex(html, r'<details class="plugin-ac" id="ac-[0-9a-f]{8}">')
        self.assertIn('<span class="plugin-ac-title">設定手順は以下の通り。</span></summary>', html)
        self.assertIn('<div class="plugin-ac-body">\n<ul>\n<li>手順1</li>', html)
        self.assertIn("ac", self.used)

    def test_見出しには記法が使える(self):
        html = self.render("#ac(&color(red){注意};){{\nx\n}}")
        self.assertIn('<span class="plugin-ac-title"><span style="color:red">注意</span></span>', html)

    def test_見出しが無ければ点々(self):
        for text in ("#ac{{\nx\n}}", "#ac(){{{\nx\n}}}"):
            with self.subTest(text=text):
                self.assertIn('<span class="plugin-ac-title">…</span>', self.render(text))

    def test_hはすぐ上の見出しを使う印を付ける(self):
        html = self.render("*Windows 関連\n#ac(h){{\nx\n}}")
        self.assertIn('data-ac-head="prev"', html)
        self.assertIn('<h2 id="windows-関連">Windows 関連</h2>\n<details', html)

    def test_open_と_alt(self):
        html = self.render("#ac(alt,h,open){{\nx\n}}")
        self.assertRegex(html, r'<details class="plugin-ac" id="ac-\w+" open data-ac-head="prev">')
        self.assertIn('</details>\n<p class="plugin-ac-alt">▴ クリック or タップで詳細を表示</p>', html)

    def test_全て開くと範囲の終わり(self):
        self.assertIn('<div class="plugin-ac-ctrl" hidden><button type="button" class="plugin-ac-all">'
                      '全て開く</button></div>', self.render("#ac(all)"))
        self.assertIn('<div class="plugin-ac-ctrl plugin-ac-end" hidden></div>', self.render("#ac(end)"))

    def test_インライン(self):
        html = self.render("文中の &ac(補足,open,alt){説明}; です")
        m = re.search(r'<input type="checkbox" class="plugin-ac-check" id="(ac-\w+)" checked>'
                      r'<label class="plugin-ac-label" for="(ac-\w+)">', html)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), m.group(2))
        self.assertIn('<span class="plugin-ac-inline-body">説明</span>', html)
        self.assertIn('<span class="plugin-ac-alt">', html)

    def test_Markdownでも使える(self):
        html = self.render("#ac(**見出し**){{\n- a\n}}\n\n&ac(補足){**太字**};", ext=".md")
        self.assertIn('<span class="plugin-ac-title"><strong>見出し</strong></span>', html)
        self.assertIn('<span class="plugin-ac-inline-body"><strong>太字</strong></span>', html)

    def test_idは呼び出しごとに違う(self):
        ids = re.findall(r'id="(ac-\w+)"', self.render("#ac{{\na\n}}\n#ac{{\nb\n}}"))
        self.assertEqual(len(set(ids)), 2)

    def test_エラー(self):
        for text in ("#ac(h)", "#ac(見出し,h){{\nx\n}}", "&ac(h){x};", "&ac(all){x};", "&ac(見出し){};"):
            with self.subTest(text=text):
                self.assertIn("plugin-error", self.render(text))


if __name__ == "__main__":
    unittest.main()
