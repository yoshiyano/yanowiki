#!/usr/bin/env python3
"""テーマの探しかた（wikilib.themes）のテスト。

1つのテーマは、**そのディレクトリ直下の `<名前>.html`** か、
**`<名前>/` フォルダの中の `<名前>.html`**（フォルダ形式）のどちらかで置ける。
探索先は「個別Wiki固有の theme/ → 全Wiki共通の theme/」の順で、フォルダ
形式のときはそのフォルダを先に見る。`common.css` のようにテーマ間で共有
する資材は、フォルダの中に無ければ外側へ落ちて見つかる——この落ちかたが
壊れると、フォルダ形式へ切り替えた瞬間にどのテーマも共有CSSを読めなくなる。

`theme.name` は運用者が書く設定値だが、素のパス結合に渡さない
（`safe_join` を通す）。`../../etc` のような値でフォルダ探索が
広がらないことも、ここで固定しておく。

サーバーは立てず、一時ディレクトリにテーマの置き場所だけを作って確かめる。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_themes.py     （このファイルだけ）
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import themes  # noqa: E402


class ThemeDirsFixture(unittest.TestCase):
    """個別Wiki固有と全Wiki共通の theme/ を持つ、最小の置き場所を作る。

        <tmp>/theme/                     全Wiki共通（themes.THEME_DIR を差し替える）
        <tmp>/wikidata/w/theme/          個別Wiki固有
        <tmp>/wikidata/w/wiki/           wiki_dir（theme_dirs はこの親から辿る）
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.common = os.path.join(root, "theme")
        self.local = os.path.join(root, "wikidata", "w", "theme")
        self.wiki_dir = os.path.join(root, "wikidata", "w", "wiki")
        for d in (self.common, self.local, self.wiki_dir):
            os.makedirs(d)
        self._saved_theme_dir = themes.THEME_DIR
        themes.THEME_DIR = self.common

    def tearDown(self):
        themes.THEME_DIR = self._saved_theme_dir
        self.tmp.cleanup()

    def put(self, directory, relpath, text="x"):
        """テーマの資材を1つ置く（途中のフォルダは作る）。"""
        path = os.path.join(directory, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path


class TestThemeSearchDirs(ThemeDirsFixture):
    """`theme_search_dirs`: そのテーマを探す場所を、見る順に並べる。"""

    def test_フォルダが無ければ探索先は2つのまま(self):
        self.put(self.common, "base.html")
        self.assertEqual(themes.theme_search_dirs(self.wiki_dir, "base"),
                         [self.local, self.common])

    def test_フォルダ形式なら中を先に見る(self):
        self.put(self.common, "tname/tname.html")
        self.assertEqual(
            themes.theme_search_dirs(self.wiki_dir, "tname"),
            [self.local, os.path.join(self.common, "tname"), self.common],
        )

    def test_個別Wiki固有のフォルダが最優先(self):
        self.put(self.local, "tname/tname.html")
        self.put(self.common, "tname/tname.html")
        self.assertEqual(
            themes.theme_search_dirs(self.wiki_dir, "tname"),
            [os.path.join(self.local, "tname"), self.local,
             os.path.join(self.common, "tname"), self.common],
        )

    def test_共有資材はフォルダの外へ落ちて見つかる(self):
        # ここが壊れると、フォルダ形式にした瞬間に common.css が読めなくなる
        self.put(self.common, "tname/tname.html")
        self.put(self.common, "common.css")
        dirs = themes.theme_search_dirs(self.wiki_dir, "tname")
        found = [d for d in dirs if os.path.isfile(os.path.join(d, "common.css"))]
        self.assertEqual(found, [self.common])

    def test_境界の外へ出る名前ではフォルダ探索をしない(self):
        for name in ("../../etc", "..", ".", "a/b", "a\\b", ""):
            self.assertEqual(themes.theme_search_dirs(self.wiki_dir, name),
                             [self.local, self.common], name)


class TestListThemeNames(ThemeDirsFixture):
    """`list_theme_names`: 選べるテーマ名の一覧（セレクタが使う）。"""

    def test_平置きとフォルダ形式の両方を数える(self):
        self.put(self.common, "base.html")
        self.put(self.common, "tname/tname.html")
        self.assertEqual(themes.list_theme_names(self.wiki_dir), ["base", "tname"])

    def test_個別Wiki固有と共通をまとめ_重複は1つにする(self):
        self.put(self.common, "base.html")
        self.put(self.local, "base.html")
        self.put(self.local, "mine.html")
        self.assertEqual(themes.list_theme_names(self.wiki_dir), ["base", "mine"])

    def test_名前の違うhtmlだけのフォルダは数えない(self):
        # <名前>/<名前>.html でなければテーマとして扱わない
        self.put(self.common, "tname/other.html")
        self.assertEqual(themes.list_theme_names(self.wiki_dir), [])

    def test_html以外は数えない(self):
        self.put(self.common, "base.css")
        self.put(self.common, "base.js")
        self.assertEqual(themes.list_theme_names(self.wiki_dir), [])

    def test_置き場所が無くても落ちない(self):
        # 個別Wiki固有の theme/ を持たないWikiのほうが多い
        os.rmdir(self.local)
        self.put(self.common, "base.html")
        self.assertEqual(themes.list_theme_names(self.wiki_dir), ["base"])


class TestSearchTemplatePlace(unittest.TestCase):
    """検索結果のテンプレートは**テーマではない**ので、theme/ ではなく _sys/search/ に置く。

    theme/ に置くとテーマとして数えられ、セレクタや設定「テーマ」で選べてしまう
    （選ぶと自分自身への継承で描けない）。"""

    def test_共通のtheme_に置かない(self):
        self.assertFalse(os.path.exists(os.path.join(themes.THEME_DIR, "search.html")))

    def test_本体の置き場所にある(self):
        from wikilib.paths import SEARCH_DIR, SEARCH_TEMPLATE, SEARCH_TEMPLATE_PREFIX
        self.assertTrue(SEARCH_TEMPLATE.startswith(SEARCH_TEMPLATE_PREFIX + "/"))
        rest = SEARCH_TEMPLATE[len(SEARCH_TEMPLATE_PREFIX) + 1:]
        self.assertTrue(os.path.isfile(os.path.join(SEARCH_DIR, rest)))

    def test_テーマの一覧に出ない(self):
        from wikilib.paths import farm_wiki_dir
        self.assertNotIn("search", themes.list_theme_names(farm_wiki_dir("_system")))


class TestDefaultZoom(unittest.TestCase):
    """`theme.zoom`（標準の拡大率）。**手書きの設定でも、common.js が受け付ける範囲に収める。**"""

    def zoom(self, value):
        return themes.default_zoom({"theme": {"zoom": value}})

    def test_未設定は100(self):
        self.assertEqual(themes.default_zoom({}), 100)
        self.assertEqual(themes.default_zoom({"theme": None}), 100)
        self.assertEqual(themes.default_zoom({"theme": {"name": "base"}}), 100)

    def test_数はそのまま(self):
        self.assertEqual(self.zoom(115), 115)
        self.assertEqual(self.zoom(70), 70)
        self.assertEqual(self.zoom(112.5), 112.5)
        self.assertEqual(self.zoom(130.0), 130)
        self.assertIsInstance(self.zoom(130.0), int)    # テーマが 130.0 と出さない

    def test_範囲は10から400まで(self):
        self.assertEqual(self.zoom(10), 10)
        self.assertEqual(self.zoom(400), 400)
        for out in (5, 9.9, 400.1, 999, 0, -50):
            self.assertEqual(self.zoom(out), 100, out)

    def test_数でないものは100(self):
        for bad in ("abc", "", None, True, False, [115], {"a": 1}, float("nan"), float("inf")):
            self.assertEqual(self.zoom(bad), 100, repr(bad))

    def test_数字の文字列は数として読む(self):
        self.assertEqual(self.zoom("115"), 115)
        self.assertEqual(self.zoom(" 130 "), 130)
        self.assertEqual(self.zoom("999"), 100)


class TestDefaultContentWide(unittest.TestCase):
    """`theme.content_wide`（本文の幅の上限を標準で外すか）。"""

    def wide(self, value):
        return themes.default_content_wide({"theme": {"content_wide": value}})

    def test_未設定は偽(self):
        self.assertFalse(themes.default_content_wide({}))
        self.assertFalse(themes.default_content_wide({"theme": None}))

    def test_真偽(self):
        self.assertTrue(self.wide(True))
        self.assertFalse(self.wide(False))

    def test_文字列の書きかたの揺れは_他の真偽の設定と同じに読む(self):
        self.assertTrue(self.wide("true"))
        for off in ("false", "no", "off", "0"):
            self.assertFalse(self.wide(off), off)


if __name__ == "__main__":
    unittest.main()
