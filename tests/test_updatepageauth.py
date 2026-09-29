#!/usr/bin/env python3
"""機能していないページの権限の記録を消す（wikilib.updatepageauth）のテスト。

消すのは「制限を緩める」操作なので、**消してはいけないものを消さない**ことを
中心に見る。判定は本文の字面ではなく、実際に描いて `readauth`・`writeauth` が
呼ばれたかで決める（囲みコードの中の書きかたは機能していない、など）。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_updatepageauth.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import auth, paths, privilege_records, updatepageauth, userdb  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

FARM = "testwiki"
HEADER = "# プラグインの記録\n"


class UpdatePageAuthTestBase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="updatepageauth-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        userdb.add_user(self.wiki_dir, "alice",
                        userdb.hash_password(self.wiki_dir, "alice", "p"), "alice")
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        self.kept_run_log = updatepageauth.RUN_LOG
        updatepageauth.RUN_LOG = os.path.join(self.work, "runs.json")
        bottle.request.bind({"REMOTE_ADDR": "192.0.2.1"})

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        updatepageauth.RUN_LOG = self.kept_run_log
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def page(self, name, text):
        path = os.path.join(self.wiki_dir, name + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def records(self, *lines):
        path = privilege_records.plugin_path_of(self.wiki_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(HEADER + "".join(line + "\n" for line in lines))

    def left(self):
        return sorted((e["page"], e["kind"])
                      for e in privilege_records.load_plugin(self.wiki_dir))

    def sweep(self):
        return updatepageauth.sweep(self.wiki_dir, {}, FARM)


class TestSweep(UpdatePageAuthTestBase):
    """`sweep`: 機能していない行だけを消す。"""

    def test_行が残っているページの記録は残る(self):
        self.page("Keep", "#readauth(alice)\n\n本文\n")
        self.page("Gone", "本文だけ\n")
        self.records("Keep:R:alice:1", "Gone:R:alice:2")
        self.assertEqual(self.sweep(), {"checked": 2, "removed": 1})
        self.assertEqual(self.left(), [("Keep", "R")])

    def test_種類ごとに見る(self):
        self.page("Both", "#readauth(alice)\n\n本文\n")
        self.records("Both:R:alice:1", "Both:W:alice:2")
        self.sweep()
        self.assertEqual(self.left(), [("Both", "R")])

    def test_ページが無ければ消す(self):
        self.records("Deleted:R:alice:1")
        self.assertEqual(self.sweep()["removed"], 1)
        self.assertEqual(self.left(), [])

    def test_囲みコードの中の書きかたは機能していない(self):
        self.page("Doc", "```\n#readauth(alice)\n```\n")
        self.records("Doc:R:alice:1")
        self.sweep()
        self.assertEqual(self.left(), [])

    def test_エラーになる書きかたでも記述が残っていれば残す(self):
        # 実在しない相手を書いた行はエラー表示になるが、プラグインは呼ばれている
        self.page("Typo", "#readauth(nobody)\n")
        self.records("Typo:R:alice:1")
        self.sweep()
        self.assertEqual(self.left(), [("Typo", "R")])

    def test_描けなければ残す(self):
        self.page("Broken", "本文だけ\n")
        self.records("Broken:R:alice:1")
        with mock.patch.object(updatepageauth, "_used_plugins", return_value=None):
            self.sweep()
        self.assertEqual(self.left(), [("Broken", "R")])

    def test_判定のあとで本文が変わっていれば残す(self):
        # 描いてから消すまでの間に、プラグインの行が書き足された
        self.page("Racing", "本文だけ\n")
        self.records("Racing:R:alice:1")
        real = updatepageauth._used_plugins

        def render_then_save(*args):
            used = real(*args)
            self.page("Racing", "#readauth(alice)\n\n本文だけ\n")
            return used
        with mock.patch.object(updatepageauth, "_used_plugins", side_effect=render_then_save):
            self.assertEqual(self.sweep()["removed"], 0)
        self.assertEqual(self.left(), [("Racing", "R")])

    def test_描いても記録や本文を書き換えない(self):
        # 途中にある行は、通常の描画なら先頭へ寄せられるが、ここでは触らない
        text = "本文\n\n#readauth(alice)\n"
        self.page("Middle", text)
        self.records("Middle:R:alice:1")
        self.sweep()
        with open(os.path.join(self.wiki_dir, "Middle.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), text)
        with open(privilege_records.plugin_path_of(self.wiki_dir), encoding="utf-8") as f:
            self.assertEqual(f.read(), HEADER + "Middle:R:alice:1\n")

    def test_記録が無ければ何もしない(self):
        self.assertEqual(self.sweep(), {"checked": 0, "removed": 0})
        self.assertFalse(os.path.exists(privilege_records.plugin_path_of(self.wiki_dir)))


class TestServe(UpdatePageAuthTestBase):
    """`/.updatePageAuth`: 誰でも実行できるが、1時間に10回まで（管理者と助手は除く）。"""

    def serve(self):
        return updatepageauth.serve_update_page_auth(self.wiki_dir, {}, FARM, False)

    def login(self, uid):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        bottle.request.bind({
            "REMOTE_ADDR": "192.0.2.1",
            "HTTP_COOKIE": f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
                           f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}"})

    def test_結果は件数だけでページ名を出さない(self):
        self.records("Secret/Name:R:alice:1")
        res = self.serve()
        self.assertEqual(res.status_code, 200)
        self.assertIn("1件を調べ", res.body)
        self.assertNotIn("Secret", res.body)

    def test_未ログインはIPごとに1時間10回まで(self):
        for _ in range(updatepageauth.RUN_MAX):
            self.assertEqual(self.serve().status_code, 200)
        self.assertEqual(self.serve().status_code, 429)
        bottle.request.bind({"REMOTE_ADDR": "192.0.2.2"})  # 別のIPは別に数える
        self.assertEqual(self.serve().status_code, 200)

    def test_ログインしていればIDごとに数える(self):
        self.login("alice")
        for _ in range(updatepageauth.RUN_MAX):
            self.assertEqual(self.serve().status_code, 200)
        self.assertEqual(self.serve().status_code, 429)

    def test_1時間たてば数え直す(self):
        now = 1_000_000.0
        for _ in range(updatepageauth.RUN_MAX):
            self.assertIsNone(updatepageauth._count_run("k", now))
        self.assertIsNotNone(updatepageauth._count_run("k", now + 10))
        self.assertIsNone(updatepageauth._count_run("k", now + updatepageauth.RUN_WINDOW))

    def test_管理者は数えない(self):
        self.login("admin")
        for _ in range(updatepageauth.RUN_MAX + 2):
            self.assertEqual(self.serve().status_code, 200)


if __name__ == "__main__":
    unittest.main()
