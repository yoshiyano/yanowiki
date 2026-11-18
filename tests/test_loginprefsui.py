#!/usr/bin/env python3
"""`#login` のアカウントタブの「この端末のログインの設定」（画面の側）のテスト。

仕組み（cookie・合言葉）は `test_loginprefs.py` が見ている。ここは画面だけ:

  フォーム    日数・曜日・時刻の欄があり、初期値は端末の設定
  表示        いまのログインがいつまでか（延ばしたあとの until）、次にログインし直す時刻
  送り先      `cmd=loginprefs` が `do_set_login_prefs` へ届き、結果の文言が出る

実行:
    _venv/bin/python3 tests/test_loginprefsui.py
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_loginpending import load_plugin  # noqa: E402
from test_loginprefs import PREF_COOKIE, PrefsBase  # noqa: E402

import bottle  # noqa: E402

from wikilib import userdb  # noqa: E402


class PrefsUiBase(PrefsBase):

    def setUp(self):
        super().setUp()
        self.plugin = load_plugin()
        self.context = mock.Mock(wiki_dir=self.wiki_dir, farm="testwiki",
                                 base_url="/=testwiki", config={}, explicit_farm=False,
                                 page="Top")

    def panel(self):
        self.send(method="GET")
        user = userdb.find_by_uid(self.wiki_dir, "admin")
        return self.plugin._account_panel_html(self.context, user, "Top", "1")


class TestForm(PrefsUiBase):

    def test_未設定ならどれも選ばれていない(self):
        self.login()
        html = self.panel()
        self.assertIn('name="cmd" value="loginprefs"', html)
        self.assertIn('<option value="">設定しない</option>', html)
        self.assertNotIn(" selected", html)
        self.assertNotIn("checked", html)
        self.assertIn('name="at" value="00:00"', html)
        self.assertIn('name="back" value="Top"', html)

    def test_初期値は端末の設定(self):
        self.jar[PREF_COOKIE] = "7.5.0830"   # 7日・月と水・8:30
        self.login()
        html = self.panel()
        self.assertIn('<option value="7" selected>7日</option>', html)
        self.assertIn('value="0" checked>月', html)
        self.assertIn('value="2" checked>水', html)
        self.assertNotIn('value="1" checked', html)
        self.assertIn('name="at" value="08:30"', html)

    def test_日数は14日まで(self):
        self.login()
        html = self.panel()
        self.assertIn('<option value="14">14日</option>', html)
        self.assertNotIn('<option value="15"', html)


class TestState(PrefsUiBase):

    def test_いつまでかを出す(self):
        self.jar[PREF_COOKIE] = "7.0.0000"
        self.login()
        st = self.state()
        html = self.panel()
        self.assertIn(f"このまま開かなければ <strong>{self.plugin._when(st['until'])}</strong>"
                      " まで", html)
        self.assertNotIn("次のログインし直し", html)

    def test_設定の無い端末にも延ばしたあとの期限を出す(self):
        # 延ばすのは描いたあと（wiki.py の dispatch）なので、expires ではなく until を出す
        self.login()
        st = self.state()
        with mock.patch.object(self.plugin, "login_state",
                               return_value=dict(st, until=st["expires"] + 86400)):
            html = self.panel()
        self.assertIn(f"このまま開かなければ <strong>{self.plugin._when(st['expires'] + 86400)}"
                      "</strong> まで", html)
        self.assertIn("毎日このWikiを開いていればログインしたまま", html)

    def test_曜日を決めたら次のログインし直しを出す(self):
        self.jar[PREF_COOKIE] = "14.127.0000"   # 毎日 0:00
        self.login()
        st = self.state()
        html = self.panel()
        self.assertIn(f"次のログインし直し: <strong>{self.plugin._when(st['next_relogin'])}",
                      html)

    def test_期限より後のログインし直しは出さない(self):
        self.jar[PREF_COOKIE] = "1.0.0000"
        self.login()
        st = self.state()
        with mock.patch.object(self.plugin, "login_state",
                               return_value=dict(st, next_relogin=st["until"] + 60)):
            html = self.panel()
        self.assertNotIn("次のログインし直し", html)

    def test_曜日の名前(self):
        import datetime
        t = datetime.datetime(2026, 11, 20, 9, 5).timestamp()   # 金曜
        self.assertEqual(self.plugin._when(t), "11月20日（金）09:05")


class TestAction(PrefsUiBase):

    def test_loginprefsは本体へ渡す(self):
        self.login()
        self.send([("cmd", "loginprefs"), ("days", "3"), ("at", ""), ("back", "Top")])
        out = self.take(self.plugin._action(self.context))
        self.assertIn("login=prefs", out.headers["Location"])
        self.assertEqual(self.jar[PREF_COOKIE], "3.0.0000")

    def test_結果の文言(self):
        bottle.request.environ.clear()
        bottle.request.environ.update({"QUERY_STRING": "login=prefs"})
        self.assertIn("この端末のログインの設定を変えました。", self.plugin._result_notice())


if __name__ == "__main__":
    unittest.main()
