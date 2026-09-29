#!/usr/bin/env python3
"""`#login` プラグインの「承認待ち x人」（赤字）と、承認制の結果の文言のテスト。

承認できる人（管理者と助手）が開いたとき、ログイン中のユーザーのすぐ下に、
承認待ちがあれば赤字で「承認待ち x人」を出す（Wiki設計者の指示、2026-09-21）。
一般のアカウントには出さない。承認待ちが0人なら出さない。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_loginpending.py     （このファイルだけ）
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import groups, userdb  # noqa: E402


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "login_plugin_under_test", os.path.join(ROOT, "plugin", "login.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PendingTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="loginpending-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "helper"):
            userdb.add_user(self.wiki_dir, uid,
                            userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        groups.add_members(self.wiki_dir, "staff", ["helper"])
        self.plugin = load_plugin()
        self.context = mock.Mock(wiki_dir=self.wiki_dir, base_url="/=testwiki")
        bottle.request.bind({})

    def tearDown(self):
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def wait(self, uid):
        userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"),
                        "", approved=False)

    def panel(self, uid):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        return self.plugin._account_panel_html(self.context, user, "")


class TestPendingCount(PendingTestBase):

    def test_管理者と助手には赤字で人数が出る(self):
        self.wait("w1")
        self.wait("w2")
        for uid in ("admin", "helper"):
            html = self.panel(uid)
            self.assertIn("承認待ち 2人", html, uid)
            self.assertIn('class="login-pending"', html, uid)

    def test_承認する画面へのリンクになる(self):
        self.wait("w1")
        self.assertIn('href="/=testwiki/.admin/approvals"', self.panel("admin"))

    def test_ログイン中のユーザーのすぐ下に出る(self):
        self.wait("w1")
        html = self.panel("admin")
        self.assertLess(html.index("現在ログイン中のユーザー"), html.index("承認待ち 1人"))
        self.assertLess(html.index("承認待ち 1人"), html.index('class="login-hint"'))

    def test_一般のアカウントには出さない(self):
        self.wait("w1")
        html = self.panel("alice")
        self.assertNotIn("承認待ち", html)
        self.assertNotIn("login-pending", html)

    def test_承認待ちが無ければ出さない(self):
        for uid in ("admin", "helper", "alice"):
            self.assertNotIn("承認待ち", self.panel(uid), uid)

    def test_承認すると減り_無くなると消える(self):
        self.wait("w1")
        self.wait("w2")
        userdb.set_approved(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "w1")["uidnum"], True)
        self.assertIn("承認待ち 1人", self.panel("admin"))
        userdb.set_approved(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "w2")["uidnum"], True)
        self.assertNotIn("承認待ち", self.panel("admin"))

    def test_赤字のCSSがある(self):
        with open(os.path.join(ROOT, "plugin", "login.css"), encoding="utf-8") as f:
            css = f.read()
        block = css[css.index(".login-pending a"):]
        self.assertIn("color: #d1242f", block[:block.index("}")])


class TestResultNotice(PendingTestBase):
    """承認制の結果（`?login=applied|pending`）の文言。"""

    def notice(self, result):
        bottle.request.bind({"QUERY_STRING": f"login={result}"})
        return self.plugin._result_notice()

    def test_申請した(self):
        text = self.notice("applied")
        self.assertIn("申請しました", text)
        self.assertNotIn("login-notice-error", text)

    def test_承認待ちでログインできない(self):
        text = self.notice("pending")
        self.assertIn("承認待ち", text)
        self.assertIn("login-notice-error", text)


if __name__ == "__main__":
    unittest.main()
