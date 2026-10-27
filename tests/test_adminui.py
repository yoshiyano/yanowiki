#!/usr/bin/env python3
"""管理の窓口（`/.admin`）のテスト。

**「管理者だけ」と「管理者と助手」を取り違えないこと**（Wiki設計者の指示、
2026-09-08）。どちらに置くかは**そこから管理者になれてしまうか**で決めて
いる。ここで見ているのは、その線引きが実際に効いているかである。

    管理者だけ      /.admin/accounts     他人のパスワードを書き換えられる
    管理者と助手    /.admin              窓口
                    /.admin/configwiki   Wikiの設定

助手グループ（`staff`）の出入りは`wikilib.groups`に統合されている
（Wiki設計者の指示、2026-09-12。旧`/.admin/staff`は廃止）。そちらのテストは
`tests/test_groups.py`にある。ここで見るのは、`wikilib.auth.is_staff`
（＝助手かどうか）が`sysui.require`の関門として正しく効くかだけ。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_adminui.py     （このファイルだけ）
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import adminui, groups, staffperms, userdb  # noqa: E402
from wikilib import auth, sysui  # noqa: E402
from wikilib.paths import (  # noqa: E402
    ADMIN_URLPATH, LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name,
)

def denial_body(html):
    """断りの画面から、**断りの中身だけ**を取り出す。

    フッタには「Logged in as …」が出る（`themes.login_label`、2026-09-14）。
    これは**見ている本人のログイン状態**で、断りの文言ではない。他人のIDが
    登録されているかを確かめる手がかりにはならない（自分が入っているかは
    自分が知っている）ので、ここでは比較から外す。"""
    found = re.search(r'<div class="acct acct-denied">.*?</div>', html, re.S)
    return found.group(0) if found else html


class AdminTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="adminui-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        userdb.add_user(self.wiki_dir, "kyun", userdb.hash_password(self.wiki_dir, "kyun", "p"), "助手さん")
        userdb.add_user(self.wiki_dir, "hito", userdb.hash_password(self.wiki_dir, "hito", "p"), "ただの人")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        shutil.rmtree(self.work, ignore_errors=True)

    def login_as(self, uid):
        """そのアカウントでログインした状態にする（cookieを組み立てる）。"""
        bottle.request.environ.clear()
        if uid is None:
            return
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, "testwiki", user["pw"])
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, 'testwiki')}={uid}; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, 'testwiki')}={token}")

    def make_assistant(self, uid):
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, [uid])

    def opens(self, principals, uid):
        """その相手がこの関門を通れるか（通れれば True）。

        関門は`sysui.require`1つに集約され、**必要なプリンシパルを渡す**形に
        なった（Wiki設計者の指示、2026-09-13）。以前は`require_admin`/`require_staff`
        という別々の関数を渡していた。"""
        self.login_as(uid)
        return sysui.require(self.wiki_dir, {}, "testwiki", False,
                             ADMIN_URLPATH, principals) is None


class TestGate(AdminTestBase):
    """入口の線引き。"""

    def test_管理者はどちらも通る(self):
        self.assertTrue(self.opens(auth.ADMIN_ONLY, "admin"))
        self.assertTrue(self.opens(auth.STAFF, "admin"))

    def test_助手は管理者と助手の入口だけ通る(self):
        self.make_assistant("kyun")
        self.assertTrue(self.opens(auth.STAFF, "kyun"))
        self.assertFalse(self.opens(auth.ADMIN_ONLY, "kyun"))

    def test_ただの利用者はどちらも通らない(self):
        self.assertFalse(self.opens(auth.STAFF, "hito"))
        self.assertFalse(self.opens(auth.ADMIN_ONLY, "hito"))

    def test_ログインしていなければ通らない(self):
        self.assertFalse(self.opens(auth.STAFF, None))
        self.assertFalse(self.opens(auth.ADMIN_ONLY, None))

    def test_助手から外すと通らなくなる(self):
        self.make_assistant("kyun")
        user = userdb.find_by_uid(self.wiki_dir, "kyun")
        groups.remove_members(self.wiki_dir, groups.STAFF_GROUP, [user["uidnum"]])
        self.assertFalse(self.opens(auth.STAFF, "kyun"))

    def test_断る理由は分けて伝えない(self):
        # 「ログインしていない」と「権限がない」を分けると、そのIDが
        # 登録されているかを外から確かめる手がかりになる
        def body(uid):
            self.login_as(uid)
            out = sysui.require(self.wiki_dir, {}, "testwiki", False,
                                ADMIN_URLPATH, auth.ADMIN_ONLY)
            raw = out.body if hasattr(out, "body") else out
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw
        self.assertEqual(denial_body(body(None)), denial_body(body("hito")))


class TestDeniedLinks(AdminTestBase):
    """断りの画面のリンク（Wiki設計者の指示、2026-09-27。閲覧の権限が無いページと
    同じく、ログインの入口へのリンクを出す）。"""

    def denied(self, uid, principals=auth.STAFF):
        self.login_as(uid)
        out = sysui.require(self.wiki_dir, {}, "testwiki", False, ADMIN_URLPATH, principals)
        raw = out.body if hasattr(out, "body") else out
        return denial_body(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    def test_ログインしていなければログインの入口へのリンクがある(self):
        body = self.denied(None)
        self.assertIn('href="/=testwiki/.login"', body)
        self.assertIn('href="/=testwiki/"', body)

    def test_ログインしていても同じリンクを出す(self):
        # 「ログインしていない」と「権限がない」を分けて伝えない決まりのまま
        self.assertEqual(self.denied("hito"), self.denied(None))

    def test_既定のWiki専用の画面も同じ(self):
        from wikilib.paths import NEWWIKI_URLPATH

        self.login_as(None)
        out = sysui.require_on_default_farm({"farm": {"default": "testwiki"}}, "testwiki",
                                            self.wiki_dir, False, NEWWIKI_URLPATH)
        raw = out.body if hasattr(out, "body") else out
        self.assertIn(".login", raw.decode("utf-8") if isinstance(raw, bytes) else raw)


class TestTools(unittest.TestCase):
    """窓口に並べる道具の一覧。"""

    @staticmethod
    def default_open():
        """既定の権限（`staffperms.default_set`）で助手が開ける道具のURL。"""
        held = staffperms.default_set()
        return {path for path, _l, _n, access in adminui.TOOLS
                if access == adminui.EVERYONE
                or (access != staffperms.ADMIN_ONLY and any(k in held for k in access))}

    def test_既定では管理者だけの道具が宣言されている(self):
        shared = self.default_open()
        for urlpath in (".admin/accounts", ".admin/stafflog", ".admin/staffperms"):
            self.assertNotIn(urlpath, shared)
            self.assertIn(urlpath, {p for p, _l, _n, _a in adminui.TOOLS})

    def test_助手の権限の道具は設定できない_管理者だけ(self):
        access = {p: a for p, _l, _n, a in adminui.TOOLS}
        self.assertEqual(access[".admin/staffperms"], staffperms.ADMIN_ONLY)

    def test_設定は助手も使える(self):
        self.assertIn(".admin/configwiki", self.default_open())

    def test_助手グループの道具はgroupsへのリンク(self):
        self.assertTrue(any(".groups" in p and groups.STAFF_GROUP in p
                            for p in self.default_open()))

    def test_Wikiの削除_一覧_再起動が並ぶ(self):
        from wikilib.paths import DELWIKI_URLPATH, RESTART_URLPATH
        paths = [path for path, _l, _n, _o in adminui.TOOLS]
        for want in (DELWIKI_URLPATH, RESTART_URLPATH, adminui.ALLWIKI_URLPATH):
            self.assertIn(want, paths)
            self.assertIn(want, self.default_open())

    def test_グループと権限の記録の後始末が並ぶ_誰でも開ける(self):
        from wikilib.paths import GROUPS_URLPATH, UPDATEPAGEAUTH_URLPATH
        access = {p: a for p, _l, _n, a in adminui.TOOLS}
        for want in (GROUPS_URLPATH, UPDATEPAGEAUTH_URLPATH):
            self.assertEqual(access[want], adminui.EVERYONE)
        # 権限を何も持たない助手にもリンクで出す
        self.assertTrue(adminui._may_open(adminui.EVERYONE, False, frozenset()))

    def test_要る権限の名前はどれも実在する(self):
        for _path, _label, _note, access in adminui.TOOLS:
            if access not in (staffperms.ADMIN_ONLY, adminui.EVERYONE):
                staffperms.check_keys(access)

    def test_既定のWiki専用の道具は別のWikiからもサイトの根へ向ける(self):
        user = {"uid": "admin", "name": "管理"}
        html = adminui.admin_tools_html("/=other", user, True)
        for name in ("newwiki", "delwiki", "restart", "allwiki"):
            self.assertIn(f'href="/.{name}"', html)
        self.assertIn('href="/=other/.admin/configwiki"', html)

    def test_一覧を出さない設定ならWikiの一覧は並べない(self):
        from unittest import mock
        user = {"uid": "admin", "name": "管理"}
        with mock.patch("wikilib.wikiconfig.load_config",
                        return_value={"farm": {"allwiki": ""}}):
            html = adminui.admin_tools_html("/=other", user, True)
        self.assertNotIn("Wikiの一覧", html)
        self.assertIn("Wikiを消す", html)

    def test_書きかたがそろっている(self):
        for path, label, note, access in adminui.TOOLS:
            self.assertTrue(path and label and note)
            self.assertTrue(access in (staffperms.ADMIN_ONLY, adminui.EVERYONE)
                            or (isinstance(access, tuple) and access))


class TestSingleSource(unittest.TestCase):
    """一覧の見た目の持ち主は `accounts.css` 1つ（Wiki設計者の指示、2026-10-12。
    「ページの二重管理にならないようにしてください」）。`/.admin` の画面も `#login`
    の「管理者メニュー」も、同じ一覧が連れてくるCSSで描かれる。"""

    def test_一覧は見た目のCSSを自分で連れてくる(self):
        user = {"uid": "admin", "name": "管理"}
        html = adminui.admin_tools_html("/=other", user, True)
        self.assertIn('<link rel="stylesheet" href="/=other/.admin/accounts.css">', html)
        # 外枠の幅を使うのは一覧の表（accounts.css の .acct.acct-list）。
        # 列の幅の基準（cqw）の入れ物は .acct-admin
        self.assertIn('class="acct acct-list acct-admin"', html)

    def test_管理の画面は自分ではCSSを足さない(self):
        # 一覧が連れてくる。画面側でも足すと、見た目の持ち主が2か所になる
        from types import SimpleNamespace
        from unittest import mock
        with mock.patch.object(adminui.sysui, "require", return_value=None), \
                mock.patch.object(adminui.sysui, "page") as page, \
                mock.patch.object(adminui.auth, "current_user",
                                  return_value={"uid": "admin", "name": ""}), \
                mock.patch.object(adminui.userdb, "is_admin", return_value=True), \
                mock.patch.object(adminui, "make_plugin_context",
                                  return_value=SimpleNamespace(base_url="/=x")), \
                mock.patch.object(adminui, "admin_tools_html", return_value="<p>tools</p>"):
            adminui.render_admin("/nowhere", {}, "x", False)
        self.assertEqual(page.call_count, 1)
        self.assertNotIn("css_url", page.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
