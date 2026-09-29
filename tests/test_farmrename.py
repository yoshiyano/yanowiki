#!/usr/bin/env python3
"""Wikiの名前を変えるところ（`wikilib.farmrename`）のテスト。

見ているのは**どこまで断るか**と、**既定Wikiの指定が置いていかれないか**の
2点である。名前はそのままURLなので、変えたあとに

  - 実体（`wikidata/<名前>/`）
  - 既定Wikiの指定（`config/server.yaml` の `farm.default`）

の2つが食い違うと、名前を付けずに開いたときの行き先が無くなる。

窓口（`/.admin/configwiki` の `op=rename`）のぶんも合わせて見ている——
**確かめの欄**（いまの名前の書き写し）を通らなければ何も起きないこと、
名前を変えた本人のログイン状態が続くこと。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_farmrename.py     （このファイルだけ）
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

from wikilib import auth, configui, farmrename, paths, userdb, wikiconfig  # noqa: E402
from wikilib.paths import (  # noqa: E402
    LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name,
)


class RenameTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="farmrename-")
        self.wikidata = os.path.join(self.work, "wikidata")
        os.makedirs(self.wikidata)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = self.wikidata
        self.kept_server = wikiconfig.SERVER_CONFIG_PATH
        self.server_path = os.path.join(self.work, "config", "server.yaml")
        os.makedirs(os.path.dirname(self.server_path))
        wikiconfig.SERVER_CONFIG_PATH = self.server_path
        self.make_wiki("sandbox")

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        wikiconfig.SERVER_CONFIG_PATH = self.kept_server
        shutil.rmtree(self.work, ignore_errors=True)

    def make_wiki(self, name):
        """最低限の中身を持つWikiを1つ置く。"""
        wiki_dir = os.path.join(self.wikidata, name, "wiki")
        os.makedirs(wiki_dir)
        with open(os.path.join(wiki_dir, "index.txt"), "w", encoding="utf-8") as f:
            f.write(f"* {name}\n")
        return wiki_dir

    def put_server_yaml(self, default):
        with open(self.server_path, "w", encoding="utf-8") as f:
            f.write("server:\n  port: 8619\nfarm:\n  default: "
                    f"{default}\n  allwiki: allwiki\n")

    def exists(self, name):
        return os.path.isdir(os.path.join(self.wikidata, name))


class TestProblem(RenameTestBase):
    """断るところ。**名前の決まりは新規作成と同じ**（WIKI_NAME_RE を共有）。"""

    def test_変えられる(self):
        self.assertIsNone(farmrename.rename_problem("sandbox", "suna"))

    def test_無いWikiは断る(self):
        self.assertIn("ありません", farmrename.rename_problem("nosuch", "suna"))

    def test_同じ名前は断る(self):
        self.assertIn("いまと同じ", farmrename.rename_problem("sandbox", "sandbox"))

    def test_空は断る(self):
        self.assertIn("入れてください", farmrename.rename_problem("sandbox", ""))

    def test_使えない字は断る(self):
        for name in ("すなば", "a b", "-start", "a/b", "../etc"):
            self.assertIsNotNone(farmrename.rename_problem("sandbox", name), name)

    def test_すでにある名前は断る(self):
        self.make_wiki("other")
        self.assertIn("すでにあります", farmrename.rename_problem("sandbox", "other"))

    def test_作れない名前のWikiは変えられない(self):
        # `_system` のような名前へは戻せないので、出る道だけを開けない
        self.make_wiki("_system")
        self.assertIsNotNone(farmrename.renamable("_system"))
        self.assertIn("変えられません", farmrename.rename_problem("_system", "system"))
        self.assertIsNone(farmrename.renamable("sandbox"))


class TestRename(RenameTestBase):
    """名前を変えたあと。"""

    def test_実体が移る(self):
        self.put_server_yaml("other")
        ok, message, new_default = farmrename.rename_farm(
            "sandbox", "suna", {"farm": {"default": "other"}})
        self.assertTrue(ok, message)
        self.assertTrue(self.exists("suna"))
        self.assertFalse(self.exists("sandbox"))
        self.assertIsNone(new_default)       # 既定Wikiではないので付け替えない

    def test_中身はそのまま(self):
        farmrename.rename_farm("sandbox", "suna", {"farm": {"default": "other"}})
        with open(os.path.join(self.wikidata, "suna", "wiki", "index.txt"),
                  encoding="utf-8") as f:
            self.assertEqual(f.read(), "* sandbox\n")   # 本文は書き換えない

    def test_既定Wikiなら指定も付け替える(self):
        self.put_server_yaml("sandbox")
        ok, message, new_default = farmrename.rename_farm(
            "sandbox", "suna", {"farm": {"default": "sandbox"}})
        self.assertTrue(ok, message)
        self.assertEqual(new_default, "suna")
        with open(self.server_path, encoding="utf-8") as f:
            self.assertIn("default: suna", f.read())

    def test_指定を書けなければ実体も戻す(self):
        # farm: の節が無い server.yaml（set_default_farm が書けない）
        with open(self.server_path, "w", encoding="utf-8") as f:
            f.write("server:\n  port: 8619\n")
        ok, message, _new_default = farmrename.rename_farm(
            "sandbox", "suna", {"farm": {"default": "sandbox"}})
        self.assertFalse(ok)
        self.assertIn("farm.default", message)
        # 実体は元の名前のまま（入口が無くなる組み合わせを残さない）
        self.assertTrue(self.exists("sandbox"))
        self.assertFalse(self.exists("suna"))

    def test_断られたときは何も動かない(self):
        ok, _message, _new = farmrename.rename_farm("sandbox", "すなば", {})
        self.assertFalse(ok)
        self.assertTrue(self.exists("sandbox"))


class TestRenameApi(RenameTestBase):
    """窓口（`/.admin/configwiki` の `op=rename`）。"""

    def setUp(self):
        super().setUp()
        self.wiki_dir = os.path.join(self.wikidata, "sandbox", "wiki")
        userdb.create_db(self.wiki_dir)
        self.kept_secret = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        self.put_server_yaml("other")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret
        super().tearDown()

    def call(self, payload, uid="admin", farm="sandbox"):
        body = json.dumps(payload).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        })
        if uid is not None:
            user = userdb.find_by_uid(self.wiki_dir, uid)
            token = auth.session_token(uid, farm, user["pw"])
            bottle.request.environ["HTTP_COOKIE"] = (
                f"{wiki_cookie_name(LOGIN_COOKIE, farm)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, farm)}={token}")
        return configui.render_configwiki_api(
            self.wiki_dir, {"farm": {"default": "other"}}, farm, True)

    def answer(self, out):
        raw = out.body if hasattr(out, "body") else out
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    def test_確かめが合わなければ何もしない(self):
        out = self.call({"op": "rename", "name": "suna", "confirm": "typo"})
        self.assertEqual(out.status_code, 400)
        self.assertIn("書き写して", self.answer(out)["message"])
        self.assertTrue(self.exists("sandbox"))

    def test_未ログインは403(self):
        out = self.call({"op": "rename", "name": "suna", "confirm": "sandbox"},
                        uid=None)
        self.assertEqual(out.status_code, 403)
        self.assertTrue(self.exists("sandbox"))

    def test_通れば新しいURLを返す(self):
        out = self.call({"op": "rename", "name": "suna", "confirm": "sandbox"})
        got = self.answer(out)
        self.assertTrue(got["ok"], got)
        self.assertTrue(self.exists("suna"))
        self.assertEqual(got["url"],
                         f"/=suna/{configui.CONFIGWIKI_URLPATH}?tab={configui.WIKINAME_TAB}")

    def test_本人のログインは続く(self):
        # 名前を変えた本人が、その場で入り直しにならないこと
        out = self.call({"op": "rename", "name": "suna", "confirm": "sandbox"})
        cookies = [v for k, v in out.headerlist if k == "Set-Cookie"]
        put = [c for c in cookies if c.startswith(
            wiki_cookie_name(LOGIN_COOKIE, "suna") + "=")]
        self.assertTrue(put, cookies)
        self.assertIn("admin", put[0])
        self.assertIn("Path=/=suna", put[0])


class TestPasswordSalt(RenameTestBase):
    """**名前を変えてもパスワードが通る**こと（Wiki設計者の指示、2026-09-21）。

    パスワードのハッシュには塩（既定はWiki名）が混ざる。塩を書いていないWikiは、
    名前が変わると全員のパスワードが通らなくなるので、移す前に旧名を
    `account.pw_salt` へ固定する（`farmrename.pin_pw_salt`）。"""

    def make_with_account(self, name="sandbox"):
        wiki_dir = os.path.join(self.wikidata, name, "wiki")
        userdb.create_db(wiki_dir, "adminpw")
        userdb.add_user(wiki_dir, "alice",
                        userdb.hash_password(wiki_dir, "alice", "alicepw"), "アリス")
        return wiki_dir

    def renamed_dir(self, new):
        return os.path.join(self.wikidata, new, "wiki")

    def test_名前を変えてもパスワードが通る(self):
        self.make_with_account()
        ok, _message, _new = farmrename.rename_farm("sandbox", "suna", {})
        self.assertTrue(ok)
        moved = self.renamed_dir("suna")
        self.assertIsNotNone(userdb.authenticate(moved, "alice", "alicepw"))
        self.assertIsNotNone(userdb.authenticate(moved, "admin", "adminpw"))

    def test_旧名が塩として設定に残る(self):
        self.make_with_account()
        farmrename.rename_farm("sandbox", "suna", {})
        moved = self.renamed_dir("suna")
        self.assertEqual(userdb.password_salt(moved), "sandbox")
        data = wikiconfig.read_yaml(wikiconfig.farm_config_path(moved))
        self.assertEqual(data["account"]["pw_salt"], "sandbox")

    def test_続けて名前を変えても通る(self):
        self.make_with_account()
        farmrename.rename_farm("sandbox", "suna", {})
        farmrename.rename_farm("suna", "hama", {})
        self.assertIsNotNone(userdb.authenticate(self.renamed_dir("hama"), "alice", "alicepw"))
        self.assertEqual(userdb.password_salt(self.renamed_dir("hama")), "sandbox")

    def test_塩を書いてあるWikiは書き換えない(self):
        wiki_dir = self.make_with_account()
        wikiconfig.save_farm_config(wiki_dir, {"account": {"pw_salt": "mine"}})
        # 塩を書いたあとで作ったアカウントのハッシュ
        userdb.add_user(wiki_dir, "bob", userdb.hash_password(wiki_dir, "bob", "bobpw"), "")
        farmrename.rename_farm("sandbox", "suna", {})
        moved = self.renamed_dir("suna")
        self.assertEqual(userdb.password_salt(moved), "mine")
        self.assertIsNotNone(userdb.authenticate(moved, "bob", "bobpw"))

    def test_設定に書いてある他の項目は残る(self):
        wiki_dir = self.make_with_account()
        wikiconfig.save_farm_config(wiki_dir, {"theme": {"site_title": "そのまま"}})
        farmrename.rename_farm("sandbox", "suna", {})
        data = wikiconfig.read_yaml(wikiconfig.farm_config_path(self.renamed_dir("suna")))
        self.assertEqual(data["theme"]["site_title"], "そのまま")
        self.assertEqual(data["account"]["pw_salt"], "sandbox")

    def test_アカウントの記録が無いWikiは何も書かない(self):
        ok, _message, _new = farmrename.rename_farm("sandbox", "suna", {})
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(
            wikiconfig.farm_config_path(self.renamed_dir("suna"))))

    def test_塩を固定できなければ名前を変えない(self):
        from unittest import mock
        self.make_with_account()
        with mock.patch.object(farmrename, "save_farm_config",
                               return_value=(False, False, "書けません")):
            ok, message, _new = farmrename.rename_farm("sandbox", "suna", {})
        self.assertFalse(ok)
        self.assertIn("名前は変えていません", message)
        self.assertTrue(self.exists("sandbox"))
        self.assertFalse(self.exists("suna"))


if __name__ == "__main__":
    unittest.main()
