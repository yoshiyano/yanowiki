#!/usr/bin/env python3
"""成り代わり（`wikilib.auth.act_as`）と、閲覧者の問い合わせ（`current_uid`）のテスト。

**システムとして動くときは、明示して `$sys` に成り代わる**（Wiki設計者の指示、
2026-09-14）。「要求が無いからシステム」とは推し量らない。ここでは次を確かめる。

  - `with act_as(uid)` の中だけ `current_uid` がその相手を返し、抜けると戻る
    （入れ子・例外で抜けた場合も）
  - 成り代わっていなければ cookie のログイン、それも無ければ None
  - `$sys` の判定器はすべてのページで `W`
  - `$sys` を cookie で名乗っても通らない
  - 成り代わりは新しいスレッドに引き継がれない（弱い側に倒れる）
  - 書き間違いの名前では成り代われない
  - ページの表示・添付の配信も、成り代わった相手の権限で判定する

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_actas.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import auth, paths, privilege_records, userdb, views  # noqa: E402
from wikilib.auth import (  # noqa: E402
    PAGE_NONE, PAGE_READ, PAGE_WRITE, SYSTEM_UID, act_as, acting_as, current_uid,
    page_privilege,
)
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

FARM = "testwiki"


class ActAsTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="actas-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        bottle.request.environ.clear()

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.environ.clear()
        shutil.rmtree(self.work, ignore_errors=True)

    def rule(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)

    def login_as(self, uid):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")

    def uid(self):
        return current_uid(self.wiki_dir, FARM)


class TestActAs(ActAsTestBase):
    """成り代わりそのもの。"""

    def test_成り代わっていなければNone(self):
        self.assertIsNone(acting_as())
        self.assertIsNone(self.uid())

    def test_withの中だけ成り代わる(self):
        with act_as("alice") as who:
            self.assertEqual(who, "alice")
            self.assertEqual(acting_as(), "alice")
            self.assertEqual(self.uid(), "alice")
        self.assertIsNone(acting_as())
        self.assertIsNone(self.uid())

    def test_システムに成り代わる(self):
        with act_as(SYSTEM_UID):
            self.assertEqual(self.uid(), "$sys")

    def test_入れ子は一つ外側に戻る(self):
        with act_as(SYSTEM_UID):
            with act_as("bob"):
                self.assertEqual(self.uid(), "bob")
            self.assertEqual(self.uid(), SYSTEM_UID)
        self.assertIsNone(self.uid())

    def test_例外で抜けても戻る(self):
        with self.assertRaises(RuntimeError):
            with act_as(SYSTEM_UID):
                raise RuntimeError("途中で失敗")
        self.assertIsNone(acting_as())

    def test_書き間違いの名前では成り代われない(self):
        for bad in ("", None, "$system", "sys", "a b", "g:staff", "../x"):
            with self.subTest(bad=bad):
                if bad == "sys":
                    # 英数字だけならログインIDの形なので通る（記録に無いIDは未ログインと同じ）
                    with act_as(bad):
                        self.assertEqual(self.uid(), "sys")
                    continue
                with self.assertRaises(ValueError):
                    with act_as(bad):
                        pass
        self.assertIsNone(acting_as())

    def test_新しいスレッドには引き継がれない(self):
        seen = []
        with act_as(SYSTEM_UID):
            t = threading.Thread(target=lambda: seen.append(acting_as()))
            t.start()
            t.join()
        self.assertEqual(seen, [None])


class TestCurrentUid(ActAsTestBase):
    """閲覧者の問い合わせ。"""

    def test_cookieでログインしていればその人(self):
        self.login_as("alice")
        self.assertEqual(self.uid(), "alice")

    def test_成り代わりがcookieより優先する(self):
        self.login_as("alice")
        with act_as(SYSTEM_UID):
            self.assertEqual(self.uid(), SYSTEM_UID)
        self.assertEqual(self.uid(), "alice")

    def test_cookieでsysを名乗っても通らない(self):
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}=$sys; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}=anything")
        self.assertIsNone(self.uid())


class TestSystemPrivilege(ActAsTestBase):
    """`$sys` の判定器。"""

    def test_規則にかかわらずすべてW(self):
        self.rule("Tech/ReadOnly", "R", "alice")
        self.rule("Tech/Secret", "W", "bob")
        self.rule("*", "R", "alice")
        privilege = page_privilege(self.wiki_dir, SYSTEM_UID)
        for page in ("Tech/ReadOnly", "Tech/Secret", "Other", ""):
            with self.subTest(page=page):
                self.assertEqual(privilege.check(page), PAGE_WRITE)

    def test_アカウントの記録が無いWikiでもW(self):
        bare = os.path.join(self.work, "wikidata", "bare", "wiki")
        os.makedirs(bare)
        self.assertEqual(page_privilege(bare, SYSTEM_UID).check("Any"), PAGE_WRITE)

    def test_ふつうの人は規則どおり(self):
        self.rule("Tech/ReadOnly", "R", "alice")
        self.rule("Tech/ReadOnly", "W", "bob")          # alice は読めるが、書ける人ではない
        self.assertEqual(page_privilege(self.wiki_dir, "alice").check("Tech/ReadOnly"),
                         PAGE_READ)
        self.assertEqual(page_privilege(self.wiki_dir, "bob").check("Tech/ReadOnly"),
                         PAGE_NONE)                     # W に載っていても、読めなければ何も付かない


class TestScreensFollowActAs(ActAsTestBase):
    """ページの表示・添付の配信が、成り代わった相手の権限で判定すること。"""

    def setUp(self):
        super().setUp()
        self.rule("Tech/Secret", "R", "alice")

    def read_page(self):
        """ページ（まだ無い `Tech/Secret`）を開いて状態コードを返す。

        読めない人には 403、読める人には「まだありません」の 404 になる
        （権限は `published_ref` が返す `ref.privilege` で見ている）。"""
        res = views.render_page(self.wiki_dir, {}, FARM, "Tech/Secret", False)
        return res.status_code

    def test_ページの表示(self):
        self.assertEqual(self.read_page(), 403)
        with act_as(SYSTEM_UID):
            self.assertEqual(self.read_page(), 404)
        with act_as("alice"):
            self.assertEqual(self.read_page(), 404)
        with act_as("bob"):
            self.assertEqual(self.read_page(), 403)

    def test_添付の閲覧(self):
        from wikilib.attach import attach_viewable
        self.assertFalse(attach_viewable(self.wiki_dir, FARM, "Tech/Secret/a.png"))
        with act_as(SYSTEM_UID):
            self.assertTrue(attach_viewable(self.wiki_dir, FARM, "Tech/Secret/a.png"))

    def test_ログイン中でも成り代わった相手で判定する(self):
        self.login_as("alice")
        self.assertEqual(self.read_page(), 404)
        with act_as("bob"):
            self.assertEqual(self.read_page(), 403)


if __name__ == "__main__":
    unittest.main()
