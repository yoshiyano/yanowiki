#!/usr/bin/env python3
"""ページの表示（`wikilib.views.render_page`）が閲覧の権限を見ることのテスト。

**権限は `published_ref` が返す `ref.privilege` で見る**（Wiki設計者の指示、
2026-09-15。以前は読み出す前に `auth.page_privilege` を別に呼んでいた）。
`-` のときも ref には本文が入ってくるので、ここでは**描画しないこと・本文を
出さないこと**を確かめる。

  - 閲覧の権限が無ければ 403 で「閲覧する権限がありません」が出る
  - そのとき本文を描かず、本文・題名も出さない
  - 読めない名前なら、無いページでも403（作成の誘いを出さない）
  - 権限があれば、これまでどおりページを描く

`ref.privilege` の中身そのものは `tests/test_publishedref.py`、判定（誰に
`W`/`R`/`-` が返るか）は `tests/test_pageprivilege.py` が見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pageview.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402
from bottle import HTTPResponse  # noqa: E402

from wikilib import auth, pagedb, paths, privilege_records, userdb, views  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

FARM = "testwiki"
SECRET_BODY = "# 秘密の題名\n\n秘密の本文です。\n"


class PageViewTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pageview-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.environ.clear()
        shutil.rmtree(self.work, ignore_errors=True)

    def rule(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)

    def publish(self, subpath, body=SECRET_BODY):
        """公開された内容（DB）にページを置く。平文ファイルは置かない。"""
        self.assertTrue(pagedb.record_page(self.wiki_dir, subpath, ".md", body))

    def login_as(self, uid):
        bottle.request.environ.clear()
        if uid is None:
            return
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")

    def open(self, pagepath, uid):
        """そのアカウントでページを開く。`(応答, HTML, 本文を描いたか)`。

        ページを描く `render_with_theme` は、渡された本文をそのまま返す偽物に
        差し替える。**権限を通ったかどうかは、これが呼ばれたかで分かる。**
        アクセスの記録とDBの控えも止めておく（テストの外に書かないため）。"""
        self.login_as(uid)

        def fake_render(wiki_dir, config, farm, pagepath, body, *args, **kwargs):
            return HTTPResponse(body="RENDERED\n" + body, status=200)

        with mock.patch.object(views, "render_with_theme", side_effect=fake_render) as spy, \
                mock.patch.object(views, "record_access"), \
                mock.patch.object(views, "maybe_backup"):
            res = views.render_page(self.wiki_dir, {}, FARM, pagepath, False)
        raw = res.body if hasattr(res, "body") else res
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return res, html, spy.called


class TestDenied(PageViewTestBase):
    """閲覧の権限が無いとき。"""

    def setUp(self):
        super().setUp()
        self.rule("Tech/Secret", "R", "alice")
        self.publish("Tech/Secret")

    def test_403で権限が無いことを出す(self):
        res, html, _ = self.open("Tech/Secret", "bob")
        self.assertEqual(res.status_code, 403)
        self.assertIn("このページを閲覧する権限がありません", html)

    def test_本文を描かず出さない(self):
        _res, html, rendered = self.open("Tech/Secret", "bob")
        self.assertFalse(rendered)
        self.assertNotIn("秘密の本文", html)
        self.assertNotIn("秘密の題名", html)

    def test_未ログインでも同じ(self):
        res, html, rendered = self.open("Tech/Secret", None)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(rendered)
        self.assertIn("ログインしてから開いてください", html)

    def test_ログイン中なら別のアカウントを案内する(self):
        _res, html, _ = self.open("Tech/Secret", "bob")
        self.assertIn("ログインし直す", html)

    def test_編集の入口を出さない(self):
        _res, html, _ = self.open("Tech/Secret", "bob")
        self.assertNotIn("data-editable", html)
        self.assertNotIn("このページを作る", html)

    def test_無いページでも同じ画面にする(self):
        # 作成の誘いを出しても、作ったあと本人が開けない（有無を隠す目的ではない）
        self.rule("Tech/*", "R", "alice")
        res, html, rendered = self.open("Tech/NoSuchPage", "bob")
        self.assertEqual(res.status_code, 403)
        self.assertFalse(rendered)
        self.assertNotIn("このページはまだありません", html)

    def test_権限はpublished_refの戻り値で見る(self):
        # 判定器を別に呼ばず、ref.privilege だけで決めていること。
        # 断りの画面は差し替える（テーマのメニューが published_ref を通して
        # 判定器を作るので、render_page 自身が呼んだかを見分けられなくなるため）
        ref = paths.PageRef("Open", "Open", ".md", "", SECRET_BODY, True, auth.PAGE_NONE)
        denied = HTTPResponse(body="denied", status=403)
        self.login_as("bob")
        with mock.patch.object(views, "published_ref", return_value=ref), \
                mock.patch.object(views, "render_no_view", return_value=denied) as no_view, \
                mock.patch.object(auth, "page_privilege") as judge:
            res = views.render_page(self.wiki_dir, {}, FARM, "Open", False)
        self.assertIs(res, denied)
        self.assertTrue(no_view.called)
        self.assertFalse(judge.called)


class TestAllowed(PageViewTestBase):
    """閲覧の権限があるとき。これまでどおりページを描く。"""

    def test_設定の無いページは未ログインでも描く(self):
        self.publish("Tech/Open", "開いた本文\n")
        res, html, rendered = self.open("Tech/Open", None)
        self.assertTrue(rendered)
        self.assertIn("開いた本文", html)

    def test_設定の無い無いページは404(self):
        res, html, rendered = self.open("Tech/NoSuchPage", None)
        self.assertFalse(rendered)
        self.assertEqual(res.status_code, 404)
        self.assertIn("このページはまだありません", html)

    def test_Rに載っている人は描く(self):
        self.rule("Tech/Secret", "R", "alice")
        self.publish("Tech/Secret")
        _res, html, rendered = self.open("Tech/Secret", "alice")
        self.assertTrue(rendered)
        self.assertIn("秘密の本文", html)
        self.assertNotIn("閲覧する権限がありません", html)

    def test_Wに載っている人も描く(self):
        self.rule("Tech/Secret", "W", "bob")
        self.publish("Tech/Secret")
        _res, _html, rendered = self.open("Tech/Secret", "bob")
        self.assertTrue(rendered)

    def test_読める人でも無いページは404(self):
        self.rule("Tech/*", "R", "alice")
        res, _html, rendered = self.open("Tech/NoSuchPage", "alice")
        self.assertFalse(rendered)
        self.assertEqual(res.status_code, 404)


class TestUrlNormalize(PageViewTestBase):
    """URLの正規化（303）は権限より先。文字列を直すだけでデータを読まない。"""

    def test_末尾スラッシュは権限を見る前に送り直す(self):
        self.rule("Tech/Secret", "R", "alice")
        self.login_as("bob")
        with mock.patch.object(views, "published_ref", return_value=None) as spy:
            res = views.render_page(self.wiki_dir, {}, FARM, "Tech/Secret", False,
                                    had_trailing_slash=True)
        self.assertEqual(res.status_code, 303)
        self.assertFalse(spy.called)


class TestLoginScreen(PageViewTestBase):
    """ログインの入口 `/.login`（`views.render_login`。Wiki設計者の指示、2026-09-21）。

    **システムのURLなので、ページ名と衝突せず、ページごとの権限の対象にもならない。**
    閲覧にもログインを求めるWikiでも、ここは開く。以前は `Login` という名前のページを
    入口にしていたが、その名前でページを作ると権限で読めなくなる・実在のページが入口の役を
    奪う、という問題があったので、システムのURLへ移した（`Login` はふつうのページ名になった）。

    ここでは `render_with_theme` を偽物に差し替えず、**実際にテーマ・プラグインを通して**
    描く（値打ちは、本当にログインフォームが出ることそのものにあるため）。"""

    def _html_of(self, res):
        raw = res.body if hasattr(res, "body") else res
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def screen(self, uid=None, query=""):
        self.login_as(uid)
        bottle.request.environ["QUERY_STRING"] = query
        return views.render_login(self.wiki_dir, {}, FARM, False)

    def test_ログインフォームが出る(self):
        res = self.screen()
        html = self._html_of(res)
        self.assertEqual(res.status_code, 200)
        self.assertIn('class="login"', html)              # #login() が作る fieldset
        self.assertIn(".plugin/login", html)              # フォームの送り先
        self.assertIn('name="back" value=".login"', html)  # 失敗の知らせを出すため、入口へ戻す

    def test_閲覧にもログインが要るWikiでも開く(self):
        self.rule("*", "R", "g:all")
        self.rule("*", "W", "admin,g:staff")
        res = self.screen()
        self.assertEqual(res.status_code, 200)
        self.assertIn(".plugin/login", self._html_of(res))
        # ページのほうは、未ログインには閲覧できない
        self.publish("Tech/A")
        res, _html, _rendered = self.open("Tech/A", None)
        self.assertEqual(res.status_code, 403)

    def test_backのページをnextとして運ぶ(self):
        html = self._html_of(self.screen(query="back=Tech/Secret"))
        self.assertIn('name="next" value="Tech/Secret"', html)

    def test_日本語のページ名も文字化けせずに運ぶ(self):
        # `request.query.get` はLatin-1として読むので、getunicode で読む必要がある
        # （`[TA向け]` のようなページ名で、ログイン後の転送先が壊れた。2026-09-21）
        from urllib.parse import quote
        name = "[TA向け]"
        html = self._html_of(self.screen(query="back=" + quote(name, safe="/")))
        self.assertIn(f'name="next" value="{name}"', html)

    def test_403の画面のリンクから入口へ_日本語のページ名が最後まで届く(self):
        # 実際の流れ: 閲覧できないページ → 403のリンク → 入口 → フォームの next
        import re
        from urllib.parse import unquote
        name = "[TA向け]"
        self.rule("*", "R", "g:all")
        self.publish(name)
        res, html403, _rendered = self.open(name, None)
        self.assertEqual(res.status_code, 403)
        href = re.search(r'href="([^"]*\.login\?back=[^"]*)"', html403).group(1)
        self.assertEqual(unquote(href.split("back=", 1)[1]), name)
        html = self._html_of(self.screen(query=href.split("?", 1)[1]))
        self.assertIn(f'name="next" value="{name}"', html)

    def test_backが無ければnextは空(self):
        self.assertIn('name="next" value=""', self._html_of(self.screen()))

    def test_ログイン中に開けばログアウトなどが出る(self):
        html = self._html_of(self.screen("alice"))
        self.assertIn("現在ログイン中のユーザー", html)

    def test_Loginという名前のページはふつうのページ(self):
        # 入口の役を奪わず、権限もふつうに効く
        self.publish("Login", "# 案内\n\n社内向けです。\n")
        self.rule("Login", "R", "alice")
        res, _html, rendered = self.open("Login", "bob")
        self.assertEqual(res.status_code, 403)
        self.assertFalse(rendered)
        res, html, _rendered = self.open("Login", "alice")
        self.assertEqual(res.status_code, 200)
        self.assertIn("社内向けです", html)

    def test_Loginのページが無ければ無いページ(self):
        # 以前は実体が無くても #login() の表示になっていた（Loginという名前の特別扱い）。もう無い
        res, _html, _rendered = self.open("Login", None)
        self.assertEqual(res.status_code, 404)

    def test_ナビのログインは入口を指す(self):
        from wikilib import themes
        ctx = themes.make_plugin_context({}, FARM, self.wiki_dir, "", False)
        self.assertFalse(hasattr(paths, "LOGIN_PAGE_NAME"))
        self.assertTrue(themes.LOGIN_URLPATH == ".login")
        self.assertEqual(ctx.base_url + "/" + themes.LOGIN_URLPATH, ctx.base_url + "/.login")


class TestNavLoginLink(PageViewTestBase):
    """ナビの「ログイン」は、**いま開いているページを戻り先として持つ**
    （Wiki設計者の報告、2026-09-21。ページ単位の閲覧制限 `#readauth` で読めないページから
    ナビのログインを踏んだら、トップへ行ってしまった）。

    実際にテーマを通して描き、`login_url` が出るところまで見る。"""

    def nav_href(self, pagepath, uid=None):
        import re
        self.login_as(uid)
        with mock.patch.object(views, "record_access"), mock.patch.object(views, "maybe_backup"):
            res = views.render_page(self.wiki_dir, {}, FARM, pagepath, False)
        raw = res.body if hasattr(res, "body") else res
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        found = re.search(r'<a class="command" href="([^"]*)">ログイン</a>', html)
        self.assertIsNotNone(found, "ナビのログインが無い")
        return found.group(1)

    def test_ふつうのページは戻り先を持つ(self):
        self.publish("Tech/Public", "# 公開\n\n本文\n")
        self.assertEqual(self.nav_href("Tech/Public"), "/=testwiki/.login?back=Tech/Public")

    def test_日本語のページ名も戻り先にできる(self):
        from urllib.parse import quote
        self.publish("[TA向け]", "# TA\n\n本文\n")
        self.assertEqual(self.nav_href("[TA向け]"),
                         "/=testwiki/.login?back=" + quote("[TA向け]", safe="/"))

    def test_トップは戻り先を持たない(self):
        self.publish("index", "# トップ\n")
        self.assertEqual(self.nav_href(""), "/=testwiki/.login")

    def test_システムの画面は戻り先を持たない(self):
        from wikilib import themes
        for path in (".search", ".admin/accounts", ".login", "=other/Page"):
            self.assertEqual(themes.login_href("/=testwiki", path), "/=testwiki/.login", path)

    def test_入口の画面自身も戻り先を持たない(self):
        # 入口の中のナビが自分自身を戻り先にしてループしない
        self.login_as(None)
        res = views.render_login(self.wiki_dir, {}, FARM, False)
        raw = res.body if hasattr(res, "body") else res
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        self.assertIn('<a class="command" href="/=testwiki/.login">ログイン</a>', html)


class TestDeniedLoginLink(PageViewTestBase):
    """未ログインの403には、ログインの入口へのリンクを添える（戻り先つき）。"""

    def setUp(self):
        super().setUp()
        self.rule("*", "R", "g:all")
        self.publish("Tech/Secret")

    def test_未ログインには入口へのリンクが出る(self):
        res, html, _ = self.open("Tech/Secret", None)
        self.assertEqual(res.status_code, 403)
        self.assertIn('href="/=testwiki/.login?back=Tech/Secret"', html)
        self.assertIn("ログインする", html)

    def test_ログイン中には出さない(self):
        self.rule("Tech/Secret", "R", "alice")
        res, html, _ = self.open("Tech/Secret", "bob")
        self.assertEqual(res.status_code, 403)
        self.assertNotIn("ログインする", html)


if __name__ == "__main__":
    unittest.main()
