#!/usr/bin/env python3
"""本文に書かれた生HTMLの扱い（wikilib.htmlpolicy）のテスト。

**素通しは保存型XSSになる**ので、ここは「通すつもりのものが通る」よりも
**「通すつもりのないものが通らない」**ことを固定するために書いてある。
危ないものを1つ増やすたびに、ここへ1件足す。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_htmlpolicy.py     （このファイルだけ）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import htmlpolicy  # noqa: E402
from wikilib.htmlpolicy import ALL, NONE, SAFE, html_policy, normalize_policy, sanitize  # noqa: E402


class TestPolicyValue(unittest.TestCase):
    """設定に書かれた値の読みかた。"""

    def test_3つの値(self):
        self.assertEqual(normalize_policy(False), NONE)
        self.assertEqual(normalize_policy(True), SAFE)
        self.assertEqual(normalize_policy("all"), ALL)

    def test_書かれていなければ通さない(self):
        self.assertEqual(normalize_policy(None), NONE)

    def test_読めない値は通さない(self):
        # 設定の書き損じで、意図せず素通しになるのを避ける
        for value in ("ALL_", "yes-please", 1, [], "false"):
            with self.subTest(value=value):
                self.assertEqual(normalize_policy(value), NONE)

    def test_大文字や前後の空白は気にしない(self):
        self.assertEqual(normalize_policy(" ALL "), ALL)
        self.assertEqual(normalize_policy("True"), SAFE)

    def test_パーサーに認識させるか(self):
        self.assertFalse(htmlpolicy.parses_html(NONE))
        self.assertTrue(htmlpolicy.parses_html(SAFE))
        self.assertTrue(htmlpolicy.parses_html(ALL))


class TestPolicySection(unittest.TestCase):
    """記法ごとに別の設定を見る。"""

    CONFIG = {"markdown": {"allow_html": "all"}, "pukiwiki": {"allow_html": False}}

    def test_txtはpukiwiki節(self):
        self.assertEqual(html_policy(self.CONFIG, ".txt"), NONE)

    def test_mdはmarkdown節(self):
        self.assertEqual(html_policy(self.CONFIG, ".md"), ALL)

    def test_設定が空なら通さない(self):
        self.assertEqual(html_policy({}, ".md"), NONE)
        self.assertEqual(html_policy(None, ".txt"), NONE)


class TestResolvePolicy(unittest.TestCase):
    """プラグインが、中身をどの水準で解釈させるか決められる。"""

    PAGE_NONE = {"markdown": {"allow_html": False}}
    PAGE_ALL = {"markdown": {"allow_html": "all"}}

    def test_指定が無ければページの設定に従う(self):
        self.assertEqual(
            htmlpolicy.resolve_policy(None, self.PAGE_NONE, ".md"), NONE)
        self.assertEqual(
            htmlpolicy.resolve_policy(None, self.PAGE_ALL, ".md"), ALL)

    def test_ページの設定より緩くできる(self):
        # allow_html は「wikiSystem自身がparseするときの最大権限」であって、
        # プラグインからの要求を縛るものではない（Wiki設計者の指示、2026-09-02）
        self.assertEqual(
            htmlpolicy.resolve_policy("all", self.PAGE_NONE, ".md"), ALL)
        self.assertEqual(
            htmlpolicy.resolve_policy(True, self.PAGE_NONE, ".md"), SAFE)

    def test_ページの設定より厳しくもできる(self):
        self.assertEqual(
            htmlpolicy.resolve_policy(False, self.PAGE_ALL, ".md"), NONE)
        self.assertEqual(
            htmlpolicy.resolve_policy(True, self.PAGE_ALL, ".md"), SAFE)


class TestSanitizeKeeps(unittest.TestCase):
    """通してよいものは、そのまま通る。"""

    def test_文字装飾(self):
        self.assertEqual(sanitize("<b>太字</b> <em>斜体</em>"), "<b>太字</b> <em>斜体</em>")

    def test_classとidは残る(self):
        # テーマのCSSを当てる書きかたが既にあるため
        self.assertEqual(sanitize('<div class="callflow" id="x">中</div>'),
                         '<div class="callflow" id="x">中</div>')

    def test_値なしの属性(self):
        self.assertEqual(sanitize("<details open><summary>s</summary></details>"),
                         "<details open><summary>s</summary></details>")

    def test_ふつうのリンクと画像(self):
        self.assertEqual(sanitize('<a href="/UsageGuide" title="案内">案内</a>'),
                         '<a href="/UsageGuide" title="案内">案内</a>')
        self.assertEqual(sanitize('<img src="https://e.com/a.png" alt="図">'),
                         '<img src="https://e.com/a.png" alt="図">')

    def test_表の結合(self):
        self.assertEqual(sanitize('<td colspan="2" rowspan="3">x</td>'),
                         '<td colspan="2" rowspan="3">x</td>')

    def test_タグ以外の文字は触らない(self):
        # すでにエスケープ済みの本文がここへ来るので、二重にしない
        self.assertEqual(sanitize("1 &lt; 2 &amp; 3 > 0"), "1 &lt; 2 &amp; 3 > 0")


class TestSanitizeDrops(unittest.TestCase):
    """通してはいけないものは、消さずに文字にする。"""

    def assertEscaped(self, fragment, needle):
        got = sanitize(fragment)
        self.assertIn(needle, got)
        self.assertNotIn("<" + needle.split("&lt;")[-1].split("&gt;")[0], got)

    def test_script(self):
        self.assertEqual(sanitize("<script>alert(1)</script>"),
                         "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_style要素(self):
        # スクリプトが無くてもページ全体の見た目を乗っ取れる
        self.assertEqual(sanitize("<style>body{display:none}</style>"),
                         "&lt;style&gt;body{display:none}&lt;/style&gt;")

    def test_iframeとobject(self):
        self.assertTrue(sanitize('<iframe src="https://e.com"></iframe>')
                        .startswith("&lt;iframe"))
        self.assertTrue(sanitize('<object data="x.swf"></object>')
                        .startswith("&lt;object"))

    def test_form系(self):
        # 偽の入力欄で認証情報を集める形を防ぐ
        for tag in ('<form action="https://e.com">', '<input name="pw">',
                    "<button>押す</button>", "<textarea>x</textarea>"):
            with self.subTest(tag=tag):
                self.assertTrue(sanitize(tag).startswith("&lt;"))

    def test_イベント属性(self):
        # タグ自体は残るが、on… は落ちる
        self.assertEqual(sanitize('<img src="a.png" onerror="alert(1)">'),
                         '<img src="a.png">')
        self.assertEqual(sanitize('<div onclick="alert(1)">x</div>'), "<div>x</div>")

    def test_style属性(self):
        self.assertEqual(sanitize('<span style="position:fixed;top:0">x</span>'),
                         "<span>x</span>")

    def test_javascriptのURL(self):
        self.assertEqual(sanitize('<a href="javascript:alert(1)">a</a>'), "<a>a</a>")
        self.assertEqual(sanitize('<img src="data:text/html;base64,PHNjcmlwdD4=">'),
                         "<img>")

    def test_スキームの間に空白や改行があっても見破る(self):
        self.assertEqual(sanitize('<a href="java\tscript:alert(1)">a</a>'), "<a>a</a>")
        self.assertEqual(sanitize('<a href=" javascript:alert(1)">a</a>'), "<a>a</a>")

    def test_コメントや宣言は通さない(self):
        # 中身を隠せるため
        self.assertTrue(sanitize("<!-- ひみつ -->").startswith("&lt;!--"))
        self.assertTrue(sanitize("<!DOCTYPE html>").startswith("&lt;!DOCTYPE"))

    def test_知らない属性は落ちる(self):
        self.assertEqual(sanitize('<div data-x="1" srcdoc="y">z</div>'), "<div>z</div>")

    def test_大文字のタグ名でも判定する(self):
        self.assertTrue(sanitize("<SCRIPT>alert(1)</SCRIPT>").startswith("&lt;SCRIPT"))
        self.assertEqual(sanitize("<B>太字</B>"), "<b>太字</b>")


if __name__ == "__main__":
    unittest.main()
