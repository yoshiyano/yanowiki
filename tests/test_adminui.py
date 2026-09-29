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
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_adminui.py     （このファイルだけ）
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

from wikilib import adminui, groups, userdb  # noqa: E402
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

    def test_管理者だけの道具が宣言されている(self):
        admin_only = {path for path, _l, _n, only in adminui.TOOLS if only}
        self.assertIn(".admin/accounts", admin_only)

    def test_設定は助手も使える(self):
        shared = {path for path, _l, _n, only in adminui.TOOLS if not only}
        self.assertIn(".admin/configwiki", shared)

    def test_助手グループの道具はgroupsへのリンク(self):
        shared = {path for path, _l, _n, only in adminui.TOOLS if not only}
        self.assertTrue(any(".groups" in p and groups.STAFF_GROUP in p for p in shared))

    def test_書きかたがそろっている(self):
        for path, label, note, only in adminui.TOOLS:
            self.assertTrue(path and label and note)
            self.assertIsInstance(only, bool)


if __name__ == "__main__":
    unittest.main()
