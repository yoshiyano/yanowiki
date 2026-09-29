#!/usr/bin/env python3
"""PukiWiki記法の定義ルール（COLOR()/SIZE()/BOLD 等）のテスト。

捕捉した部分（`COLOR(red):''foo''` の `''foo''`）は**通常のインライン記法として
解釈し直す**。かつては文字列のままHTMLへ埋め込んでいたため、強調やリンクが
効かず、**読み手が書いた `<script>` が `allow_html` の検閲を通って出てしまった**
（extra_rule_html は検閲の対象外のため）。両方をここで固定する。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_extrarules.py     （このファイルだけ）
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import pukiwiki  # noqa: E402
from wikilib.extrarules import ExtraRules, load_extra_rules  # noqa: E402
from wikilib.plugins import build_markdown_renderer  # noqa: E402


def html_of(text, rules=None, allow_html=False):
    """本文を、標準の定義ルール（雛形）つきでHTMLにする。"""
    if rules is None:
        rules = load_extra_rules({})   # 雛形（config/pukiwiki.extrarules.example.yaml）
    engine = build_markdown_renderer({}, None, None)
    tokens = pukiwiki.parse(text, extra_rules=rules, allow_html=allow_html)
    return engine.renderer.render(tokens, engine.options, {}).strip()


class TestCapturedPartIsParsed(unittest.TestCase):

    def test_捕捉部分の強調が効く(self):
        self.assertEqual(html_of("COLOR(red):''foo''"),
                         '<p><span style="color:red"><strong>foo</strong></span></p>')

    def test_波括弧の形でも効く(self):
        self.assertEqual(html_of("COLOR(red){''foo'' と '''bar'''}"),
                         '<p><span style="color:red"><strong>foo</strong> と '
                         '<em>bar</em></span></p>')

    def test_リンクも効く(self):
        self.assertIn('<a href="', html_of("COLOR(red){[[リンク>FrontPage]]}"))

    def test_入れ子のルールも展開される(self):
        self.assertEqual(html_of("SIZE(20){COLOR(blue){''x''}}"),
                         '<p><span style="font-size:20px"><span style="color:blue">'
                         '<strong>x</strong></span></span></p>')

    def test_コロン形の入れ子(self):
        self.assertEqual(html_of("SIZE(20):COLOR(blue):''深''"),
                         '<p><span style="font-size:20px"><span style="color:blue">'
                         '<strong>深</strong></span></span></p>')

    def test_捕捉が空でも壊れない(self):
        self.assertEqual(html_of("COLOR(red){}"), '<p><span style="color:red"></span></p>')


class TestCapturedPartIsNotTrustedHtml(unittest.TestCase):
    """**捕捉した部分は読み手が書いたもの**なので、生HTMLとして出さない。"""

    def test_scriptは文字になる(self):
        html = html_of("COLOR(red){<script>alert(1)</script>}")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_コロン形でもタグは文字になる(self):
        html = html_of("BOLD:<img src=x onerror=alert(2)>")
        self.assertNotIn("<img", html)

    def test_置換文字列の固定部分は管理者の書いたHTMLとして出る(self):
        # allow_html が偽でも、定義した側のspanは効く（標準ルールが動く前提）
        self.assertIn('<span style="color:red">', html_of("COLOR(red){x}", allow_html=False))


class TestRuleDepthLimit(unittest.TestCase):
    """捕捉した部分にまた同じルールが当たる定義でも、止まる。"""

    def test_自分自身に当たる定義で無限再帰しない(self):
        rules = ExtraRules([(re.compile(r"\((foo)\)"), r"<i>\1</i>"),
                            (re.compile(r"(foo)"), r"<b>\1</b>")])
        # (foo) → <i> + parse("foo") → <b> + parse("foo") → …… 上限で打ち切る
        html = html_of("(foo)", rules=rules)
        self.assertIn("<i>", html)
        self.assertLess(len(html), 2000)

    def test_捕捉と同じ長さのパターンでも止まる(self):
        rules = ExtraRules([(re.compile(r"(.+)"), r"<u>\1</u>")])
        html = html_of("abc", rules=rules)
        self.assertIn("<u>", html)
        self.assertLess(len(html), 2000)


class TestEmptyMatch(unittest.TestCase):
    """空に当たるパターンで、解析が止まらなくならない。"""

    def test_空の一致は無いものとして扱う(self):
        rules = ExtraRules([(re.compile(r"x*"), "<b>x</b>")])
        # 以前は位置が進まず、同じ場所で永久に回った
        self.assertEqual(html_of("abc", rules=rules), "<p>abc</p>")

    def test_空でない一致は使える(self):
        rules = ExtraRules([(re.compile(r"x+"), "<b>x</b>")])
        self.assertIn("<b>x</b>", html_of("axxb", rules=rules))


if __name__ == "__main__":
    unittest.main()
