#!/usr/bin/env python3
"""検索（`wikilib.search`）が、閲覧権限の無いページを結果から省くことのテスト。

[ページごとの権限](/Tech/PagePermissions) の要件6（「閲覧権限がないページは
検索結果から省く」）。Wiki設計者の指摘（2026-09-24。「認証まわりの実施漏れ」の
指摘に対する対応）で、`search_matches`・`search_pages`・`render_results_block`
は `auth.page_privilege(...)` の判定器を**必須の引数**として受け取るようにした
（渡し忘れて全ページが対象になる側に倒れないため）。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_search.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import auth, pagedb, privilege_records, search, userdb  # noqa: E402


class SearchPrivilegeTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="search-privilege-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        userdb.add_user(self.wiki_dir, "alice", userdb.hash_password(self.wiki_dir, "alice", "p"), "alice")
        for subpath, body in (
            ("Open", "# 開いた題名\n\nだれでも読める、めだまやきの話。\n"),
            ("Secret", "# 秘密の題名\n\naliceだけが読める、めだまやきの話。\n"),
        ):
            self.assertTrue(pagedb.record_page(self.wiki_dir, subpath, ".md", body))
            self.assertTrue(pagedb.record_page_info(self.wiki_dir, subpath, subpath, [], []))
        ok, message, _ = privilege_records.put(self.wiki_dir, "Secret", "R", "alice")
        self.assertTrue(ok, message)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def privilege(self, uid):
        return auth.page_privilege(self.wiki_dir, uid)

    def matches(self, uid, terms=("めだまやき",), mode="and"):
        return search.search_matches(self.wiki_dir, list(terms), mode, self.privilege(uid))

    def pages_of(self, got):
        return {m[0] for m in got}


class TestSearchMatches(SearchPrivilegeTestBase):

    def test_未ログインは閲覧できるページだけ(self):
        self.assertEqual(self.pages_of(self.matches(None)), {"Open"})

    def test_許可された利用者には両方出る(self):
        self.assertEqual(self.pages_of(self.matches("alice")), {"Open", "Secret"})

    def test_無関係な利用者は閲覧できるページだけ(self):
        userdb.add_user(self.wiki_dir, "bob", userdb.hash_password(self.wiki_dir, "bob", "p"), "bob")
        self.assertEqual(self.pages_of(self.matches("bob")), {"Open"})

    def test_ページ名検索でも絞られる(self):
        got = self.matches(None, terms=("Secret",), mode="or")
        self.assertEqual(self.pages_of(got), set())
        got = self.matches("alice", terms=("Secret",), mode="or")
        self.assertEqual(self.pages_of(got), {"Secret"})

    def test_privilegeは必須の引数(self):
        # 渡し忘れて全ページが対象になる側に倒れないよう、省略はできない
        with self.assertRaises(TypeError):
            search.search_matches(self.wiki_dir, ["めだまやき"], "and")

    def test_システム権限なら絞られない(self):
        sys_privilege = auth.page_privilege(self.wiki_dir, auth.SYSTEM_UID)
        got = search.search_matches(self.wiki_dir, ["めだまやき"], "and", sys_privilege)
        self.assertEqual(self.pages_of(got), {"Open", "Secret"})

    def test_ロック中は未ログインと同じ扱い(self):
        userdb.lock_user(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"])
        self.assertEqual(self.pages_of(self.matches("alice")), {"Open"})


class TestSearchPages(SearchPrivilegeTestBase):

    def test_search_pagesも絞られる(self):
        results = search.search_pages(self.wiki_dir, ["めだまやき"], "and", self.privilege(None))
        self.assertEqual({r["page"] for r in results}, {"Open"})


class TestRenderResultsBlock(SearchPrivilegeTestBase):

    def test_結果のHTMLに閲覧できないページの抜粋が出ない(self):
        params = {"q": "めだまやき"}
        html = str(search.render_results_block(
            self.wiki_dir, "/=testwiki", params, ["めだまやき"], "and", "all", "",
            1, self.privilege(None)))
        self.assertIn("Open", html)
        self.assertNotIn("Secret", html)
        self.assertIn("1</strong> 件", html)   # 件数もSecretを含まない

    def test_許可された利用者には件数に含まれる(self):
        params = {"q": "めだまやき"}
        html = str(search.render_results_block(
            self.wiki_dir, "/=testwiki", params, ["めだまやき"], "and", "all", "",
            1, self.privilege("alice")))
        self.assertIn("Secret", html)
        self.assertIn("2</strong> 件", html)


if __name__ == "__main__":
    unittest.main()
