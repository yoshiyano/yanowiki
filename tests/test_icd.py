"""icd プラグイン: 文中のコード。Markdown の `code` と同じ HTML になること。"""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "_sys"))

from wikilib.icdbody import decode_body, encode_body, markdown_code  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import render_source  # noqa: E402


def render(text, ext=".txt"):
    ctx = PluginContext(config={}, farm="t", wiki_dir=None, page="P", ext=ext)
    engine = build_markdown_renderer({}, None, ctx)
    return render_source(engine, text, ext, False, context=ctx)[0].strip()


class TestSameAsMarkdown(unittest.TestCase):
    """PukiWiki の &icd{…}; と Markdown の `…` の出力を比べる。"""

    def assertSame(self, pukiwiki, markdown):
        self.assertEqual(render(pukiwiki), render(markdown, ".md"))

    def test_ふつうのコード(self):
        self.assertSame("&icd{wiki.py}; を開く", "`wiki.py` を開く")

    def test_HTMLの記号(self):
        self.assertSame("&icd{<a href=\"x\">&};", "`<a href=\"x\">&`")

    def test_文字参照は書いたまま見せる(self):
        self.assertSame("&icd{&amp; &#124;};", "`&amp; &#124;`")

    def test_書きかたを展開しない(self):
        self.assertSame("&icd{''a'' [[b]] &br;};", "`''a'' [[b]] &br;`")

    def test_対になった波括弧(self):
        self.assertSame("&icd{f(){ g(); }};", "`f(){ g(); }`")

    def test_強調の中(self):
        self.assertSame("''&icd{a};''", "**`a`**")

    def test_対になっていない波括弧をエスケープ(self):
        self.assertSame("&icd{\\{};", "`{`")
        self.assertSame("&icd{\\}};", "`}`")

    def test_表のセルの縦棒は付けても付けなくてもよい(self):
        expected = "| h |\n|---|\n| `a\\|b` |"
        self.assertSame("|~h|h\n|&icd{a|b};|", expected)
        self.assertSame("|~h|h\n|&icd{a\\|b};|", expected)

    def test_定義リストの用語の縦棒(self):
        self.assertSame(":&icd{a|b};|説明", "`a|b`\n: 説明")

    def test_強調の中のクォート(self):
        self.assertSame("''&icd{a\\'\\'b};''", "**`a''b`**")

    def test_打ち消しの中のパーセント(self):
        self.assertSame("%%&icd{a\\%\\%b};%%", "~~`a%%b`~~")

    def test_ほかのバックスラッシュはそのまま(self):
        self.assertSame("&icd{C:\\Users \\d+ \\\\srv};", "`C:\\Users \\d+ \\\\srv`")

    def test_末尾のバックスラッシュ(self):
        self.assertSame("&icd{C:\\\\};", "`C:\\`")

    def test_エスケープの形そのもの(self):
        self.assertSame("&icd{\\\\\\|};", "`\\|`")


class TestLimitedToIcd(unittest.TestCase):
    """エスケープはこのプラグインだけ。ほかの読みかたは変わらない。"""

    def test_ほかのプラグインはバックスラッシュで閉じられる(self):
        self.assertIn(">C:\\<", render("&color(red){C:\\};"))
        self.assertIn(">C:\\<", render("&color(red){C:\\};", ".md"))

    def test_ふつうのセルの縦棒はこれまでどおり区切り(self):
        self.assertEqual(render("|a\\|b|").count("<td>"), 2)

    def test_ほかのプラグインの中の縦棒はこれまでどおり区切り(self):
        self.assertEqual(render("|&color(red){a|b};|").count("<td>"), 2)

    def test_閉じていないicdの縦棒は区切り(self):
        self.assertEqual(render("|&icd{a|b|").count("<td>"), 2)


class TestCallForms(unittest.TestCase):

    def test_PukiWikiでは丸括弧を書いてもよい(self):
        self.assertEqual(render("&icd(){a};"), "<p><code>a</code></p>")

    def test_Markdownでは丸括弧つきで動く(self):
        self.assertEqual(render("&icd(){**a**};", ".md"), "<p><code>**a**</code></p>")

    def test_中身が無いとエラー(self):
        self.assertIn("plugin-error", render("&icd();"))

    def test_引数を書くとエラー(self):
        self.assertIn("plugin-error", render("&icd(x){a};"))

    def test_ブロックとしては使えない(self):
        self.assertIn("plugin-error", render("#icd(){a}"))

    def test_中身が複数行のプラグインの中(self):
        self.assertIn("<code>a|b</code>", render("#note(){{\n&icd{a|b};\n}}"))


class TestMechanicalReplace(unittest.TestCase):
    """`code` と &icd{…}; を、機械的な置き換えで行き来できること。"""

    SAMPLES = ("a", "a|b", "{", "}", "}{", "f() { g(); }", "''", "'''a'''", "%%", "it's", "50%",
               "C:\\", "C:\\Users", "\\d+", "\\\\srv", "\\|", "\\{", "\\\\", "\\'\\'", "`", "a`b",
               "``", "&amp;", "&#124;", "&br;", "<b>", "\"x\"", "''a|{%%\\")

    def test_中身へ変えて戻すと元の文字列(self):
        for text in self.SAMPLES:
            self.assertEqual(decode_body(encode_body(text)), text, text)

    def test_要らないエスケープは付けない(self):
        for text in ("a|b", "f() { g(); }", "it's", "50%", "C:\\Users", "\\d+"):
            self.assertEqual(encode_body(text), text)

    def test_Markdownと同じ表示(self):
        for text in self.SAMPLES:
            call = "&icd{" + encode_body(text) + "};"
            code = markdown_code(text)
            self.assertEqual(render(call), render(code, ".md"), text)
            self.assertEqual(render("''" + call + "''"), render("**" + code + "**", ".md"), text)
            self.assertEqual(render("|~h|h\n|" + call + "|"),
                             render("| h |\n|---|\n| " + markdown_code(text, True) + " |", ".md"),
                             text)


if __name__ == "__main__":
    unittest.main()
