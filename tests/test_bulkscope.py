#!/usr/bin/env python3
"""まとめて書き換える範囲（wikilib.bulkscope。2026-10-01）のテスト。

- 範囲の中では DB の接続を1つにまとめ、範囲を出るときに確定する
  （中では自分の書き込みが読め、外の接続には出るまで見えない）
- 入れ子にすると、いちばん外側でまとまる
- 範囲の中では同じ本文の解析結果を使い回し、外では毎回解析する
- 名前の変更（範囲の中で行う）で、リンクの書き換えと記録が範囲を使わないときと同じになる

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_bulkscope.py     （このファイルだけ）
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import bulkscope, pagedb, paths  # noqa: E402
from wikilib.pagelinks import plain_tokens  # noqa: E402
from wikilib.pagerename import rename_page  # noqa: E402
from wikilib.pagesync import sync_wiki  # noqa: E402

FARM = "testwiki"


class TestBulkScope(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="bulkscope-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        self.kept = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        bottle.request.bind({})

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept
        shutil.rmtree(self.work, ignore_errors=True)

    def write(self, subpath, text):
        path = os.path.join(self.wiki_dir, subpath + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def outside_body(self, subpath):
        """範囲と関係のない別の接続から見た本文。"""
        con = sqlite3.connect(pagedb.db_path(self.wiki_dir))
        try:
            row = con.execute("SELECT body FROM pages WHERE subpath = ?", (subpath,)).fetchone()
        finally:
            con.close()
        return row[0] if row else None

    def test_範囲を出るときに確定する(self):
        self.write("A", "一\n")
        sync_wiki(self.wiki_dir, {})
        with bulkscope.scope():
            pagedb.record_page(self.wiki_dir, "A", ".md", "二\n")
            # 範囲の中では自分の書き込みが読める
            self.assertEqual(pagedb.load_page_body(self.wiki_dir, "A"), "二\n")
            # 外の接続には、まだ見えない
            self.assertEqual(self.outside_body("A"), "一\n")
        self.assertEqual(self.outside_body("A"), "二\n")

    def test_入れ子は外側でまとまる(self):
        self.write("A", "一\n")
        sync_wiki(self.wiki_dir, {})
        with bulkscope.scope():
            with bulkscope.scope():
                pagedb.record_page(self.wiki_dir, "A", ".md", "二\n")
            self.assertEqual(self.outside_body("A"), "一\n")
        self.assertEqual(self.outside_body("A"), "二\n")

    def test_範囲の外はこれまでどおり確定する(self):
        self.write("A", "一\n")
        sync_wiki(self.wiki_dir, {})
        pagedb.record_page(self.wiki_dir, "A", ".md", "二\n")
        self.assertEqual(self.outside_body("A"), "二\n")

    def test_解析は範囲の中だけ使い回す(self):
        text = "# 見出し\n\n`code` と [link](/X)\n"
        self.assertIsNot(plain_tokens(text, ".md"), plain_tokens(text, ".md"))
        with bulkscope.scope():
            self.assertIs(plain_tokens(text, ".md"), plain_tokens(text, ".md"))
            self.assertIsNot(plain_tokens(text, ".md"), plain_tokens(text + "x", ".md"))

    def test_名前の変更でリンクを直す(self):
        # 範囲の中で動く rename_page が、他のページのリンクと DB の記録を直す
        self.write("Doc/index", "# Doc\n")
        self.write("Doc/Sub", "# Sub\n")
        self.write("Ref", "# Ref\n\n[doc](/Doc) と [sub](/Doc/Sub)\n")
        sync_wiki(self.wiki_dir, {})
        ok, message, _ = rename_page(self.wiki_dir, {}, "Doc/index", "Book")
        self.assertTrue(ok, message)
        with open(os.path.join(self.wiki_dir, "Ref.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "# Ref\n\n[doc](/Book) と [sub](/Book/Sub)\n")
        self.assertEqual(self.outside_body("Ref"), "# Ref\n\n[doc](/Book) と [sub](/Book/Sub)\n")
        self.assertEqual(sorted(pagedb.backlinks_of(self.wiki_dir, "/Book")), ["Ref"])


if __name__ == "__main__":
    unittest.main()
