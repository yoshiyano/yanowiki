#!/usr/bin/env python3
"""編集の権限（権限の既定の行 `*:R:g:any`・`*:W:g:all`）のテスト。

**ログインしていない閲覧者から編集権限を取り上げる**には、権限の既定の行（`*`）を
置く。以前は設定 `edit.no_onlooker_permission` だったが、Wiki設計者の指示
（2026-09-21）で削除した。既定の行が無いWikiは、未ログインも編集できる——Wikiを
作った直後はアカウントがまだ無く、締めると誰も何も書けないため。ここでは次を確かめる。

  - 旧設定が雛形と設定画面から無くなっていること
  - 編集の権限が無ければ、ページの表示が `editable=False` で描かれる
    （テーマはこれ1つで「編集・履歴・リネーム」もホットキーもセクション編集の
    目印も落とす）
  - 編集画面（`cmd=edit` のPOST）とセクション編集は、権限が無ければ403で断る

以下、テストの中で「締める」と書いているのは、既定の行を置くこと。

判定そのもの（誰に `W`/`R`/`-` が返るか）は `tests/test_pageprivilege.py` が見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_editprivilege.py     （このファイルだけ）
"""
import io
import json
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
from bottle import HTTPResponse  # noqa: E402

from wikilib import auth, editor, pagedb, paths, privilege_records, userdb, views  # noqa: E402
from wikilib import configui, wikiconfig  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, farm_config_path, wiki_cookie_name  # noqa: E402

FARM = "testwiki"
BODY = "# 題名\n\n本文です。\n\n## 見出し\n\n続きです。\n"


class EditPrivilegeTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="editprivilege-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        os.makedirs(os.path.join(self.work, "wikidata", FARM, "config"), exist_ok=True)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        bottle.request.bind({})
        # 平文とDBの両方に置く（表示はDB、編集は平文を読む）
        with open(os.path.join(self.wiki_dir, "Open.md"), "w", encoding="utf-8") as f:
            f.write(BODY)
        self.assertTrue(pagedb.record_page(self.wiki_dir, "Open", ".md", BODY))

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def tighten(self, tight):
        """既定の行（`*:R:g:any`・`*:W:g:all`）を置く／外す。

        置くと、未ログインは閲覧だけ・ログインした登録ユーザは編集できる、になる。
        外すのは既定の行だけで、ほかの行（テストが足したもの）は残す。"""
        if tight:
            self.rule("*", "R", "g:any")
            self.rule("*", "W", "g:all")
        else:
            privilege_records.save(self.wiki_dir, [
                e for e in privilege_records.load(self.wiki_dir)
                if e["page"] != privilege_records.WILDCARD])

    def write_config(self, tight):
        """これまでの呼びかたのまま、既定の行の有無を切り替える。"""
        self.tighten(tight)

    def config(self, tight=False):
        """画面の関数へ渡す設定（もう権限は含まない）。呼ぶと既定の行も切り替える。"""
        self.tighten(tight)
        return {}

    def rule(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)

    def login_as(self, uid, environ=None):
        env = dict(environ or {})
        if uid is not None:
            user = userdb.find_by_uid(self.wiki_dir, uid)
            token = auth.session_token(uid, FARM, user["pw"])
            env["HTTP_COOKIE"] = (
                f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")
        bottle.request.bind(env)

    def post_env(self, **fields):
        data = urlencode(fields).encode("utf-8")
        return {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(data)),
            "wsgi.input": io.BytesIO(data),
        }


class TestRemovedSetting(EditPrivilegeTestBase):
    """旧設定 `edit.no_onlooker_permission` は無くなった（2026-09-21）。"""

    def test_雛形に無い(self):
        example = wikiconfig.read_yaml(wikiconfig.example_of(paths.CONFIG_PATH))
        self.assertNotIn("no_onlooker_permission", example["edit"])

    def test_設定画面に無い(self):
        self.assertNotIn("edit.no_onlooker_permission", configui.fields_by_path())

    def test_読む関数も無い(self):
        self.assertFalse(hasattr(wikiconfig, "no_onlooker_permission"))

    def test_書いてあっても効かない(self):
        # 残っている設定ファイルに書いてあっても、判定は既定の行だけで決まる
        with open(farm_config_path(self.wiki_dir), "w", encoding="utf-8") as f:
            f.write("edit:\n  no_onlooker_permission: true\n")
        self.assertTrue(auth.page_privilege(self.wiki_dir, None).check("Open") == "W")


class TestRemovedShowEdit(EditPrivilegeTestBase):
    """旧設定 `theme.show_edit`・`theme.edit_hotkey` は無くなった（2026-09-29。編集の入口は
    権限で出し分ける）。"""

    def test_雛形に無い(self):
        example = wikiconfig.read_yaml(wikiconfig.example_of(paths.CONFIG_PATH))
        for key in ("show_edit", "edit_hotkey"):
            self.assertNotIn(key, example["theme"])

    def test_設定画面に無い(self):
        for path in ("theme.show_edit", "theme.edit_hotkey"):
            self.assertNotIn(path, configui.fields_by_path())

    def test_読む関数も無い(self):
        from wikilib import themes
        self.assertFalse(hasattr(themes, "show_edit"))
        self.assertFalse(hasattr(themes, "edit_hotkey_enabled"))

    def test_書いてあっても効かない(self):
        # 残っている設定ファイルに show_edit: false があっても、入口は権限だけで決まる
        with open(farm_config_path(self.wiki_dir), "w", encoding="utf-8") as f:
            f.write("theme:\n  show_edit: false\n")
        self.write_config(False)
        self.assertTrue(TestPageView.editable_for(self, None))

    def test_編集にはいつもAltEの目印が付く(self):
        from wikilib.themes import common_menu_html
        html = str(common_menu_html("/=w", "/=w/.login", "/=w", "Open", True))
        self.assertIn('data-hotkey="edit"', html)
        self.assertNotIn("編集", str(common_menu_html("/=w", "/=w/.login", "/=w", "Open", False)))


class TestNoPageCreate(EditPrivilegeTestBase):
    """404 の「このページを作る」は、そのページの編集の権限で出し分ける。"""

    def create_shown(self, uid, page="NewPage"):
        self.login_as(uid)
        with mock.patch.object(views, "render_theme",
                               return_value=HTTPResponse(body="RENDERED")) as spy:
            views.render_no_page(self.wiki_dir, {}, FARM, page, False)
        self.assertTrue(spy.called)
        return "このページを作る" in repr(spy.call_args)

    def test_既定では未ログインにも出す(self):
        self.write_config(False)
        self.assertTrue(self.create_shown(None))

    def test_締めると未ログインには出さない(self):
        self.write_config(True)
        self.assertFalse(self.create_shown(None))
        self.assertTrue(self.create_shown("alice"))

    def test_そのページを編集できない人には出さない(self):
        self.write_config(False)
        self.rule("NewPage", "W", "bob")
        self.assertFalse(self.create_shown("alice"))
        self.assertTrue(self.create_shown("bob"))


class TestPageView(EditPrivilegeTestBase):
    """ページの表示。編集の入口を出すかどうかは `editable` に集約されている。"""

    def editable_for(self, uid):
        """そのアカウントでページを開き、テーマへ渡された `editable` を返す。"""
        self.login_as(uid)
        with mock.patch.object(views, "render_with_theme",
                               return_value=HTTPResponse(body="RENDERED")) as spy, \
                mock.patch.object(views, "record_access"), \
                mock.patch.object(views, "maybe_backup"):
            views.render_page(self.wiki_dir, {}, FARM, "Open", False)
        self.assertTrue(spy.called)
        return spy.call_args.kwargs["editable"]

    def test_既定では未ログインでも編集の入口を出す(self):
        self.write_config(False)
        self.assertTrue(self.editable_for(None))

    def test_締めると未ログインには出さない(self):
        self.write_config(True)
        self.assertFalse(self.editable_for(None))

    def test_締めてもログイン中には出す(self):
        self.write_config(True)
        self.assertTrue(self.editable_for("alice"))

    def test_閲覧だけのページには出さない(self):
        # 読めるが、W の行には載っていない人（W は bob だけ。2026-09-21から、W の指定が
        # 無ければ読める人は書ける。読むだけにするには W の行で絞る）
        self.rule("Open", "R", "alice")
        self.rule("Open", "W", "bob")
        self.write_config(False)
        self.assertFalse(self.editable_for("alice"))


class TestEditScreen(EditPrivilegeTestBase):
    """編集画面（`cmd=edit` のPOST）。画面から消すだけでなく入口も断る。"""

    def open_edit(self, uid, no_onlooker, page="Open"):
        self.login_as(uid, self.post_env(cmd="edit"))
        with mock.patch.object(editor, "save_page") as save:
            res = editor.render_edit(self.wiki_dir, self.config(no_onlooker),
                                     FARM, page, False)
        raw = res.body if hasattr(res, "body") else res
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return res, html, save.called

    def test_締めると未ログインは403(self):
        res, html, saved = self.open_edit(None, True)
        self.assertEqual(res.status_code, 403)
        self.assertIn("このページを編集する権限がありません", html)
        self.assertIn("ログインしてください", html)
        self.assertFalse(saved)

    def test_既定では未ログインでも開ける(self):
        res, _html, _saved = self.open_edit(None, False)
        self.assertNotEqual(res.status_code, 403)

    def test_締めてもログイン中は開ける(self):
        res, _html, _saved = self.open_edit("alice", True)
        self.assertNotEqual(res.status_code, 403)

    def test_閲覧だけのページは403(self):
        self.rule("Open", "R", "alice")
        self.rule("Open", "W", "bob")           # alice は読めるが、書ける人ではない
        res, html, _saved = self.open_edit("alice", False)
        self.assertEqual(res.status_code, 403)
        self.assertIn("ログインし直す", html)

    def test_保存も断る(self):
        self.login_as(None, self.post_env(cmd="save", source="書き換え", origin=""))
        with mock.patch.object(editor, "save_page") as save:
            res = editor.render_edit(self.wiki_dir, self.config(True), FARM, "Open", False)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(save.called)
        with open(os.path.join(self.wiki_dir, "Open.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), BODY)


class TestSection(EditPrivilegeTestBase):
    """セクション編集（`/.section/<ページパス>`）。取り出しも保存も断る。"""

    def test_締めると取り出しを断る(self):
        self.login_as(None, {"REQUEST_METHOD": "GET"})
        res = editor.serve_section(self.wiki_dir, self.config(True), FARM, "Open", False)
        self.assertEqual(res.status_code, 403)
        self.assertIn("編集する権限がありません", res.body)

    def test_既定では取り出せる(self):
        self.login_as(None, {"REQUEST_METHOD": "GET"})
        res = editor.serve_section(self.wiki_dir, self.config(False), FARM, "Open", False)
        self.assertNotEqual(res.status_code, 403)

    def test_締めると保存も断る(self):
        self.login_as(None, self.post_env(source="書き換え", origin=""))
        with mock.patch.object(editor, "save_page") as save:
            res = editor.serve_section(self.wiki_dir, self.config(True), FARM, "Open", False)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(save.called)


class TestRename(EditPrivilegeTestBase):
    """名前の変更・移動（ファイル一覧。`pagerename.unwritable_pages`）。動くページすべてに
    `W` が要る。以前は `/.rename` の画面を通して試していた（画面は 2026-09-29 に外した）。"""

    def setUp(self):
        super().setUp()
        # フォルダ Tech（入口 Tech/index）と、その中のページ Tech/Secret
        os.makedirs(os.path.join(self.wiki_dir, "Tech"))
        for subpath in ("Tech/index", "Tech/Secret"):
            with open(os.path.join(self.wiki_dir, subpath + ".md"), "w", encoding="utf-8") as f:
                f.write(BODY)
            self.assertTrue(pagedb.record_page(self.wiki_dir, subpath, ".md", BODY))

    def unwritable(self, uid, tight, subpath="Open"):
        from wikilib import pagerename
        self.config(tight)
        return pagerename.unwritable_pages(self.wiki_dir, subpath,
                                           auth.page_privilege(self.wiki_dir, uid))

    def test_締めると未ログインは変えられない(self):
        self.assertEqual(self.unwritable(None, True), ["Open"])

    def test_既定では未ログインでも変えられる(self):
        self.assertEqual(self.unwritable(None, False), [])

    def test_一緒に動くページが編集できなければ断る(self):
        # フォルダ Tech の入口は編集できるが、中の Tech/Secret は alice には閲覧だけ
        # （W は bob だけ。W の指定が無ければ読める人は書ける）
        self.rule("Tech/Secret", "R", "alice")
        self.rule("Tech/Secret", "W", "bob")
        self.assertEqual(self.unwritable("alice", False, "Tech/index"), ["Tech/Secret"])

    def test_中のページも編集できるなら変えられる(self):
        self.rule("Tech/Secret", "W", "alice")
        self.assertEqual(self.unwritable("alice", False, "Tech/index"), [])


class TestConflict(EditPrivilegeTestBase):
    """競合の統合（`/.conflict/<ページパス>`）。統合結果を保存する画面。"""

    def open_conflict(self, uid, no_onlooker):
        from wikilib import conflict
        self.login_as(uid, {"REQUEST_METHOD": "GET"})
        res = conflict.render_conflict(self.wiki_dir, self.config(no_onlooker),
                                       FARM, "Open", False)
        raw = res.body if hasattr(res, "body") else res
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return res, html

    def test_締めると未ログインは403(self):
        res, html = self.open_conflict(None, True)
        self.assertEqual(res.status_code, 403)
        self.assertIn("このページを編集する権限がありません", html)
        self.assertNotIn("本文です", html)   # いまの本文を見せない

    def test_権限があれば通す(self):
        # 書きかけが無いので303でページへ戻る（403ではない）
        res, _html = self.open_conflict(None, False)
        self.assertEqual(res.status_code, 303)


class TestPreviewDiff(EditPrivilegeTestBase):
    """プレビューと差分（`POST <ページパス>?cmd=preview|diff`）。"""

    def raw_post(self, uid, body, query):
        """生テキストを本体に載せたPOST（編集画面のJSと同じ送りかた）。"""
        data = body.encode("utf-8")
        self.login_as(uid, {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "text/plain;charset=UTF-8",
            "CONTENT_LENGTH": str(len(data)),
            "QUERY_STRING": query,
            "wsgi.input": io.BytesIO(data),
        })

    def call(self, which, uid, no_onlooker, body="書きかけの本文"):
        self.raw_post(uid, body, "cmd=" + which)
        fn = editor.render_preview if which == "preview" else editor.render_diff
        res = fn(self.wiki_dir, self.config(no_onlooker), FARM, False, "Open")
        raw = res.body if hasattr(res, "body") else res
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return res, html

    def test_締めると未ログインは403(self):
        for which in ("preview", "diff"):
            with self.subTest(which=which):
                res, html = self.call(which, None, True)
                self.assertEqual(res.status_code, 403)
                self.assertIn("編集する権限がありません", html)
                self.assertNotIn("書きかけの本文", html)

    def test_既定では未ログインでも使える(self):
        res, html = self.call("preview", None, False)
        self.assertEqual(res.status_code, 200)
        self.assertIn("書きかけの本文", html)
        res, _html = self.call("diff", None, False)
        self.assertEqual(res.status_code, 200)

    def test_閲覧だけのページでは断る(self):
        self.rule("Open", "R", "alice")
        self.rule("Open", "W", "bob")           # alice は読めるが、書ける人ではない
        for which in ("preview", "diff"):
            with self.subTest(which=which):
                res, html = self.call(which, "alice", False)
                self.assertEqual(res.status_code, 403)
                # 差分は保存されている本文を読むので、それが出ていないことも見る
                self.assertNotIn("本文です", html)


class TestPreviewPluginAssets(TestPreviewDiff):
    """プレビューの応答ヘッダーに、描いた断片が使ったプラグインの資材が載る。
    節編集のプレビュー（theme/common.js）が、ページにまだ無いものを後から読み込む。"""

    def assets(self, body):
        res, _html = self.call("preview", None, False, body)
        self.assertEqual(res.status_code, 200)
        return (json.loads(res.headers[editor.PREVIEW_STYLES_HEADER]),
                json.loads(res.headers[editor.PREVIEW_SCRIPTS_HEADER]))

    def test_使ったプラグインの資材が載る(self):
        styles, scripts = self.assets("&katex(){x^2};\n")
        self.assertTrue(any(u.endswith("/katex.css") for u in styles), styles)
        self.assertTrue(any(u.endswith("/katex.js") for u in scripts), scripts)

    def test_プラグインを使わなければ空(self):
        self.assertEqual(self.assets("ただの本文\n"), ([], []))

    # 親クラスの試験は繰り返さない
    test_締めると未ログインは403 = None
    test_既定では未ログインでも使える = None
    test_閲覧だけのページでは断る = None


if __name__ == "__main__":
    unittest.main()
