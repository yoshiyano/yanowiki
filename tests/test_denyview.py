#!/usr/bin/env python3
"""`PluginContext.deny_view`（標準の「閲覧する権限がありません」の画面で止める）のテスト。

`#readauth` の権限なしの表示を標準の403の画面にそろえるために作った（Wiki設計者の指示、
2026-09-21）。その後 `#readauth`・`#writeauth` は「権限の記録だけを行う」プラグインに
なり（`config/privileges.plugin`。表示を止める処理は持たない）、`deny_view` を呼ぶ
プラグインは今は無い。本体が `privileges.plugin` を読んで止めるときや、権限を理由に本文を
止めるプラグインを作るときの口として残してある。ここでは口そのものを見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_denyview.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import auth, paths, userdb, views  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402
from wikilib.plugins import PluginContext  # noqa: E402

FARM = "testwiki"


class DenyViewTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="readauth-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.environ.clear()
        shutil.rmtree(self.work, ignore_errors=True)

    def login_as(self, uid):
        bottle.request.environ.clear()
        if uid is None:
            return
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")

    def context(self, page="Members/TA"):
        return PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page=page,
                             base_url="/=testwiki")

    def deny(self, uid, page="Members/TA", by="myplugin"):
        """`deny_view` を1回呼び、止めた内容（`view_block`）を返す。"""
        self.login_as(uid)
        ctx = self.context(page)
        self.assertTrue(ctx.deny_view(by=by))
        return ctx.view_block


class TestDenyView(DenyViewTestBase):

    def test_未ログインは標準の403の画面で止まる(self):
        block = self.deny(None)
        self.assertEqual(block["status"], 403)
        self.assertEqual(block["by"], "myplugin")
        self.assertIn("このページを閲覧する権限がありません", block["message"])
        self.assertIn("/Members/TA", block["message"])

    def test_未ログインにはログインのリンクが付き_戻り先はこのページ(self):
        block = self.deny(None)
        self.assertIn('href="/=testwiki/.login?back=Members/TA"', block["message"])
        self.assertIn("閲覧できるアカウントでログインしてから開いてください", block["message"])

    def test_ログイン中の人にはリンクを出さない(self):
        block = self.deny("bob")
        self.assertEqual(block["status"], 403)
        self.assertNotIn("ログインする", block["message"])
        self.assertIn("ログインし直すか", block["message"])

    def test_標準の画面と同じ本文(self):
        # ページの権限で断られたときの画面（views.no_view_body_html）そのもの
        block = self.deny(None)
        self.assertEqual(block["message"],
                         views.no_view_body_html("/=testwiki", "Members/TA", False))

    def test_先に立てたものが効く(self):
        self.login_as(None)
        ctx = self.context()
        self.assertTrue(ctx.deny_view(by="first"))
        self.assertFalse(ctx.deny_view(by="second"))
        self.assertFalse(ctx.block_view("別の文言", by="third"))
        self.assertEqual(ctx.view_block["by"], "first")

    def test_自分の文言を出したいときはblock_viewのまま(self):
        self.login_as(None)
        ctx = self.context()
        self.assertTrue(ctx.block_view("<p>閲覧期間外です</p>", by="viewable_period"))
        self.assertEqual(ctx.view_block["status"], 200)
        self.assertNotIn("閲覧する権限がありません", ctx.view_block["message"])

    def test_wiki_dirを持たないcontextでも動く(self):
        ctx = PluginContext(config={}, farm=FARM, wiki_dir=None, page="P", base_url="/=testwiki")
        self.assertTrue(ctx.deny_view(by="x"))
        self.assertEqual(ctx.view_block["status"], 403)


if __name__ == "__main__":
    unittest.main()
