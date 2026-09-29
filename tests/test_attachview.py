#!/usr/bin/env python3
"""添付ファイルの配信（`/.attach/…`。`wikilib.attach.serve_attach`）が
閲覧の権限を見ることのテスト。

**添付は持ち主のページの閲覧権限に従う**（Wiki設計者の指示、2026-09-14）。
読めなければ `File not found`（404）を返し、ファイルを探しにも行かない。

  - 持ち主のページが読めなければ 404 `File not found`
  - そのとき、ファイルシステムの置き場所を引かない（`safe_join` を呼ばない）
  - 読めれば、これまでどおりファイルが返る
  - フォルダの入口（`Tech/index/…`）の添付は `Tech` の権限に従う
  - `a/../b` のような書きかたでも、正規化した先のページで判定する

判定そのものは `tests/test_pageprivilege.py` が見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_attachview.py     （このファイルだけ）
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

from wikilib import attach, auth, paths, privilege_records, userdb  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

FARM = "testwiki"


class AttachViewTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="attachview-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        for rel in ("Tech/Secret/logo.png", "Tech/Open/logo.png", "Tech/index/logo.png"):
            self.put_file(rel)

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.environ.clear()
        shutil.rmtree(self.work, ignore_errors=True)

    def put_file(self, rel):
        path = os.path.join(self.work, "wikidata", FARM, "attach", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"\x89PNG secret bytes")

    def rule(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)

    def login_as(self, uid):
        bottle.request.environ.clear()
        bottle.request.environ["REQUEST_METHOD"] = "GET"
        if uid is None:
            return
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        bottle.request.environ["HTTP_COOKIE"] = (
            f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
            f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")

    def fetch(self, relpath, uid):
        """そのアカウントで添付を取りに行く。`(応答, 本文, 置き場所を引いたか)`。"""
        self.login_as(uid)
        with mock.patch.object(attach, "safe_join", wraps=attach.safe_join) as spy, \
                mock.patch.object(attach, "record_access"), \
                mock.patch.object(attach, "maybe_backup"):
            res = attach.serve_attach(self.wiki_dir, {}, FARM, relpath, False)
        body = res.body
        if hasattr(body, "read"):
            body = body.read()
            res.body.close()
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        return res, body, spy.called


class TestDenied(AttachViewTestBase):

    def setUp(self):
        super().setUp()
        self.rule("Tech/Secret", "R", "alice")

    def test_読めなければFileNotFound(self):
        res, body, _ = self.fetch("Tech/Secret/logo.png", "bob")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(body, "File not found")

    def test_未ログインでも同じ(self):
        res, body, _ = self.fetch("Tech/Secret/logo.png", None)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(body, "File not found")

    def test_ファイルを探しに行かない(self):
        _res, _body, looked = self.fetch("Tech/Secret/logo.png", "bob")
        self.assertFalse(looked)

    def test_無いファイルでも同じ応答(self):
        res, body, looked = self.fetch("Tech/Secret/nothing.png", "bob")
        self.assertEqual((res.status_code, body, looked), (404, "File not found", False))

    def test_点点で回り込んでも持ち主のページで判定する(self):
        res, body, _ = self.fetch("Tech/Open/../Secret/logo.png", "bob")
        self.assertEqual((res.status_code, body), (404, "File not found"))


class TestAllowed(AttachViewTestBase):

    def test_設定の無いページの添付は未ログインでも返る(self):
        res, body, _ = self.fetch("Tech/Open/logo.png", None)
        self.assertEqual(res.status_code, 200)
        self.assertIn("secret bytes", body)

    def test_Rに載っている人には返る(self):
        self.rule("Tech/Secret", "R", "alice")
        res, _body, _ = self.fetch("Tech/Secret/logo.png", "alice")
        self.assertEqual(res.status_code, 200)

    def test_読める人が無いファイルを開いても権限が無いときと同じ応答(self):
        # 見た目が違うと、見比べるだけで制限がかかっていると分かってしまう
        # （Wiki設計者の指示、2026-09-14）
        self.rule("Tech/Secret", "R", "alice")
        missing = self.fetch("Tech/Open/nothing.png", None)
        denied = self.fetch("Tech/Secret/logo.png", None)
        self.assertTrue(missing[2])    # こちらは探しに行ったうえで無かった
        self.assertFalse(denied[2])    # こちらは探しに行っていない
        self.assertEqual((missing[0].status_code, missing[1], missing[0].content_type),
                         (denied[0].status_code, denied[1], denied[0].content_type))
        self.assertEqual(missing[1], "File not found")

    def test_置き場所の外を指しても同じ応答(self):
        res, body, _ = self.fetch("../wiki/secret.md", None)
        self.assertEqual((res.status_code, body), (404, "File not found"))


class TestOwnerPage(AttachViewTestBase):
    """持ち主のページの取り出しかた。"""

    def test_フォルダの入口の添付はフォルダのページに従う(self):
        self.rule("Tech", "R", "alice")
        res, body, _ = self.fetch("Tech/index/logo.png", "bob")
        self.assertEqual((res.status_code, body), (404, "File not found"))
        res, _body, _ = self.fetch("Tech/index/logo.png", "alice")
        self.assertEqual(res.status_code, 200)

    def test_子ページの制限は親の添付に効かない(self):
        self.rule("Tech/Secret", "R", "alice")
        res, _body, _ = self.fetch("Tech/Open/logo.png", "bob")
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
