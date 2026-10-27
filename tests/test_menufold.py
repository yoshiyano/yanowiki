#!/usr/bin/env python3
"""メニューの開け閉め（wikilib.menufold。2026-09-30）のテスト。

- 下の階層を持つ `+` の項目は <details>（閉）、`-` の項目は <details open>（開）
- 下の階層を持たない項目・`*` の項目はこれまでどおり
- 記号が変わって分かれた <ul> は1つにつなぐ
- HTMLを許可しない設定でも同じように出る
- メニューの目印（`data-menu-fold`。開け閉めの記録をメニューごとに分ける。2026-10-07）は
  一番外の <ul> だけに付く

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_menufold.py     （このファイルだけ）
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

from markdown_it import MarkdownIt  # noqa: E402

from wikilib.menufold import fold_menu_lists  # noqa: E402


def render(src, html=True, menu_id=""):
    md = MarkdownIt("commonmark", {"html": html})
    return md.renderer.render(fold_menu_lists(md.parse(src), menu_id), md.options, {})


class TestMenuFold(unittest.TestCase):
    def test_プラスは閉じマイナスは開く(self):
        html = render("+ a\n  - b\n- c\n  - d\n")
        self.assertIn('<li class="menu-fold">\n<details>\n<summary>a</summary>', html)
        self.assertIn('<li class="menu-fold">\n<details open="">\n<summary>c</summary>', html)

    def test_下の階層が無い項目はそのまま(self):
        html = render("- a\n+ b\n")
        self.assertIn("<li>a</li>\n<li>b</li>", html)
        self.assertNotIn("details", html)

    def test_アスタリスクは開け閉めしない(self):
        html = render("* a\n  - b\n")
        self.assertNotIn("details", html)

    def test_分かれたリストを1つにつなぐ(self):
        html = render("- a\n+ b\n- c\n")
        self.assertEqual(html.count("<ul>"), 1)

    def test_入れ子の中でも効く(self):
        html = render("- a\n  - b\n  + c\n    - d\n")
        self.assertEqual(html.count("<ul>"), 3)  # 外・a の下・c の下
        self.assertIn("<details>\n<summary>c</summary>", html)
        self.assertIn('<details open="">\n<summary>a</summary>', html)

    def test_詳細の閉じはliの内側(self):
        html = render("+ a\n  - b\n")
        self.assertIn("</ul>\n</details>\n</li>", html)

    def test_HTMLを許可しなくても出る(self):
        html = render("+ a\n  - b\n", html=False)
        self.assertIn("<details>\n<summary>a</summary>", html)

    def test_リンクの項目(self):
        html = render("+ [プラグイン](/Syntax/Plugin)\n  - [br](/Syntax/Plugin/br)\n")
        self.assertIn('<summary><a href="/Syntax/Plugin">プラグイン</a></summary>', html)

    def test_メニューの目印は一番外のulだけに付く(self):
        html = render("- a\n  - b\n+ c\n  - d\n", menu_id="/=w/mainmenu")
        self.assertEqual(html.count("data-menu-fold"), 1)
        self.assertIn('<ul data-menu-fold="/=w/mainmenu">', html)

    def test_目印を渡さなければ付けない(self):
        self.assertNotIn("data-menu-fold", render("- a\n  - b\n"))

    def test_下の階層が無いメニューにも目印は付く(self):
        # 記録を消す側が「このメニューには開け閉めの項目が無くなった」と分かるように
        self.assertIn('data-menu-fold="m"', render("- a\n- b\n", menu_id="m"))

    def test_間に段落があって離れたリストにはそれぞれ付く(self):
        html = render("- a\n  - b\n\n段落\n\n- c\n  - d\n", menu_id="m")
        self.assertEqual(html.count('data-menu-fold="m"'), 2)

    def test_目印の値はエスケープされる(self):
        html = render("- a\n", menu_id='/=w/"x"<y>')
        self.assertIn('data-menu-fold="/=w/&quot;x&quot;&lt;y&gt;"', html)


if __name__ == "__main__":
    unittest.main()
