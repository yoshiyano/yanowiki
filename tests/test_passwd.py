#!/usr/bin/env python3
"""自分のパスワードを変える画面（`/.passwd`、wikilib.accounts.render_passwd）のテスト。

ユーザ管理を3層に分けたとき（2026-09-13）に、この画面が使っていた名前
（`RETRY_DELAY`・`back_page_url` ほか）が `wikilib.auth` へ移り、POSTを受けると
500になっていた（2026-09-26に報告）。GETしか通していなかったため気付かなかったので、
POSTの経路を通しておく。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_passwd.py     （このファイルだけ）
"""
import io
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

from wikilib import auth, userdb  # noqa: E402
from wikilib.accounts import render_passwd  # noqa: E402


class TestPasswdPost(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="passwd-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        userdb.add_user(self.wiki_dir, "alice",
                        userdb.hash_password(self.wiki_dir, "alice", "oldpass"), "アリス")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        # 間違えたときの1秒の待ちは、テストでは要らない
        patcher = mock.patch.object(auth, "RETRY_DELAY", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        shutil.rmtree(self.work, ignore_errors=True)

    def post(self, **fields):
        body = urlencode(fields).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "REMOTE_ADDR": "127.0.0.1",
        })
        return render_passwd(self.wiki_dir, {}, "testwiki", False)

    def body(self, out):
        return out if isinstance(out, str) else (out.body or "")

    def test_いまのパスワードが違えば断る(self):
        out = self.post(uid="alice", current="wrong", new1="newpass", new2="newpass")
        self.assertIn("IDかいまのパスワードが違います", self.body(out))
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "alice", "oldpass"))

    def test_変えられる(self):
        out = self.post(uid="alice", current="oldpass", new1="newpass", new2="newpass")
        self.assertIn("パスワードを変えました", self.body(out))
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "alice", "newpass"))

    def test_ページのフォームから来たらそのページへ戻す(self):
        out = self.post(uid="alice", current="oldpass", new1="newpass", new2="newpass",
                        back="Memo")
        self.assertEqual(out.status_code, 303)
        self.assertIn("/=testwiki/Memo?login=done", out.headers["Location"])


if __name__ == "__main__":
    unittest.main()
