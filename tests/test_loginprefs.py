#!/usr/bin/env python3
"""端末ごとのログインの設定（何日続けるか・決まった曜日と時刻に入れ直させるか）のテスト。

見ていること:

  未設定        今までの合言葉のまま（ログインした日の翌日まで）
  日数          設定した端末は、最後に開いてから N日通る。最大14日
  延ばす        ページを開くたびに延ばす（refresh_login）。未設定の端末は今日のぶんへ置き換える
  書き換え      合言葉の数字を書き換えても通らない（日数を延ばせない）
  設定を変える  曜日・時刻はいまから数える
  曜日・時刻    決めた時刻を過ぎたら通らない
  取り消し      他端末からの認証を解除する・パスワードを変えると通らない
  ログアウト    ログイン状態は消えるが、端末の設定は残る

実行:
    _venv/bin/python3 tests/test_loginprefs.py
"""
import datetime
import io
import os
import sys
import time
import unittest
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_accounts import AUTH_COOKIE, USER_COOKIE, AccountsTestBase  # noqa: E402

import bottle  # noqa: E402
from bottle import HTTPResponse  # noqa: E402

from wikilib import auth, userdb  # noqa: E402
from wikilib.paths import LOGIN_PREF_COOKIE, wiki_cookie_name  # noqa: E402

PREF_COOKIE = wiki_cookie_name(LOGIN_PREF_COOKIE, "testwiki")
DAY = 24 * 60 * 60


def local(y, mo, d, h=0, mi=0):
    return datetime.datetime(y, mo, d, h, mi).timestamp()


class PrefsBase(AccountsTestBase):

    def setUp(self):
        super().setUp()
        self.jar = {}

    def send(self, fields=(), method="POST"):
        """cookie の入れ物（self.jar）を載せて要求を作る。"""
        body = urlencode(list(fields)).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": method, "REMOTE_ADDR": "127.0.0.1",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
            "HTTP_COOKIE": "; ".join(f"{k}={v}" for k, v in self.jar.items()),
        })

    def take(self, out):
        """応答の Set-Cookie を入れ物へ移す（消されたものは除く）。"""
        for k, v in out.headerlist:
            if k != "Set-Cookie":
                continue
            name, _, rest = v.partition("=")
            value = rest.split(";", 1)[0]
            if "Max-Age=0" in v or value in ("", '""'):
                self.jar.pop(name, None)
            else:
                self.jar[name] = value.strip('"')
        return out

    def login(self):
        self.send([("uid", "admin"), ("pw", "adminpw")])
        return self.take(auth.do_login({}, "testwiki", self.wiki_dir, False, None))

    def set_prefs(self, days="", weekdays=(), at=""):
        fields = [("cmd", "loginprefs"), (auth.LOGIN_PREFS_FORM_DAYS, days),
                  (auth.LOGIN_PREFS_FORM_TIME, at)]
        fields += [(auth.LOGIN_PREFS_FORM_WEEKDAY, str(w)) for w in weekdays]
        self.send(fields)
        return self.take(auth.do_set_login_prefs({}, "testwiki", self.wiki_dir, False, "/=testwiki/"))

    def state(self, now=None):
        self.send(method="GET")
        return auth.login_state(self.wiki_dir, "testwiki", now)


class TestUnset(PrefsBase):

    def test_未設定なら今までの合言葉(self):
        self.login()
        user = userdb.find_by_uid(self.wiki_dir, "admin")
        self.assertEqual(self.jar[AUTH_COOKIE], auth.session_token("admin", "testwiki", user["pw"]))
        self.assertNotIn(PREF_COOKIE, self.jar)
        self.assertIsNone(self.state()["prefs"])


class TestDays(PrefsBase):

    def test_14日にするとログインから14日通る(self):
        self.login()
        self.set_prefs(days="14")
        st = self.state()
        self.assertTrue(self.jar[AUTH_COOKIE].startswith(auth.TOKEN2_PREFIX))
        self.assertIsNotNone(self.state(st["issued"] + 14 * DAY - 1))
        self.assertIsNone(self.state(st["issued"] + 14 * DAY))

    def test_設定はログインの前から効く(self):
        self.jar[PREF_COOKIE] = "7.0.0000"
        before = time.time()
        self.login()
        st = self.state()
        self.assertGreaterEqual(st["issued"], int(before))
        self.assertEqual(st["expires"], st["issued"] + 7 * DAY)

    def test_15日以上は受けない(self):
        self.login()
        out = self.set_prefs(days="15")
        self.assertIn("login=ng", out.headers["Location"])
        self.assertNotIn(PREF_COOKIE, self.jar)

    def test_日数を書き換えても通らない(self):
        self.jar[PREF_COOKIE] = "2.0.0000"
        self.login()
        parts = self.jar[AUTH_COOKIE].split(".")
        parts[3] = "14"
        self.jar[AUTH_COOKIE] = ".".join(parts)
        self.assertIsNone(self.state())


    def test_未設定に戻すと今までの合言葉(self):
        self.jar[PREF_COOKIE] = "14.0.0000"
        self.login()
        self.set_prefs(days="")
        self.assertNotIn(PREF_COOKIE, self.jar)
        self.assertFalse(self.jar[AUTH_COOKIE].startswith(auth.TOKEN2_PREFIX))
        self.assertIsNotNone(self.state())

    def test_cookieの長さは残りの期間(self):
        self.jar[PREF_COOKIE] = "14.0.0000"
        out = self.login()
        lines = [v for k, v in out.headerlist if k == "Set-Cookie" and v.startswith(AUTH_COOKIE)]
        age = int(lines[0].split("Max-Age=")[1].split(";")[0])
        self.assertAlmostEqual(age, 14 * DAY, delta=5)


class TestRefresh(PrefsBase):
    """ページを開くたびに延ばす（設計者の指示、2026-11-18「開くたびに延ばしてください」）。"""

    def refresh(self, now):
        self.send(method="GET")
        auth.note_wiki_context({}, "testwiki", self.wiki_dir, False)
        out = HTTPResponse(body="")
        kept = auth.time.time
        auth.time.time = lambda: now
        try:
            auth.refresh_login(out)
        finally:
            auth.time.time = kept
        return self.take(out)

    def token_at(self, now, prefs=None):
        user = userdb.find_by_uid(self.wiki_dir, "admin")
        if prefs is None:
            return auth.session_token("admin", "testwiki", user["pw"], now)
        p = auth.parse_login_prefs(prefs)
        return auth.session_token2(user, "testwiki", now, now, p)

    def test_未設定は昨日のぶんを今日のぶんに置き換える(self):
        now = 100 * DAY + 10
        self.jar[USER_COOKIE] = "admin"
        self.jar[AUTH_COOKIE] = self.token_at(now - DAY)
        self.refresh(now)
        self.assertEqual(self.jar[AUTH_COOKIE], self.token_at(now))

    def test_未設定で今日のぶんなら触らない(self):
        now = 100 * DAY + 10
        self.jar[USER_COOKIE] = "admin"
        self.jar[AUTH_COOKIE] = self.token_at(now)
        out = self.refresh(now + 60)
        self.assertFalse([v for k, v in out.headerlist if k == "Set-Cookie"])

    def test_設定した端末は最後に開いてからN日(self):
        start = time.time()
        self.jar[USER_COOKIE] = "admin"
        self.jar[AUTH_COOKIE] = self.token_at(start, "3.0.0000")
        later = start + 2 * DAY
        self.refresh(later)
        self.assertEqual(self.state(later)["expires"], int(later) + 3 * DAY)
        self.assertIsNotNone(self.state(later + 3 * DAY - 1))
        self.assertIsNone(self.state(later + 3 * DAY))

    def test_作ってから1時間は作り直さない(self):
        start = time.time()
        self.jar[USER_COOKIE] = "admin"
        self.jar[AUTH_COOKIE] = self.token_at(start, "3.0.0000")
        out = self.refresh(start + 60)
        self.assertFalse([v for k, v in out.headerlist if k == "Set-Cookie"])

    def test_延ばしても決めた曜日と時刻では切れる(self):
        user = userdb.find_by_uid(self.wiki_dir, "admin")
        prefs = auth.parse_login_prefs("14.1.0900")      # 月曜 9:00
        login = local(2026, 11, 16, 10)
        self.jar[USER_COOKIE] = "admin"
        self.jar[AUTH_COOKIE] = auth.session_token2(user, "testwiki", login, login, prefs)
        self.refresh(local(2026, 11, 20, 12))             # 金曜に開いて延ばした
        self.assertIsNone(self.state(local(2026, 11, 23, 9)))

    def test_untilは延ばしたあとの期限(self):
        now = 100 * DAY + 10
        self.jar[USER_COOKIE] = "admin"
        self.jar[AUTH_COOKIE] = self.token_at(now - DAY)        # 昨日のぶん
        st = self.state(now)
        self.assertEqual(st["expires"], 101 * DAY)
        self.assertEqual(st["until"], 102 * DAY)
        self.refresh(now)
        self.assertEqual(self.state(now)["expires"], st["until"])

    def test_設定した端末のuntilも延ばしたあとの期限(self):
        start = time.time()
        self.jar[USER_COOKIE] = "admin"
        self.jar[AUTH_COOKIE] = self.token_at(start, "3.0.0000")
        self.assertEqual(self.state(start + 60)["until"], int(start) + 3 * DAY)   # 延ばさない
        later = start + 2 * DAY
        until = self.state(later)["until"]
        self.refresh(later)
        self.assertEqual(self.state(later)["expires"], int(until))

    def test_ログインしていなければ何もしない(self):
        out = self.refresh(time.time())
        self.assertFalse([v for k, v in out.headerlist if k == "Set-Cookie"])


class TestWeekly(PrefsBase):

    def test_決めた時刻を過ぎたら通らない(self):
        user = userdb.find_by_uid(self.wiki_dir, "admin")
        prefs = auth.parse_login_prefs("14.1.0900")      # 月曜 9:00
        issued = local(2026, 11, 16, 10)                  # 月曜 10:00 にログイン
        token = auth.session_token2(user, "testwiki", issued, issued, prefs)
        check = lambda now: auth.check_token(self.wiki_dir, "testwiki", "admin", token, now)
        self.assertIsNotNone(check(local(2026, 11, 23, 8, 59)))   # 次の月曜 8:59
        self.assertIsNone(check(local(2026, 11, 23, 9, 0)))       # 次の月曜 9:00
        self.assertEqual(check(issued)["next_relogin"], local(2026, 11, 23, 9))

    def test_曜日は複数選べる(self):
        prefs = auth.parse_login_prefs("0.{}.0800".format(1 | 16))   # 月・金
        self.assertEqual(auth.next_relogin(prefs, local(2026, 11, 18, 12)),  # 水曜
                         local(2026, 11, 20, 8))
        self.assertEqual(auth.last_relogin(prefs, local(2026, 11, 18, 12)),
                         local(2026, 11, 16, 8))

    def test_曜日だけなら日数は2日(self):
        self.login()
        self.set_prefs(weekdays=[0], at="09:00")
        self.assertEqual(self.jar[PREF_COOKIE], "0.1.0900")
        st = self.state()
        self.assertEqual(st["expires"], st["issued"] + 2 * DAY)

    def test_設定する前に過ぎた時刻では切らない(self):
        self.login()
        today = datetime.datetime.now()
        self.set_prefs(days="14", weekdays=[today.weekday()], at="00:00")
        self.assertIsNotNone(self.state())

    def test_時刻を書き換えても通らない(self):
        self.login()
        self.set_prefs(days="14", weekdays=[0], at="09:00")
        parts = self.jar[AUTH_COOKIE].split(".")
        parts[4] = "0"
        self.jar[AUTH_COOKIE] = ".".join(parts)
        self.assertIsNone(self.state())


class TestRevoke(PrefsBase):

    def test_他端末の解除で通らなくなり押した端末は残る(self):
        self.jar[PREF_COOKIE] = "14.0.0000"
        self.login()
        other = self.jar[AUTH_COOKIE]
        self.send()
        self.take(auth.do_revoke_others({}, "testwiki", self.wiki_dir, False, None))
        self.assertIsNotNone(self.state())
        self.assertIsNone(auth.check_token(self.wiki_dir, "testwiki", "admin", other))

    def test_パスワードを変えると通らない(self):
        self.jar[PREF_COOKIE] = "14.0.0000"
        self.login()
        userdb.update_user(self.wiki_dir, 1, "admin",
                           userdb.hash_password(self.wiki_dir, "admin", "newpw"), "管理者")
        self.assertIsNone(self.state())


class TestLogout(PrefsBase):

    def test_ログアウトしても端末の設定は残る(self):
        self.jar[PREF_COOKIE] = "14.0.0000"
        self.login()
        self.send()
        self.take(auth.do_logout({}, "testwiki", self.wiki_dir, False, None))
        self.assertNotIn(AUTH_COOKIE, self.jar)
        self.assertNotIn(USER_COOKIE, self.jar)
        self.assertEqual(self.jar[PREF_COOKIE], "14.0.0000")


class TestParse(unittest.TestCase):

    def test_読めない値は未設定(self):
        for bad in ("", "x", "15.0.0000", "1.128.0000", "1.0.2400", "1.0.0960", "0.0.0000",
                    "1.0.900", "-1.0.0000"):
            self.assertIsNone(auth.parse_login_prefs(bad), bad)

    def test_書いて読むと同じ(self):
        prefs = auth.parse_login_prefs("14.65.0830")
        self.assertEqual(auth.format_login_prefs(prefs), "14.65.0830")


if __name__ == "__main__":
    unittest.main()
