#!/usr/bin/env python3
"""`wikilib.pagedb.published_ref` が返す `PageRef.privilege` のテスト。

**`published_ref` は、いまの閲覧者のそのページのアクセス権（`W`/`R`/`-`）を
`privilege` に入れて返す**（Wiki設計者の指示、2026-09-15）。ここでは次を確かめる。

  - 閲覧者（ログイン・未ログイン・成り代わり）ごとに `privilege` が判定器と揃う
  - **`-` でも本文などのデータは返す**（今後の拡張で本文が要る場面のため）
  - 公開されていないページも None にせず `exists=False` で返し、`privilege` を持つ
    （無いページでも、その人がそこを読めるか・書けるかが分かるように）
  - 取り込めなかったときも `exists=False` で、平文の本文は入れない
  - `resolve_page_ref` が作る PageRef の `privilege` は None（判定しない層）

判定そのもの（誰に何が返るか）は `tests/test_pageprivilege.py` が見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_publishedref.py     （このファイルだけ）
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

from wikilib import auth, pagedb, pagesync, paths, privilege_records, userdb  # noqa: E402
from wikilib.auth import PAGE_NONE, PAGE_READ, PAGE_WRITE, SYSTEM_UID, act_as  # noqa: E402
from wikilib.pagedb import published_ref  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, resolve_page_ref, wiki_cookie_name  # noqa: E402

FARM = "testwiki"
BODY = "# 題名\n\n本文です。\n"


class PublishedRefTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="publishedref-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        bottle.request.environ.clear()

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.environ.clear()
        shutil.rmtree(self.work, ignore_errors=True)

    def rule(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)

    def publish(self, subpath, body=BODY):
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

    def ref_as(self, pagepath, uid):
        self.login_as(uid)
        return published_ref(self.wiki_dir, pagepath)


class TestPrivilege(PublishedRefTestBase):
    """閲覧者ごとの `privilege`。"""

    def test_設定の無いページ(self):
        # 未ログインも既定では編集できる（既定の行 `*` が無いWiki）
        self.publish("Open")
        self.assertEqual(self.ref_as("Open", None).privilege, PAGE_WRITE)
        self.assertEqual(self.ref_as("Open", "alice").privilege, PAGE_WRITE)

    def test_Rの行に載っている人と載っていない人(self):
        self.rule("Tech/Secret", "R", "alice")
        self.publish("Tech/Secret")
        # W の指定が無いので、読める人は書ける（2026-09-21）
        self.assertEqual(self.ref_as("Tech/Secret", "alice").privilege, PAGE_WRITE)
        self.assertEqual(self.ref_as("Tech/Secret", "bob").privilege, PAGE_NONE)
        self.assertEqual(self.ref_as("Tech/Secret", None).privilege, PAGE_NONE)

    def test_Wの行に載っていない人は読むだけ(self):
        self.rule("Tech/Secret", "R", "alice,bob")
        self.rule("Tech/Secret", "W", "alice")
        self.publish("Tech/Secret")
        self.assertEqual(self.ref_as("Tech/Secret", "alice").privilege, PAGE_WRITE)
        self.assertEqual(self.ref_as("Tech/Secret", "bob").privilege, PAGE_READ)

    def test_Wの行に載っている人(self):
        self.rule("Tech/Secret", "W", "bob")
        self.publish("Tech/Secret")
        self.assertEqual(self.ref_as("Tech/Secret", "bob").privilege, PAGE_WRITE)

    def test_成り代わった相手で判定する(self):
        self.rule("Tech/Secret", "R", "alice")
        self.publish("Tech/Secret")
        self.login_as("alice")
        with act_as("bob"):
            self.assertEqual(published_ref(self.wiki_dir, "Tech/Secret").privilege, PAGE_NONE)
        with act_as(SYSTEM_UID):
            self.assertEqual(published_ref(self.wiki_dir, "Tech/Secret").privilege, PAGE_WRITE)

    def test_判定器と同じ答えになる(self):
        self.rule("Tech/*", "R", "alice")
        self.rule("Tech/Secret", "W", "bob")
        pages = ("Tech/Secret", "Tech/Other", "Open")
        for page in pages:
            self.publish(page)
        for uid in (None, "alice", "bob"):
            privilege = auth.page_privilege(self.wiki_dir, uid)
            for page in pages:
                with self.subTest(uid=uid, page=page):
                    self.assertEqual(self.ref_as(page, uid).privilege, privilege.check(page))


class TestData(PublishedRefTestBase):
    """`privilege` に応じてデータを削らないこと、公開されていないときの形。"""

    def test_読めない人にも本文などのデータを返す(self):
        self.rule("Tech/Secret", "R", "alice")
        self.publish("Tech/Secret")
        ref = self.ref_as("Tech/Secret", "bob")
        self.assertEqual(ref.privilege, PAGE_NONE)
        self.assertTrue(ref.exists)
        self.assertEqual(ref.body, BODY)
        self.assertEqual(ref.subpath, "Tech/Secret")
        self.assertEqual(ref.ext, ".md")

    def test_公開されていないページもNoneにせずexistsが偽(self):
        self.rule("Tech/*", "R", "alice")
        ref = self.ref_as("Tech/NoSuchPage", "bob")
        self.assertIsNotNone(ref)
        self.assertFalse(ref.exists)
        self.assertEqual(ref.body, "")
        self.assertEqual(ref.privilege, PAGE_NONE)
        self.assertEqual(self.ref_as("Tech/NoSuchPage", "alice").privilege, PAGE_WRITE)

    def test_取り込めなかったときは平文の本文を入れない(self):
        path = os.path.join(self.wiki_dir, "Draft.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("取り込まれていない本文\n")
        with mock.patch.object(pagesync, "adopt_page", return_value=False) as adopt:
            ref = self.ref_as("Draft", "alice")
        self.assertTrue(adopt.called)
        self.assertFalse(ref.exists)
        self.assertEqual(ref.body, "")
        self.assertEqual(ref.privilege, PAGE_WRITE)

    def test_wiki_dirの外はNone(self):
        self.assertIsNone(self.ref_as("../outside", "alice"))

    def test_resolve_page_refはprivilegeを持たない(self):
        self.assertIsNone(resolve_page_ref(self.wiki_dir, "Open").privilege)


if __name__ == "__main__":
    unittest.main()
