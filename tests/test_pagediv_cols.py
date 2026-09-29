#!/usr/bin/env python3
"""pagediv の cols・cols=N（行の高さを揃えず、列ごとに上から詰める。2026-09-27）のテスト。

- cols: 列＝表の列。`>` でつないだセルは始まりの列、`^` は無視、空のセルは飛ばす
- cols=N: 書いた順に左の列から1つずつ振り分け、幅は等分
- 単語の cols は、ページの並びの受け皿から拾う（cols=N は名前付きのみ）

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pagediv_cols.py     （このファイルだけ）
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

from wikilib import auth, paths, userdb  # noqa: E402
from wikilib.pagesync import sync_wiki  # noqa: E402
from wikilib.paths import farm_plugin_dir  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import parse_source  # noqa: E402

FARM = "testwiki"


class TestPagedivCols(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pagedivcols-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        self.kept = (paths.WIKIDATA_DIR, auth.SECRET_PATH)
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        for name in ("A", "B", "C", "D", "E", "F", "G", "2026"):
            with open(os.path.join(self.wiki_dir, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(f"{name}の本文\n")
        sync_wiki(self.wiki_dir, {})
        bottle.request.bind({})

    def tearDown(self):
        paths.WIKIDATA_DIR, auth.SECRET_PATH = self.kept
        shutil.rmtree(self.work, ignore_errors=True)

    def render(self, text):
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page="Top",
                                base_url="", ext=".txt")
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        return md.renderer.render(parse_source(md, text, ".txt", env), md.options, env)

    def columns(self, html):
        """列ごとの、差し込まれたページ名の並び。"""
        parts = html.split('<div class="pagediv-col">')[1:]
        return [re.findall(r">(\w+)の本文", part) for part in parts]

    def test_colsは表の列ごとに詰める(self):
        html = self.render("#pagediv(cols){{\n|A;40%|B|\n|C|>|\n|^|D|\n||E|\n}}")
        self.assertIn('<div class="pagediv pagediv-cols" style="--pd-cols: minmax(0, 40fr)'
                      ' minmax(0, 60fr);">', html)
        self.assertEqual(self.columns(html), [["A", "C"], ["B", "D", "E"]])
        self.assertNotIn("--pd-area", html)

    def test_つないだセルは始まりの列に置く(self):
        html = self.render("#pagediv(cols){{\n|>|A|\n|B|C|\n}}")
        self.assertEqual(self.columns(html), [["A", "B"], ["C"]])

    def test_cols_Nは順に振り分ける(self):
        html = self.render("#pagediv(cols=3){{\n|A|B|C|D|E|F|G|\n}}")
        self.assertIn("--pd-cols: repeat(3, minmax(0, 1fr));", html)
        self.assertEqual(self.columns(html), [["A", "D", "G"], ["B", "E"], ["C", "F"]])

    def test_cols_Nは表の行をまたいで書いた順(self):
        html = self.render("#pagediv(cols=2){{\n|A|B|C|\n|D||E|\n}}")
        self.assertEqual(self.columns(html), [["A", "C", "E"], ["B", "D"]])

    def test_両方書いたらcols_N(self):
        html = self.render("#pagediv(cols, cols=2){{\n|A|B|C|\n}}")
        self.assertEqual(self.columns(html), [["A", "C"], ["B"]])

    def test_引数で並べる形(self):
        html = self.render("#pagediv(cols, A, B)")
        self.assertEqual(self.columns(html), [["A"], ["B"]])

    def test_数字の名前のページは列の数と取り違えない(self):
        html = self.render("#pagediv(2026, A)")
        self.assertNotIn("pagediv-cols", html)
        self.assertIn("2026の本文", html)

    def test_nostackと見出し(self):
        html = self.render("#pagediv(cols, nostack, notitle){{\n|A|B|\n}}")
        self.assertIn('class="pagediv pagediv-cols pagediv-nostack"', html)
        self.assertNotIn("pagediv-title", html)

    def test_cols_Nの値が正しくなければエラー(self):
        for text in ("#pagediv(cols=0){{\n|A|\n}}", "#pagediv(cols=x){{\n|A|\n}}"):
            with self.subTest(text=text):
                self.assertIn("plugin-error", self.render(text))

    def test_colsが無ければこれまでどおり(self):
        html = self.render("#pagediv{{\n|A|B|\n}}")
        self.assertNotIn("pagediv-cols", html)
        self.assertIn("--pd-area: 1 / 1 / span 1 / span 1;", html)


if __name__ == "__main__":
    unittest.main()
