#!/usr/bin/env python3
"""アカウントの画面（wikilib.accounts）のうち、cookieの扱いのテスト。

ログインできた相手を控える2つのcookie（Wiki設計者の指示、2026-09-06）。

  wikiuser_<Wiki名>  そのアカウントの uid。ログイン画面のID欄を埋めるのにも使う
  wikiauth_<Wiki名>  そのログイン状態が本物であることの合言葉
                     （wikilib.auth.session_token）

見ているのは **どこへ、どういう約束で置くか** と、**2つが揃ってはじめて
認めるか** である。

  名前       Wikiごとに分ける。Pathだけで分けると、Pathの付かない既定の
             Wikiのcookieがどのwikiへも届き、同じ名前どうしで取り違える
             （wikilib.paths.wiki_cookie_name。Wiki設計者からの不具合報告、
             2026-09-18）
  Path       そのWikiの入口だけ。アカウントはWikiごとに別なので、隣のWikiへ
             持ち出されないようにする
  HttpOnly   画面側のJavaScriptから読む用が無い。とくに合言葉のほうは、
             読めてしまうと持ち出しが容易になる
  SameSite   別のサイトから連れてこられた要求には送らない

**`wikiuser` だけでは何も認めない。** あちらは手で書き換えられる名前に
すぎない。ここで `test_名前を書き換えても通らない` を置いているのはその確認で、
合言葉の側を確かめずに名前を信じる作りへ戻ったら、ここで落ちる。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_accounts.py     （このファイルだけ）
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from bottle import HTTPResponse  # noqa: E402

from wikilib import auth, sysui, userdb  # noqa: E402
from wikilib.auth import remember_login  # noqa: E402
from wikilib.paths import (  # noqa: E402
    ACCOUNTS_URLPATH, LOGIN_AUTH_COOKIE, LOGIN_COOKIE, LOGIN_COOKIE_MAX_AGE,
    wiki_cookie_name,
)


# テストのWiki名（`testwiki`）に対して実際に置かれるcookieの名前。
USER_COOKIE = wiki_cookie_name(LOGIN_COOKIE, "testwiki")
AUTH_COOKIE = wiki_cookie_name(LOGIN_AUTH_COOKIE, "testwiki")


class AccountsTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="accounts-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir)
        # 設置ごとの合言葉は、動かしている本物ではなく作業用の場所から取る
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        shutil.rmtree(self.work, ignore_errors=True)

    def cookies(self, uid="admin", farm="testwiki", explicit_farm=False):
        """cookieを載せて、{名前: Set-Cookieの中身} で返す。"""
        user = userdb.find_by_uid(self.wiki_dir, uid)
        out = HTTPResponse(body="")
        remember_login(out, {}, farm, self.wiki_dir, explicit_farm, user)
        values = [v for k, v in out.headerlist if k == "Set-Cookie"]
        self.assertEqual(len(values), 2, "名前と合言葉の2つを置くはず")
        return {v.split("=", 1)[0]: v for v in values}


class TestRememberLogin(AccountsTestBase):

    def test_名前と合言葉の2つを置く(self):
        got = self.cookies()
        self.assertIn(USER_COOKIE, got)
        self.assertIn(AUTH_COOKIE, got)

    def test_cookieの名前はWikiごとに分かれる(self):
        """**Pathだけでは分けきれない**（Wiki設計者からの不具合報告、2026-09-18）。

        既定のWikiのcookieはPathが `/` になり、どのWikiのURLにも一緒に
        送られる。名前まで同じだと、受け取る側（http.cookies）が後に来た
        ほうで上書きしてしまい、いま見ているWikiのログインが消える。"""
        self.assertEqual(USER_COOKIE, "wikiuser_testwiki")
        self.assertEqual(AUTH_COOKIE, "wikiauth_testwiki")
        other = self.cookies(farm="otherwiki")
        self.assertIn("wikiuser_otherwiki", other)
        self.assertNotIn(USER_COOKIE, other)

    def test_名前にはuidが入る(self):
        self.assertIn(USER_COOKIE + "=admin", self.cookies()[USER_COOKIE])

    def test_合言葉は決められた作りかたのとおり(self):
        user = userdb.find_by_uid(self.wiki_dir, "admin")
        want = auth.session_token("admin", "testwiki", user["pw"])
        self.assertIn(AUTH_COOKIE + "=" + want,
                      self.cookies()[AUTH_COOKIE])

    def test_合言葉にパスワードそのものは出さない(self):
        # ハッシュ値も含めて、材料がそのまま見えては困る
        user = userdb.find_by_uid(self.wiki_dir, "admin")
        line = self.cookies()[AUTH_COOKIE]
        self.assertNotIn(user["pw"], line)
        self.assertNotIn("adminpw", line)

    def test_そのWikiの入口だけに置く(self):
        # 隣のWikiへ持ち出されないように（アカウントはWikiごとに別）
        for line in self.cookies().values():
            self.assertIn("Path=/=testwiki", line)

    def test_JavaScriptからは読ませない(self):
        for line in self.cookies().values():
            self.assertIn("HttpOnly", line)

    def test_別のサイトからの要求には送らない(self):
        for line in self.cookies().values():
            self.assertIn("SameSite=lax", line)

    def test_控える長さは合言葉が通る長さと同じ(self):
        for line in self.cookies().values():
            self.assertIn(f"Max-Age={LOGIN_COOKIE_MAX_AGE}", line)
        # 合言葉は今日ぶんと昨日ぶんが通るので、cookieもそこまで持たせる。
        # 1日で消すと、25時間ぶりに開いた人が「昨日のぶんで通る」はずなのに
        # cookieを失って入れ直しになる
        self.assertEqual(LOGIN_COOKIE_MAX_AGE,
                         auth.TOKEN_PERIOD * (auth.TOKEN_GRACE + 1))

    def test_Wikiが変わればPathも合言葉も変わる(self):
        one = self.cookies(farm="testwiki")
        other = self.cookies(farm="otherwiki")
        self.assertIn("Path=/=testwiki", one[USER_COOKIE])
        self.assertIn("Path=/=otherwiki", other["wikiuser_otherwiki"])
        self.assertNotEqual(one[AUTH_COOKIE], other["wikiauth_otherwiki"])


class TestCurrentUser(AccountsTestBase):
    """置いたcookieから、ログイン状態を読み戻せるか。

    `wikilib.auth.current_user` はbottleの `request` を見るので、ここでは
    その中身を作って呼ぶ。"""

    def current(self, uid, token, wikiname="testwiki", also=""):
        """`wikiname` のcookieを載せて `current_user` を呼ぶ。

        `also` を渡すと、そのcookieを**後ろに**足す（隣のWikiのぶんが
        一緒に届く場面を作るため。RFC 6265 はPathの長いものを先に置くと
        定めているので、Pathの付かない既定のWikiのぶんは後ろに来る）。"""
        import bottle
        from wikilib.auth import current_user
        cookies = (f"{wiki_cookie_name(LOGIN_COOKIE, wikiname)}={uid}; "
                   f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, wikiname)}={token}")
        if also:
            cookies += "; " + also
        bottle.request.environ.clear()
        bottle.request.environ["HTTP_COOKIE"] = cookies
        return current_user(self.wiki_dir, wikiname)

    def token(self, uid="admin", wikiname="testwiki"):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        return auth.session_token(uid, wikiname, user["pw"])

    def test_揃っていれば通る(self):
        user = self.current("admin", self.token())
        self.assertIsNotNone(user)
        self.assertEqual(user["name"], "管理者")

    def test_合言葉が無ければ通らない(self):
        self.assertIsNone(self.current("admin", ""))

    def test_名前が無ければ通らない(self):
        self.assertIsNone(self.current("", self.token()))

    def test_名前を書き換えても通らない(self):
        # **cookieの中身を信じない**ことの確認。ここが通ると、誰でも
        # 好きなアカウントとしてログインできることになる
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        self.assertIsNone(self.current("admin", self.token("yoshi")))

    def test_でたらめな合言葉では通らない(self):
        self.assertIsNone(self.current("admin", "0" * 40))

    def test_居ないIDは通らない(self):
        self.assertIsNone(self.current("nobody", self.token()))

    def test_別のWikiで作った合言葉は通らない(self):
        self.assertIsNone(self.current("admin", self.token(wikiname="otherwiki")))

    def test_隣のWikiのcookieが一緒に届いても取り違えない(self):
        """**この不具合の再発を見張るテスト**（Wiki設計者からの報告、2026-09-18）。

        既定のWikiで入っていると、そのcookieはPathが `/` になってどのWikiへも
        送られる。cookieの名前が全Wiki共通だった頃は、後から届いた既定Wiki
        のぶんで上書きされ、`=1ev-c` で入り直しても来訪者のままになった。"""
        other = (f"{wiki_cookie_name(LOGIN_COOKIE, 'otherwiki')}=admin; "
                 f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, 'otherwiki')}="
                 f"{self.token(wikiname='otherwiki')}")
        user = self.current("admin", self.token(), also=other)
        self.assertIsNotNone(user, "隣のWikiのcookieに上書きされてはいけない")
        self.assertEqual(user["uid"], "admin")


class TestRequireAdmin(AccountsTestBase):
    """アカウントの一覧（`/.admin/accounts`）は**管理者だけが開ける**
    （Wiki設計者の指示、2026-09-06）。

    **あの画面は「見るだけ」ではない。** 他人のパスワードを書き換えられるので、
    届いた相手は誰にでもなりすませる。ここが緩むと、ログインを覚える仕組みごと
    意味を失う。

    管理者かどうかは `uid` ではなく `uidnum` で見る。名前は一覧の画面から
    書き換えられるので、`uid == "admin"` で見ていると、名前を `admin` に
    変えるだけで管理者になれてしまう（`test_名前をadminに変えても通らない`）。"""

    def setUp(self):
        super().setUp()
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")

    def denied(self, uid=None, token=None, wikiname="testwiki"):
        """関門（`sysui.require`＋`auth.ADMIN_ONLY`）の戻り。
        断られたときだけ HTTPResponse が返る。"""
        import bottle
        from wikilib import auth, sysui
        bottle.request.environ.clear()
        if uid is not None:
            bottle.request.environ["HTTP_COOKIE"] = (
                f"{wiki_cookie_name(LOGIN_COOKIE, wikiname)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, wikiname)}={token}")
        return sysui.require(self.wiki_dir, {}, wikiname, False,
                             ACCOUNTS_URLPATH, auth.ADMIN_ONLY)

    def token(self, uid, wikiname="testwiki"):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        return auth.session_token(uid, wikiname, user["pw"])

    def test_管理者なら通る(self):
        self.assertIsNone(self.denied("admin", self.token("admin")))

    def test_ログインしていなければ断る(self):
        out = self.denied()
        self.assertIsNotNone(out)
        self.assertEqual(out.status_code, 403)

    def test_管理者でなければ断る(self):
        out = self.denied("yoshi", self.token("yoshi"))
        self.assertIsNotNone(out)
        self.assertEqual(out.status_code, 403)

    def test_合言葉が無ければ断る(self):
        # 名前のcookieだけでは通らない
        out = self.denied("admin", "")
        self.assertIsNotNone(out)

    def test_名前をadminに変えても通らない(self):
        # uidnum で見ていることの確認。**uid で見ていたらここで通ってしまう**
        # IDを変えるときはパスワードも付け直す（ハッシュにIDが混ざるため）
        userdb.update_user(self.wiki_dir, 1, "root",
                           userdb.hash_password(self.wiki_dir, "root", "x"), "管理者")
        userdb.update_user(self.wiki_dir, 2, "admin",
                           userdb.hash_password(self.wiki_dir, "admin", "y"), "矢野")
        out = self.denied("admin", self.token("admin"))
        self.assertIsNotNone(out)
        self.assertEqual(out.status_code, 403)
        # 番号のほうを持っている本人は、名前が変わっても通る
        self.assertIsNone(self.denied("root", self.token("root")))

    def test_断る理由は分けて伝えない(self):
        # 「居ない」と「管理者ではない」を分けると、そのIDが登録されて
        # いるかどうかを外から確かめる手がかりになる
        def body(out):
            raw = out.body if hasattr(out, "body") else out
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw
        # フッタの「Logged in as …」は断りの文言ではなく、見ている本人の
        # ログイン状態なので比較から外す（`themes.login_label`、2026-09-14）。
        # 他人のIDが登録されているかを確かめる手がかりにはならない
        def denied_part(html):
            found = re.search(r'<div class="acct acct-denied">.*?</div>', html, re.S)
            return found.group(0) if found else html
        self.assertEqual(denied_part(body(self.denied())),
                         denied_part(body(self.denied("yoshi", self.token("yoshi")))))

    def test_断ったときは中身を出さない(self):
        raw = self.denied().body
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        admin = userdb.find_by_uid(self.wiki_dir, "admin")
        self.assertNotIn(admin["pw"], html)   # ハッシュ値を漏らさない
        self.assertNotIn("矢野", html)        # 誰が登録されているかも出さない


class TestRemainingCount(AccountsTestBase):
    """「ロックまで残りn回」をいつ出すか（Wiki設計者の指示、2026-09-07）。

    **止めているあいだは出さない。** あのあいだは数が動かないので、出すと
    「減らない数」が並んで壊れて見える（Wiki設計者の指摘）。数が出るのは実際に
    1つ減ったときだけ——明けたあとにまちがえれば、そこで「残り(N-1)回」と出る。
    """

    def setUp(self):
        super().setUp()
        import bottle

        bottle.request.environ.clear()
        bottle.request.environ["REMOTE_ADDR"] = "127.0.0.1"

    def attempt(self, password="ちがう"):
        """1回試して、(ロック中か, ロックまでの残り) を返す。"""
        from wikilib.auth import try_password

        user, locked, left = try_password(self.wiki_dir, "admin", "admin", password)
        return (user is not None), locked, left

    def wait_out(self):
        """無視の時間が過ぎたことにする（記録の時刻を巻き戻す）。"""
        import sqlite3

        from wikilib import authlog

        con = sqlite3.connect(authlog.db_path(self.wiki_dir))
        with con:
            con.execute("UPDATE authlog SET unixtime = unixtime - ?",
                        (authlog.IGNORE_SECONDS + 1,))
        con.close()

    def test_まちがえるたびに減る(self):
        from wikilib import authlog

        for i in range(1, authlog.IGNORE_AFTER + 1):
            _ok, _locked, left = self.attempt()
            self.assertEqual(left, authlog.LOCK_AFTER - i)

    def test_止めているあいだは出さない(self):
        from wikilib import authlog

        for _ in range(authlog.IGNORE_AFTER):
            self.attempt()
        # 正しいパスワードでも通らない。そのとき数も出さない
        ok, locked, left = self.attempt("adminpw")
        self.assertFalse(ok)
        self.assertFalse(locked)
        self.assertIsNone(left)

    def test_明けてまちがえると1つ減って出る(self):
        from wikilib import authlog

        for _ in range(authlog.IGNORE_AFTER):
            self.attempt()
        self.attempt("adminpw")          # 止められているあいだの1回
        self.wait_out()
        _ok, _locked, left = self.attempt()
        self.assertEqual(left, authlog.LOCK_AFTER - authlog.IGNORE_AFTER - 1)

    def attempt_through_turns(self, count):
        """まちがえるのを count 回、**止めに入るたびに明けるまで待って**続ける。
        運用の値（5回ごとに10分、3ターンでロック）では、待たずに続けると
        2ターン目以降が無視されて数が進まない。実際の利用者の流れに合わせる。"""
        from wikilib import authlog

        results = []
        for i in range(1, count + 1):
            results.append(self.attempt())
            if i % authlog.IGNORE_AFTER == 0 and i < count:
                self.wait_out()
        return results

    def test_ロックしたら残りは0(self):
        # IGNORE_AFTER回 → 止まる → 明ける → …（ターンごとに繰り返し）→ LOCK_AFTER回目でロック
        from wikilib import authlog

        results = self.attempt_through_turns(authlog.LOCK_AFTER)
        for i, (_ok, locked, left) in enumerate(results[:-1], 1):
            self.assertFalse(locked, i)
            self.assertEqual(left, authlog.LOCK_AFTER - i, i)
        _ok, locked, left = results[-1]         # LOCK_AFTER 回目
        self.assertTrue(locked)
        self.assertEqual(left, 0)

    def test_ロックしたあとも残りは出さない(self):
        # 何回試しても通らない状態なので、残り回数に意味が無い
        from wikilib import authlog

        self.attempt_through_turns(authlog.LOCK_AFTER)
        _ok, locked, left = self.attempt("adminpw")
        self.assertTrue(locked)
        self.assertEqual(left, 0)


class TestBackPageUrl(AccountsTestBase):
    """ページの中のフォームから来たときの戻り先（Wiki設計者の指示、2026-09-08）。

    **受け取るのはページパスだけで、URLはこちらで組み立てる。** 送られてきた
    文字列をそのまま転送先にすると、好きなURLへ飛ばす踏み台になる。"""

    def back(self, value=None, farm="testwiki"):
        import io as _io
        from urllib.parse import urlencode

        import bottle

        from wikilib.auth import back_page_url

        pairs = [] if value is None else [("back", value)]
        body = urlencode(pairs).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": _io.BytesIO(body),
        })
        return back_page_url({}, farm, self.wiki_dir, False)

    def test_ページパスならそのページのURL(self):
        self.assertEqual(self.back("Tech/Accounts"), "/=testwiki/Tech/Accounts")

    def test_ルートも戻り先になる(self):
        # 空文字はルートページ。**「無い」とは別物**
        self.assertEqual(self.back(""), "/=testwiki/")

    def test_送られてこなければNone(self):
        self.assertIsNone(self.back(None))

    def test_URLらしい値は受けない(self):
        for bad in ("http://evil.example/x", "//evil.example", "a:b"):
            self.assertIsNone(self.back(bad), bad)

    def test_システムの入口は受けない(self):
        # **ログインの入口 `.login` だけは例外**（Wiki設計者の指示、2026-09-21。
        # TestLoginEntranceBack）。それ以外のシステムのURLは戻り先にしない
        for bad in (".admin", ".plugin/login", "=other/Page", "..", "a/../b"):
            self.assertIsNone(self.back(bad), bad)


class TestDoLogin(AccountsTestBase):
    """`#login` プラグインの `_action`（`/.plugin/login`）から呼ばれる
    `do_login`/`do_logout`/`do_signup`（Wiki設計者の指示、2026-09-11。旧
    `render_login`/`_do_logout`/`_do_signup` を `/.login` 廃止に伴い
    分割・公開名にしたもの）。**画面は無いので、303の行き先とcookieだけを
    確かめる。**"""

    def form(self, fields):
        import io as _io
        from urllib.parse import urlencode

        import bottle

        body = urlencode(fields).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": _io.BytesIO(body),
            "REMOTE_ADDR": "127.0.0.1",
        })

    def test_通ればbackへ303でcookieが付く(self):
        from wikilib.auth import do_login

        self.form({"uid": "admin", "pw": "adminpw", "back": "Members/index"})
        out = do_login({}, "testwiki", self.wiki_dir, False, "/=testwiki/Members/index")
        self.assertEqual(out.status_code, 303)
        self.assertEqual(out.headers["Location"],
                         "/=testwiki/Members/index?login=done")
        self.assertEqual(len([v for k, v in out.headerlist if k == "Set-Cookie"]), 2)

    def test_通らなければng(self):
        from wikilib.auth import do_login

        self.form({"uid": "admin", "pw": "ちがう", "back": ""})
        out = do_login({}, "testwiki", self.wiki_dir, False, "/=testwiki/")
        self.assertEqual(out.status_code, 303)
        self.assertIn("?login=ng", out.headers["Location"])

    def test_backが無ければそのWikiの入口へ(self):
        # `#login` プラグインを経由しない直接POSTなど、想定していない使いかた
        from wikilib.auth import do_login

        self.form({"uid": "admin", "pw": "adminpw"})
        out = do_login({}, "testwiki", self.wiki_dir, False, None)
        self.assertEqual(out.status_code, 303)
        self.assertEqual(out.headers["Location"], "/=testwiki")

    def test_ログアウトはcookieを消してbackへ303(self):
        from wikilib.auth import do_logout

        self.form({"cmd": "logout", "back": ""})
        out = do_logout({}, "testwiki", self.wiki_dir, False, "/=testwiki/")
        self.assertEqual(out.status_code, 303)
        self.assertIn("?login=out", out.headers["Location"])

    def _login_as(self, uid, token=None):
        import bottle

        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = token or auth.session_token(uid, "testwiki", user["pw"],
                                            cnt=userdb.user_cnt(user))
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, 'testwiki')}={uid}; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, 'testwiki')}={token}")
        # bottleはcookieの解析結果をenvironに覚える。付け替えたら捨てる
        bottle.request.environ.pop("bottle.request.cookies", None)
        return token

    def test_他端末の認証解除で古い合言葉は通らず_押した端末は残る(self):
        from wikilib.auth import current_user, do_revoke_others

        self.form({"cmd": "revoke", "back": ""})
        old = self._login_as("admin")
        self.assertEqual(current_user(self.wiki_dir, "testwiki")["uid"], "admin")
        out = do_revoke_others({}, "testwiki", self.wiki_dir, False, "/=testwiki/")
        self.assertEqual(out.status_code, 303)
        self.assertIn("?login=revoked", out.headers["Location"])
        self.assertEqual(userdb.user_cnt(userdb.find_by_uid(self.wiki_dir, "admin")), 1)
        # 押した端末には、作り直した合言葉が置かれる
        cookies = [v for k, v in out.headerlist if k == "Set-Cookie"]
        self.assertEqual(len(cookies), 2)
        new = auth.session_token("admin", "testwiki",
                                 userdb.find_by_uid(self.wiki_dir, "admin")["pw"], cnt=1)
        self.assertTrue(any(new in c for c in cookies))
        # 他の端末（古い合言葉）はもう通らない
        self._login_as("admin", old)
        self.assertIsNone(current_user(self.wiki_dir, "testwiki"))
        # 作り直したほうは通る
        self._login_as("admin", new)
        self.assertEqual(current_user(self.wiki_dir, "testwiki")["uid"], "admin")

    def test_他端末の認証解除はパスワードでの照合を壊さない(self):
        from wikilib.auth import do_revoke_others

        self.form({"cmd": "revoke", "back": ""})
        self._login_as("admin")
        do_revoke_others({}, "testwiki", self.wiki_dir, False, "/=testwiki/")
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))

    def test_他端末の認証解除は本人のアカウントだけに効く(self):
        from wikilib.auth import current_user, do_revoke_others

        userdb.add_user(self.wiki_dir, "yoshi",
                        userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        yoshi_token = self._login_as("yoshi")
        self._login_as("admin")
        self.form({"cmd": "revoke", "back": ""})
        do_revoke_others({}, "testwiki", self.wiki_dir, False, "/=testwiki/")
        self._login_as("yoshi", yoshi_token)
        self.assertEqual(current_user(self.wiki_dir, "testwiki")["uid"], "yoshi")

    def test_ログインしていなければ他端末の認証解除は何もしない(self):
        import bottle
        from wikilib.auth import do_revoke_others

        self.form({"cmd": "revoke", "back": ""})
        bottle.request.environ.pop("HTTP_COOKIE", None)
        bottle.request.environ.pop("bottle.request.cookies", None)
        out = do_revoke_others({}, "testwiki", self.wiki_dir, False, "/=testwiki/")
        self.assertEqual(out.status_code, 303)
        self.assertNotIn("?login=revoked", out.headers["Location"])
        self.assertEqual(userdb.user_cnt(userdb.find_by_uid(self.wiki_dir, "admin")), 0)
        self.assertEqual([v for k, v in out.headerlist if k == "Set-Cookie"], [])

    def test_パスワードを変えるとcntが0に戻る(self):
        admin = userdb.find_by_uid(self.wiki_dir, "admin")
        userdb.bump_cnt(self.wiki_dir, admin["uidnum"])
        userdb.bump_cnt(self.wiki_dir, admin["uidnum"])
        # 同じハッシュで上書き・ハッシュ空（変えない）では戻さない
        userdb.update_user(self.wiki_dir, admin["uidnum"], "admin", admin["pw"], "x")
        userdb.update_user(self.wiki_dir, admin["uidnum"], "admin", "", "x")
        self.assertEqual(userdb.user_cnt(userdb.find_by_uid(self.wiki_dir, "admin")), 2)
        # 実際に変えたときだけ0に戻る
        userdb.update_user(self.wiki_dir, admin["uidnum"], "admin", "newhash", "x")
        self.assertEqual(userdb.user_cnt(userdb.find_by_uid(self.wiki_dir, "admin")), 0)

    def test_cntが無い古い形の辞書は0として扱う(self):
        self.assertEqual(userdb.user_cnt({}), 0)
        self.assertEqual(userdb.user_cnt({"cnt": None}), 0)

    def test_サインアップで作られてそのまま入る(self):
        from wikilib import userdb
        from wikilib.auth import do_signup

        self.form({"cmd": "signup", "uid": "newbie", "name": "新人",
                  "pw": "p@ssw0rd", "pw2": "p@ssw0rd", "back": ""})
        out = do_signup({}, "testwiki", self.wiki_dir, False, "/=testwiki/")
        self.assertEqual(out.status_code, 303)
        self.assertIn("?login=made", out.headers["Location"])
        self.assertIsNotNone(userdb.find_by_uid(self.wiki_dir, "newbie"))
        self.assertEqual(len([v for k, v in out.headerlist if k == "Set-Cookie"]), 2)

    def test_サインアップはパスワード不一致でng(self):
        from wikilib import userdb
        from wikilib.auth import do_signup

        self.form({"cmd": "signup", "uid": "newbie2", "pw": "a", "pw2": "b", "back": ""})
        out = do_signup({}, "testwiki", self.wiki_dir, False, "/=testwiki/")
        self.assertIn("?login=ng", out.headers["Location"])
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "newbie2"))


class TestLoginEntranceBack(AccountsTestBase):
    """ログインの入口（`/.login`）から送られたフォームの戻り先（Wiki設計者の指示、2026-09-21）。

    フォームは `back=.login` と `next=<ログイン後に戻るページ>` を送る。失敗・申請の知らせは
    入口に出す（入口へ戻す）が、**ログイン・登録に成功したら `next` のページへ振り替える**。
    `next` は `back` と同じ確かめを通す（好きなURLへ飛ばす踏み台にしない）。"""

    def form(self, fields):
        import io as _io
        from urllib.parse import urlencode

        import bottle

        body = urlencode(fields).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": _io.BytesIO(body),
            "REMOTE_ADDR": "127.0.0.1",
        })

    def back_url(self, **fields):
        from wikilib.auth import back_page_url
        self.form(fields)
        return back_page_url({}, "testwiki", self.wiki_dir, False)

    def test_入口の戻り先は_nextをbackとして持つ(self):
        self.assertEqual(self.back_url(back=".login", next="Tech/Secret"),
                         "/=testwiki/.login?back=Tech/Secret")

    def test_nextが無ければ入口だけ(self):
        self.assertEqual(self.back_url(back=".login", next=""), "/=testwiki/.login")
        self.assertEqual(self.back_url(back=".login"), "/=testwiki/.login")

    def test_日本語のページ名も運べる(self):
        url = self.back_url(back=".login", next="メモ/今日")
        self.assertTrue(url.startswith("/=testwiki/.login?back="))
        self.assertNotIn("メモ", url)           # URLとして符号化される
        from urllib.parse import parse_qs, urlsplit
        self.assertEqual(parse_qs(urlsplit(url).query)["back"], ["メモ/今日"])

    def test_おかしなnextは捨てる(self):
        for bad in ("//evil.example/x", "/abs", "a:b", "a\\b", ".admin/accounts", "=other/Page"):
            self.assertEqual(self.back_url(back=".login", next=bad), "/=testwiki/.login", bad)

    def test_入口以外のシステムのURLはbackにできない(self):
        for bad in (".admin", ".plugin/login", ".login/extra", "=other/.login"):
            self.assertIsNone(self.back_url(back=bad, next="Tech/Secret"), bad)

    def test_ふつうのbackはこれまでどおり(self):
        self.assertEqual(self.back_url(back="Members/index"), "/=testwiki/Members/index")
        self.assertEqual(self.back_url(back=""), "/=testwiki/")

    def login(self, uid, pw, url):
        from wikilib.auth import do_login
        self.form({"uid": uid, "pw": pw, "back": ".login"})
        return do_login({}, "testwiki", self.wiki_dir, False, url)

    def test_成功したらnextのページへ振り替える(self):
        out = self.login("admin", "adminpw", "/=testwiki/.login?back=Tech/Secret")
        self.assertEqual(out.headers["Location"], "/=testwiki/Tech/Secret?login=done")
        self.assertEqual(len([v for k, v in out.headerlist if k == "Set-Cookie"]), 2)

    def test_日本語のページ名へ最後まで戻れる(self):
        # 入口 → フォーム（next） → ログイン成功 → 元のページ。`[TA向け]` で壊れた不具合の見張り
        from urllib.parse import unquote, urlsplit
        name = "[TA向け]"
        url = self.back_url(back=".login", next=name)
        out = self.login("admin", "adminpw", url)
        location = out.headers["Location"]
        self.assertEqual(unquote(urlsplit(location).path), f"/=testwiki/{name}")
        self.assertTrue(location.endswith("?login=done"))

    def test_失敗しても日本語のnextを保つ(self):
        from urllib.parse import parse_qs, urlsplit
        name = "[TA向け]"
        out = self.login("admin", "ちがう", self.back_url(back=".login", next=name))
        query = parse_qs(urlsplit(out.headers["Location"]).query)
        self.assertEqual(query["back"], [name])
        self.assertEqual(query["login"], ["ng"])

    def test_成功してnextが無ければWikiの入口へ(self):
        out = self.login("admin", "adminpw", "/=testwiki/.login")
        self.assertEqual(out.headers["Location"], "/=testwiki/?login=done")

    def test_失敗したら入口に留まる_知らせを出すため(self):
        out = self.login("admin", "ちがう", "/=testwiki/.login?back=Tech/Secret")
        self.assertEqual(out.headers["Location"].split("&left=")[0],
                         "/=testwiki/.login?back=Tech/Secret&login=ng")

    def test_失敗して戻り先が無くても入口に留まる(self):
        out = self.login("admin", "ちがう", "/=testwiki/.login")
        self.assertIn("/=testwiki/.login?login=ng", out.headers["Location"])

    def test_ふつうのページからの戻りは変わらない(self):
        from wikilib.auth import do_login
        self.form({"uid": "admin", "pw": "adminpw", "back": "Members/index"})
        out = do_login({}, "testwiki", self.wiki_dir, False, "/=testwiki/Members/index")
        self.assertEqual(out.headers["Location"], "/=testwiki/Members/index?login=done")

    def test_サインアップの成功もnextへ_承認待ちは入口に留まる(self):
        from wikilib import wikiconfig
        from wikilib.auth import do_signup
        self.form({"cmd": "signup", "uid": "newbie", "name": "", "pw": "p@ssw0rd", "pw2": "p@ssw0rd",
                   "back": ".login", "next": "Tech/Secret"})
        out = do_signup({}, "testwiki", self.wiki_dir, False, "/=testwiki/.login?back=Tech/Secret")
        self.assertEqual(out.headers["Location"], "/=testwiki/Tech/Secret?login=made")
        # 承認制なら、入れないので入口に留まって「申請しました」を出す
        ok, _saved, message = wikiconfig.save_farm_config(self.wiki_dir, {"account": {"policy": "approval"}})
        self.assertTrue(ok, message)
        self.form({"cmd": "signup", "uid": "newbie2", "name": "", "pw": "p@ssw0rd", "pw2": "p@ssw0rd",
                   "back": ".login", "next": "Tech/Secret"})
        out = do_signup({}, "testwiki", self.wiki_dir, False, "/=testwiki/.login?back=Tech/Secret")
        self.assertEqual(out.headers["Location"], "/=testwiki/.login?back=Tech/Secret&login=applied")


class TestAccountsApi(AccountsTestBase):
    """一覧（`/.admin/accounts`）の更新・削除を1件ずつ受けるJSON API
    （`render_accounts_api`。Wiki設計者の指示、2026-09-12。「いずれの処理も
    単一ユーザへの処理として api 開放」）。

    見ているのは、**本体（`/.admin/accounts`）と同じ認証で断るか**・
    **1件の操作として正しく通るか**・**操作をログに残すか**の3点。"""

    def setUp(self):
        super().setUp()
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")

    def token(self, uid, wikiname="testwiki"):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        return auth.session_token(uid, wikiname, user["pw"])

    def call(self, payload, uid="admin", wikiname="testwiki", login=True):
        """`render_accounts_api` を1回呼び、そのHTTPResponseを返す。"""
        import io as _io
        import json as _json

        import bottle
        from wikilib.accounts import render_accounts_api

        body = _json.dumps(payload).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": _io.BytesIO(body),
            "REMOTE_ADDR": "127.0.0.1",
        })
        if login:
            bottle.request.environ["HTTP_COOKIE"] = (
                f"{wiki_cookie_name(LOGIN_COOKIE, wikiname)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, wikiname)}="
                f"{self.token(uid, wikiname)}")
        return render_accounts_api(self.wiki_dir, {}, wikiname, False)

    def body_of(self, out):
        import json as _json

        raw = out.body if hasattr(out, "body") else out
        raw = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return _json.loads(raw)

    def test_管理者でなければ断る(self):
        out = self.call({"cmd": "update"}, uid="yoshi")
        self.assertEqual(out.status_code, 403)

    def test_ログインしていなければ断る(self):
        out = self.call({"cmd": "update"}, login=False)
        self.assertEqual(out.status_code, 403)

    def test_更新できる(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "yoshi")["uidnum"]
        pw = userdb.find_by_uid(self.wiki_dir, "yoshi")["pw"]
        out = self.call({"cmd": "update", "uidnum": uidnum, "uid": "yoshi",
                         "name": "改名後", "pw": pw})
        data = self.body_of(out)
        self.assertTrue(data["ok"])
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "yoshi")["name"], "改名後")

    def test_生のパスワードを送るとサーバーがハッシュにして登録する(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "yoshi")["uidnum"]
        # IDも同時に変える。ハッシュは変更後のIDで計算される
        out = self.call({"cmd": "update", "uidnum": uidnum, "uid": "yoshi2",
                         "name": "", "raw": "secret-pw"})
        data = self.body_of(out)
        self.assertTrue(data["ok"], data)
        want = userdb.hash_password(self.wiki_dir, "yoshi2", "secret-pw")
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "yoshi2")["pw"], want)
        self.assertEqual(data["pw"], want)
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "yoshi2", "secret-pw"))

    def test_ハッシュ値はそのまま受け付ける(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "yoshi")["uidnum"]
        h = userdb.hash_password(self.wiki_dir, "yoshi", "pw-a")
        out = self.call({"cmd": "update", "uidnum": uidnum, "uid": "yoshi",
                         "name": "", "pw": h})
        self.assertTrue(self.body_of(out)["ok"])
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "yoshi")["pw"], h)

    def test_ハッシュ値の形でない値は断る(self):
        user = userdb.find_by_uid(self.wiki_dir, "yoshi")
        out = self.call({"cmd": "update", "uidnum": user["uidnum"], "uid": "yoshi",
                         "name": "", "pw": "うっかり入れた生のパスワード"})
        self.assertFalse(self.body_of(out)["ok"])
        self.assertEqual(userdb.find_by_uid(self.wiki_dir, "yoshi")["pw"], user["pw"])

    def test_lockを送るとLOCKEDになる(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "yoshi")["uidnum"]
        out = self.call({"cmd": "update", "uidnum": uidnum, "uid": "yoshi",
                         "name": "", "lock": True})
        self.assertTrue(self.body_of(out)["ok"])
        self.assertTrue(userdb.is_locked(userdb.find_by_uid(self.wiki_dir, "yoshi")))

    def test_削除できる(self):
        uidnum = userdb.find_by_uid(self.wiki_dir, "yoshi")["uidnum"]
        out = self.call({"cmd": "delete", "uidnum": uidnum})
        data = self.body_of(out)
        self.assertTrue(data["ok"])
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "yoshi"))

    def test_管理者は削除できない(self):
        admin_uidnum = userdb.find_by_uid(self.wiki_dir, "admin")["uidnum"]
        out = self.call({"cmd": "delete", "uidnum": admin_uidnum})
        data = self.body_of(out)
        self.assertFalse(data["ok"])
        self.assertIsNotNone(userdb.find_by_uid(self.wiki_dir, "admin"))

    def test_知らない操作は断る(self):
        out = self.call({"cmd": "nope", "uidnum": 1})
        self.assertEqual(out.status_code, 400)

    def test_uidnumが無ければ断る(self):
        out = self.call({"cmd": "update"})
        self.assertEqual(out.status_code, 400)

    def test_操作をログに残す(self):
        import sqlite3

        from wikilib import adminlog

        uidnum = userdb.find_by_uid(self.wiki_dir, "yoshi")["uidnum"]
        self.call({"cmd": "delete", "uidnum": uidnum})
        con = sqlite3.connect(adminlog.db_path(self.wiki_dir))
        rows = con.execute(
            "SELECT actor_uid, cmd, target_uidnum, target_uid, ok FROM adminlog").fetchall()
        con.close()
        self.assertEqual(rows, [("admin", "delete", uidnum, "yoshi", 1)])

    def test_権限で断られた操作はログに残らない(self):
        """管理者でない相手は、ログに残す前（認証チェック）で断る。"""
        import os

        from wikilib import adminlog

        uidnum = userdb.find_by_uid(self.wiki_dir, "yoshi")["uidnum"]
        self.call({"cmd": "delete", "uidnum": uidnum}, uid="yoshi")
        self.assertFalse(os.path.isfile(adminlog.db_path(self.wiki_dir)))


class TestLockWarning(unittest.TestCase):
    """断りに添える文言（Wiki設計者の指示、2026-09-07）。

    **`#login` プラグインもこれを呼ぶ**ので、名前に `_` を付けない
    （2026-09-08。同じ文言を2か所に書くと、片方だけ直したときに食い違う）。"""

    def warn(self, left):
        from wikilib.auth import lock_warning

        return lock_warning(left)

    def test_出しはじめは残りWARN_LEFT回から(self):
        # 止めに入る回（残りが IGNORE_AFTER の倍数になる回）では出さない。
        # あそこで出すと、次に消えることで「いま止められている」と読めてしまう
        from wikilib import authlog

        self.assertEqual(self.warn(str(authlog.IGNORE_AFTER)), "")
        n = authlog.WARN_LEFT
        self.assertEqual(self.warn(str(n)), f"（ロックまで残り{n}回）")
        self.assertEqual(self.warn("2"), "（ロックまで残り2回）")

    def test_最後の1回は言葉にする(self):
        # 「残り1回」だと、いま失敗したら掛かるのか次なのかが読めない
        self.assertEqual(self.warn("1"), "（次回失敗したらロックします）")

    def test_多いときは出さない(self):
        from wikilib import authlog

        for left in (str(authlog.WARN_LEFT + 1), str(authlog.LOCK_AFTER), "0", ""):
            self.assertEqual(self.warn(left), "")

    def test_数でなければ出さない(self):
        for left in ("あ", "-1", "1.5", "1a"):
            self.assertEqual(self.warn(left), "")


if __name__ == "__main__":
    unittest.main()
