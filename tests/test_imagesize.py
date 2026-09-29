#!/usr/bin/env python3
"""画像の解像度の読み取り（`wikilib.imagesize.image_dimensions`）のうち、
SVGの扱いと、添付ファイル一覧のサイズ欄の表示（`attach.format_attach_size`）の
テスト。

SVGは、ルート要素の width・height を使い、無いものは viewBox で補う。

  - 中の要素の width や、stroke-width のような別の属性を拾わない
  - XML宣言・DOCTYPE・コメントが先にあっても、ルート要素を見つける
  - 絶対単位（pt・in・mm など）はpxに直す。% などの相対単位は使わない
  - 片方しか無ければ viewBox の縦横比で補う。どちらも無ければ viewBox の大きさ
  - どこからも決まらなければ None。一覧では画像なら "(未知)" を添える

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_imagesize.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.attach import format_attach_size  # noqa: E402
from wikilib.imagesize import image_dimensions  # noqa: E402


class SvgDimensionsTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def dims(self, text):
        path = os.path.join(self.tmp, "image.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return image_dimensions(path)

    def test_inner_elements_and_stroke_width_are_ignored(self):
        # =evj3room/NetworkMap の network.svg と同じ形。以前は (1, 46) になっていた
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 640" '
            'width="1000" height="640" font-family="\'Noto Sans CJK JP\',sans-serif">\n'
            '  <rect x="0" y="0" width="1000" height="640" fill="#ffffff"/>\n'
            '  <line x1="500" y1="4" x2="500" y2="30" stroke-width="2"/>\n'
            '  <rect x="420" y="30" width="160" height="46" rx="8"/>\n'
            '</svg>\n'
        )
        self.assertEqual(self.dims(svg), (1000, 640))

    def test_attribute_named_like_width_in_root(self):
        svg = '<svg stroke-width="2" data-height="9" width="120" height="80"></svg>'
        self.assertEqual(self.dims(svg), (120, 80))

    def test_prolog_before_root(self):
        svg = (
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            '<!-- Generator: Adobe Illustrator 27.0.0 -->\n'
            '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
            '"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
            '<svg version="1.1"\n\txmlns="http://www.w3.org/2000/svg"\n'
            '\twidth="300px"\n\theight="150px">\n</svg>\n'
        )
        self.assertEqual(self.dims(svg), (300, 150))

    def test_utf8_bom(self):
        self.assertEqual(self.dims('﻿<svg width="40" height="30"/>'), (40, 30))

    def test_svg_inside_comment_is_not_root(self):
        svg = '<!-- <svg width="1" height="1"> -->\n<svg width="64" height="48"></svg>'
        self.assertEqual(self.dims(svg), (64, 48))

    def test_gt_inside_attribute_value(self):
        svg = '<svg aria-label="a > b" width="10" height="20"></svg>'
        self.assertEqual(self.dims(svg), (10, 20))

    def test_single_quotes(self):
        self.assertEqual(self.dims("<svg width='33' height='44'/>"), (33, 44))

    def test_absolute_units(self):
        self.assertEqual(self.dims('<svg width="72pt" height="1in"/>'), (96, 96))
        self.assertEqual(self.dims('<svg width="210mm" height="297mm"/>'), (794, 1123))

    def test_percent_falls_back_to_viewbox(self):
        svg = '<svg width="100%" height="100%" viewBox="0 0 640 480"/>'
        self.assertEqual(self.dims(svg), (640, 480))

    def test_one_side_uses_viewbox_ratio(self):
        self.assertEqual(self.dims('<svg width="320" viewBox="0,0,640,480"/>'), (320, 240))
        self.assertEqual(self.dims('<svg height="120" viewBox="0 0 640 480"/>'), (160, 120))

    def test_viewbox_only(self):
        self.assertEqual(self.dims('<svg viewBox="-10 -10 2e2 100.4"/>'), (200, 100))

    def test_unknown(self):
        self.assertIsNone(self.dims('<svg xmlns="http://www.w3.org/2000/svg"></svg>'))
        self.assertIsNone(self.dims('<svg width="100%" height="100%"/>'))
        self.assertIsNone(self.dims('<svg width="100"/>'))
        self.assertIsNone(self.dims('<svg width="0" height="0"/>'))
        self.assertIsNone(self.dims('<svg viewBox="0 0 0 0"/>'))
        self.assertIsNone(self.dims('<html><body>svg</body></html>'))


class FormatAttachSizeTest(unittest.TestCase):

    def test_image_with_dimensions(self):
        self.assertEqual(format_attach_size(2048, (1000, 640), True), "2.0 KB (1000×640)")

    def test_image_without_dimensions_is_unknown(self):
        self.assertEqual(format_attach_size(2048, None, True), "2.0 KB (未知)")

    def test_not_image(self):
        self.assertEqual(format_attach_size(2048, None, False), "2.0 KB")


if __name__ == "__main__":
    unittest.main()
