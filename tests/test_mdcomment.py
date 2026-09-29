"""Markdown記法の `<!-- … -->` を表示から取り除く（wikilib.mdcomment）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_sys"))

from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import render_source  # noqa: E402


def render(text, ext=".md", config=None):
    ctx = PluginContext(config=config or {}, farm="t", wiki_dir=None, page="P")
    ctx.ext = ext
    engine = build_markdown_renderer(config or {}, None, ctx)
    html, _title, toc = render_source(engine, text, ext, False, context=ctx)
    return html, toc


class TestMarkdownComment(unittest.TestCase):

    def test_行頭のコメントは消える(self):
        html, _ = render("A\n\n<!-- secret -->\n\nB")
        self.assertNotIn("secret", html)
        self.assertIn("<p>A</p>", html)
        self.assertIn("<p>B</p>", html)

    def test_空行と見出しを含む複数行も消え_目次にも入らない(self):
        html, toc = render("A\n\n<!--\n## 隠す見出し\n\n中身\n-->\n\n## 見える見出し\n")
        self.assertNotIn("隠す見出し", html)
        self.assertNotIn("中身", html)
        self.assertIn("見える見出し", html)
        self.assertNotIn("隠す見出し", str(toc))

    def test_文中のコメントはその部分だけ消える(self):
        html, _ = render("B <!-- inline --> C")
        self.assertNotIn("inline", html)
        self.assertIn("B", html)
        self.assertIn("C", html)

    def test_閉じのあとに続く本文は残る(self):
        html, _ = render("<!-- メモ --> 本文")
        self.assertNotIn("メモ", html)
        self.assertIn("本文", html)

    def test_コードの中は消さない(self):
        html, _ = render("`<!-- a -->`\n\n```\n<!-- b -->\n```\n\n    <!-- c -->")
        for word in ("a", "b", "c"):
            self.assertIn(f"&lt;!-- {word} --&gt;", html)

    def test_閉じの無い文中のコメントは文字のまま(self):
        html, _ = render("X <!-- 閉じない")
        self.assertIn("&lt;!-- 閉じない", html)

    def test_allow_htmlがallでも消える(self):
        html, _ = render("A <!-- secret --> B", config={"markdown": {"allow_html": "all"}})
        self.assertNotIn("secret", html)

    def test_PukiWiki記法には効かない(self):
        html, _ = render("A\n<!-- p -->\nB", ext=".txt")
        self.assertIn("&lt;!-- p --&gt;", html)

    def test_プラグインの中身でも消える(self):
        html, _ = render("#note{{\nA <!-- secret --> B\n}}")
        self.assertNotIn("secret", html)


if __name__ == "__main__":
    unittest.main()
