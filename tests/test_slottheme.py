#!/usr/bin/env python3
"""スロットHTML のテーマ（`wikilib.slottheme`）のテスト。

  - サニタイズ: スクリプト・フォーム・style・on*、目印以外の data-*、theme- で始まらない id、
    本体の部品の class、外へのリンク、data-asset の無い link を取り除く
  - 目印を埋める: data-text（エスケープ）・data-if/unless・data-slot・wiki-slot・data-href・
    data-asset・content の入れ物の属性・メニューの開閉モード
  - `{{ }}` は式として動かない（Jinja2 を通さない）
  - render_theme: theme.name・cookie でスロットHTML を選べる。同じ名前の Jinja2 のテーマが
    あればそちらを描く。名指しのテンプレート（検索結果）は Jinja2 のテーマで描く
  - 資材 `/.slottheme/<テーマ>/<ファイル>`: CSS・画像・フォントだけを配る。CSS は取り除いてから配る
  - CSS の検査: @import・外への url()・expression() などを取り除く。エスケープですり抜けられない
  - 解析の結果を覚えておき、ファイルが変われば読み直す

実行:
    _venv/bin/python tests/test_slottheme.py
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402
from markupsafe import Markup  # noqa: E402

from wikilib import paths, slottheme, themes  # noqa: E402

FARM = "testwiki"

THEME = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url=https://evil.example/">
<title data-text="head_title">見本</title>
<meta name="wiki-slot" content="plugin-assets">
<link rel="stylesheet" data-asset="my.css" href="../my.css">
<link rel="stylesheet" data-asset="common:common.css">
<link rel="stylesheet" href="https://evil.example/x.css">
<meta name="wiki-behaviors" content="menu1-fold">
<style>body{}</style>
</head>
<body onload="alert(1)">
<script>alert(1)</script>
<header class="site-header search" id="top" style="color:red">
  <a data-href="home" data-text="site_title" href="https://evil.example/">サイト名</a>
  <a href="#theme-x">内側</a>
  <wiki-slot name="search-form"></wiki-slot>
</header>
<div class="content" data-editable data-base-url="https://evil.example" data-theme-x="1"
     id="theme-decoy">偽物</div>
<form action="/x"><input name="q"></form>
<main class="content" data-slot="content">本文の見本</main>
<nav class="toc" data-if="toc"><ul data-slot="toc"></ul></nav>
<span data-if="login_as" class="login">ログイン</span>
<span data-unless="login_as" class="anon">未ログイン</span>
<p>{{ 7 * 7 }}</p>
<img data-asset="logo.png" src="x.png" onerror="alert(1)" alt="ロゴ">
<wiki-slot name="scripts"></wiki-slot>
</body>
</html>
"""


class SlotThemeTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="slottheme-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        self.common = os.path.join(self.work, "theme")
        self.common_slot = os.path.join(self.work, "slottheme")
        self.site_slot = os.path.join(self.work, "wikidata", FARM, "slottheme")
        for d in (self.common, self.common_slot, self.site_slot):
            os.makedirs(d)
        self.kept = (themes.THEME_DIR, slottheme.SLOTTHEME_DIR, paths.WIKIDATA_DIR)
        themes.THEME_DIR = self.common
        slottheme.SLOTTHEME_DIR = self.common_slot
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        bottle.request.bind({"PATH_INFO": "/", "QUERY_STRING": ""})
        slottheme._cache.clear()

    def tearDown(self):
        themes.THEME_DIR, slottheme.SLOTTHEME_DIR, paths.WIKIDATA_DIR = self.kept
        themes._jinja_envs.clear()
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def write(self, path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def ctx(self, **extra):
        ctx = {"site_title": "<サイト>", "page_title": "ページ", "base_url": "/=testwiki",
               "theme_url": "/=testwiki/.theme", "search_url": "/=testwiki/.search",
               "content": "<p>本物の本文</p>", "editable": True, "page": "Foo",
               "toc": [], "login_as": "", "menu1_mode": "fix"}
        ctx.update(extra)
        return ctx

    def render(self, text=THEME, **extra):
        path = os.path.join(self.site_slot, "mine.html")
        self.write(path, text)
        return slottheme.render(self.wiki_dir, path, "mine", self.ctx(**extra))


class TestSanitize(SlotThemeTestBase):

    def test_危ないものを取り除く(self):
        html, report = self.render()
        for bad in ("<script>alert", "<style>", "onload", "onerror", "style=", '<form action="/x"',
                    "http-equiv", "evil.example", 'id="top"', "data-theme-decoy"):
            self.assertNotIn(bad, html, bad)
        self.assertTrue(report)

    def test_目印以外のdata属性と部品のclassを除く(self):
        html, _ = self.render()
        # 偽の入れ物は data-editable・data-base-url・class="content" を失う
        self.assertIn('<div data-theme-x="1" id="theme-decoy">偽物</div>', html)
        self.assertIn('class="site-header"', html)   # search は除く
        self.assertEqual(html.count("data-base-url"), 1)
        self.assertIn('<main class="content" data-editable data-base-url="/=testwiki" '
                      'data-page="Foo"><p>本物の本文</p></main>', html)

    def test_チェックで取り除くものが分かる(self):
        report = slottheme.check("<p onclick='x'>a</p><script></script>")
        self.assertTrue(any("onclick" in r for r in report))
        self.assertTrue(any("script" in r for r in report))
        self.assertEqual(slottheme.check('<p class="theme">a</p>'), [])


class TestFill(SlotThemeTestBase):

    def test_値はエスケープして埋める(self):
        html, _ = self.render()
        self.assertIn("<title>ページ - &lt;サイト&gt;</title>", html)
        self.assertIn('<a href="/=testwiki/">&lt;サイト&gt;</a>', html)

    def test_式は動かない(self):
        html, _ = self.render()
        self.assertIn("<p>{{ 7 * 7 }}</p>", html)
        self.assertNotIn("49", html)

    def test_data_ifとunless(self):
        html, _ = self.render()
        self.assertNotIn("ログイン</span>", html.replace("未ログイン", ""))
        self.assertIn("未ログイン", html)
        self.assertNotIn('class="toc"', html)   # 目次が1つ以下なら空
        html, _ = self.render(login_as="Logged in as a",
                              toc=[{"level": 2, "id": "a", "title": "A"},
                                   {"level": 2, "id": "b", "title": "B"}])
        self.assertIn('class="login"', html)
        self.assertNotIn("未ログイン", html)
        self.assertIn('<li class="toc-l2"><a href="#a">A</a></li>', html)

    def test_スロットと資材(self):
        self.write(os.path.join(self.site_slot, "my.css"), "body{}")
        html, _ = self.render()
        self.assertIn('class="search" id="site-search-form" action="/=testwiki/.search"', html)
        self.assertIn('<link rel="stylesheet" href="/=testwiki/.slottheme/mine/my.css">', html)
        self.assertIn('<link rel="stylesheet" href="/=testwiki/.theme/common.css">', html)
        # スロットHTML のフォルダに無いものは共通の資材を指す
        self.assertIn('<img alt="ロゴ" src="/=testwiki/.theme/logo.png">', html)
        self.assertIn('<script src="/=testwiki/.theme/common.js"></script>', html)
        self.assertIn('<script src="/=testwiki/.theme/base.js"></script>', html)
        self.assertIn('<html lang="ja" data-menu1-mode="fix">', html)

    def test_infoの知らせ(self):
        theme = THEME.replace("<main", '<p data-if="page-info" data-slot="page-info"></p><main', 1)
        html, report = self.render(theme)
        self.assertNotIn("page-info-slot", html)   # 知らせが無ければ入れ物ごと出さない
        self.assertNotIn("知らないスロット: page-info", report)
        html, _ = self.render(theme, page_info=Markup('<a href="/x">i</a><a href="/y">j</a>'))
        self.assertIn('<p><span class="page-info-slot"><a href="/x">i</a><a href="/y">j</a>'
                      '</span></p>', html)

    def test_標準の拡大率と幅を_html_に付ける(self):
        html, _ = self.render(default_zoom=115, default_content_wide=True)
        self.assertIn('<html lang="ja" data-menu1-mode="fix" data-default-zoom="115" '
                      'data-default-wide="1">', html)

    def test_標準の幅は真のときだけ付ける(self):
        html, _ = self.render(default_zoom=100, default_content_wide=False)
        self.assertIn('data-default-zoom="100"', html)
        self.assertNotIn("data-default-wide", html)

    def test_標準の値が渡されなければ付けない(self):
        html, _ = self.render()
        self.assertNotIn("data-default-zoom", html)
        self.assertNotIn("data-default-wide", html)

    def test_テーマが書いた標準の値は使わない(self):
        # data-default-* は目印ではないので、テーマの作者が書いても取り除く（本体だけが付ける）
        mine = THEME.replace('<html lang="ja">',
                             '<html lang="ja" data-default-zoom="999" data-default-wide="1">')
        html, _ = self.render(mine)
        self.assertNotIn("999", html)
        self.assertNotIn("data-default-wide", html)
        html, _ = self.render(mine, default_zoom=90)
        self.assertIn('data-default-zoom="90"', html)
        self.assertNotIn("999", html)

    def test_ファイルが変われば読み直す(self):
        path = os.path.join(self.site_slot, "mine.html")
        self.write(path, "<p>一</p>")
        self.assertIn("一", slottheme.render(self.wiki_dir, path, "mine", self.ctx())[0])
        time.sleep(0.01)
        self.write(path, "<p>二つめ</p>")
        self.assertIn("二つめ", slottheme.render(self.wiki_dir, path, "mine", self.ctx())[0])


class TestRenderTheme(SlotThemeTestBase):

    def page(self, config=None, template=None, cookie=None):
        env = {"PATH_INFO": "/", "QUERY_STRING": ""}
        if cookie:
            from wikilib.paths import THEME_COOKIE, wiki_cookie_name
            env["HTTP_COOKIE"] = f"{wiki_cookie_name(THEME_COOKIE, FARM)}={cookie}"
        bottle.request.bind(env)
        res = themes.render_theme(None, self.wiki_dir, config or {}, FARM, "Foo", "題",
                                  "<p>本文</p>", template=template, editable=False)
        return res.body

    def setUp(self):
        super().setUp()
        self.write(os.path.join(self.common, "base.html"),
                   "JINJA-BASE {{ page_title }}{% block content %}{% endblock %}")
        self.write(os.path.join(self.common_slot, "slotty.html"),
                   '<p>SLOT <span data-text="page_title"></span> {{ 1 + 1 }}</p>')

    def test_設定でスロットHTMLを選べる(self):
        body = self.page({"theme": {"name": "slotty"}})
        self.assertIn("SLOT <span>題</span> {{ 1 + 1 }}", body)
        self.assertIn("slotty", themes.list_theme_names(self.wiki_dir))

    def test_cookieでも選べる(self):
        self.assertIn("SLOT", self.page(cookie="slotty"))

    def test_個別Wikiが共通より先(self):
        self.write(os.path.join(self.site_slot, "slotty.html"), "<p>SITE</p>")
        self.assertIn("SITE", self.page({"theme": {"name": "slotty"}}))

    def test_同じ名前ならJinja2を描く(self):
        self.write(os.path.join(self.common_slot, "base.html"), "<p>SLOT-BASE</p>")
        body = self.page({"theme": {"name": "base"}})
        self.assertIn("JINJA-BASE", body)

    def test_Jinja2のテーマへ標準の拡大率と幅を渡す(self):
        self.write(os.path.join(self.common, "probe.html"),
                   "ZOOM={{ default_zoom }} WIDE={{ default_content_wide }}")
        body = self.page({"theme": {"name": "probe", "zoom": 115, "content_wide": True}})
        self.assertEqual(body, "ZOOM=115 WIDE=True")

    def test_標準の値が無ければ100と偽(self):
        self.write(os.path.join(self.common, "probe.html"),
                   "ZOOM={{ default_zoom }} WIDE={{ default_content_wide }}")
        self.assertEqual(self.page({"theme": {"name": "probe"}}), "ZOOM=100 WIDE=False")
        # 手書きのおかしな値は100・偽に戻す
        body = self.page({"theme": {"name": "probe", "zoom": "abc", "content_wide": "off"}})
        self.assertEqual(body, "ZOOM=100 WIDE=False")
        self.assertIn("ZOOM=100", self.page({"theme": {"name": "probe", "zoom": 999}}))

    def test_スロットHTMLのテーマにも標準の値が付く(self):
        self.write(os.path.join(self.common_slot, "slothtml.html"),
                   '<!doctype html><html lang="ja"><body><p>SLOT</p></body></html>')
        body = self.page({"theme": {"name": "slothtml", "zoom": 130, "content_wide": True}})
        self.assertIn('data-default-zoom="130" data-default-wide="1"', body)
        body = self.page({"theme": {"name": "slothtml"}})
        self.assertIn('data-default-zoom="100"', body)
        self.assertNotIn("data-default-wide", body)

    def test_名指しのテンプレートはJinja2で描く(self):
        # 検索結果のテンプレートは本体のもの（_sys/search/search.html）
        body = self.page({"theme": {"name": "slotty"}}, template=paths.SEARCH_TEMPLATE)
        self.assertIn("JINJA-BASE", body)
        self.assertIn('class="search-detail"', body)

    def test_検索結果のテンプレートはテーマの置き場所に同じ名前があっても本体のもの(self):
        # テーマではないので、テーマ側からは上書きされない
        os.makedirs(os.path.join(self.common, "search"))
        self.write(os.path.join(self.common, "search", "search.html"), "THEME-SEARCH")
        self.write(os.path.join(self.common, "search.html"), "THEME-SEARCH")
        body = self.page({"theme": {"name": "base"}}, template=paths.SEARCH_TEMPLATE)
        self.assertNotIn("THEME-SEARCH", body)
        self.assertIn('class="search-detail"', body)


class TestAssets(SlotThemeTestBase):

    def test_CSSと画像だけを配る(self):
        os.makedirs(os.path.join(self.site_slot, "mine"))
        self.write(os.path.join(self.site_slot, "mine", "a.css"), "body{}")
        self.write(os.path.join(self.site_slot, "b.png"), "png")
        for name in ("evil.html", "evil.js", "evil.svg", "mine.html"):
            self.write(os.path.join(self.site_slot, name), "<script>alert(1)</script>")
        for rest in ("mine/a.css", "mine/b.png"):
            res = slottheme.serve_slot_asset(self.wiki_dir, rest)
            self.assertEqual(res.status_code, 200, rest)
            self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")
            if hasattr(res.body, "close"):
                res.body.close()
        for rest in ("mine/evil.html", "mine/evil.js", "mine/evil.svg", "mine/mine.html",
                     "mine/../b.png", "../x/a.css", "mine/nothing.css", "mine"):
            self.assertEqual(slottheme.serve_slot_asset(self.wiki_dir, rest).status_code, 404, rest)


class TestCss(SlotThemeTestBase):

    def test_取り除くもの(self):
        css = (r"@import 'x.css';" "\n"
               r".a{color:red;background:u\72l(http://evil/x)}" "\n"
               ".b{background:url(logo.png);behavior:url(x.htc)}\n"
               '.c{background-image:image-set("https://e/a.png" 1x)}\n'
               ".d{x:expression(alert(1));margin:0}\n"
               '.e{background:url("data:image/svg+xml,%3Csvg%3E")}\n'
               "@font-face{font-family:F;src:url(f.woff2)}\n"
               "@media (min-width:1px){.f{background:url(//evil)} .g{color:blue}}\n")
        out, problems = slottheme.clean_css(css)
        for bad in ("@import", "evil", "behavior", "https://e", "expression"):
            self.assertNotIn(bad, out, bad)
        for good in (".a{color:red;}", "url(logo.png)", "data:image/svg+xml", "url(f.woff2)",
                     ".g{color:blue;}", "margin:0"):
            self.assertIn(good, out, good)
        self.assertEqual(len(problems), 6, problems)
        self.assertEqual(slottheme.check_css(".a{color:red} @media print{.b{display:none}}"), [])

    def test_配るときにも取り除く(self):
        os.makedirs(os.path.join(self.site_slot, "mine"))
        self.write(os.path.join(self.site_slot, "mine", "a.css"),
                   ".a{color:red;background:url(http://evil/)}")
        res = slottheme.serve_slot_asset(self.wiki_dir, "mine/a.css")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.body, ".a{color:red;}\n")
        self.assertTrue(res.headers["Content-Type"].startswith("text/css"))
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
