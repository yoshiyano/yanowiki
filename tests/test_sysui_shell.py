"""管理ページ共通の外枠（`sysui.page`）。テーマを通さず、テーマを替えても同じ形になる。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_sys"))

from wikilib import sysui  # noqa: E402


def _html(res):
    raw = res.body if hasattr(res, "body") else res
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


class TestShell(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wiki_dir = os.path.join(self.tmp.name, "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, config):
        return sysui.page(self.wiki_dir, config, "testwiki", False, "admin",
                          "管理", "<p>本文</p>", css_url=".admin/x.css", status=201)

    def test_共通の外枠で本文と画面のCSSが入る(self):
        res = self.page({})
        html = _html(res)
        self.assertEqual(res.status_code, 201)
        self.assertIn('class="sys-body"', html)
        self.assertIn('class="sys-head"', html)
        self.assertIn('class="sys-kind">管理<', html)
        self.assertIn("<p>本文</p>", html)
        self.assertIn('href="/=testwiki/.admin/x.css"', html)
        self.assertIn(".sys-main", html)  # shell.css が埋め込まれている

    def test_テーマの設定を替えても外枠は同じ(self):
        # サイト名以外の差は出ない。テーマ名を替えても同じ形になる
        a = _html(self.page({"theme": {"name": "base", "site_title": "S"}}))
        b = _html(self.page({"theme": {"name": "bloom", "site_title": "S"}}))
        self.assertEqual(a, b)
        self.assertNotIn("site-header", a)

    def test_サイト名は設定から出す(self):
        html = _html(self.page({"theme": {"site_title": "うちのWiki"}}))
        self.assertIn(">うちのWiki</a>", html)
        self.assertIn("<title>管理 - うちのWiki</title>", html)


if __name__ == "__main__":
    unittest.main()
