#!/usr/bin/env python3
"""img の回り込み（float）と、割合の幅（w30%・[MIN;30%;MAX]）の組み合わせ（2026-09-28）。

回り込む枠は中身に合わせて幅が決まるので、割合の幅を画像に付けると枠と画像で
堂々巡りになり、文章が回り込まなかった。回り込むときは幅を枠に付け、画像は枠
いっぱいにする。回り込まないときの出力は変えない。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_img_float.py     （このファイルだけ）
"""
import os
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


class TestImgFloatWidth(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="imgfloat-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "t", "wiki")
        os.makedirs(self.wiki_dir)
        attach = os.path.join(self.work, "wikidata", "t", "attach", "Top")
        os.makedirs(attach)
        with open(os.path.join(attach, "a.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        with open(os.path.join(self.wiki_dir, "Top.txt"), "w", encoding="utf-8") as f:
            f.write("x\n")
        bottle.request.bind({})

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def render(self, text):
        context = PluginContext(config={}, farm="t", wiki_dir=self.wiki_dir, page="Top",
                                base_url="", ext=".txt")
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        return md.renderer.render(parse_source(md, text, ".txt", env), md.options, env)

    def test_回り込むときは割合の幅を枠に付ける(self):
        html = self.render("#img(a.png,right,,w30%)")
        self.assertIn('<div class="plugin-img plugin-img-float" style="float:right;width:30%">', html)
        self.assertIn('style="width:100%;height:auto;"', html)

    def test_clampも枠に付ける(self):
        html = self.render("#img(a.png,left,,[200;30%;600])")
        self.assertIn('style="float:left;width:clamp(200px, 30%, 600px)"', html)
        html = self.render("#img(a.png,left,,[10%;30%;80%])")
        self.assertIn('style="float:left;width:30%"', html)
        self.assertIn('data-zoom-min="10%"', html)   # 仕上げは img.js が枠に付ける

    def test_元の大きさに対する割合はこれまでどおり(self):
        html = self.render("#img(a.png,right,,30%)")
        self.assertIn('<div class="plugin-img plugin-img-float" style="float:right">', html)
        self.assertIn('style="zoom:30%;"', html)

    def test_回り込まないときは画像に付ける(self):
        html = self.render("#img(a.png,,,w30%)")
        self.assertIn('<div class="plugin-img">', html)
        self.assertIn('style="width:30%;height:auto;"', html)


if __name__ == "__main__":
    unittest.main()
