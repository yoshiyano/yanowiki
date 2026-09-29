#!/usr/bin/env python3
"""サービス全体に効く操作（`/.restart`・`/.newwiki`・`/.allwiki`）の関門のテスト。

**判定に使うのは、いま開いているWikiではなく既定Wikiのアカウント**
（Wiki設計者の指示、2026-09-13。「`/.restart` と `/.newwiki` は default wiki の
g:staff と admin による操作のみとします」）。再起動もWikiの作成もサービス
全体に効くので、Wikiがいくつ増えても**権限の持ち主は増えない**。

**全Wikiの一覧（`/.allwiki`）も同じ関門を通る**（Wiki設計者の指示、2026-09-16。
「`.allwiki` は `.newwiki` と同様、デフォルトwikiの admin 権限を持っている人のみ
実行可能に。また `=subwiki/.allwiki` は実行できないように」）。

**Wikiを消す（`/.delwiki`）も同じ**（2026-09-18）。増やせる人と減らせる人を
別の組にする理由が無いので揃えてある——ただしあちらは関門を通ったあとに、
**消される側のWikiの管理者のパスワード**をもう一段確かめる
（`tests/test_delwiki.py`）。

ここで見るのは次の3つ。

  - 通すのは**既定Wikiの管理者と助手だけ**。隣のWikiの管理者は通らない
  - **Wiki名を含むURL（`/=<Wiki名>/.restart`）は、既定Wikiのものでも
    403で断る**（Wiki設計者の指示、2026-09-13）。入口を素のURL1つに絞ると、
    読めるcookieが既定Wikiのものに定まる（cookieはWikiごとの`Path`に
    置いてあるため。`wikilib.auth.remember_login`）
  - **4つの入口が実際にこの関門を呼んでいる**（`TestEntrances`）。関門だけを
    試しても、入口が呼び忘れていれば素通りになるため

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_servicegate.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import auth, groups, paths, sysui, userdb  # noqa: E402
from wikilib.paths import (  # noqa: E402
    ALLWIKI_COMMAND, DELWIKI_URLPATH, LOGIN_AUTH_COOKIE, LOGIN_COOKIE,
    NEWWIKI_URLPATH, RESTART_URLPATH, SYSTEM_PREFIX, wiki_cookie_name,
)

ALLWIKI_URLPATH = SYSTEM_PREFIX + ALLWIKI_COMMAND  # 既定の /.allwiki

DEFAULT_FARM = "home"    # 既定Wiki
OTHER_FARM = "other"     # 隣のWiki


class ServiceGateBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="servicegate-")
        self.wiki_dirs = {}
        for farm in (DEFAULT_FARM, OTHER_FARM):
            d = os.path.join(self.work, "wikidata", farm, "wiki")
            os.makedirs(d)
            self.wiki_dirs[farm] = d
            userdb.create_db(d, "adminpw")
        # 既定Wikiだけに、助手とただの利用者を置く
        home = self.wiki_dirs[DEFAULT_FARM]
        userdb.add_user(home, "kyun", userdb.hash_password(home, "kyun", "p"), "助手さん")
        userdb.add_user(home, "hito", userdb.hash_password(home, "hito", "p"), "ただの人")

        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        self.config = {"farm": {"default": DEFAULT_FARM}}

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        shutil.rmtree(self.work, ignore_errors=True)

    def login_as(self, farm, uid):
        """そのWikiのそのアカウントでログインした状態にする。"""
        bottle.request.environ.clear()
        if uid is None:
            return
        user = userdb.find_by_uid(self.wiki_dirs[farm], uid)
        token = auth.session_token(uid, farm, user["pw"])
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, farm)}={uid}; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, farm)}={token}")

    def gate(self, farm, uid, urlpath=RESTART_URLPATH, explicit_farm=False):
        """その相手がこの関門をどう扱われるか。通れれば None が返る。

        `explicit_farm` は**URLにWiki名が入っていたか**（`/=<Wiki名>/.restart`
        の形か）。入っていれば、既定Wikiのものでも断られる。"""
        self.login_as(farm, uid)
        return sysui.require_on_default_farm(
            self.config, farm, self.wiki_dirs[farm], explicit_farm, urlpath)

    def opens(self, farm, uid, urlpath=RESTART_URLPATH, explicit_farm=False):
        return self.gate(farm, uid, urlpath, explicit_farm) is None


class TestWhoPasses(ServiceGateBase):
    """誰が通るか。"""

    def test_既定Wikiの管理者は通る(self):
        self.assertTrue(self.opens(DEFAULT_FARM, "admin"))
        self.assertTrue(self.opens(DEFAULT_FARM, "admin", NEWWIKI_URLPATH))
        self.assertTrue(self.opens(DEFAULT_FARM, "admin", ALLWIKI_URLPATH))
        self.assertTrue(self.opens(DEFAULT_FARM, "admin", DELWIKI_URLPATH))

    def test_既定Wikiの助手は通る(self):
        groups.add_members(self.wiki_dirs[DEFAULT_FARM], groups.STAFF_GROUP, ["kyun"])
        self.assertTrue(self.opens(DEFAULT_FARM, "kyun"))

    def test_ただの利用者は通らない(self):
        self.assertFalse(self.opens(DEFAULT_FARM, "hito"))
        self.assertFalse(self.opens(DEFAULT_FARM, "hito", ALLWIKI_URLPATH))
        self.assertFalse(self.opens(DEFAULT_FARM, "hito", DELWIKI_URLPATH))

    def test_ログインしていなければ通らない(self):
        self.assertFalse(self.opens(DEFAULT_FARM, None))

    def test_助手から外すと通らなくなる(self):
        home = self.wiki_dirs[DEFAULT_FARM]
        groups.add_members(home, groups.STAFF_GROUP, ["kyun"])
        user = userdb.find_by_uid(home, "kyun")
        groups.remove_members(home, groups.STAFF_GROUP, [user["uidnum"]])
        self.assertFalse(self.opens(DEFAULT_FARM, "kyun"))


class TestUrlShape(ServiceGateBase):
    """URLの形。**Wiki名を含むURLは、既定Wikiのものでも断る**
    （Wiki設計者の指示、2026-09-13）。

    入口を素のURL1つに絞ると、**読めるcookieが既定Wikiのものに定まる。**
    Wiki名付きのURLを通していると、どのWikiのcookieが読まれるかが
    そのときの状況次第になる（cookieはWikiごとの`Path`に置いてあるため）。"""

    def test_隣のWikiのURLは通らない(self):
        # **隣のWikiにも admin は居る。** そちらで通ってしまうと、Wikiを
        # 1つ作れば誰でもサービス全体を再起動できることになる
        self.assertFalse(self.opens(OTHER_FARM, "admin"))
        self.assertEqual(self.gate(OTHER_FARM, "admin").status_code, 403)

    def test_既定WikiでもWiki名付きのURLなら通らない(self):
        # `/=dwiki/.restart` も禁止（Wiki設計者の指示、2026-09-13）
        self.assertFalse(self.opens(DEFAULT_FARM, "admin", explicit_farm=True))
        self.assertEqual(
            self.gate(DEFAULT_FARM, "admin", explicit_farm=True).status_code, 403)

    def test_既定Wikiの素のURLなら通る(self):
        self.assertTrue(self.opens(DEFAULT_FARM, "admin"))

    def test_断りかたはWikiの新規作成でも同じ(self):
        self.assertEqual(
            self.gate(OTHER_FARM, "admin", NEWWIKI_URLPATH).status_code, 403)

    def test_Wikiの一覧も同じ扱い(self):
        # `=subwiki/.allwiki` は実行できない（Wiki設計者の指示、2026-09-16）。
        # 隣のWikiのURLでも、既定WikiにWiki名を付けたURLでも断る
        self.assertEqual(
            self.gate(OTHER_FARM, "admin", ALLWIKI_URLPATH).status_code, 403)
        self.assertEqual(
            self.gate(DEFAULT_FARM, "admin", ALLWIKI_URLPATH,
                      explicit_farm=True).status_code, 403)
        self.assertTrue(self.opens(DEFAULT_FARM, "admin", ALLWIKI_URLPATH))


class TestEntrances(ServiceGateBase):
    """**入口が実際に関門を呼んでいるか。**

    関門の関数だけを試しても、入口が呼び忘れていれば素通りになる。ここでは
    3つの入口をそのまま呼んで、**通らない相手には403が返り、一覧の中身
    （他のWikiの名前）が出ないこと**を見る。"""

    def setUp(self):
        super().setUp()
        self.config = {"farm": {"default": DEFAULT_FARM, "allwiki": ALLWIKI_COMMAND}}
        # `wikilib.allwiki` は WIKIDATA_DIR を読み込み時に自分の名前へ束ねて
        # いるので、`paths` 側の差し替えだけでは届かない。ここも仮置き場へ向ける
        from wikilib import allwiki
        self.allwiki = allwiki
        self.kept_allwiki_dir = allwiki.WIKIDATA_DIR
        allwiki.WIKIDATA_DIR = paths.WIKIDATA_DIR

    def tearDown(self):
        self.allwiki.WIKIDATA_DIR = self.kept_allwiki_dir
        super().tearDown()

    def call(self, render, farm, uid, explicit_farm=False):
        self.login_as(farm, uid)
        return render(self.wiki_dirs[farm], self.config, farm, explicit_farm)

    def body_of(self, out):
        raw = out.body if hasattr(out, "body") else out
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def test_Wikiの一覧はただの利用者に403(self):
        from wikilib.allwiki import render_allwiki
        out = self.call(render_allwiki, DEFAULT_FARM, "hito")
        self.assertEqual(out.status_code, 403)
        # 断られた画面に**他のWikiの名前が載っていない**こと。関門が
        # `wiki_entries()` より先に効いているかを、出力の側から確かめる
        self.assertNotIn(OTHER_FARM, self.body_of(out))

    def test_Wikiの一覧はWiki名付きのURLで403(self):
        from wikilib.allwiki import render_allwiki
        out = self.call(render_allwiki, DEFAULT_FARM, "admin", explicit_farm=True)
        self.assertEqual(out.status_code, 403)
        out = self.call(render_allwiki, OTHER_FARM, "admin")
        self.assertEqual(out.status_code, 403)

    def test_Wikiの一覧は既定Wikiの管理者には出る(self):
        from wikilib.allwiki import render_allwiki
        out = self.call(render_allwiki, DEFAULT_FARM, "admin")
        html = self.body_of(out)
        self.assertIn(OTHER_FARM, html)   # 隣のWikiも並ぶ
        self.assertIn(DEFAULT_FARM, html)

    def test_新規作成と再起動の入口も断る(self):
        from wikilib.newwiki import render_newwiki
        from wikilib.restart import serve_restart
        self.assertEqual(
            self.call(render_newwiki, DEFAULT_FARM, "hito").status_code, 403)
        self.assertEqual(
            self.call(serve_restart, DEFAULT_FARM, "hito").status_code, 403)

    def test_Wikiを消す入口も断る(self):
        # **隣のWikiの管理者でも断る。** ここを素通りさせると、Wikiを1つ
        # 作った人が他のWikiを消しにかかれることになる
        from wikilib.delwiki import render_delwiki
        self.assertEqual(
            self.call(render_delwiki, DEFAULT_FARM, "hito").status_code, 403)
        self.assertEqual(
            self.call(render_delwiki, OTHER_FARM, "admin").status_code, 403)
        self.assertEqual(
            self.call(render_delwiki, DEFAULT_FARM, "admin",
                      explicit_farm=True).status_code, 403)


if __name__ == "__main__":
    unittest.main()
