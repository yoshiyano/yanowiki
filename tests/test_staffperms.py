#!/usr/bin/env python3
"""助手に与える権限（`wikilib.staffperms`・`wikilib.staffpermsui`）のテスト。

管理者は `/.admin/staffperms` で、助手ごと・操作ごとに権限を与える・外せる。**何も設定
していないときの動きは、この仕組みを入れる前と同じ**（既定＝それまでの状態）。ここで
確かめるのは次。

  - 権限の定義（既定がそれまでの状態か、前提の並び）と、設定の読み書き
  - 各画面の関門が、助手に与えた権限で開く・閉じる（アカウント・承認・グループ・設定・
    アクセス制限・記録・中断した操作・テーマ・既定のWiki専用の画面）
  - **管理者のアカウントを助手に触らせない**・**権限の設定画面は管理者だけ**
  - 設定の画面（表の出しかた・保存・触れない助手・前提の揃え）

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_staffperms.py     （このファイルだけ）
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import (  # noqa: E402
    accounts, adminui, approvalsui, auth, configui, groups, operationsui, privilegesui,
    staffperms, staffpermsui, stafflog, stafflogui, sysui, themefilesui, userdb,
)
from wikilib.paths import (  # noqa: E402
    ACCOUNTS_URLPATH, ADMIN_URLPATH, APPROVALS_URLPATH, LOGIN_AUTH_COOKIE, LOGIN_COOKIE,
    NEWWIKI_URLPATH, STAFFPERMS_URLPATH, wiki_cookie_name,
)

FARM = "testwiki"

# この仕組みを入れる前に、助手が使えなかった操作（管理者だけだったもの）
ADMIN_ONLY_BEFORE = {
    "accounts.view", "accounts.add", "accounts.rename", "accounts.password", "accounts.delete",
    "stafflog.view", "stafflog.undo", "themes.site.view", "themes.site.edit",
}


class Base(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="staffperms-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("kyun", "sub", "hito"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["kyun", "sub"])
        self.kyun = userdb.find_by_uid(self.wiki_dir, "kyun")["uidnum"]
        self.sub = userdb.find_by_uid(self.wiki_dir, "sub")["uidnum"]
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        bottle.request.bind({})

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    # ---- 呼びかた ----

    def cookie(self, uid):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        return (f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")

    def bind(self, uid, method="GET", body=b"", ctype="", query=""):
        env = {"REQUEST_METHOD": method, "QUERY_STRING": query, "REMOTE_ADDR": "127.0.0.1",
               "CONTENT_TYPE": ctype, "CONTENT_LENGTH": str(len(body)),
               "wsgi.input": io.BytesIO(body)}
        if uid:
            env["HTTP_COOKIE"] = self.cookie(uid)
        bottle.request.environ.clear()
        bottle.request.bind(env)

    def as_user(self, uid):
        """GETの要求として uid でログインした状態にする（None なら未ログイン）。"""
        self.bind(uid)

    def post_json(self, uid, payload):
        self.bind(uid, "POST", json.dumps(payload).encode("utf-8"), "application/json")

    def post_form(self, uid, fields, query=""):
        self.bind(uid, "POST", urlencode(fields, doseq=True).encode("utf-8"),
                  "application/x-www-form-urlencoded", query)

    @staticmethod
    def body_of(out):
        raw = out.body if hasattr(out, "body") else out
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def json_of(self, out):
        return json.loads(self.body_of(out))

    def grant(self, uidnum, *keys, revoke=()):
        """既定の状態から、`keys` を足し `revoke` を外した設定にする。"""
        want = set(staffperms.default_set()) | set(keys)
        want -= set(revoke)
        staffperms.save(self.wiki_dir, {uidnum: want})


class TestCatalog(unittest.TestCase):

    def test_既定は入れる前の状態(self):
        # 管理者だけだったものだけが既定で外れ、助手が使えていたものはすべて既定で許す
        off = {p.key for p in staffperms.PERMS if not p.default}
        self.assertEqual(off, ADMIN_ONLY_BEFORE)
        self.assertEqual(staffperms.default_set(), {p.key for p in staffperms.PERMS if p.default})

    def test_名前は重ならず_前提は先に並ぶ(self):
        keys = [p.key for p in staffperms.PERMS]
        self.assertEqual(len(keys), len(set(keys)))
        for i, perm in enumerate(staffperms.PERMS):
            for need in perm.needs:
                self.assertIn(need, keys[:i], perm.key)

    def test_前提が外れていれば従属も効かない(self):
        held = staffperms.resolve({"config.view": False})
        self.assertNotIn("config.view", held)
        self.assertNotIn("config.edit", held)      # 既定は許すが、前提が無い
        self.assertIn("privileges.edit", held)     # 別の画面は影響を受けない

    def test_従属だけ許しても前提が無ければ効かない(self):
        held = staffperms.resolve({"accounts.add": True})
        self.assertNotIn("accounts.add", held)
        held = staffperms.resolve({"accounts.add": True, "accounts.view": True})
        self.assertIn("accounts.add", held)

    def test_前提は深くたどる(self):
        held = staffperms.resolve({"themes.site.edit": True, "themes.view": False})
        self.assertNotIn("themes.site.edit", held)
        held = staffperms.resolve({"themes.site.edit": True})   # site.view が無い
        self.assertNotIn("themes.site.edit", held)

    def test_知らない名前は書き間違いとして知らせる(self):
        with self.assertRaises(KeyError):
            staffperms.check_keys(("accounts.veiw",))


class TestStore(Base):

    def test_管理者は全部持つ(self):
        admin = userdb.find_by_uid(self.wiki_dir, "admin")
        self.assertEqual(staffperms.granted_set(self.wiki_dir, admin), staffperms.ALL_KEYS)

    def test_助手は何も設定しなければ既定(self):
        user = userdb.find_by_uid(self.wiki_dir, "kyun")
        self.assertEqual(staffperms.granted_set(self.wiki_dir, user), staffperms.default_set())

    def test_助手でない人と未ログインは何も持たない(self):
        self.assertEqual(staffperms.granted_set(
            self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "hito")), frozenset())
        self.assertEqual(staffperms.granted_set(self.wiki_dir, None), frozenset())

    def test_与える_外すは人ごと(self):
        self.grant(self.kyun, "accounts.view", revoke=("config.edit",))
        kyun = staffperms.granted_set(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "kyun"))
        sub = staffperms.granted_set(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "sub"))
        self.assertIn("accounts.view", kyun)
        self.assertNotIn("config.edit", kyun)
        self.assertEqual(sub, staffperms.default_set())

    def test_既定と同じにすれば行は消える(self):
        self.grant(self.kyun, "accounts.view")
        self.assertEqual(staffperms.overrides(self.wiki_dir, self.kyun), {"accounts.view": True})
        staffperms.save(self.wiki_dir, {self.kyun: set(staffperms.default_set())})
        self.assertEqual(staffperms.overrides(self.wiki_dir, self.kyun), {})

    def test_前提を外して保存すると従属も外れる(self):
        changes = staffperms.save(self.wiki_dir, {
            self.kyun: set(staffperms.default_set()) - {"config.view"}})
        added, removed = changes[0][1], changes[0][2]
        self.assertEqual(added, [])
        self.assertEqual(set(removed), {"config.view", "config.edit", "config.extrarules",
                                        "config.rename"})

    def test_変わらなければ変更として返さない(self):
        self.assertEqual(staffperms.save(self.wiki_dir, {
            self.kyun: set(staffperms.default_set())}), [])

    def test_含めなかった助手には触れない(self):
        self.grant(self.sub, "accounts.view")
        staffperms.save(self.wiki_dir, {self.kyun: set()})
        self.assertIn("accounts.view", staffperms.granted_set(
            self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "sub")))

    def test_助手でない番号と管理者は無視する(self):
        hito = userdb.find_by_uid(self.wiki_dir, "hito")["uidnum"]
        self.assertEqual(staffperms.save(self.wiki_dir, {
            hito: set(staffperms.ALL_KEYS), userdb.ADMIN_UIDNUM: set()}), [])
        self.assertEqual(staffperms.overrides(self.wiki_dir, hito), {})
        self.assertEqual(staffperms.overrides(self.wiki_dir, userdb.ADMIN_UIDNUM), {})

    def test_助手を外すと何も持たない_戻すと設定が残っている(self):
        self.grant(self.kyun, "accounts.view")
        groups.remove_members(self.wiki_dir, groups.STAFF_GROUP, [self.kyun])
        user = userdb.find_by_uid(self.wiki_dir, "kyun")
        self.assertEqual(staffperms.granted_set(self.wiki_dir, user), frozenset())
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["kyun"])
        self.assertIn("accounts.view", staffperms.granted_set(self.wiki_dir, user))

    def test_アカウントを消すと設定も消える(self):
        self.grant(self.kyun, "accounts.view")
        userdb.delete_user(self.wiki_dir, self.kyun)
        self.assertEqual(staffperms.overrides(self.wiki_dir, self.kyun), {})

    def test_知らない名前の行は無視する(self):
        import sqlite3
        with sqlite3.connect(userdb.db_path(self.wiki_dir)) as con:
            con.execute("INSERT INTO staff_perms VALUES (?, 'no.such', 1)", (self.kyun,))
        self.assertEqual(staffperms.overrides(self.wiki_dir, self.kyun), {})
        self.assertEqual(staffperms.granted_set(
            self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "kyun")), staffperms.default_set())

    def test_矛盾した行は効かない側に倒れる(self):
        import sqlite3
        with sqlite3.connect(userdb.db_path(self.wiki_dir)) as con:
            con.execute("INSERT INTO staff_perms VALUES (?, 'accounts.delete', 1)", (self.kyun,))
        held = staffperms.granted_set(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "kyun"))
        self.assertNotIn("accounts.delete", held)    # accounts.view が無い

    def test_古いDBにも表が増える(self):
        import sqlite3
        path = userdb.db_path(self.wiki_dir)
        with sqlite3.connect(path) as con:
            con.execute("DROP TABLE staff_perms")
        self.assertEqual(staffperms.overrides(self.wiki_dir, self.kyun), {})   # 開いて作り直す
        self.grant(self.kyun, "accounts.view")
        self.assertIn("accounts.view", staffperms.overrides(self.wiki_dir, self.kyun))


class TestGates(Base):
    """`auth.can`・`sysui.require_perm`・既定のWiki専用の関門。"""

    def can(self, uid, *keys):
        self.as_user(uid)
        return auth.can(self.wiki_dir, FARM, *keys)

    def test_管理者は常に通り_助手は与えたものだけ(self):
        self.assertTrue(self.can("admin", "accounts.view"))
        self.assertFalse(self.can("kyun", "accounts.view"))
        self.assertTrue(self.can("kyun", "config.view"))
        self.grant(self.kyun, "accounts.view")
        self.assertTrue(self.can("kyun", "accounts.view"))
        self.assertFalse(self.can("sub", "accounts.view"))

    def test_複数を渡せばどれかで通る(self):
        self.assertTrue(self.can("kyun", "accounts.view", "config.view"))
        self.assertFalse(self.can("kyun", "accounts.view", "stafflog.view"))

    def test_助手でない人と未ログインは通らない(self):
        self.assertFalse(self.can("hito", "config.view"))
        self.assertFalse(self.can(None, "config.view"))

    def test_書き間違いは黙って通さず例外(self):
        with self.assertRaises(KeyError):
            self.can("admin", "config.veiw")
        with self.assertRaises(ValueError):
            self.can("admin")

    def test_require_permは断りの画面を返す(self):
        self.as_user("kyun")
        out = sysui.require_perm(self.wiki_dir, {}, FARM, False, ACCOUNTS_URLPATH, "accounts.view")
        self.assertEqual(out.status_code, 403)
        self.assertIsNone(sysui.require_perm(
            self.wiki_dir, {}, FARM, False, ACCOUNTS_URLPATH, "config.view"))

    def test_既定のWiki専用の画面も権限で決まる(self):
        cfg = {"farm": {"default": FARM}}
        self.as_user("kyun")
        self.assertIsNone(sysui.require_on_default_farm(
            cfg, FARM, self.wiki_dir, False, NEWWIKI_URLPATH, "site.newwiki"))
        self.grant(self.kyun, revoke=("site.newwiki",))
        self.as_user("kyun")
        out = sysui.require_on_default_farm(
            cfg, FARM, self.wiki_dir, False, NEWWIKI_URLPATH, "site.newwiki")
        self.assertEqual(out.status_code, 403)
        # 外していない別の操作は通る
        self.assertIsNone(sysui.require_on_default_farm(
            cfg, FARM, self.wiki_dir, False, "x", "site.restart"))
        self.as_user("admin")
        self.assertIsNone(sysui.require_on_default_farm(
            cfg, FARM, self.wiki_dir, False, NEWWIKI_URLPATH, "site.newwiki"))

    def test_既定のWiki専用の画面は権限を省くと助手なら誰でも通る(self):
        cfg = {"farm": {"default": FARM}}
        self.as_user("kyun")
        self.assertIsNone(sysui.require_on_default_farm(
            cfg, FARM, self.wiki_dir, False, NEWWIKI_URLPATH))
        self.as_user("hito")
        self.assertEqual(sysui.require_on_default_farm(
            cfg, FARM, self.wiki_dir, False, NEWWIKI_URLPATH).status_code, 403)


class TestAccountsPermissions(Base):

    def call(self, uid, payload):
        self.post_json(uid, payload)
        return accounts.render_accounts_api(self.wiki_dir, {}, FARM, False)

    def update(self, actor, target_uid, **fields):
        """`actor` として、`target_uid` のアカウントを書き換える要求を送る（変える項目だけ渡す）。"""
        target = userdb.find_by_uid(self.wiki_dir, target_uid)
        payload = {"cmd": "update", "uidnum": target["uidnum"], "uid": target["uid"],
                   "name": target["name"], "pw": target["pw"]}
        payload.update(fields)
        return self.call(actor, payload)

    def test_既定では助手は開けない(self):
        self.as_user("kyun")
        out = accounts.render_accounts(self.wiki_dir, {}, FARM, False)
        self.assertEqual(out.status_code, 403)
        self.assertEqual(self.call("kyun", {"cmd": "delete", "uidnum": 3}).status_code, 403)

    def test_見る権限だけでは何も書き換えられない(self):
        self.grant(self.kyun, "accounts.view")
        self.as_user("kyun")
        self.assertEqual(accounts.render_accounts(self.wiki_dir, {}, FARM, False).status_code, 200)
        self.assertEqual(self.update("kyun", "hito", name="変えた").status_code, 403)
        self.assertEqual(self.call("kyun", {"cmd": "delete",
                         "uidnum": userdb.find_by_uid(self.wiki_dir, "hito")["uidnum"]}).status_code, 403)
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "hito")["name"], "hito")

    def test_名前を変える権限(self):
        self.grant(self.kyun, "accounts.view", "accounts.rename")
        out = self.update("kyun", "hito", name="ひと")
        self.assertEqual(out.status_code, 200)
        self.assertTrue(self.json_of(out)["ok"])
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "hito")["name"], "ひと")

    def test_パスワードは名前の権限だけでは変えられない(self):
        self.grant(self.kyun, "accounts.view", "accounts.rename")
        before = userdb.find_by_uid(self.wiki_dir, "hito")["pw"]
        self.assertEqual(self.update("kyun", "hito", raw="new").status_code, 403)
        self.assertEqual(self.update("kyun", "hito", lock=True).status_code, 403)
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "hito")["pw"], before)

    def test_パスワードの権限だけでは名前を変えられない(self):
        self.grant(self.kyun, "accounts.view", "accounts.password")
        self.assertEqual(self.update("kyun", "hito", name="x").status_code, 403)
        out = self.update("kyun", "hito", raw="newpass")
        self.assertEqual(out.status_code, 200)
        self.assertTrue(userdb.authenticate(self.wiki_dir, "hito", "newpass"))

    def test_ロックもパスワードの権限(self):
        self.grant(self.kyun, "accounts.view", "accounts.password")
        self.assertTrue(self.json_of(self.update("kyun", "hito", lock=True))["ok"])
        self.assertTrue(userdb.is_locked(userdb.find_by_uid(self.wiki_dir, "hito")))

    def test_IDを変えるには名前とパスワードの両方の権限が要る(self):
        self.grant(self.kyun, "accounts.view", "accounts.rename")
        out = self.update("kyun", "hito", uid="hito2")
        self.assertEqual(out.status_code, 403)
        self.assertIn("パスワード", self.json_of(out)["message"])
        self.grant(self.kyun, "accounts.view", "accounts.rename", "accounts.password")
        out = self.update("kyun", "hito", uid="hito2", raw="p")
        self.assertEqual(out.status_code, 200)
        self.assertIsNotNone(userdb.find_by_uid(self.wiki_dir, "hito2"))

    def test_消す権限(self):
        self.grant(self.kyun, "accounts.view", "accounts.delete")
        hito = userdb.find_by_uid(self.wiki_dir, "hito")["uidnum"]
        out = self.call("kyun", {"cmd": "delete", "uidnum": hito})
        self.assertEqual(out.status_code, 200)
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "hito"))

    def test_管理者のアカウントは助手に触らせない(self):
        self.grant(self.kyun, *[k for k in staffperms.ALL_KEYS if k.startswith("accounts.")])
        admin_pw = userdb.find_by_uid(self.wiki_dir, "admin")["pw"]
        out = self.update("kyun", "admin", raw="takeover")
        self.assertEqual(out.status_code, 403)
        self.assertEqual(self.call("kyun", {"cmd": "delete", "uidnum": 1}).status_code, 403)
        self.assertEqual(self.update("kyun", "admin", name="x").status_code, 403)
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "admin")["pw"], admin_pw)
        self.assertTrue(accounts.can_modify(userdb.find_by_uid(self.wiki_dir, "admin"), 1))
        self.assertFalse(accounts.can_modify(userdb.find_by_uid(self.wiki_dir, "kyun"), 1))

    def test_管理者は今までどおりすべてできる(self):
        out = self.update("admin", "hito", name="ひと")
        self.assertEqual(out.status_code, 200)

    def test_追加は権限が要る(self):
        self.grant(self.kyun, "accounts.view")
        self.post_form("kyun", {"cmd": "add", "uid": "newbie", "name": "n", "raw": "pw"})
        accounts.render_accounts(self.wiki_dir, {}, FARM, False)
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "newbie"))
        self.grant(self.kyun, "accounts.view", "accounts.add")
        self.post_form("kyun", {"cmd": "add", "uid": "newbie", "name": "n", "raw": "pw"})
        accounts.render_accounts(self.wiki_dir, {}, FARM, False)
        self.assertIsNotNone(userdb.find_by_uid(self.wiki_dir, "newbie"))

    def test_画面は持たない操作を出さない(self):
        self.grant(self.kyun, "accounts.view", "accounts.rename")
        self.as_user("kyun")
        html = self.body_of(accounts.render_accounts(self.wiki_dir, {}, FARM, False))
        self.assertNotIn("新しく追加する", html)
        self.assertIn("選んだ行を削除", html)            # ボタンはあるが隠れて押せない
        self.assertRegex(html, r'id="acct-delete-btn"[^>]*disabled hidden')
        hito_num = userdb.find_by_uid(self.wiki_dir, "hito")["uidnum"]
        hito = re.search(r'<tr data-uidnum="%d".*?</tr>' % hito_num, html, re.S).group(0)
        self.assertNotRegex(hito, r'class="acct-f-uid"[^>]*readonly')    # 名前は書き換えられる
        self.assertNotRegex(hito, r'class="acct-f-name"[^>]*readonly')
        # パスワードの欄は読み取り専用
        self.assertRegex(hito, r'class="acct-f-pw acct-hash"[^>]*readonly')
        # 管理者の行は、助手には読み取り専用
        admin_row = re.search(r'<tr data-uidnum="1".*?</tr>', html, re.S).group(0)
        self.assertRegex(admin_row, r'class="acct-f-uid"[^>]*readonly')
        self.assertRegex(admin_row, r'class="acct-f-name"[^>]*readonly')

    def test_管理者の画面は全部出る(self):
        self.as_user("admin")
        html = self.body_of(accounts.render_accounts(self.wiki_dir, {}, FARM, False))
        self.assertIn("新しく追加する", html)
        self.assertNotRegex(html, r'id="acct-delete-btn"[^>]*hidden')

    def test_助手の操作は記録に残る(self):
        self.grant(self.kyun, "accounts.view", "accounts.rename", "accounts.delete")
        self.update("kyun", "hito", name="ひと")
        hito = userdb.find_by_uid(self.wiki_dir, "hito")["uidnum"]
        self.call("kyun", {"cmd": "delete", "uidnum": hito})
        kinds = [(e["kind"], e["actor_uid"]) for e in stafflog.entries(self.wiki_dir)]
        self.assertEqual(sorted(kinds), [("account.delete", "kyun"), ("account.update", "kyun")])

    def test_管理者の操作は助手の記録に残さない(self):
        self.update("admin", "hito", name="ひと")
        self.assertEqual(stafflog.entries(self.wiki_dir), [])

    def test_消したアカウントは記録から戻せる(self):
        from wikilib import staffundo
        self.grant(self.kyun, "accounts.view", "accounts.delete")
        hito = userdb.find_by_uid(self.wiki_dir, "hito")
        self.call("kyun", {"cmd": "delete", "uidnum": hito["uidnum"]})
        entry = stafflog.entries(self.wiki_dir)[0]
        ok, _message = staffundo.undo(self.wiki_dir, {}, FARM, entry["id"], "admin")
        self.assertTrue(ok)
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "hito")["pw"], hito["pw"])

    def test_書き換えと追加の記録に書かない値は表示で隠れる(self):
        self.grant(self.kyun, "accounts.view", "accounts.password")
        self.update("kyun", "hito", raw="secret-new")
        entry = stafflog.entries(self.wiki_dir)[0]
        self.assertEqual(entry["kind"], "account.update")
        shown = stafflogui._diff_html(entry["before"], entry["after"])
        self.assertNotIn(userdb.find_by_uid(self.wiki_dir, "hito")["pw"], shown)
        self.assertIn("パスワードを入れ直した", entry["summary"])


class TestApprovalsPermissions(Base):

    def pending(self, uid="waiting"):
        userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid,
                        approved=False)
        return userdb.find_by_uid(self.wiki_dir, uid)["uidnum"]

    def act(self, uid, op, uidnum):
        self.post_form(uid, {"op": op, "uidnum": uidnum})
        return approvalsui.render_approvals(self.wiki_dir, {}, FARM, False)

    def test_既定では助手は承認も断るもできる(self):
        n = self.pending("a")
        self.act("kyun", "approve", n)
        self.assertTrue(userdb.is_approved(userdb.get_user(self.wiki_dir, n)))
        m = self.pending("b")
        self.act("kyun", "reject", m)
        self.assertIsNone(userdb.get_user(self.wiki_dir, m))

    def test_承認だけ許すと断るはできない(self):
        self.grant(self.kyun, revoke=("approvals.reject",))
        n = self.pending()
        out = self.act("kyun", "reject", n)
        self.assertIn("done=ng", out.headers["Location"])
        self.assertIsNotNone(userdb.get_user(self.wiki_dir, n))
        self.act("kyun", "approve", n)
        self.assertTrue(userdb.is_approved(userdb.get_user(self.wiki_dir, n)))

    def test_どちらも外すと開けない(self):
        self.grant(self.kyun, revoke=("approvals.approve", "approvals.reject"))
        self.as_user("kyun")
        out = approvalsui.render_approvals(self.wiki_dir, {}, FARM, False)
        self.assertEqual(out.status_code, 403)

    def test_持たない操作のボタンは出さない(self):
        self.pending()
        self.grant(self.kyun, revoke=("approvals.reject",))
        self.as_user("kyun")
        html = self.body_of(approvalsui.render_approvals(self.wiki_dir, {}, FARM, False))
        self.assertIn("承認する", html)
        self.assertNotIn("断る</button>", html)


class TestGroupsPermissions(Base):

    def edit(self, uid, gname):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        return auth.can_edit_group(self.wiki_dir, gname, user["uidnum"])

    def setUp(self):
        super().setUp()
        groups.create_group(self.wiki_dir, "club", userdb.find_by_uid(self.wiki_dir, "hito")["uidnum"])

    def test_既定では助手はどのグループも編集できる(self):
        self.assertTrue(self.edit("kyun", "club"))
        self.assertTrue(self.edit("kyun", groups.STAFF_GROUP))

    def test_助手グループの編集だけ外せる(self):
        self.grant(self.kyun, revoke=("groups.staff",))
        self.assertFalse(self.edit("kyun", groups.STAFF_GROUP))   # 助手自身でも、許されなければ不可
        self.assertTrue(self.edit("kyun", "club"))
        self.assertTrue(self.edit("sub", groups.STAFF_GROUP))     # ほかの助手は変わらない

    def test_ほかのグループの編集を外しても_自分のグループは編集できる(self):
        self.grant(self.kyun, revoke=("groups.others",))
        self.assertFalse(self.edit("kyun", "club"))
        groups.add_members(self.wiki_dir, "club", ["kyun"])
        self.assertTrue(self.edit("kyun", "club"))

    def test_管理者はいつでも(self):
        self.assertTrue(self.edit("admin", groups.STAFF_GROUP))
        self.assertTrue(self.edit("admin", "club"))

    def test_ただの人は自分のグループだけ(self):
        self.assertTrue(self.edit("hito", "club"))
        self.assertFalse(self.edit("hito", groups.STAFF_GROUP))


class TestConfigPrivilegesPermissions(Base):

    def config_api(self, uid, payload):
        self.post_json(uid, payload)
        return configui.render_configwiki_api(self.wiki_dir, {}, FARM, False)

    def test_設定の操作ごとに権限が要る(self):
        self.grant(self.kyun, revoke=("config.edit",))
        # 知らない操作は、権限があれば「知らない操作」(400)、なければ権限なし(403)
        out = self.config_api("kyun", {"op": "set", "path": "x", "use": False})
        self.assertEqual(out.status_code, 403)
        # 外していない定義ルール・Wiki名は通る（Wiki名は確かめの欄が違うので400）
        out = self.config_api("kyun", {"op": "rename", "name": "zzz", "confirm": "no"})
        self.assertEqual(out.status_code, 400)

    def test_Wiki名を外す(self):
        self.grant(self.kyun, revoke=("config.rename",))
        out = self.config_api("kyun", {"op": "rename", "name": "zzz", "confirm": FARM})
        self.assertEqual(out.status_code, 403)

    def test_定義ルールを外す(self):
        self.grant(self.kyun, revoke=("config.extrarules",))
        out = self.config_api("kyun", {"op": "rx_add"})
        self.assertEqual(out.status_code, 403)

    def test_設定を見るのを外すと画面を開けず_編集も効かない(self):
        self.grant(self.kyun, revoke=("config.view",))
        self.as_user("kyun")
        self.assertEqual(configui.render_configwiki(self.wiki_dir, {}, FARM, False).status_code, 403)
        self.assertEqual(self.config_api("kyun", {"op": "set", "path": "x"}).status_code, 403)

    def test_助手でない人は断る(self):
        self.assertEqual(self.config_api("hito", {"op": "set"}).status_code, 403)

    def privileges_api(self, uid, payload):
        self.post_json(uid, payload)
        return privilegesui.render_privileges_api(self.wiki_dir, {}, FARM, False)

    def test_アクセス制限は見るだけと書き換えを分ける(self):
        self.grant(self.kyun, revoke=("privileges.edit",))
        out = self.privileges_api("kyun", {"op": "evaluate", "page": "Foo"})
        self.assertEqual(out.status_code, 200)
        for op in ("add", "set", "delete"):
            out = self.privileges_api("kyun", {"op": op, "page": "Foo", "r": "admin", "w": "admin"})
            self.assertEqual(out.status_code, 403, op)

    def test_アクセス制限を見るのを外すと開けない(self):
        self.grant(self.kyun, revoke=("privileges.view",))
        self.as_user("kyun")
        self.assertEqual(privilegesui.render_privileges(self.wiki_dir, {}, FARM, False).status_code, 403)
        self.assertEqual(self.privileges_api("kyun", {"op": "evaluate", "page": "Foo"}).status_code, 403)


class TestRecordsAndOperations(Base):

    def test_既定では記録を見られない(self):
        self.as_user("kyun")
        self.assertEqual(stafflogui.render_stafflog(self.wiki_dir, {}, FARM, False).status_code, 403)

    def test_記録を見る権限と戻す権限は別(self):
        self.grant(self.kyun, "stafflog.view")
        self.as_user("kyun")
        self.assertEqual(stafflogui.render_stafflog(self.wiki_dir, {}, FARM, False).status_code, 200)
        entry_id = stafflog.record(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "sub"),
                                   "group.members", "club", "x", before=[], after=[])
        self.post_form("kyun", {"id": entry_id})
        html = self.body_of(stafflogui.render_stafflog(self.wiki_dir, {}, FARM, False))
        self.assertIn("元に戻す権限がありません", html)
        self.assertIsNone(stafflog.get(self.wiki_dir, entry_id)["undone_at"])

    def test_戻す権限があれば戻せる(self):
        self.grant(self.kyun, "stafflog.view", "stafflog.undo")
        groups.create_group(self.wiki_dir, "club", self.sub)
        before = groups.member_rows(self.wiki_dir, "club")
        groups.add_members(self.wiki_dir, "club", ["hito"])
        after = groups.member_rows(self.wiki_dir, "club")
        entry_id = stafflog.record(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "sub"),
                                   "group.members", "club", "x", before=before, after=after)
        self.post_form("kyun", {"id": entry_id})
        stafflogui.render_stafflog(self.wiki_dir, {}, FARM, False)
        self.assertIsNotNone(stafflog.get(self.wiki_dir, entry_id)["undone_at"])

    def test_中断した操作は見る権限と続ける権限が別(self):
        self.grant(self.kyun, revoke=("operations.resume",))
        self.as_user("kyun")
        self.assertEqual(operationsui.render_operations(self.wiki_dir, {}, FARM, False).status_code, 200)
        self.post_form("kyun", {"id": "nothing"})
        html = self.body_of(operationsui.render_operations(self.wiki_dir, {}, FARM, False))
        self.assertIn("続きを行う権限がありません", html)

    def test_中断した操作を見るのを外すと開けない(self):
        self.grant(self.kyun, revoke=("operations.view",))
        self.as_user("kyun")
        self.assertEqual(operationsui.render_operations(self.wiki_dir, {}, FARM, False).status_code, 403)


class TestThemeMounts(Base):

    def access(self, uid, mount):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = themefilesui._viewer.set((staffperms.granted_set(self.wiki_dir, user), None))
        try:
            return themefilesui._mount_access(None, mount)
        finally:
            themefilesui._viewer.reset(token)

    def test_既定の助手は入れる前のとおり(self):
        self.assertEqual(self.access("kyun", themefilesui.SITE_MOUNT), None)
        self.assertEqual(self.access("kyun", themefilesui.SLOT_SITE_MOUNT), "rw")
        self.assertEqual(self.access("kyun", themefilesui.SLOT_COMMON_MOUNT), "ro")
        common = self.access("kyun", themefilesui.COMMON_MOUNT)
        self.assertEqual(common, {"access": "ro", "disable": [themefilesui.COPY_COMMAND]})

    def test_管理者は全部(self):
        self.assertEqual(self.access("admin", themefilesui.SITE_MOUNT), "rw")
        self.assertEqual(self.access("admin", themefilesui.COMMON_MOUNT), "ro")
        self.assertEqual(self.access("admin", themefilesui.SLOT_SITE_MOUNT), "rw")

    def test_sitethemeは見るだけ_編集の2段階(self):
        self.grant(self.kyun, "themes.site.view")
        self.assertEqual(self.access("kyun", themefilesui.SITE_MOUNT), "ro")
        self.grant(self.kyun, "themes.site.view", "themes.site.edit")
        self.assertEqual(self.access("kyun", themefilesui.SITE_MOUNT), "rw")
        self.assertEqual(self.access("kyun", themefilesui.COMMON_MOUNT), "ro")   # コピーも出る

    def test_編集だけ許しても見る権限が無ければ見えない(self):
        self.grant(self.kyun, "themes.site.edit")
        self.assertEqual(self.access("kyun", themefilesui.SITE_MOUNT), None)

    def test_slotthemeの編集を外すと読み取りだけ_コピーも出ない(self):
        self.grant(self.kyun, revoke=("themes.slot",))
        self.assertEqual(self.access("kyun", themefilesui.SLOT_SITE_MOUNT), "ro")
        self.assertEqual(self.access("kyun", themefilesui.SLOT_COMMON_MOUNT),
                         {"access": "ro", "disable": [themefilesui.SLOT_COPY_COMMAND]})

    def test_テーマを開く権限を外すと画面に入れない(self):
        self.grant(self.kyun, revoke=("themes.view",))
        self.as_user("kyun")
        out = themefilesui.serve_themefiles(self.wiki_dir, {}, FARM, False, "http://x/.admin/themes")
        self.assertEqual(out.status_code, 403)


class TestAdminWindow(Base):

    def html(self, uid, wiki_dir=True):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        return adminui.admin_tools_html("/=" + FARM, user, userdb.is_admin(user),
                                        self.wiki_dir if wiki_dir else None)

    def test_管理者は全部に入口がある(self):
        html = self.html("admin")
        self.assertNotIn('class="acct-only"', html)     # 開けない印がどこにも付かない
        self.assertIn(f'href="/={FARM}/{STAFFPERMS_URLPATH}"', html)

    def test_助手には与えていない道具を印つきで見せる(self):
        html = self.html("kyun")
        self.assertIn('アカウント <span class="acct-only">権限がありません</span>', html)
        self.assertIn('助手の権限 <span class="acct-only">管理者だけ</span>', html)  # 設定は管理者だけ
        self.assertIn(f'href="/={FARM}/.admin/configwiki"', html)

    def test_与えると開ける印になる(self):
        self.grant(self.kyun, "accounts.view", "stafflog.view")
        html = self.html("kyun")
        self.assertIn(f'href="/={FARM}/{ACCOUNTS_URLPATH}"', html)
        self.assertIn(f'href="/={FARM}/.admin/stafflog"', html)

    def test_外すと印になる(self):
        self.grant(self.kyun, revoke=("config.view",))
        self.assertNotIn(f'href="/={FARM}/.admin/configwiki"', self.html("kyun"))

    def test_Wikiを渡さない呼び出しは既定の権限で出し分ける(self):
        self.grant(self.kyun, "accounts.view")
        html = self.html("kyun", wiki_dir=False)    # `#login` プラグインの呼びかた
        self.assertNotIn(f'href="/={FARM}/{ACCOUNTS_URLPATH}"', html)
        self.assertIn(f'href="/={FARM}/.admin/configwiki"', html)


class TestPermsScreen(Base):

    def get(self, uid, query=""):
        self.bind(uid, query=query)
        return staffpermsui.render_staffperms(self.wiki_dir, {}, FARM, False)

    def post(self, uid, fields):
        self.post_form(uid, fields)
        return staffpermsui.render_staffperms(self.wiki_dir, {}, FARM, False)

    def test_管理者だけが開ける(self):
        for uid in ("kyun", "hito", None):
            self.assertEqual(self.get(uid).status_code, 403, uid)
        self.assertEqual(self.get("admin").status_code, 200)

    def test_助手に許しても設定の画面は開けない_自分に足せない(self):
        self.grant(self.kyun, *staffperms.ALL_KEYS)
        self.assertEqual(self.get("kyun").status_code, 403)
        out = self.post("kyun", {"shown": [self.kyun], f"perm.{self.kyun}": ["accounts.view"]})
        self.assertEqual(out.status_code, 403)

    def test_表は横が助手_縦が機能(self):
        html = self.body_of(self.get("admin"))
        self.assertIn("<code>kyun</code>", html)
        self.assertIn("<code>sub</code>", html)
        self.assertNotIn("<code>hito</code>", html)      # 助手でない人は並べない
        self.assertNotIn("<code>admin</code>", html)     # 管理者は設定の対象外
        for perm in staffperms.PERMS:
            self.assertIn(f'data-key="{perm.key}"', html)
        # 助手の数 × 権限の数だけチェックボックスが並ぶ
        self.assertEqual(html.count('type="checkbox"'), 2 * len(staffperms.PERMS))

    def test_既定のチェックの入りかた(self):
        html = self.body_of(self.get("admin"))
        m = re.search(r'<input type="checkbox" name="perm.%d" value="config.edit"[^>]*>' % self.kyun, html)
        self.assertIn(" checked", m.group(0))
        m = re.search(r'<input type="checkbox" name="perm.%d" value="accounts.view"[^>]*>' % self.kyun, html)
        self.assertNotIn(" checked", m.group(0))

    def test_注意の付く権限がある(self):
        html = self.body_of(self.get("admin"))
        self.assertIn("その人になりすませます", html)

    def test_保存する(self):
        out = self.post("admin", {
            "shown": [self.kyun, self.sub],
            f"perm.{self.kyun}": sorted(set(staffperms.default_set()) | {"accounts.view"}),
            f"perm.{self.sub}": sorted(set(staffperms.default_set()) - {"site.restart"}),
        })
        self.assertEqual(out.status_code, 303)
        self.assertIn("saved=2", out.headers["Location"])
        self.assertIn("accounts.view", staffperms.granted_set(
            self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "kyun")))
        self.assertNotIn("site.restart", staffperms.granted_set(
            self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "sub")))

    def test_保存した結果が表に出る(self):
        self.post("admin", {"shown": [self.kyun], f"perm.{self.kyun}": ["accounts.view"]})
        html = self.body_of(self.get("admin"))
        m = re.search(r'<input type="checkbox" name="perm.%d" value="accounts.view"[^>]*>' % self.kyun, html)
        self.assertIn(" checked", m.group(0))
        m = re.search(r'<input type="checkbox" name="perm.%d" value="config.edit"[^>]*>' % self.kyun, html)
        self.assertNotIn(" checked", m.group(0))         # 送らなかったものは外れる

    def test_送られなかった助手には触れない(self):
        self.grant(self.sub, "accounts.view")
        self.post("admin", {"shown": [self.kyun], f"perm.{self.kyun}": []})
        self.assertIn("accounts.view", staffperms.granted_set(
            self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "sub")))

    def test_前提が外れていれば許さず_知らせる(self):
        out = self.post("admin", {"shown": [self.kyun],
                                  f"perm.{self.kyun}": ["accounts.add"]})   # accounts.view が無い
        self.assertIn("dropped=1", out.headers["Location"])
        self.assertNotIn("accounts.add", staffperms.granted_set(
            self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "kyun")))
        html = self.body_of(self.get("admin", "saved=1&dropped=1"))
        self.assertIn("前提の権限が外れていた", html)

    def test_知らない権限の名前は無視する(self):
        self.post("admin", {"shown": [self.kyun],
                            f"perm.{self.kyun}": ["config.view", "no.such"]})
        self.assertEqual(staffperms.overrides(self.wiki_dir, self.kyun).get("no.such"), None)

    def test_助手でない番号を送っても書かない(self):
        hito = userdb.find_by_uid(self.wiki_dir, "hito")["uidnum"]
        self.post("admin", {"shown": [hito, "abc"], f"perm.{hito}": sorted(staffperms.ALL_KEYS)})
        self.assertEqual(staffperms.overrides(self.wiki_dir, hito), {})

    def test_保存は管理者の記録に残る(self):
        import sqlite3
        from wikilib import adminlog
        self.post("admin", {"shown": [self.kyun], f"perm.{self.kyun}": ["accounts.view"]})
        with sqlite3.connect(adminlog.db_path(self.wiki_dir)) as con:
            rows = con.execute("SELECT actor_uid, cmd, target_uid, ok, message FROM adminlog").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][:4], ("admin", "staffperms", "kyun", 1))
        self.assertIn("許した", rows[0][4])
        self.assertIn("外した", rows[0][4])

    def test_助手がいなければ案内を出す(self):
        groups.remove_members(self.wiki_dir, groups.STAFF_GROUP, [self.kyun, self.sub])
        html = self.body_of(self.get("admin"))
        self.assertIn("助手はまだいません", html)
        self.assertNotIn('id="sp-form"', html)
        self.assertIn('data-key="accounts.view"', html)       # 既定の一覧は見える

    def test_変更なしの知らせ(self):
        html = self.body_of(self.get("admin", "saved=0&dropped=0"))
        self.assertIn("変更はありませんでした", html)

    def test_窓口から経由で取り次がれる(self):
        self.bind("admin")
        out = adminui.serve_admin(self.wiki_dir, {}, FARM, False, "/staffperms")
        self.assertEqual(out.status_code, 200)
        for suffix in ("css", "js"):
            self.bind("admin")
            res = adminui.serve_admin(self.wiki_dir, {}, FARM, False, f"/staffperms.{suffix}")
            self.assertEqual(res.status_code, 200, suffix)
            res.body.close()
        self.bind("admin")
        self.assertEqual(adminui.serve_admin(
            self.wiki_dir, {}, FARM, False, "/staffperms.txt").status_code, 404)

    def test_JSとCSSが対応している(self):
        base = os.path.join(ROOT, "_sys", "staffperms")
        with open(os.path.join(base, "staffperms.js"), encoding="utf-8") as f:
            js = f.read()
        with open(os.path.join(base, "staffperms.css"), encoding="utf-8") as f:
            css = f.read()
        for token in ("sp-table", "sp-form", "sp-save", "sp-status", "sp-reset", "sp-changed",
                      "data-needs", "data-default"):
            self.assertIn(token, js)
        for cls in ("sp-table", "sp-group", "sp-dep", "sp-changed", "sp-warn-mark", "sp-user"):
            self.assertIn("." + cls, css)


if __name__ == "__main__":
    unittest.main()
