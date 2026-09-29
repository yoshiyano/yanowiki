#!/usr/bin/env python3
"""平文ファイルの取り込み（wikilib.pagesync）のうち、**1回目の扱い**のテスト。

取ってきた一式にはページの平文だけが入っていて、引くための記録
（`pageinfo/wikiall.db`）は入っていない。**はじめて動かしたときに、置いて
あるページを全部登録する**（Wiki設計者の指示、2026-09-08）。

以前もページ自体は入っていたが、数えかたが「目次・リンクの取り出し」で、
**初めて動かした人には何が起きたのか読み取れなかった。** ここで見るのは
その数えかたと、書き添える1行である。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pagesync.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import pagedb  # noqa: E402
from wikilib.pagesync import format_result, sync_wiki  # noqa: E402


class SyncTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pagesync-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        for name in ("index", "Guide", "Tech/Notes"):
            self.put(name)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, subpath, text="# 見出し\n\n本文\n"):
        path = os.path.join(self.wiki_dir, subpath + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def sync(self):
        return sync_wiki(self.wiki_dir, config={})


class TestFirstSync(SyncTestBase):
    """1回目（記録がまだ無い）。"""

    def test_全部を追加として数える(self):
        result = self.sync()
        self.assertTrue(result["first"])
        self.assertEqual(result["added"], 3)
        self.assertEqual(result["filled"], 0)

    def test_取り出しも済ませる(self):
        # 逆リンクは全ページ分が揃わないと数えられないので、1回目でまとめて
        self.sync()
        for row in pagedb.all_pages(self.wiki_dir):
            self.assertIsNotNone(row["toc"], row["subpath"])

    def test_どのページかも残す(self):
        result = self.sync()
        kinds = {kind for kind, _sub in result["pages"]}
        self.assertEqual(kinds, {"added"})
        self.assertEqual(len(result["pages"]), 3)

    def test_2回目は1回目ではない(self):
        self.sync()
        result = self.sync()
        self.assertFalse(result["first"])
        self.assertEqual((result["added"], result["updated"], result["filled"]),
                         (0, 0, 0))

    def test_2回目からは変わったぶんだけ(self):
        self.sync()
        self.put("New")
        result = self.sync()
        self.assertFalse(result["first"])
        self.assertEqual(result["added"], 1)

    def test_記録を消せばまた1回目(self):
        # 記録はいつ消してもよい（正本は平文のほう）。消したら作り直される
        self.sync()
        os.remove(pagedb.db_path(self.wiki_dir))
        result = self.sync()
        self.assertTrue(result["first"])
        self.assertEqual(result["added"], 3)


class TestFormatResult(unittest.TestCase):
    """起動ログの1行。"""

    def line(self, **over):
        result = {"updated": 0, "added": 0, "removed": 0, "filled": 0,
                  "seconds": 1.0, "pages": [], "shadowed": [], "first": False}
        result.update(over)
        return format_result({"testwiki": result})

    def test_1回目はそのことを書き添える(self):
        got = self.line(first=True, added=139)
        self.assertIn("追加139", got)
        self.assertIn("記録がまだ無かったので", got)
        self.assertIn("testwiki", got)

    def test_2回目からは書き添えない(self):
        got = self.line(added=1)
        self.assertIn("追加1", got)
        self.assertNotIn("記録がまだ無かったので", got)

    def test_変わらなければ変更なし(self):
        self.assertIn("変更なし", self.line())

    def test_古い形の結果でも落ちない(self):
        # "first" を持たない結果（他所から渡されたもの）でも読める
        got = format_result({"testwiki": {"updated": 0, "added": 0, "removed": 0,
                                          "filled": 0, "seconds": 0.5}})
        self.assertIn("変更なし", got)


if __name__ == "__main__":
    unittest.main()
