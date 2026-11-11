#!/usr/bin/env python3
"""PukiWiki記法と Markdown の本文の変換（wikilib.markupconv）のテスト。

文字列の形を見るものと、変換の前後で描画した HTML を比べるものがある。後者は
変換の目的そのもの（同じ表示になること）を、パーサーと描画を通して確かめる。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_markupconv.py     （このファイルだけ）
"""
import os
import re
import sys
import tempfile
import unittest
from html import unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

from wikilib import markupconv as mc  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import render_source  # noqa: E402

PLUGIN_DIR = os.path.join(ROOT, "plugin")


def options(**kw):
    kw.setdefault("plugin_dir", PLUGIN_DIR)
    return mc.ConvertOptions(**kw)


def to_md(text, **kw):
    return mc.pukiwiki_to_markdown(text, options(**kw)).text.rstrip("\n")


def to_pw(text, **kw):
    return mc.markdown_to_pukiwiki(text, options(**kw)).text.rstrip("\n")


def rendered(text, ext):
    ctx = PluginContext(config={}, farm="t", wiki_dir=None, page="P", ext=ext)
    engine = build_markdown_renderer({}, PLUGIN_DIR, ctx)
    html = render_source(engine, text, ext, True, context=ctx)[0]
    html = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    html = re.sub(r'\sid="[^"]*"', "", html)
    html = re.sub(r"\s*\n\s*", "", html).replace(" />", ">")
    return re.sub(r"&#(\d+);", lambda m: unescape(m.group(0)), html)  # 文字参照は表示で同じ


class TestBlocksToMarkdown(unittest.TestCase):

    def test_対応する書きかた(self):
        for source, expected in [
            ("* a", "## a"), ("** a", "### a"), ("*** a", "#### a"),
            ("----", "---"),
            ("- a\n-- b\n--- c\n- d", "- a\n  - b\n    - c\n- d"),
            ("+ a\n++ b\n+ c", "1. a\n   1. b\n2. c"),
            ("> a", "> a"),
            (":語|説明\n:|説明2", "語\n: 説明\n: 説明2"),
            (" a\n  b", "    a\n     b"),
            ("#contents", "#contents()"),
            ("// c\n\na", "<!-- c-->\n\na"),
        ]:
            with self.subTest(source):
                self.assertEqual(to_md(source), expected)

    def test_説明が次の行から始まる定義リスト(self):
        self.assertEqual(to_md(":語|\n説明"), "語\n: 説明")

    def test_箇条書きの中のコメントで箇条書きが切れない(self):
        self.assertEqual(to_md("- a\n// c\n- b"), "- a\n  <!-- c-->\n- b")

    def test_プラグインの中の行頭スラッシュはコメントにしない(self):
        out = to_md("#pre(){{\n// x\n}}")
        self.assertEqual(out, "#pre(){{\n// x\n}}")

    def test_コードはフェンスにして色付けの宣言を足す(self):
        self.assertEqual(to_md("#code(py){{\na\n}}"), "```py\na\n```\n\n#code()")

    def test_言語以外の引数があるコードはプラグインのまま(self):
        self.assertEqual(to_md("#code(py, nonum){{\na\n}}"), "#code(py, nonum){{\na\n}}")

    def test_本体を展開するプラグインの中も変換する(self):
        self.assertEqual(to_md("#note(){{\n''a''\n}}"), "#note(){{\n**a**\n}}")
        self.assertEqual(to_md("&color(red){''a''};"), "&color(red){**a**};")

    def test_本体を展開しないプラグインの中は触らない(self):
        self.assertEqual(to_md("#pre(){{\n''a''\n}}"), "#pre(){{\n''a''\n}}")


class TestTablesToMarkdown(unittest.TestCase):

    def test_見出し行のある表はGFMにする(self):
        self.assertEqual(to_md("|~a|~b|h\n|c|d|"), "| a | b |\n|---|---|\n| c | d |")

    def test_列の書式はGFMの揃えにする(self):
        self.assertEqual(to_md("|LEFT:|CENTER:|c\n|~a|~b|h\n|c|d|"),
                         "| a | b |\n|:---|:---:|\n| c | d |")

    def test_GFMで書けない表はtableプラグインにする(self):
        for source in ["|c|d|", "|>|a|\n|b|c|", "|COLOR(red):c|d|", "|a|b|\n|c|d|f"]:
            with self.subTest(source):
                self.assertTrue(to_md(source).startswith("#table(){{\n"))

    def test_CSVの表(self):
        self.assertEqual(to_md(",a, b ,c"), "#table(){{\n|a|CENTER:b|c|\\\\\n}}")

    def test_CSVのチルダは見出しの目印にしない(self):
        self.assertIn("|&#126;/x|", to_md(",~/x,y"))


class TestInlineToMarkdown(unittest.TestCase):

    def test_飾りとリンク(self):
        for source, expected in [
            ("''a''", "**a**"), ("'''a'''", "*a*"), ("%%a%%", "~~a~~"),
            ("a~\nb", "a\\\nb"),
            ("[[Foo]]", "[Foo](Foo)"), ("[[x>Foo]]", "[x](Foo)"),
            ("{[x>Foo]}", "[x](./Foo)"), ("[[x>#a]]", "[x](#a)"),
            ("[[x:https://e.com/]]", "[x](https://e.com/)"),
            ("[[a b]]", "[a b](<a b>)"),
            ("[[alt>a.png]]", "![alt](::a.png)"),
            ("https://e.com/", "https://e.com/"),
            ("&br;", "&br();"),
            ("&icd{a};", "`a`"),
            ("((x))", "^[x]"),
            ("%%%a%%%", "&html(){<ins>a</ins>};"),
        ]:
            with self.subTest(source):
                self.assertEqual(to_md(source), expected)

    def test_飾りの内側の空白は外へ出す(self):
        self.assertEqual(to_md("''a ''b"), "**a** b")

    def test_文字がMarkdownの書きかたにならない(self):
        for source, expected in [
            ("~# a", "\\# a"), ("~1. a", "1\\. a"), ("~> a", "\\> a"),
            ("a*b", "a\\*b"), ("_a_", "\\_a\\_"), ("`a`", "\\`a\\`"),
            ("[a](b)", "\\[a\\](b)"), ("<b>", "\\<b>"), ("^[a]", "\\^[a]"),
        ]:
            with self.subTest(source):
                self.assertEqual(to_md(source), expected)

    def test_記号の文字参照は文字に戻す(self):
        self.assertEqual(to_md("&#39;&#39;a&#39;&#39;"), "''a''")
        self.assertEqual(to_md("&#45; a"), "\\- a")
        self.assertEqual(to_md("&#91;a](b)"), "\\[a\\](b)")
        self.assertEqual(to_md("&#38;br;"), "&#38;br;")

    def test_行末のバックスラッシュを残す(self):
        self.assertEqual(to_md("C:\\"), "C:\\\\")

    def test_飾りにならない形はそのまま(self):
        for source in ["snake_case_word", "2 * 3", "- [ ] a"]:
            with self.subTest(source):
                self.assertEqual(to_md(source), source)

    def test_定義ルールの色はプラグインにする(self):
        from wikilib.extrarules import load_extra_rules
        rules = load_extra_rules({})
        self.assertEqual(to_md("COLOR(#f50){''a''}", extra_rules=rules),
                         "&color(#f50){**a**};")
        self.assertEqual(to_md("SIZE(20){a}", extra_rules=rules), "&size(20){a};")
        self.assertEqual(to_md("&smile;", extra_rules=rules), "😊")

    def test_表示時の置き換えは残して知らせる(self):
        result = mc.pukiwiki_to_markdown("&_date;", options())
        self.assertEqual(result.text.strip(), "&_date;")
        self.assertTrue(result.warnings)

    def test_太字が効かない形を知らせる(self):
        result = mc.pukiwiki_to_markdown("''日本語(ja)''を", options())
        self.assertTrue(any("太字" in w for w in result.warnings))


class TestWikiName(unittest.TestCase):
    """設計者の決定（2026-11-07）。有効・無効で対応を変える。"""

    def test_有効なら同名のページがあるときだけリンクにする(self):
        exists = {"FrontPage"}.__contains__
        self.assertEqual(to_md("FrontPage GitHub", page_exists=exists),
                         "[FrontPage](FrontPage) GitHub")

    def test_無効なら常に文字のまま(self):
        self.assertEqual(to_md("FrontPage", wikiname=False, page_exists=lambda n: True),
                         "FrontPage")

    def test_明示したリンクは無効でもリンクのまま(self):
        self.assertEqual(to_md("[[FrontPage]]", wikiname=False), "[FrontPage](FrontPage)")

    def test_PukiWikiへは本文を編集しない(self):
        self.assertEqual(to_pw("GitHub"), "GitHub")
        self.assertEqual(to_pw("GitHub", wikiname=False), "GitHub")


class TestAnchors(unittest.TestCase):
    """見出しのアンカーは、参照があるものだけ残す。"""

    def test_参照が無ければ捨てる(self):
        self.assertEqual(to_md("* a [#x]"), "## a")

    def test_同じページの参照があれば残す(self):
        self.assertEqual(to_md("* a [#x]\n\n[[b>#x]]"), "## &aname(x);a\n\n[b](#x)")

    def test_ほかのページの参照があれば残す(self):
        self.assertEqual(to_md("* a [#x]", referenced_anchors=frozenset({"x"})),
                         "## &aname(x);a")

    def test_全ページの本文から参照を集める(self):
        with tempfile.TemporaryDirectory() as pages:
            with open(os.path.join(pages, "a.txt"), "w", encoding="utf-8") as f:
                f.write("* 見出し [#own]\n\n[[b>c#ref1]]\n")
            os.mkdir(os.path.join(pages, ".hidden"))
            with open(os.path.join(pages, ".hidden", "b.txt"), "w", encoding="utf-8") as f:
                f.write("[[b>c#ignored]]\n")
            self.assertEqual(mc.collect_referenced_anchors(pages), {"ref1"})


class TestBlocksToPukiWiki(unittest.TestCase):

    def test_対応する書きかた(self):
        for source, expected in [
            ("## a", "* a"), ("### a", "** a"), ("#### a", "*** a"),
            ("---", "----"),
            ("- a\n  - b\n    - c\n- d", "- a\n-- b\n--- c\n- d"),
            ("1. a\n   1. b\n2. c", "+ a\n++ b\n+ c"),
            ("> a\n>\n> > b", "> a\n>\n> > b"),
            ("語\n: 説明\n: 説明2", ":語|説明\n:|説明2"),
            ("    a\n     b", " a\n  b"),
            ("```py\na\n```", "#code(py){{\na\n}}"),
            ("```\na\n```", "#code(){{\na\n}}"),
            ("    a\n\n    b", "#pre(){{\na\n\nb\n}}"),
            ("<!-- c -->\n\na", "// c\n\na"),
            ("<!--\nx\ny\n-->", "//\n//x\n//y"),
            ("- [x] a", "- [x] a"),
            ("| a | b |\n|:--|--:|\n| c | d |", "|LEFT:|RIGHT:|c\n|~a|~b|h\n|c|d|"),
        ]:
            with self.subTest(source):
                self.assertEqual(to_pw(source), expected)

    def test_文中のコメントは段落の後ろの行へ移す(self):
        self.assertEqual(to_pw("a<!-- c -->b"), "ab\n// c")

    def test_段落の項目(self):
        self.assertEqual(to_pw("- a\n\n- b"), "-~ a\n-~ b")

    def test_項目に段落が続くと_チルダの段落にする(self):
        self.assertEqual(to_pw("- a\n\n  b\n\n- c"), "- a\n~b\n-~ c")

    def test_文字の無い項目のブロックは次の行に置く(self):
        self.assertEqual(to_pw("- #hr()"), "-~\n#hr()")

    def test_tableプラグインのセル(self):
        self.assertEqual(to_pw("#table(){{\n|**a**|-18%|\\\\\n}}"),
                         "#table(){{\n|''a''|&#45;18%|\\\\\n}}")

    def test_tableプラグインの複数行のセル(self):
        self.assertEqual(to_pw("#table(){{\n|**a**\n- b|c|\\\\\n}}"),
                         "#table(){{\n|''a''\n\n- b|c|\\\\\n}}")


class TestTitle(unittest.TestCase):
    """先頭の `# 題` は、ページ名と同じなら消し、違えば `* 題` にする。"""

    def test_ページ名と同じなら消す(self):
        self.assertEqual(to_pw("# Foo\n\na", page_name="Bar/Foo"), "a")
        self.assertEqual(to_pw("# Foo\n\na", page_name="Foo/index"), "a")

    def test_ページ名と違えば見出しにする(self):
        self.assertEqual(to_pw("# 題\n\na", page_name="Foo"), "* 題\n\na")

    def test_タイトルとして扱わない設定なら見出しにする(self):
        self.assertEqual(to_pw("# Foo", page_name="Foo", first_h1_as_title=False), "* Foo")


class TestInlineToPukiWiki(unittest.TestCase):

    def test_飾りとリンク(self):
        for source, expected in [
            ("**a**", "''a''"), ("*a*", "'''a'''"), ("~~a~~", "%%a%%"),
            ("a\\\nb", "a~\nb"),
            ("[Foo](Foo)", "[[Foo]]"), ("[x](Foo)", "[[x>Foo]]"),
            ("[日本語](ページ/下)", "[[日本語>ページ/下]]"),
            ("[x](https://e.com/)", "[[x>https://e.com/]]"),
            ("![alt](::a.png)", "[[alt>::a.png]]"),
            ("https://e.com/", "https://e.com/"),
            ("`a`", "&icd{a};"), ("`a|b`", "&icd{a|b};"),
            ("^[x]", "((x))"), ("^[**x**]", "((''x''))"),
            ("&html(){<ins>a</ins>};", "%%%a%%%"),
            ("&_date;", "&_date;"),
            ("&color(red){**a**};", "&color(red){''a''};"),
        ]:
            with self.subTest(source):
                self.assertEqual(to_pw(source), expected)

    def test_文字がPukiWikiの書きかたにならない(self):
        for source, expected in [
            ("''a''", "&#39;&#39;a&#39;&#39;"),
            ("%%a%%", "&#37;&#37;a&#37;&#37;"),
            ("((a))", "&#40;&#40;a))"),
            ("[[a]]", "&#91;[a]]"),
            ("&amp;br;", "&amp;br;"),
            ("//a", "&#47;/a"),
            (",a", "&#44;a"),
            ("\\- a", "&#45; a"),
            ("a~", "a&#126;"),
            ("~a", "&#126;a"),
        ]:
            with self.subTest(source):
                self.assertEqual(to_pw(source), expected)

    def test_複数行の飾りは行ごとに囲む(self):
        self.assertEqual(to_pw("**a\nb**"), "''a''\n''b''")

    def test_太字と斜体の重なりは太字だけにして知らせる(self):
        result = mc.markdown_to_pukiwiki("***a***", options())
        self.assertEqual(result.text.strip(), "''a''")
        self.assertTrue(result.warnings)

    def test_太字だけのリンクの文字は外側を太字にする(self):
        self.assertEqual(to_pw("[**x**](y)"), "''[[x>y]]''")

    def test_リンクの文字の飾りは知らせて落とす(self):
        result = mc.markdown_to_pukiwiki("[a `b`](y)", options())
        self.assertEqual(result.text.strip(), "[[a b>y]]")
        self.assertTrue(result.warnings)

    def test_定義ルールに読まれる文字を守る(self):
        from wikilib.extrarules import load_extra_rules
        self.assertEqual(to_pw("BOLD:a", extra_rules=load_extra_rules({})), "&#66;OLD:a")


class TestSameRendering(unittest.TestCase):
    """変換の前後で、描画した HTML が同じになる。"""

    PUKIWIKI = [
        "* 見出し A\n\n本文 ''強'' '''斜''' %%消%% [[x>Foo]]~\n次の行",
        "- a\n-- b\n--- c\n- d\n\n+ a\n++ b",
        "> a\n>\n> b",
        ":語|説明\n:|説明2",
        "|LEFT:|RIGHT:|c\n|~a|~b|h\n|1|2|",
        " a\n  b",
        "#note(type=tip){{\n''a''\n\n- b\n}}",
        "&color(red){''a''}; &size(20){b};",
        "#code(py){{\nprint(1)\n}}",
        "&icd{a|b}; と &icd{''c''};",
        "~- 箇条書きではない\n\n~1. 番号でもない\n\n~# 見出しでもない",
    ]
    MARKDOWN = [
        "## 見出し A\n\n本文 **強** *斜* ~~消~~ [x](Foo)\\\n次の行",
        "- a\n  - b\n    - c\n- d\n\n1. a\n   1. b",
        "> a\n>\n> b",
        "語\n: 説明\n: 説明2",
        "| a | b |\n|:--|--:|\n| 1 | 2 |",
        "    a\n     b",
        "#note(type=tip){{\n**a**\n\n- b\n}}",
        "`a|b` と `''c''`",
        "''a'' %%b%% ((c)) [[d]] //e",
        "\\- a\n\n1\\. b\n\n\\# c",
    ]

    def test_PukiWikiからMarkdownへ(self):
        for source in self.PUKIWIKI:
            with self.subTest(source):
                self.assertEqual(rendered(source, ".txt"), rendered(to_md(source), ".md"))

    def test_MarkdownからPukiWikiへ(self):
        for source in self.MARKDOWN:
            with self.subTest(source):
                self.assertEqual(rendered(source, ".md"), rendered(to_pw(source), ".txt"))

    def test_往復で変わらない(self):
        for source in self.PUKIWIKI:
            with self.subTest(source):
                once = to_md(source)
                self.assertEqual(to_md(to_pw(once)), once)


if __name__ == "__main__":
    unittest.main()
