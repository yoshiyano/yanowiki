#!/usr/bin/env python3
"""プロキシが伝える入口の接頭辞（`X-Forwarded-Prefix`）のテスト。

外向きの `/sandbox/` を内側の `/=sandbox/` へ対応づけるプロキシの後ろで、
システムが作るリンク（CSS・ページ間リンク・リダイレクト・cookieのPath）が
外向きの形になることを固定する。**ここが崩れると、公開したURLでCSSが
読めずレイアウトが壊れる**（`/=sandbox/…` は外からは見えないため）。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_forwardedprefix.py     （このファイルだけ）
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from bottle import request  # noqa: E402

from wikilib.render import rewrite_content_links  # noqa: E402
from wikilib.wikiconfig import farm_base_url, forwarded_prefix  # noqa: E402

CONFIG = {"farm": {"default": "_system"}}


def with_header(value):
    """`X-Forwarded-Prefix` が付いたリクエストの中で実行するための文脈。"""
    environ = {} if value is None else {"HTTP_X_FORWARDED_PREFIX": value}
    return request.bind(environ)


class TestForwardedPrefix(unittest.TestCase):

    def test_ヘッダが無ければNone(self):
        with_header(None)
        self.assertIsNone(forwarded_prefix())

    def test_値を取り出す(self):
        with_header("/sandbox")
        self.assertEqual(forwarded_prefix(), "/sandbox")

    def test_末尾スラッシュは落とす(self):
        with_header("/sandbox/")
        self.assertEqual(forwarded_prefix(), "/sandbox")

    def test_多段の接頭辞(self):
        with_header("/wiki/sandbox")
        self.assertEqual(forwarded_prefix(), "/wiki/sandbox")

    def test_不正な値は無視する(self):
        for bad in ("//evil.com", "sandbox", "/a/../b", "/..", "/a b", '/a"b',
                    "/<script>", "http://evil.com/x", "/", ""):
            with_header(bad)
            self.assertIsNone(forwarded_prefix(), bad)


class TestFarmBaseUrl(unittest.TestCase):

    def test_ヘッダ無しは従来どおり(self):
        with_header(None)
        self.assertEqual(farm_base_url(CONFIG, "_system", False), "")
        self.assertEqual(farm_base_url(CONFIG, "_system", True), "/=_system")
        self.assertEqual(farm_base_url(CONFIG, "sandbox", False), "/=sandbox")
        self.assertEqual(farm_base_url(CONFIG, "sandbox", True), "/=sandbox")

    def test_server_prefixは従来どおり足される(self):
        with_header(None)
        config = {"farm": {"default": "_system"}, "server": {"prefix": "/a/b"}}
        self.assertEqual(farm_base_url(config, "_system", False), "/a/b")
        self.assertEqual(farm_base_url(config, "sandbox", True), "/a/b/=sandbox")

    def test_ヘッダがあればそれが入口で_Wiki名は付けない(self):
        with_header("/sandbox")
        self.assertEqual(farm_base_url(CONFIG, "sandbox", True), "/sandbox")
        self.assertEqual(farm_base_url(CONFIG, "sandbox", False), "/sandbox")

    def test_ヘッダがあればserver_prefixより優先(self):
        with_header("/sandbox")
        config = {"farm": {"default": "_system"}, "server": {"prefix": "/a/b"}}
        self.assertEqual(farm_base_url(config, "sandbox", True), "/sandbox")

    def test_不正なヘッダは従来の組み立てに戻る(self):
        with_header("//evil.com")
        self.assertEqual(farm_base_url(CONFIG, "sandbox", True), "/=sandbox")


class TestRewriteTwice(unittest.TestCase):
    """書き換え済みのリンクをもう一度通しても、入口が二重に付かない。

    `#include` は取り込んだ本文を自分で書き換え、そのあと外側のページ全体が
    もう一度書き換える。`/sandbox/sandbox/…` になっていた（実際の不具合）。"""

    def rewrite_twice(self, html, base_url):
        once = rewrite_content_links(html, base_url, "Page")
        return once, rewrite_content_links(once, base_url, "Page")

    def test_入口が_farm名なしの形でも二重にならない(self):
        once, twice = self.rewrite_twice('<a href="講義/第01回">x</a>', "/1ev-py")
        self.assertEqual(once, '<a href="/1ev-py/講義/第01回">x</a>')
        self.assertEqual(twice, once)

    def test_添付の書き換えも二重にならない(self):
        once, twice = self.rewrite_twice('<img src="logo.png">', "/1ev-py")
        self.assertEqual(once, '<img src="/1ev-py/.attach/Page/logo.png">')
        self.assertEqual(twice, once)

    def test_farm名つきの入口も従来どおり(self):
        once, twice = self.rewrite_twice('<a href="foo">x</a>', "/=sandbox")
        self.assertEqual(once, '<a href="/=sandbox/foo">x</a>')
        self.assertEqual(twice, once)

    def test_入口が空なら従来どおり(self):
        self.assertEqual(rewrite_content_links('<a href="foo">x</a>', "", ""),
                         '<a href="/foo">x</a>')

    def test_外部リンクとアンカーは触らない(self):
        html = '<a href="https://example.com/a">x</a><a href="#top">y</a>'
        self.assertEqual(rewrite_content_links(html, "/1ev-py", ""), html)


class TestSystemUrls(unittest.TestCase):
    """本文に書いたシステムのURL（`/.〜`）にも入口を付ける。付けないと、既定以外の
    Wikiで押したとき既定のWikiの添付・設定画面が開く（2026-09-25）。既定のWikiで
    しか開けない画面（`/.newwiki` など。Wiki名付きは403）は書かれたまま。"""

    def rewrite(self, href, base_url="/=_system"):
        html = rewrite_content_links(f'<a href="{href}">x</a>', base_url, "index")
        return html[len('<a href="'):-len('">x</a>')]

    def test_Wikiごとの画面と添付には入口を付ける(self):
        for href in ("/.attach/index/logo.png", "/.admin/configwiki", "/.search?q=x",
                     "/.groups"):
            with self.subTest(href=href):
                self.assertEqual(self.rewrite(href), "/=_system" + href)

    def test_既定のWikiでしか開けない画面は書かれたまま(self):
        for href in ("/.newwiki", "/.newwiki.css", "/.delwiki", "/.restart",
                     "/.allwiki", "/.allwiki?x=1", "/.markers-panel"):
            with self.subTest(href=href):
                self.assertEqual(self.rewrite(href), href)

    def test_名前が前方一致するだけのものは別物(self):
        self.assertEqual(self.rewrite("/.newwikifoo"), "/=_system/.newwikifoo")

    def test_一覧の名前を変えたらその名前で見分ける(self):
        with mock.patch("wikilib.wikiconfig.load_config",
                        return_value={"farm": {"allwiki": "wikis"}}):
            self.assertEqual(self.rewrite("/.wikis"), "/.wikis")
            self.assertEqual(self.rewrite("/.allwiki"), "/=_system/.allwiki")

    def test_既定のWikiでは変わらない(self):
        self.assertEqual(self.rewrite("/.attach/index/logo.png", ""), "/.attach/index/logo.png")

    def test_プロキシの入口でも付き_二重にならない(self):
        once = rewrite_content_links('<img src="/.attach/index/a.png">', "/sandbox", "index")
        self.assertEqual(once, '<img src="/sandbox/.attach/index/a.png">')
        self.assertEqual(rewrite_content_links(once, "/sandbox", "index"), once)


class TestServerPrefixLinks(unittest.TestCase):
    """`server.prefix`（`/pre`）でサブパスに置いたとき、別のWikiへのリンクと、既定の
    Wikiでしか開けない画面にはサイトの根（`/pre`）を付ける（2026-09-26）。
    プロキシが入口を伝えているときは根が分からないので付けない。"""

    def setUp(self):
        request.bind({})

    def tearDown(self):
        request.bind({})

    def rewrite(self, href, base_url):
        html = rewrite_content_links(f'<a href="{href}">x</a>', base_url, "index")
        return html[len('<a href="'):-len('">x</a>')]

    def test_別のWikiへのリンクにはサイトの根(self):
        for base in ("/pre", "/pre/=_system"):
            with self.subTest(base=base):
                self.assertEqual(self.rewrite("/=other/X", base), "/pre/=other/X")

    def test_既定のWikiでしか開けない画面にもサイトの根(self):
        for base in ("/pre", "/pre/=_system"):
            with self.subTest(base=base):
                self.assertEqual(self.rewrite("/.newwiki", base), "/pre/.newwiki")
                self.assertEqual(self.rewrite("/.allwiki", base), "/pre/.allwiki")

    def test_Wikiごとの画面は入口(self):
        self.assertEqual(self.rewrite("/.attach/i/a.png", "/pre/=_system"),
                         "/pre/=_system/.attach/i/a.png")

    def test_二度通しても変わらない(self):
        for href in ("/=other/X", "/.newwiki", "/.attach/i/a.png", "/Page"):
            for base in ("/pre", "/pre/=_system"):
                with self.subTest(href=href, base=base):
                    once = rewrite_content_links(f'<a href="{href}">', base, "index")
                    self.assertEqual(rewrite_content_links(once, base, "index"), once)

    def test_接頭辞が無ければ従来どおり(self):
        self.assertEqual(self.rewrite("/=other/X", "/=_system"), "/=other/X")
        self.assertEqual(self.rewrite("/.newwiki", "/=_system"), "/.newwiki")

    def test_プロキシの入口では根が分からないので付けない(self):
        request.bind({"HTTP_X_FORWARDED_PREFIX": "/sandbox"})
        self.assertEqual(self.rewrite("/=other/X", "/sandbox"), "/=other/X")
        self.assertEqual(self.rewrite("/.newwiki", "/sandbox"), "/.newwiki")


if __name__ == "__main__":
    unittest.main()
