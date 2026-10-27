#!/usr/bin/env python3
"""別のサイトから送られた POST を断る仕組み（`wikilib.web.cross_site_reason`）のテスト。

書き換えの POST は、`Origin`（無ければ `Referer`）の宛先が、この要求の宛先（`Host`・
`X-Forwarded-Host`）と同じときだけ受ける（設計者の決定、2026-10-23）。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_crosssite.py     （このファイルだけ）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib.web import cross_site_reason, reject_cross_site  # noqa: E402


class TestCrossSite(unittest.TestCase):

    def tearDown(self):
        bottle.request.environ.clear()

    def reason(self, host="wiki.example:8619", **headers):
        env = bottle.request.environ
        env.clear()
        env["REQUEST_METHOD"] = "POST"
        if host is not None:
            env["HTTP_HOST"] = host
        env.update({"HTTP_" + k.upper(): v for k, v in headers.items()})
        return cross_site_reason()

    def test_同じサイトのOriginは通す(self):
        self.assertIsNone(self.reason(origin="http://wiki.example:8619"))

    def test_大文字小文字は問わない(self):
        self.assertIsNone(self.reason(origin="http://WIKI.example:8619"))

    def test_別のサイトのOriginは断る(self):
        self.assertIsNotNone(self.reason(origin="http://evil.example"))

    def test_ポート番号が違えば断る(self):
        self.assertIsNotNone(self.reason(origin="http://wiki.example:9000"))

    def test_隣のサブドメインも断る(self):
        # SameSite=Lax では同じサイトとして cookie が付くが、Origin は違う
        self.assertIsNotNone(self.reason(host="wiki.example.com",
                                         origin="https://other.example.com"))

    def test_既定のポート番号は省いて比べる(self):
        self.assertIsNone(self.reason(host="wiki.example:443", origin="https://wiki.example"))
        self.assertIsNone(self.reason(host="wiki.example", origin="http://wiki.example:80"))

    def test_スキームは見ない(self):
        # TLS を終えるプロキシの後ろでは、ブラウザは https、サーバは http で受ける
        self.assertIsNone(self.reason(host="wiki.example", origin="https://wiki.example"))

    def test_X_Forwarded_Hostと同じなら通す(self):
        self.assertIsNone(self.reason(host="127.0.0.1:8619", origin="https://wiki.example",
                                      x_forwarded_host="wiki.example"))

    def test_Originが無ければRefererで見る(self):
        self.assertIsNone(self.reason(referer="http://wiki.example:8619/=sandbox/A"))
        self.assertIsNotNone(self.reason(referer="http://evil.example/form.html"))

    def test_Originを優先する(self):
        self.assertIsNotNone(self.reason(origin="http://evil.example",
                                         referer="http://wiki.example:8619/A"))

    def test_どちらも無ければ通す(self):
        # ブラウザ以外（curl・スクリプト）。CSRF はブラウザに送らせる攻撃
        self.assertIsNone(self.reason())

    def test_Origin_nullは断る(self):
        self.assertIsNotNone(self.reason(origin="null"))

    def test_宛先が分からなければ断る(self):
        self.assertIsNotNone(self.reason(host=None, origin="http://wiki.example"))

    def test_断る画面は403(self):
        self.assertEqual(reject_cross_site().status_code, 403)


class TestDispatch(unittest.TestCase):
    """入口（`wiki.py` の `dispatch`）が、どの画面へ渡すより先に断ること。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wiki.py")
        spec = importlib.util.spec_from_file_location("wiki_main", path)
        cls.wiki = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.wiki)

    def tearDown(self):
        bottle.request.environ.clear()

    def test_別のサイトからのPOSTは画面へ渡さない(self):
        env = bottle.request.environ
        env.clear()
        env.update({"REQUEST_METHOD": "POST", "PATH_INFO": "/", "HTTP_HOST": "wiki.example",
                    "HTTP_ORIGIN": "http://evil.example"})
        from unittest import mock
        with mock.patch.object(self.wiki, "load_config") as load:
            res = self.wiki.dispatch("")
        self.assertEqual(res.status_code, 403)
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
