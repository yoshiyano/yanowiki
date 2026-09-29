#!/usr/bin/env python3
"""グループ管理画面（wikilib.groupsui）のテスト。

見ているのは、**ログインしていなければ`/.groups`ごと断るか**・
**グループ編集の中身は編集できる人だけが見えるか**・**APIの認証と操作**の
3点（Wiki設計者の指示、2026-09-12）。関門は`sysui.require`、権限判断は`auth`。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_groupsui.py     （このファイルだけ）
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import auth, groups, userdb  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402


class GroupsUiTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="groupsui-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir)
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        userdb.add_user(self.wiki_dir, "moe", userdb.hash_password(self.wiki_dir, "moe", "m@ss"), "萌")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        shutil.rmtree(self.work, ignore_errors=True)

    def uidnum(self, uid):
        return userdb.find_by_uid(self.wiki_dir, uid)["uidnum"]

    def token(self, uid, wikiname="testwiki"):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        return auth.session_token(uid, wikiname, user["pw"])

    def _set_cookie(self, uid, wikiname="testwiki"):
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, wikiname)}={uid}; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, wikiname)}={self.token(uid, wikiname)}")

    def get(self, query="", uid=None, wikiname="testwiki"):
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": query,
        })
        if uid is not None:
            self._set_cookie(uid, wikiname)
        from wikilib.groupsui import render_groups
        return render_groups(self.wiki_dir, {}, wikiname, False)

    def post_form(self, fields, uid=None, wikiname="testwiki"):
        from urllib.parse import urlencode
        body = urlencode(fields).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        })
        if uid is not None:
            self._set_cookie(uid, wikiname)
        from wikilib.groupsui import render_groups
        return render_groups(self.wiki_dir, {}, wikiname, False)

    def call_api(self, payload, uid=None, wikiname="testwiki"):
        body = json.dumps(payload).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        })
        if uid is not None:
            self._set_cookie(uid, wikiname)
        from wikilib.groupsui import render_groups_api
        return render_groups_api(self.wiki_dir, {}, wikiname, False)

    def body_text(self, out):
        raw = out.body if hasattr(out, "body") else out
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def body_json(self, out):
        return json.loads(self.body_text(out))


class TestRenderGroupsAuth(GroupsUiTestBase):
    """`/.groups` は**ログインしていなければ開けない**
    （Wiki設計者の指示、2026-09-12。管理者・助手である必要は無い）。"""

    def test_未ログインは403(self):
        out = self.get(uid=None)
        self.assertEqual(out.status_code, 403)

    def test_ただのユーザでも開ける(self):
        out = self.get(uid="yoshi")
        self.assertEqual(out.status_code, 200)

    def test_既定は作成タブ(self):
        html = self.body_text(self.get(uid="yoshi"))
        self.assertIn('data-panel="create"', html)
        self.assertNotIn('data-panel="create" hidden', html)

    def test_groupを指定すると編集タブが既定になる(self):
        html = self.body_text(self.get(query="group=team-a", uid="yoshi"))
        self.assertIn('data-panel="edit"', html)
        self.assertNotIn('data-panel="edit" hidden', html)


class TestCreateGroupForm(GroupsUiTestBase):
    """グループ作成フォーム（POST）。"""

    def test_作れたら編集タブへ303(self):
        out = self.post_form({"gname": "team-a"}, uid="yoshi")
        self.assertEqual(out.status_code, 303)
        self.assertIn("tab=edit", out.headers["Location"])
        self.assertIn("group=team-a", out.headers["Location"])
        self.assertTrue(groups.is_member(self.wiki_dir, "team-a", self.uidnum("yoshi")))

    def test_既にあるグループは作れない(self):
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("moe"))
        out = self.post_form({"gname": "team-a"}, uid="yoshi")
        self.assertEqual(out.status_code, 200)
        html = self.body_text(out)
        self.assertIn("すでに存在します", html)
        self.assertFalse(groups.is_member(self.wiki_dir, "team-a", self.uidnum("yoshi")))

    def test_使えない名前は断る(self):
        out = self.post_form({"gname": "Team!"}, uid="yoshi")
        self.assertEqual(out.status_code, 200)
        self.assertFalse(groups.exists(self.wiki_dir, "Team!"))

    def test_未ログインでは作れない(self):
        out = self.post_form({"gname": "team-a"}, uid=None)
        self.assertEqual(out.status_code, 403)
        self.assertFalse(groups.exists(self.wiki_dir, "team-a"))


class TestEditTabAccess(GroupsUiTestBase):
    """編集タブの中身（メンバー一覧・追加フォーム）は**編集できる人だけ**
    が見られる（Wiki設計者の指示、2026-09-12。g:foo・admin・g:staffの誰か）。"""

    def setUp(self):
        super().setUp()
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))

    def test_メンバーには一覧が見える(self):
        html = self.body_text(self.get(query="group=team-a&tab=edit", uid="yoshi"))
        self.assertIn("grp-member-table", html)
        self.assertIn("yoshi", html)

    def test_無関係な利用者には見えない(self):
        html = self.body_text(self.get(query="group=team-a&tab=edit", uid="moe"))
        self.assertNotIn("grp-member-table", html)
        self.assertIn("編集する権限がありません", html)

    def test_管理者は自分が入っていなくても見える(self):
        html = self.body_text(self.get(query="group=team-a&tab=edit", uid="admin"))
        self.assertIn("grp-member-table", html)

    def test_助手は自分が入っていなくても見える(self):
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["moe"])
        html = self.body_text(self.get(query="group=team-a&tab=edit", uid="moe"))
        self.assertIn("grp-member-table", html)

    def test_存在しないグループは案内(self):
        html = self.body_text(self.get(query="group=no-such&tab=edit", uid="yoshi"))
        self.assertNotIn("grp-member-table", html)
        self.assertIn("ありません", html)


class TestGroupsApi(GroupsUiTestBase):
    """一覧の追加・削除を受けるAPI（`/.groups/api`）。"""

    def setUp(self):
        super().setUp()
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))

    def test_未ログインは403(self):
        out = self.call_api({"cmd": "add", "group": "team-a", "uids": ["moe"]}, uid=None)
        self.assertEqual(out.status_code, 403)

    def test_編集権が無ければ403(self):
        out = self.call_api({"cmd": "add", "group": "team-a", "uids": ["yoshi"]}, uid="moe")
        self.assertEqual(out.status_code, 403)

    def test_管理者は自分が入っていなくても呼べる(self):
        out = self.call_api({"cmd": "add", "group": "team-a", "uids": ["moe"]}, uid="admin")
        self.assertTrue(self.body_json(out)["ok"])

    def test_メンバーなら追加できる(self):
        out = self.call_api({"cmd": "add", "group": "team-a", "uids": ["moe"]}, uid="yoshi")
        data = self.body_json(out)
        self.assertTrue(data["ok"])
        self.assertEqual([m["uid"] for m in data["added"]], ["moe"])
        self.assertTrue(groups.is_member(self.wiki_dir, "team-a", self.uidnum("moe")))

    def test_メンバーなら削除できる(self):
        groups.add_members(self.wiki_dir, "team-a", ["moe"])
        out = self.call_api(
            {"cmd": "remove", "group": "team-a", "uidnums": [self.uidnum("moe")]}, uid="yoshi")
        data = self.body_json(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["removed"], 1)

    def test_知らない操作は断る(self):
        out = self.call_api({"cmd": "nope", "group": "team-a"}, uid="yoshi")
        self.assertEqual(out.status_code, 400)

    def test_使えないグループ名は断る(self):
        out = self.call_api({"cmd": "add", "group": "Team!", "uids": ["moe"]}, uid="yoshi")
        self.assertEqual(out.status_code, 400)


if __name__ == "__main__":
    unittest.main()
