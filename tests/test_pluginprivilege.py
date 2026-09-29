#!/usr/bin/env python3
"""プラグインが閲覧の権限（`W`/`R`/`-`）に従うことのテスト。

**各プラグインでもアクセス権に従えるようにした**（Wiki設計者の指示、2026-09-15）。
ここでは次を確かめる。

  - `PluginContext.privilege` が、いまの閲覧者（cookie・成り代わり）の判定器を返す
  - 本文を出す経路は `-` なら本文を出さない
      `#include`・`#ls` の読み込み表示・`page_headings`（`#contents`）・テーマのメニュー
  - 書き込みの経路は `-` なら403で断り、ページを読みにも行かない。`R` は通す
      `#comment`・`#vote`・`#tasklist` の `_action`

プラグインは本物（`plugin/*.py`）をファイルから読み込んで呼ぶ。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pluginprivilege.py     （このファイルだけ）
"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import auth, pagedb, paths, privilege_records, themes, userdb  # noqa: E402
from wikilib.auth import PAGE_NONE, PAGE_READ, PAGE_WRITE, act_as, page_privilege  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, farm_plugin_dir, wiki_cookie_name  # noqa: E402
from wikilib.plugins import PluginArgumentError, PluginContext, build_markdown_renderer  # noqa: E402

FARM = "testwiki"
SECRET_BODY = "# 秘密の題名\n\n## 秘密の見出し\n\n秘密の本文です。\n"


def load_plugin(name):
    """`plugin/<name>.py` を、試験用の名前で読み込む。"""
    spec = importlib.util.spec_from_file_location(
        f"plugin_under_test_{name}", os.path.join(ROOT, "plugin", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PluginPrivilegeTestBase(unittest.TestCase):
    """`Secret` は alice だけが読める（R）。`Open` は設定の無いページ。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pluginprivilege-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        bottle.request.bind({})

        ok, message, _ = privilege_records.put(self.wiki_dir, "Secret", "R", "alice")
        self.assertTrue(ok, message)
        for subpath, body in (("Secret", SECRET_BODY), ("Open", "# 開いた題名\n\n開いた本文\n")):
            self.assertTrue(pagedb.record_page(self.wiki_dir, subpath, ".md", body))
            toc = [{"level": 1, "id": "h", "title": subpath + "の見出し"}]
            self.assertTrue(pagedb.record_page_info(self.wiki_dir, subpath, subpath, toc, []))

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def context(self, page="Top"):
        return PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page=page)


class TestContextPrivilege(PluginPrivilegeTestBase):
    """`PluginContext.privilege`。"""

    def test_成り代わった相手で判定する(self):
        with act_as("alice"):
            self.assertEqual(self.context().privilege.check("Secret"), PAGE_WRITE)
        with act_as("bob"):
            self.assertEqual(self.context().privilege.check("Secret"), PAGE_NONE)
            self.assertEqual(self.context().privilege.check("Open"), PAGE_WRITE)

    def test_未ログインは設定の無いページだけ扱える(self):
        # 設定の無いページは既定で編集もできる（既定の行 `*` が無いWiki）
        privilege = self.context().privilege
        self.assertEqual(privilege.check("Secret"), PAGE_NONE)
        self.assertEqual(privilege.check("Open"), PAGE_WRITE)

    def test_cookieのログインにも従い_farmの無いcontextでも動く(self):
        user = userdb.find_by_uid(self.wiki_dir, "alice")
        token = auth.session_token("alice", FARM, user["pw"])
        bottle.request.bind({"HTTP_COOKIE":
                             f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}=alice; "
                             f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}"})
        bare = PluginContext(wiki_dir=self.wiki_dir, page="Top")
        self.assertEqual(bare.privilege.check("Secret"), PAGE_WRITE)

    def test_同じcontextでは作り直さない(self):
        context = self.context()
        self.assertIs(context.privilege, context.privilege)


class TestReadPaths(PluginPrivilegeTestBase):
    """本文を出す経路。"""

    def test_page_headingsは読めなければ空(self):
        with act_as("bob"):
            self.assertEqual(self.context("Secret").page_headings(), [])
        with act_as("alice"):
            self.assertEqual(self.context("Secret").page_headings()[0]["title"], "Secretの見出し")

    def test_メニューは読めなければ出さない(self):
        with act_as("bob"):
            self.assertEqual(themes.render_menu(None, self.wiki_dir, "", "Secret"), "")
        with act_as("alice"):
            engine = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir))
            self.assertIn("秘密の本文", themes.render_menu(engine, self.wiki_dir, "", "Secret"))

    def test_includeは読めなければ本文の代わりに案内を出す(self):
        include = load_plugin("include")
        with act_as("bob"):
            context = self.context()
            html = include._convert({"page": "Secret", "title": "title"}, None, context)
        self.assertIn("このページを閲覧する権限がありません: Secret", html)
        self.assertNotIn("秘密の本文", html)
        self.assertNotIn("include-title", html)
        self.assertEqual(context._include_state["count"], 1)   # 差し込み件数に数えない

    def test_includeは読めれば差し込む(self):
        include = load_plugin("include")
        with act_as("alice"):
            html = include._convert({"page": "Secret", "title": "notitle"}, None, self.context())
        self.assertIn("秘密の本文", html)

    def test_lsの一覧に読めないページは並ばない(self):
        # 一覧そのもの（`pagelist` 経由）。読み込み表示とは別の経路
        ls = load_plugin("ls")
        opts = {"folder": "/", "recursive": False, "sort": "FNAME",
                "format_md": "BOTH", "format_pk": "BOTH", "ajaxview": False,
                "natural": False, "exclude": None}
        with act_as("bob"):
            html = ls._convert(opts, None, self.context())
        self.assertIn("Open", html)
        self.assertNotIn("Secret", html)
        with act_as("alice"):
            self.assertIn("Secret", ls._convert(opts, None, self.context()))

    def test_lsの読み込み表示は読めなければ断る(self):
        ls = load_plugin("ls")
        bottle.request.bind({"REQUEST_METHOD": "GET", "QUERY_STRING": "page=Secret"})
        with act_as("bob"):
            html = ls._action(self.context())
        self.assertIn("このページを閲覧する権限がありません", html)
        self.assertNotIn("秘密の本文", html)
        with act_as("alice"):
            self.assertIn("秘密の本文", ls._action(self.context()))


class TestWriteActions(PluginPrivilegeTestBase):
    """書き込みの経路。`#comment`・`#vote` は `-` だけを断り `R` は通す。
    `#tasklist` は `W` が無ければ断る（Wiki設計者の指示、2026-09-25）。"""

    def post(self, **fields):
        data = urlencode(fields).encode("utf-8")
        bottle.request.bind({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(data)),
            "wsgi.input": io.BytesIO(data),
        })

    def call(self, name, uid, fields):
        """`_action` を呼ぶ。`(戻り値か例外, ページを読みに行ったか, 保存したか)`。"""
        module = load_plugin(name)
        self.post(**fields)
        with mock.patch.object(module, "resolve_page_ref",
                               wraps=module.resolve_page_ref) as resolve, \
                mock.patch.object(module, "save_page") as save, \
                (act_as(uid) if uid else mock.MagicMock()):
            try:
                result = module._action(self.context())
            except PluginArgumentError as exc:
                result = exc
        return result, resolve.called, save.called

    FORMS = {
        "comment": {"msg": "こんにちは", "comment_no": "0"},
        "vote": {"vote_no": "0", "index": "0"},
        "tasklist": {"line": "0", "checked": "1"},
    }

    def test_読めないページへの書き込みは403で断る(self):
        for name, form in self.FORMS.items():
            for uid in ("bob", None):
                with self.subTest(plugin=name, uid=uid):
                    result, read, saved = self.call(name, uid, dict(form, page="Secret"))
                    self.assertEqual(getattr(result, "status_code", None), 403)
                    self.assertFalse(read)
                    self.assertFalse(saved)

    def test_Rのページへの書き込みは通す(self):
        # alice は Secret が R、未ログインは Open が R。どちらも権限では断らない
        # （平文ファイルが無いので、その先の「まだありません」で止まる）
        for name, form in self.FORMS.items():
            if name == "tasklist":
                continue  # 下の試験
            for uid, page in (("alice", "Secret"), (None, "Open")):
                with self.subTest(plugin=name, uid=uid, page=page):
                    result, read, _saved = self.call(name, uid, dict(form, page=page))
                    self.assertNotEqual(getattr(result, "status_code", None), 403)
                    self.assertTrue(read)

    def test_tasklistは編集の権限が無ければ断る(self):
        form = self.FORMS["tasklist"]
        # Open は誰でも読めるが、書けるのは alice だけ
        ok, message, _ = privilege_records.put(self.wiki_dir, "Open", "W", "alice")
        self.assertTrue(ok, message)
        for uid in (None, "bob"):
            with self.subTest(uid=uid):
                result, read, saved = self.call("tasklist", uid, dict(form, page="Open"))
                self.assertEqual(getattr(result, "status_code", None), 403)
                self.assertFalse(read)
                self.assertFalse(saved)
        result, read, _saved = self.call("tasklist", "alice", dict(form, page="Open"))
        self.assertNotEqual(getattr(result, "status_code", None), 403)
        self.assertTrue(read)


class TestTasklistRender(PluginPrivilegeTestBase):
    """`#tasklist(sync)` のページでも、編集の権限が無い人には押せる形で出さない。"""

    TEXT = "#tasklist(sync)\n\n- [ ] やること\n"

    def render(self, uid):
        context = self.context("Open")
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        with (act_as(uid) if uid else mock.MagicMock()):   # None は未ログイン
            return md.render(self.TEXT, {"wiki": context})

    def test_編集の権限で出し分ける(self):
        ok, message, _ = privilege_records.put(self.wiki_dir, "Open", "W", "alice")
        self.assertTrue(ok, message)
        html = self.render("alice")
        self.assertIn("data-api=", html)
        self.assertNotIn("data-noauth", html)
        for uid in (None, "bob"):
            with self.subTest(uid=uid):
                html = self.render(uid)
                self.assertNotIn("data-api=", html)
                self.assertIn("data-noauth", html)


class TestAuthPluginsToPrivilege(PluginPrivilegeTestBase):
    """`#readauth`・`#writeauth` が実際に書いた記録（`config/privileges.plugin`）が、
    `auth.page_privilege` の判定に反映されること（本体とプラグインをまたぐ統合の
    確認。Wiki設計者の指示、2026-09-23。手で書く `config/privileges` より優先
    されるが、緩和する方向には働かない——ロジックそのものの網羅的なテストは
    `test_pageprivilege.py` の `TestPluginRecords` にある）。"""

    def setUp(self):
        super().setUp()
        # `_authcommon.run` は「実在するページ」を平文ファイルの有無で見る
        # （`resolve_page_ref`。`pagedb.record_page` はDBだけで、平文ファイルは
        # 別に要る）。setUp で作った "Open" の平文ファイルを、ここで足す
        ref = paths.resolve_page_ref(self.wiki_dir, "Open")
        os.makedirs(os.path.dirname(ref.path), exist_ok=True)
        with open(ref.path, "w", encoding="utf-8") as f:
            f.write("# 開いた題名\n\n開いた本文\n")

    def call(self, name, uid, users, page="Open"):
        module = load_plugin(name)
        with act_as(uid):
            return module._convert({"users": users}, None, self.context(page))

    def test_readauthが書いた記録で絞られる(self):
        self.call("readauth", "alice", "alice")
        self.assertEqual(page_privilege(self.wiki_dir, "alice").check("Open"), PAGE_WRITE)
        self.assertEqual(page_privilege(self.wiki_dir, "bob").check("Open"), PAGE_NONE)

    def test_writeauthが書いた記録は読みには効かない(self):
        self.call("writeauth", "alice", "alice")
        self.assertEqual(page_privilege(self.wiki_dir, "alice").check("Open"), PAGE_WRITE)
        self.assertEqual(page_privilege(self.wiki_dir, "bob").check("Open"), PAGE_READ)

    def test_システムの規則より優先しつつ緩和はしない(self):
        # config/privileges 側は誰でも読める設定。#readauth はそれより絞る
        ok, message, _ = privilege_records.put(self.wiki_dir, "Open", "R", "g:any")
        self.assertTrue(ok, message)
        self.call("readauth", "alice", "alice")
        self.assertEqual(page_privilege(self.wiki_dir, "alice").check("Open"), PAGE_WRITE)
        self.assertEqual(page_privilege(self.wiki_dir, "bob").check("Open"), PAGE_NONE)

    def test_空呼びで記録を消せば_systemの規則に戻る(self):
        ok, message, _ = privilege_records.put(self.wiki_dir, "Open", "R", "alice")
        self.assertTrue(ok, message)
        self.call("readauth", "alice", "alice")
        self.call("readauth", "alice", "")   # 空呼び。プラグインの記録だけ消える
        self.assertEqual(page_privilege(self.wiki_dir, "bob").check("Open"), PAGE_NONE)   # system は残る


if __name__ == "__main__":
    unittest.main()
