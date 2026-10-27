#!/usr/bin/env python3
"""table プラグイン（セルの中を複数行で書ける表・TSV の表。2026-09-30）のテスト。

- 行の終わりは `|\\\\`。セルの中の改行は <br />、`|` の前後の改行は捨てる
- 目印（`~`・`>`・`CENTER:` など）と行の種類（h/f/c）は PukiWiki記法の表と同じ
- セルの中は、ページの書きかた（Markdown / PukiWiki）のインライン記法として展開する
- tsv は引用符の中の改行・`""` を読み、目印は読まない
- cols・width で列と表の幅、cols の `||` と `==` の行で二重線

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_table_plugin.py     （このファイルだけ）
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import parse_source  # noqa: E402

PLUGIN_DIR = os.path.join(ROOT, "plugin")


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "plugin_under_test_table", os.path.join(PLUGIN_DIR, "table.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(text, ext=".txt"):
    context = PluginContext(config={}, farm="t", wiki_dir=None, page="Top",
                            base_url="", ext=ext)
    md = build_markdown_renderer({}, PLUGIN_DIR, context)
    env = {"wiki": context}
    return md.renderer.render(parse_source(md, text, ext, env), md.options, env)


def table(body, args="", ext=".txt"):
    return render("#table(%s){{\n%s\n}}" % (args, body), ext)


class TestPukiwikiFormat(unittest.TestCase):
    def test_行末の区切りまでを1行として読む(self):
        html = table("|a|b\nc\ndef|\\\\\n|x| abcde |\\\\")
        self.assertIn("<td>b<br />\nc<br />\ndef</td>", html)
        self.assertIn("<td>abcde</td>", html)
        self.assertEqual(html.count("<tr>"), 2)

    def test_1セルを1行ずつ書ける(self):
        html = table("|a\n|b\nc\n|\\\\")
        self.assertIn("<td>a</td>\n<td>b<br />\nc</td>", html)

    def test_行の種類と見出しセル(self):
        html = table("|~品名|~説明|h\\\\\n|a|b|\\\\\n|合計|1|f\\\\\n|CENTER:|RIGHT:|c\\\\")
        self.assertIn("<thead>\n<tr>\n<th style=\"text-align:center\">品名</th>", html)
        self.assertIn("<tfoot>\n<tr>\n<td style=\"text-align:center\">合計</td>", html)
        self.assertIn('<td style="text-align:right">b</td>', html)

    def test_結合(self):
        html = table("|>|a|\\\\\n|b|c|\\\\\n|~|d|\\\\")
        self.assertIn('<td colspan="2">a</td>', html)
        self.assertIn('<td rowspan="2">b</td>', html)

    def test_書式指定(self):
        html = table("|COLOR(red):BGCOLOR(#eee):SIZE(12):字|\\\\")
        self.assertIn('style="color:red;background-color:#eee;font-size:12px"', html)

    def test_縦棒はエスケープして書ける(self):
        html = table("|a\\|b|c|\\\\")
        self.assertIn("<td>a|b</td>\n<td>c</td>", html)

    def test_最後の行の区切りは省ける(self):
        html = table("|a|\\\\\n|b|")
        self.assertEqual(html.count("<tr>"), 2)

    def test_行と行のあいだのコメント(self):
        html = table("|a|\\\\\n// 注\n|b\n// 字|\\\\")
        self.assertNotIn("注", html)
        # PukiWiki のページでは、セルの中も本文と同じくコメントになる（2026-10-23）
        self.assertNotIn("字", html)
        # Markdown のページでは、セルの中の // は文字のまま
        self.assertIn("// 字", table("|a|\\\\\n// 注\n|b\n// 字|\\\\", ext=".md"))

    def test_数式の行末は行の終わりにしない(self):
        html = table("|a \\\\\nb|\\\\")
        self.assertEqual(html.count("<tr>"), 1)

    def test_表の外の文字はエラー(self):
        self.assertIn("plugin-error", table("abc"))

    def test_セルにブロック要素を書ける(self):
        # 2026-10-04 の要求（2026-10-23 に入れた）
        html = table("|a\n-項目1\n-項目2|\\\\")
        self.assertIn("<ul>", html)
        html = table("|- 項目1\n- 項目2\n\n> 引用|\\\\", ext=".md")
        self.assertIn("<ul>", html)
        self.assertIn("<blockquote>", html)

    def test_段落1つだけのセルはpを付けない(self):
        self.assertIn("<td>a<br />\nb</td>", table("|a\nb|\\\\", ext=".md"))
        self.assertIn("<td><p>a</p>\n<p>b</p></td>", table("|a\n\nb|\\\\", ext=".md"))

    def test_見出しは目次やアンカーに入らない飾りの見出し(self):
        for ext, text in ((".txt", "|*見出し|\\\\"), (".md", "|## 見出し|\\\\")):
            with self.subTest(ext=ext):
                html = table(text, ext=ext)
                self.assertRegex(html, r"<h[1-6]>見出し</h[1-6]>")
                self.assertNotIn("id=", html)

    def test_PukiWikiのページではPukiWikiのインライン(self):
        html = table("|''強調''|[[Top]]|\\\\")
        self.assertIn("<strong>強調</strong>", html)
        self.assertIn('<a href="Top">Top</a>', html)

    def test_Markdownのページではマークダウンのインライン(self):
        html = table("|**強調**\n`x\\|y`|[l](Top)|\\\\", ext=".md")
        self.assertIn("<strong>強調</strong><br />\n<code>x|y</code>", html)
        self.assertIn('<a href="Top">l</a>', html)

    def test_headerはtsvだけ(self):
        from wikilib.plugins import PluginArgumentError
        plugin = load_plugin()
        with self.assertRaisesRegex(PluginArgumentError, "tsv のときだけ"):
            plugin._convert({"format": "pukiwiki", "header": True, "cols": None, "width": None},
                            "|a|\\\\", None)


class TestTsvFormat(unittest.TestCase):
    def test_タブと改行で区切る(self):
        html = table("A\tB\n1\t2", "tsv")
        self.assertIn("<td>A</td>\n<td>B</td>", html)
        self.assertEqual(html.count("<tr>"), 2)

    def test_引用符の中の改行とタブ(self):
        html = table('"x\ny"\t"a\tb"\t"q""r"', "tsv")
        self.assertIn("<td>x<br />\ny</td>", html)
        self.assertIn("<td>a\tb</td>", html)
        self.assertIn("<td>q&quot;r</td>", html)

    def test_目印は読まない(self):
        html = table("~a\t>\tCENTER:b", "tsv")
        self.assertIn("<td>~a</td>\n<td>&gt;</td>\n<td>CENTER:b</td>", html)

    def test_1行目を見出しにする(self):
        html = table("A\tB\n1\t2", "tsv, header")
        self.assertIn("<thead>\n<tr>\n<th>A</th>\n<th>B</th>", html)

    def test_空の行を飛ばし足りないセルを埋める(self):
        html = table("A\tB\n\n1\n\r\n", "tsv")
        self.assertEqual(html.count("<tr>"), 2)
        self.assertIn("<td>1</td>\n<td></td>", html)

    def test_Markdownのページ(self):
        html = table("**a**\t|b|", "tsv", ext=".md")
        self.assertIn("<td><strong>a</strong></td>\n<td>|b|</td>", html)


class TestWidthAndLines(unittest.TestCase):
    def test_列の幅(self):
        html = table("|a|b|c|\\\\", 'cols="120px | 30% | calc(100% - 200px)", width=100%')
        self.assertIn('<table style="width:100%;table-layout:fixed">', html)
        self.assertIn('<colgroup>\n<col style="width:120px">\n<col style="width:30%">\n'
                      '<col style="width:calc(100% - 200px)">\n</colgroup>', html)

    def test_単位の無い数はpxで空欄は内容に合わせる(self):
        html = table("|a|b|c|\\\\", 'cols="80 | | 2em"')
        self.assertIn('<col style="width:80px">\n<col>\n<col style="width:2em">', html)

    def test_幅を書かなければcolgroupを出さない(self):
        html = table("|a|b|\\\\", 'cols="|| "')
        self.assertNotIn("colgroup", html)
        self.assertNotIn("table-layout", html)

    def test_書けない幅はエラー(self):
        for cols in ('"1px;color:red"', '"url(x)"', '"calc(1px"', '"10px ||| 5px"'):
            with self.subTest(cols=cols):
                self.assertIn("plugin-error", table("|a|\\\\", "cols=" + cols))
        self.assertIn("plugin-error", table("|a|\\\\", "width=wide"))

    def test_縦の二重線(self):
        html = table("|a|b|c|\\\\", 'cols="|| 1px | 2px || 3px ||"')
        self.assertIn('<td class="table-dl">a</td>\n<td>b</td>\n'
                      '<td class="table-dl table-dr">c</td>', html)

    def test_縦の二重線は結合したセルをまたがない(self):
        html = table("|a|b|c|\\\\\n|>|d|e|\\\\", 'cols="| || | |"')
        self.assertIn('<td>a</td>\n<td class="table-dl">b</td>', html)
        self.assertIn('<td colspan="2">d</td>\n<td>e</td>', html)

    def test_横の二重線(self):
        html = table("==\n|~品名|h\\\\\n==\n|a|\\\\\n|b|\\\\\n==")
        self.assertIn('<th class="table-dt">品名</th>', html)
        self.assertIn('<td class="table-dt">a</td>', html)
        self.assertIn('<td class="table-db">b</td>', html)

    def test_横の二重線は行と一緒に並べ替わる(self):
        html = table("|a|\\\\\n==\n|合計|f\\\\")
        self.assertIn('<tfoot>\n<tr>\n<td class="table-dt">合計</td>', html)

    def test_書式指定の行の前の横線は次の行へ(self):
        html = table("|a|\\\\\n==\n|CENTER:|c\\\\\n|b|\\\\")
        self.assertIn('<td class="table-dt" style="text-align:center">b</td>', html)

    def test_縦に結合したセルは終わる行で下線(self):
        html = table("|a|b|\\\\\n|~|c|\\\\\n==")
        self.assertIn('<td class="table-db" rowspan="2">a</td>', html)
        self.assertIn('<td class="table-db">c</td>', html)

    def test_セルの中の二重線の目印は文字のまま(self):
        html = table("|a\n==\nb|\\\\")
        self.assertIn("<td>a<br />\n==<br />\nb</td>", html)

    def test_tsvの横線(self):
        html = table('A\tB\n==\n1\t2\n"=="', "tsv, header")
        self.assertIn('<td class="table-dt">1</td>', html)
        self.assertIn("<td>==</td>", html)  # 引用符で囲んだ == は文字


if __name__ == "__main__":
    unittest.main()
