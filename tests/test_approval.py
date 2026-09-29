#!/usr/bin/env python3
"""承認制（`account.policy: approval`）のテスト。

「アカウント作成」で申請されたアカウントは**承認待ちで始まり、入れない**。助手か
管理者が承認する（`/.admin/approvals`）まで、権限の上でも**未ログインと同じ**で、
`g:all` にも入らない（Wiki設計者の指示、2026-09-21）。ここでは次を確かめる。

  - アカウントの記録（`approved` の列）と、古いDBを開いたときの移行
  - 「アカウント作成」（`open` はこれまでどおり入れる／`approval` は入れない）
  - 承認待ちはログインできず、cookieを持ち出しても通らない。承認を取り消すと
    持ち出されたcookieもその場で効かなくなる
  - 承認待ちは `g:all` に入らず、権限の判定では未ログインと同じ
  - 承認する画面（管理者と助手だけ。承認・断る。承認待ちだけを扱う）

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_approval.py     （このファイルだけ）
"""
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402
from bottle import HTTPResponse  # noqa: E402

from wikilib import approvalsui, auth, groups, privilege_records, sysui, userdb, wikiconfig  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

FARM = "testwiki"


class ApprovalTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="approval-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "helper"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "pw-" + uid), uid)
        groups.add_members(self.wiki_dir, "staff", ["helper"])
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        bottle.request.bind({})

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def set_policy(self, policy):
        ok, _saved, message = wikiconfig.save_farm_config(
            self.wiki_dir, {"account": {"policy": policy}})
        self.assertTrue(ok, message)

    def form(self, fields, method="POST", query=""):
        body = urlencode(fields).encode("utf-8")
        bottle.request.bind({
            "REQUEST_METHOD": method,
            "QUERY_STRING": query,
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "REMOTE_ADDR": "127.0.0.1",
        })

    def login_cookie(self, uid):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        return (f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")

    def signup(self, uid="newbie", pw="p@ssw0rd"):
        self.form({"cmd": "signup", "uid": uid, "name": "新人", "pw": pw, "pw2": pw, "back": ""})
        return auth.do_signup({}, FARM, self.wiki_dir, False, "/=testwiki/")

    def cookies_in(self, out):
        return [v for k, v in out.headerlist if k == "Set-Cookie"]


class TestUserdb(ApprovalTestBase):
    """アカウントの記録。"""

    def test_既定は承認済み(self):
        self.assertTrue(userdb.is_approved(userdb.find_by_uid(self.wiki_dir, "alice")))
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "alice")["approved"], 1)

    def test_承認待ちで足せる(self):
        userdb.add_user(self.wiki_dir, "waiting", userdb.hash_password(self.wiki_dir, "waiting", "p"), "", approved=False)
        user = userdb.find_by_uid(self.wiki_dir, "waiting")
        self.assertEqual(user["approved"], 0)
        self.assertFalse(userdb.is_approved(user))
        self.assertEqual([u["uid"] for u in userdb.pending_users(self.wiki_dir)], ["waiting"])

    def test_承認と取り消し(self):
        userdb.add_user(self.wiki_dir, "waiting", userdb.hash_password(self.wiki_dir, "waiting", "p"), "", approved=False)
        uidnum = userdb.find_by_uid(self.wiki_dir, "waiting")["uidnum"]
        self.assertTrue(userdb.set_approved(self.wiki_dir, uidnum, True)[0])
        self.assertTrue(userdb.is_approved(userdb.get_user(self.wiki_dir, uidnum)))
        self.assertTrue(userdb.set_approved(self.wiki_dir, uidnum, False)[0])
        self.assertFalse(userdb.is_approved(userdb.get_user(self.wiki_dir, uidnum)))

    def test_管理者の承認は取り消せない(self):
        ok, _message = userdb.set_approved(self.wiki_dir, userdb.ADMIN_UIDNUM, False)
        self.assertFalse(ok)
        self.assertTrue(userdb.is_approved(userdb.get_user(self.wiki_dir, userdb.ADMIN_UIDNUM)))

    def test_知らない番号は断る(self):
        self.assertFalse(userdb.set_approved(self.wiki_dir, 9999, True)[0])

    def test_列を持たない辞書は承認済みとして扱う(self):
        self.assertTrue(userdb.is_approved({"uid": "x"}))
        self.assertFalse(userdb.is_approved(None))

    def test_古いDBを開くと列が足され_既存のアカウントは承認済み(self):
        old = os.path.join(self.work, "wikidata", "oldwiki", "wiki")
        os.makedirs(old)
        os.makedirs(os.path.join(os.path.dirname(old), "config"))
        con = sqlite3.connect(userdb.db_path(old))
        con.executescript("""
            CREATE TABLE passwd (uidnum INTEGER PRIMARY KEY, uid TEXT NOT NULL,
                                 pw TEXT NOT NULL, name TEXT NOT NULL DEFAULT '');
            CREATE UNIQUE INDEX passwd_uid ON passwd(uid);
            INSERT INTO passwd VALUES (1, 'admin', 'x', '管理者'), (2, 'bob', 'y', 'ボブ');
        """)
        con.commit()
        con.close()
        users = userdb.all_users(old)
        self.assertEqual([(u["uid"], u["approved"]) for u in users], [("admin", 1), ("bob", 1)])
        # 移行のあとで、承認待ちの新規も足せる
        ok, _message = userdb.add_user(old, "carol", "z", "", approved=False)
        self.assertTrue(ok)
        self.assertEqual([u["uid"] for u in userdb.pending_users(old)], ["carol"])


class TestSignup(ApprovalTestBase):
    """「アカウント作成」。"""

    def test_openならそのまま入る(self):
        out = self.signup()
        self.assertIn("?login=made", out.headers["Location"])
        self.assertEqual(len(self.cookies_in(out)), 2)
        self.assertTrue(userdb.is_approved(userdb.find_by_uid(self.wiki_dir, "newbie")))

    def test_approvalなら承認待ちで始まり入れない(self):
        self.set_policy("approval")
        out = self.signup()
        self.assertEqual(out.status_code, 303)
        self.assertIn("?login=applied", out.headers["Location"])
        self.assertEqual(self.cookies_in(out), [])        # cookieを置かない
        user = userdb.find_by_uid(self.wiki_dir, "newbie")
        self.assertIsNotNone(user)
        self.assertFalse(userdb.is_approved(user))

    def test_approvalでもパスワード不一致はng(self):
        self.set_policy("approval")
        self.form({"cmd": "signup", "uid": "x1", "pw": "a", "pw2": "b", "back": ""})
        out = auth.do_signup({}, FARM, self.wiki_dir, False, "/=testwiki/")
        self.assertIn("?login=ng", out.headers["Location"])
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "x1"))

    def test_管理者が作るアカウントは承認済み(self):
        self.set_policy("approval")
        userdb.add_user(self.wiki_dir, "byadmin", userdb.hash_password(self.wiki_dir, "byadmin", "p"), "")
        self.assertTrue(userdb.is_approved(userdb.find_by_uid(self.wiki_dir, "byadmin")))


class TestLogin(ApprovalTestBase):
    """承認待ちはログインできない。"""

    def setUp(self):
        super().setUp()
        self.set_policy("approval")
        self.signup()

    def login(self, uid, pw):
        self.form({"uid": uid, "pw": pw, "back": ""})
        return auth.do_login({}, FARM, self.wiki_dir, False, "/=testwiki/")

    def test_パスワードが合っていても入れない(self):
        out = self.login("newbie", "p@ssw0rd")
        self.assertIn("?login=pending", out.headers["Location"])
        self.assertEqual(self.cookies_in(out), [])

    def test_承認すると入れる(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "newbie")["uidnum"]
        userdb.set_approved(self.wiki_dir, uidnum, True)
        out = self.login("newbie", "p@ssw0rd")
        self.assertIn("?login=done", out.headers["Location"])
        self.assertEqual(len(self.cookies_in(out)), 2)

    def test_承認済みのアカウントは影響を受けない(self):
        out = self.login("alice", "pw-alice")
        self.assertIn("?login=done", out.headers["Location"])

    def test_パスワードが違えばngのまま(self):
        # 承認待ちかどうかを、パスワードの合わない相手に教えない
        out = self.login("newbie", "ちがう")
        self.assertIn("?login=ng", out.headers["Location"])

    def test_持ち出したcookieでも入れない_取り消すとその場で効かなくなる(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "newbie")["uidnum"]
        userdb.set_approved(self.wiki_dir, uidnum, True)
        cookie = self.login_cookie("newbie")
        bottle.request.bind({"HTTP_COOKIE": cookie})
        self.assertIsNotNone(auth.current_user(self.wiki_dir, FARM))
        userdb.set_approved(self.wiki_dir, uidnum, False)
        bottle.request.bind({"HTTP_COOKIE": cookie})
        self.assertIsNone(auth.current_user(self.wiki_dir, FARM))

    def test_承認待ちのcookieは最初から通らない(self):
        bottle.request.bind({"HTTP_COOKIE": self.login_cookie("newbie")})
        self.assertIsNone(auth.current_user(self.wiki_dir, FARM))


class TestPrivilege(ApprovalTestBase):
    """権限の上では未ログインと同じで、`g:all` に入らない。"""

    def setUp(self):
        super().setUp()
        userdb.add_user(self.wiki_dir, "waiting", userdb.hash_password(self.wiki_dir, "waiting", "p"), "", approved=False)
        for kind, who in (("R", "g:any"), ("W", "g:all")):
            ok, message, _ = privilege_records.put(self.wiki_dir, "*", kind, who)
            self.assertTrue(ok, message)

    def check(self, uid):
        return auth.page_privilege(self.wiki_dir, uid).check("Tech/A")

    def test_承認待ちは編集できない_承認済みはできる(self):
        self.assertEqual(self.check("alice"), "W")
        self.assertEqual(self.check("waiting"), "R")       # 未ログインと同じ
        self.assertEqual(self.check(None), "R")

    def test_承認すると編集できる(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "waiting")["uidnum"]
        userdb.set_approved(self.wiki_dir, uidnum, True)
        self.assertEqual(self.check("waiting"), "W")

    def test_g_allの展開に承認待ちは入らない(self):
        waiting = userdb.find_by_uid(self.wiki_dir, "waiting")["uidnum"]
        alice = userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"]
        got = auth.expand_principal(self.wiki_dir, "g:all")
        self.assertIn(alice, got)
        self.assertNotIn(waiting, got)

    def test_閲覧にもログインが要る形でも承認待ちは読めない(self):
        privilege_records.put(self.wiki_dir, "*", "R", "g:all")
        self.assertEqual(self.check("waiting"), "-")
        self.assertEqual(self.check("alice"), "W")


class TestApprovalsScreen(ApprovalTestBase):
    """承認する画面（`/.admin/approvals`）。"""

    def setUp(self):
        super().setUp()
        self.set_policy("approval")
        self.signup("newbie")
        self.signup("second")
        self.uidnum = userdb.find_by_uid(self.wiki_dir, "newbie")["uidnum"]

    def call(self, uid, method="GET", fields=None, query=""):
        env = {"REQUEST_METHOD": method, "QUERY_STRING": query, "REMOTE_ADDR": "127.0.0.1"}
        if method == "POST":
            body = urlencode(fields or {}).encode("utf-8")
            env.update({"CONTENT_TYPE": "application/x-www-form-urlencoded",
                        "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)})
        if uid is not None:
            env["HTTP_COOKIE"] = self.login_cookie(uid)
        bottle.request.bind(env)
        with mock.patch.object(sysui, "page",
                               side_effect=lambda *a, **k: HTTPResponse(body=a[6], status=k.get("status", 200))), \
                mock.patch.object(approvalsui, "make_plugin_context",
                                  return_value=mock.Mock(base_url="/=testwiki")):
            return approvalsui.render_approvals(self.wiki_dir, {}, FARM, False)

    def test_未ログインと一般のアカウントは断る(self):
        for uid in (None, "alice"):
            res = self.call(uid)
            self.assertEqual(res.status_code, 403, uid)

    def test_一般のアカウントは承認できない(self):
        res = self.call("alice", "POST", {"op": "approve", "uidnum": self.uidnum})
        self.assertEqual(res.status_code, 403)
        self.assertFalse(userdb.is_approved(userdb.get_user(self.wiki_dir, self.uidnum)))

    def test_助手と管理者は承認待ちの一覧を見られる(self):
        for uid in ("helper", "admin"):
            res = self.call(uid)
            self.assertEqual(res.status_code, 200, uid)
            body = res.body if isinstance(res.body, str) else res.body.decode()
            self.assertIn("newbie", body)
            self.assertIn("second", body)
            self.assertNotIn(">alice<", body)             # 承認済みは並べない

    def test_承認する(self):
        res = self.call("helper", "POST", {"op": "approve", "uidnum": self.uidnum})
        self.assertEqual(res.status_code, 303)
        self.assertIn("done=approved", res.headers["Location"])
        self.assertIn("uid=newbie", res.headers["Location"])
        self.assertTrue(userdb.is_approved(userdb.get_user(self.wiki_dir, self.uidnum)))

    def test_断ると消える_申請し直せる(self):
        res = self.call("admin", "POST", {"op": "reject", "uidnum": self.uidnum})
        self.assertIn("done=rejected", res.headers["Location"])
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "newbie"))
        out = self.signup("newbie")
        self.assertIn("?login=applied", out.headers["Location"])

    def test_承認済みのアカウントは断る操作で消せない(self):
        alice = userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"]
        res = self.call("helper", "POST", {"op": "reject", "uidnum": alice})
        self.assertIn("done=gone", res.headers["Location"])
        self.assertIsNotNone(userdb.find_by_uid(self.wiki_dir, "alice"))

    def test_管理者は断る操作で消せない(self):
        res = self.call("helper", "POST", {"op": "reject", "uidnum": userdb.ADMIN_UIDNUM})
        self.assertIn("done=gone", res.headers["Location"])
        self.assertIsNotNone(userdb.find_by_uid(self.wiki_dir, "admin"))

    def test_おかしな入力はngで何も変えない(self):
        for fields in ({"op": "approve", "uidnum": "x"}, {"op": "drop", "uidnum": self.uidnum},
                       {"uidnum": self.uidnum}):
            res = self.call("helper", "POST", fields)
            self.assertIn("done=ng", res.headers["Location"], fields)
        self.assertEqual(len(userdb.pending_users(self.wiki_dir)), 2)

    def test_転送されてきた結果の知らせが出る(self):
        res = self.call("helper", query="done=approved&uid=newbie")
        body = res.body if isinstance(res.body, str) else res.body.decode()
        self.assertIn("newbie", body)
        self.assertIn("承認しました", body)

    def test_承認制でないWikiにはその旨を添える(self):
        self.set_policy("open")
        res = self.call("helper")
        body = res.body if isinstance(res.body, str) else res.body.decode()
        self.assertIn("承認制ではありません", body)


if __name__ == "__main__":
    unittest.main()
