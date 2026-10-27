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
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_approval.py     （このファイルだけ）
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

from wikilib import approvalsui, auth, groups, pagenotice, privilege_records, sysui, userdb, wikiconfig  # noqa: E402
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
        # 同じIPからの申請の数は、試験ごとに別の記録で数える
        self.kept_signup_log = auth.SIGNUP_LOG
        auth.SIGNUP_LOG = os.path.join(self.work, "signup.json")
        bottle.request.bind({})

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        auth.SIGNUP_LOG = self.kept_signup_log
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

    def signup(self, uid="newbie", pw="p@ssw0rd", ip="127.0.0.1", name="新人"):
        self.form({"cmd": "signup", "uid": uid, "name": name, "pw": pw, "pw2": pw, "back": ""})
        bottle.request.environ["REMOTE_ADDR"] = ip
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


class TestSignupLimits(ApprovalTestBase):
    """申請の受付の限り（同じIPからの回数・承認待ちの上限・期限・表示名の長さ）。"""

    DAY = 24 * 60 * 60

    def setUp(self):
        super().setUp()
        self.set_policy("approval")

    def result(self, out):
        return out.headers["Location"].rsplit("login=", 1)[1]

    def test_同じIPからは1時間に3件まで(self):
        for n in range(3):
            self.assertEqual(self.result(self.signup("u%d" % n)), "applied")
        self.assertEqual(self.result(self.signup("u3")), "busy")
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "u3"))
        # 別のIPからは受け付ける
        self.assertEqual(self.result(self.signup("u4", ip="10.0.0.2")), "applied")

    def test_X_Forwarded_For_があればその先頭で数える(self):
        for n in range(3):
            self.signup("u%d" % n)
        self.form({"cmd": "signup", "uid": "u9", "name": "", "pw": "p", "pw2": "p", "back": ""})
        bottle.request.environ["HTTP_X_FORWARDED_FOR"] = "10.9.9.9, 127.0.0.1"
        out = auth.do_signup({}, FARM, self.wiki_dir, False, "/=testwiki/")
        self.assertEqual(self.result(out), "applied")

    def test_受け付けなかった申請は数えない(self):
        for n in range(3):
            self.form({"cmd": "signup", "uid": "x%d" % n, "pw": "a", "pw2": "b", "back": ""})
            auth.do_signup({}, FARM, self.wiki_dir, False, "/=testwiki/")
        self.assertEqual(self.result(self.signup("ok1")), "applied")

    def test_openのWikiでは回数を数えない(self):
        self.set_policy("open")
        for n in range(5):
            self.assertEqual(self.result(self.signup("o%d" % n)), "made")

    def test_承認待ちが20件あれば受け付けない(self):
        for n in range(userdb.PENDING_MAX):
            ok, message = userdb.add_user(self.wiki_dir, "p%d" % n,
                                          userdb.hash_password(self.wiki_dir, "p%d" % n, "x"), "",
                                          approved=False)
            self.assertTrue(ok, message)
        self.assertFalse(userdb.signup_open(self.wiki_dir))
        self.assertEqual(self.result(self.signup("late")), "closed")
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "late"))
        # 1件断れば、受付を再開する
        userdb.delete_user(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "p0")["uidnum"])
        self.assertEqual(self.result(self.signup("late")), "applied")

    def test_承認を取り消したアカウントは上限に数えない(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"]
        userdb.set_approved(self.wiki_dir, uidnum, False)
        self.assertEqual(userdb.pending_applications(self.wiki_dir), 0)
        # 期限でも消さない（申請ではない）
        userdb.expire_pending(self.wiki_dir, now=9999999999)
        self.assertIsNotNone(userdb.find_by_uid(self.wiki_dir, "alice"))

    def test_3日たっても承認されなければ消える(self):
        self.signup("slow")
        applied = userdb.find_by_uid(self.wiki_dir, "slow")["applied_at"]
        self.assertGreater(applied, 0)
        self.assertEqual(len(userdb.pending_users(self.wiki_dir, now=applied + 3 * self.DAY - 1)), 1)
        self.assertEqual(userdb.pending_users(self.wiki_dir, now=applied + 3 * self.DAY), [])
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "slow"))
        # ID は空く
        self.assertEqual(self.result(self.signup("slow", ip="10.0.0.3")), "applied")

    def test_承認したアカウントは期限で消えない(self):
        self.signup("good")
        user = userdb.find_by_uid(self.wiki_dir, "good")
        userdb.set_approved(self.wiki_dir, user["uidnum"], True)
        userdb.expire_pending(self.wiki_dir, now=user["applied_at"] + 30 * self.DAY)
        self.assertIsNotNone(userdb.find_by_uid(self.wiki_dir, "good"))

    def test_期限切れの申請でログインすると_承認待ちではなくng(self):
        self.signup("slow")
        user = userdb.find_by_uid(self.wiki_dir, "slow")
        with sqlite3.connect(userdb.db_path(self.wiki_dir)) as con:
            con.execute("UPDATE passwd SET applied_at = ? WHERE uidnum = ?",
                        (user["applied_at"] - 3 * self.DAY, user["uidnum"]))
        self.form({"uid": "slow", "pw": "p@ssw0rd"})
        found, locked, _left = auth.try_password(self.wiki_dir, "slow", "slow", "p@ssw0rd")
        self.assertIsNone(found)
        self.assertFalse(locked)
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "slow"))

    def test_助手の承認を元に戻すと_期限は数え直す(self):
        self.signup("back")
        user = userdb.find_by_uid(self.wiki_dir, "back")
        with sqlite3.connect(userdb.db_path(self.wiki_dir)) as con:
            con.execute("UPDATE passwd SET approved = 1, applied_at = 1 WHERE uidnum = ?",
                        (user["uidnum"],))
        userdb.set_approved(self.wiki_dir, user["uidnum"], False, renew=True)
        self.assertGreater(userdb.find_by_uid(self.wiki_dir, "back")["applied_at"], 1)

    def test_列の無い古いDBの承認待ちは_いまから数える(self):
        with sqlite3.connect(userdb.db_path(self.wiki_dir)) as con:
            con.execute("CREATE TABLE p2 AS SELECT uidnum, uid, pw, name, approved, cnt FROM passwd")
            con.execute("DROP TABLE passwd")
            con.execute("ALTER TABLE p2 RENAME TO passwd")
            con.execute("UPDATE passwd SET approved = 0 WHERE uid = 'alice'")
        alice = userdb.find_by_uid(self.wiki_dir, "alice")
        self.assertGreater(alice["applied_at"], 0)
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "helper")["applied_at"], 0)

    def test_表示名は32文字まで(self):
        self.assertEqual(self.result(self.signup("n1", name="あ" * 33)), "ng")
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "n1"))
        self.assertEqual(self.result(self.signup("n2", name="あ" * 32)), "applied")
        ok, message = userdb.add_user(self.wiki_dir, "n3", userdb.hash_password(self.wiki_dir, "n3", "p"),
                                      "x" * 33)
        self.assertFalse(ok)
        self.assertIn("32文字まで", message)
        alice = userdb.find_by_uid(self.wiki_dir, "alice")
        ok, _m = userdb.update_user(self.wiki_dir, alice["uidnum"], "alice", "", "x" * 33)
        self.assertFalse(ok)
        ok, _m = userdb.update_user(self.wiki_dir, alice["uidnum"], "alice", "", "x" * 32)
        self.assertTrue(ok)


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

    def test_受付を止めているときは_そう案内する(self):
        body = lambda res: res.body if isinstance(res.body, str) else res.body.decode()  # noqa: E731
        self.assertNotIn("受付を止めています", body(self.call("admin")))
        for n in range(userdb.PENDING_MAX):
            userdb.add_user(self.wiki_dir, "p%d" % n,
                            userdb.hash_password(self.wiki_dir, "p%d" % n, "x"), "", approved=False)
        self.assertIn("受付を止めています", body(self.call("admin")))

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


class TestSignupNotice(ApprovalTestBase):
    """申請の受付を止めているあいだ、承認できる人の info に知らせを出す（`pagenotice.signup_notice`）。"""

    def setUp(self):
        super().setUp()
        self.set_policy("approval")

    def fill(self):
        for n in range(userdb.PENDING_MAX):
            userdb.add_user(self.wiki_dir, "p%d" % n,
                            userdb.hash_password(self.wiki_dir, "p%d" % n, "x"), "", approved=False)

    def info(self, uid, subpath="FrontPage"):
        bottle.request.bind({"HTTP_COOKIE": self.login_cookie(uid)} if uid else {})
        return pagenotice.page_info_for({}, FARM, "/=testwiki", self.wiki_dir, subpath)

    def test_受け付けているあいだは出さない(self):
        self.assertEqual(self.info("admin"), "")

    def test_止めているときは_管理者と助手にだけ出す(self):
        self.fill()
        for uid in ("admin", "helper"):
            html = self.info(uid)
            self.assertIn("申請の受付を止めています", html, uid)
            self.assertIn('href="/=testwiki/.admin/approvals"', html, uid)
        for uid in (None, "alice"):
            self.assertEqual(self.info(uid), "", uid)

    def test_openのWikiでは出さない(self):
        self.fill()
        self.set_policy("open")
        self.assertEqual(self.info("admin"), "")

    def test_ページに付かない場面でも出す(self):
        self.fill()
        self.assertIn("申請の受付を止めています", self.info("admin", subpath=None))

    def test_重複の知らせと並べて出す(self):
        self.fill()
        for ext in (".txt", ".md"):
            with open(os.path.join(self.wiki_dir, "FrontPage" + ext), "w", encoding="utf-8") as f:
                f.write("x\n")
        html = self.info("admin")
        self.assertEqual(html.count("<a "), 2)
        self.assertLess(html.index("同じ名前のファイル"), html.index("申請の受付を止めています"))
        self.assertEqual(self.info(None).count("<a "), 1)


if __name__ == "__main__":
    unittest.main()
