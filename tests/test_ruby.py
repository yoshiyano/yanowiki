"""ruby プラグイン: 中身は本家と同じく展開してからタグだけを除く。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_sys"))

from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import render_source  # noqa: E402


def render(text, ext=".txt"):
    ctx = PluginContext(config={}, farm="t", wiki_dir=None, page="P")
    ctx.ext = ext
    engine = build_markdown_renderer({}, None, ctx)
    return render_source(engine, text, ext, False, context=ctx)[0]


class TestRubyBody(unittest.TestCase):

    def test_文字参照はその文字として出る(self):
        self.assertIn("<rb>X&amp;Y</rb>", render("&ruby(a){X&amp;Y};"))

    def test_飾りは外れて文字だけ残る(self):
        self.assertIn("<rb>漢</rb>", render("&ruby(かん){''漢''};"))
        self.assertIn("<rb>赤</rb>", render("&ruby(a){&color(red){赤};};"))

    def test_Markdown記法のページでも同じ(self):
        self.assertIn("<rb>太&amp;字</rb>", render("&ruby(よみ){**太**&amp;字};", ".md"))

    def test_タグは文字のまま(self):
        html = render("&ruby(<b>){<script>x</script>};")
        self.assertNotIn("<script>", html)
        self.assertIn("<rt>&lt;b&gt;</rt>", html)

    def test_中身が空ならエラー(self):
        self.assertIn("plugin-error", render("&ruby(a){};"))


if __name__ == "__main__":
    unittest.main()
