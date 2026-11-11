#!/usr/bin/env python3
"""既にあるWikiを起点Wikiに切り替える（`/.allwiki` のボタン）のテスト。

切り替えるとサービス全体の権限が移り、画面からは戻せないので、**書き換わらないはずの
場面で `server.yaml` が変わらないこと**を中心に見る。

実行:
    _venv/bin/python3 tests/test_defaultswitch.py
"""
import io as _io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import allwiki, auth, defaultswitch, groups, paths, userdb, wikiconfig  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

HOME = "home"       # いまの起点Wiki
TARGET = "target"   # 切り替え先
NOADMIN = "noadmin"  # アカウントの記録が無いWiki
SERVER_YAML = ("# 手で付けたコメント\nserver:\n  port: 8619\nfarm:\n"
               f"  default: {HOME}  # 行末のコメント\n  allwiki: allwiki\n")


class SwitchBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="defaultswitch-")
        self.wikidata = os.path.join(self.work, "wikidata")
        self.wiki_dirs = {}
        for farm, password in ((HOME, "homepw"), (TARGET, "targetpw"), (NOADMIN, None)):
            d = os.path.join(self.wikidata, farm, "wiki")
            os.makedirs(d)
            self.wiki_dirs[farm] = d
            if password:
                userdb.create_db(d, password)
        home = self.wiki_dirs[HOME]
        userdb.add_user(home, "kyun", userdb.hash_password(home, "kyun", "p"), "助手")
        userdb.add_user(home, "hito", userdb.hash_password(home, "hito", "p"), "利用者")
        groups.add_members(home, groups.STAFF_GROUP, ["kyun"])

        self.server_path = os.path.join(self.work, "server.yaml")
        with open(self.server_path, "w", encoding="utf-8") as f:
            f.write(SERVER_YAML)
        self.kept = (paths.WIKIDATA_DIR, allwiki.WIKIDATA_DIR, auth.SECRET_PATH,
                     wikiconfig.SERVER_CONFIG_PATH)
        paths.WIKIDATA_DIR = allwiki.WIKIDATA_DIR = self.wikidata
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        wikiconfig.SERVER_CONFIG_PATH = self.server_path
        self.config = {"farm": {"default": HOME, "allwiki": "allwiki"}}

    def tearDown(self):
        (paths.WIKIDATA_DIR, allwiki.WIKIDATA_DIR, auth.SECRET_PATH,
         wikiconfig.SERVER_CONFIG_PATH) = self.kept
        shutil.rmtree(self.work, ignore_errors=True)

    def request(self, method, uid, farm=HOME, explicit_farm=False, **fields):
        body = urlencode(fields).encode("utf-8")
        environ = {
            "REQUEST_METHOD": method,
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": _io.BytesIO(body),
            "REMOTE_ADDR": "127.0.0.1",
        }
        if uid is not None:
            user = userdb.find_by_uid(self.wiki_dirs[farm], uid)
            token = auth.session_token(uid, farm, user["pw"])
            environ["HTTP_COOKIE"] = (
                f"{wiki_cookie_name(LOGIN_COOKIE, farm)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, farm)}={token}")
        bottle.request.environ.clear()
        bottle.request.environ.update(environ)
        return allwiki.render_allwiki(self.wiki_dirs[farm], self.config, farm, explicit_farm)

    def switch(self, uid="admin", password="targetpw", name=TARGET, **kwargs):
        return self.request("POST", uid, step=defaultswitch.STEP_PASSWORD, name=name,
                            admin_pw=password, **kwargs)

    def body_of(self, out):
        raw = out.body
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def server_yaml(self):
        with open(self.server_path, encoding="utf-8") as f:
            return f.read()

    def assertNotSwitched(self):
        self.assertEqual(self.server_yaml(), SERVER_YAML)


class TestSwitch(SwitchBase):

    def test_正しいパスワードで切り替わりコメントは残る(self):
        out = self.switch()
        self.assertEqual(out.status_code, 200)
        self.assertEqual(self.server_yaml(),
                         SERVER_YAML.replace(f"default: {HOME}", f"default: {TARGET}"))
        self.assertEqual(wikiconfig.load_default_farm(wikiconfig.read_yaml(self.server_path)),
                         TARGET)
        self.assertIn("切り替えました", self.body_of(out))

    def test_確認の画面ではまだ変わらない(self):
        out = self.request("POST", "admin", step=defaultswitch.STEP_CHOOSE, name=TARGET)
        self.assertEqual(out.status_code, 200)
        self.assertIn('type="password"', self.body_of(out))
        self.assertIn("移ります", self.body_of(out))  # 権限が移ることを先に見せる
        self.assertNotSwitched()

    def test_パスワードが無ければ確認の画面止まり(self):
        # step を偽っても、空のパスワードは通らない
        out = self.switch(password="")
        self.assertEqual(out.status_code, 403)
        self.assertNotSwitched()

    def test_いまの起点Wikiのパスワードでは通らない(self):
        out = self.switch(password="homepw")
        self.assertEqual(out.status_code, 403)
        self.assertNotSwitched()

    def test_ロックされた管理者では正しいパスワードでも通らない(self):
        userdb.lock_user(self.wiki_dirs[TARGET], userdb.ADMIN_UIDNUM)
        out = self.switch()
        self.assertEqual(out.status_code, 403)
        self.assertIn("ロックされています", self.body_of(out))
        self.assertNotSwitched()

    def test_照合は切り替え先のアカウントでログインと同じ関数に通す(self):
        # 記録とロックをログインと揃えるため。素通しの窓口にしない
        with mock.patch.object(auth, "try_password", wraps=auth.try_password) as tried:
            self.switch(password="wrong")
        self.assertEqual(tried.call_args.args[0], self.wiki_dirs[TARGET])
        self.assertNotSwitched()

    def test_書き込めなければ失敗を伝える(self):
        with mock.patch.object(defaultswitch, "set_default_farm", return_value=False):
            out = self.switch()
        self.assertEqual(out.status_code, 500)
        self.assertIn("変わっていません", self.body_of(out))


class TestWhoCanSwitch(SwitchBase):

    def test_助手は切り替えられない(self):
        out = self.switch(uid="kyun")
        self.assertEqual(out.status_code, 403)
        self.assertNotSwitched()

    def test_助手の確認の画面も断る(self):
        out = self.request("POST", "kyun", step=defaultswitch.STEP_CHOOSE, name=TARGET)
        self.assertEqual(out.status_code, 403)

    def test_ただの利用者と未ログインは断る(self):
        for uid in ("hito", None):
            self.assertEqual(self.switch(uid=uid).status_code, 403, uid)
        self.assertNotSwitched()

    def test_Wiki名付きのURLは起点Wikiのものでも断る(self):
        self.assertEqual(self.switch(explicit_farm=True).status_code, 403)
        self.assertNotSwitched()

    def test_別のWikiの管理者は断る(self):
        self.assertEqual(self.switch(farm=TARGET).status_code, 403)
        self.assertNotSwitched()

    def test_ボタンは管理者にだけ出る(self):
        admin = self.body_of(self.request("GET", "admin"))
        self.assertIn("起点Wikiにする", admin)
        # いまの起点Wikiの行には出ない
        self.assertNotIn(f'name="name" value="{HOME}"', admin)
        self.assertIn(f'name="name" value="{TARGET}"', admin)
        self.assertNotIn("起点Wikiにする", self.body_of(self.request("GET", "kyun")))


class TestTarget(SwitchBase):

    def assertRefused(self, name, phrase):
        # step を飛ばして直接POSTしても断られること
        out = self.switch(name=name)
        self.assertIn(phrase, self.body_of(out))
        self.assertNotSwitched()

    def test_管理者のいないWikiへは切り替えない(self):
        self.assertRefused(NOADMIN, "管理者がいない")

    def test_無いWikiへは切り替えない(self):
        self.assertRefused("nosuch", "ありません")
        self.assertRefused("../home", "ありません")

    def test_いまの起点Wikiは選べない(self):
        self.assertRefused(HOME, "すでに起点Wiki")

    def test_YAMLに書けない名前へは切り替えない(self):
        for name in ("a b", "123", "true", "null"):
            d = os.path.join(self.wikidata, name, "wiki")
            os.makedirs(d)
            userdb.create_db(d, "pw")
            self.assertRefused(name, "切り替えられません")

    def test_書ける名前の判定(self):
        for name in ("_system", "sandbox", "1ev-c", "303WifiLC01", "1e3"):
            self.assertTrue(defaultswitch.writable_name(name), name)
        for name in ("a b", "123", "true", "-x", "a:b", "a#b", "すなば", ""):
            self.assertFalse(defaultswitch.writable_name(name), name)


if __name__ == "__main__":
    unittest.main()
