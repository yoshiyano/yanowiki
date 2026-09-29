#!/usr/bin/env python3
"""Wikiの取り違えを防ぐ目印（`wikilib.wikimark`）のテスト。

**「いまそのWikiを実際に見ている人にしか書けない値」**を作るところ。
`./wiki.py resetpw`（フッターを丸ごと貼る）と `/.delwiki` の3段目
（2つの値を別々に書く）が、どちらもここを通る。

見るのは次の3つ。

  - **フッターと同じ行を作る**（`TestMarks`）。貼り付けと突き合わせられる形か
  - **書きかたの揺れを吸収する**（`TestNormalize`）。確かめたいのは値を
    知っているかどうかで、書式を揃える練習ではない
  - **見ただけでは何も書き足さない**（`TestNoSideEffect`）。目印を作るだけの
    つもりで、そのWikiに空のDBを生やしてしまわないこと

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_wikimark.py     （このファイルだけ）
"""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import diskusage, wikimark  # noqa: E402


class WikimarkBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="wikimark-")
        self.wiki_dir = os.path.join(self.work, "sandbox", "wiki")
        os.makedirs(self.wiki_dir)
        with open(os.path.join(self.wiki_dir, "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# トップ\n")
        diskusage.invalidate(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)


class TestMarks(WikimarkBase):

    def test_フッターと同じ2行ができる(self):
        marks = wikimark.marks(self.wiki_dir)
        self.assertEqual(len(marks), 2)
        self.assertTrue(marks[0].startswith("Last-modified: "))
        self.assertTrue(marks[1].startswith("DiskUsage: Page/Attached "))

    def test_貼り付けと突き合わせられる(self):
        pasted = "Convert-time: 17.1ms " + " ".join(wikimark.marks(self.wiki_dir))
        self.assertEqual(wikimark.missing_marks(self.wiki_dir, pasted), [])

    def test_合わなければ足りない印が返る(self):
        missing = wikimark.missing_marks(self.wiki_dir, "まるで関係のない文字列")
        self.assertEqual(len(missing), 2)

    def test_トップページが無ければ日時は作れない(self):
        os.remove(os.path.join(self.wiki_dir, "index.md"))
        self.assertIsNone(wikimark.source_updated(self.wiki_dir))
        # 使用量のほうは数えられるので、印が1つだけ返る（呼ぶ側が数を見る）
        self.assertEqual(len(wikimark.marks(self.wiki_dir)), 1)

    def test_使用量は2つの値を並べた形(self):
        self.assertIn("/", wikimark.usage_text(self.wiki_dir))


class TestNormalize(unittest.TestCase):
    """**書きかたの揺れは吸収する。**"""

    def test_使用量はフッターの行ごと貼れる(self):
        self.assertEqual(
            wikimark.normalize_usage("DiskUsage: Page/Attached 1.2MB/349KB"),
            wikimark.normalize_usage("1.2MB/349KB"))
        self.assertEqual(wikimark.normalize_usage(" 1.2mb / 349kb "), "1.2MB/349KB")

    def test_日付はいくつかの書きかたを通す(self):
        for typed in ("2026-09-18", "2026/09/18", "20260918",
                      "2026-09-18 14:33", "Last-modified: 2026-09-18 14:33"):
            self.assertEqual(wikimark.normalize_day(typed), "2026-09-18", typed)

    def test_読めない日付は空(self):
        for typed in ("", "きのう", "18-09-2026", "2026-13"):
            self.assertEqual(wikimark.normalize_day(typed), "")


class TestTyped(WikimarkBase):
    """2つの値を別々に書いてもらう場合（`/.delwiki` の3段目）。"""

    def test_合っていれば通る(self):
        day = datetime.date.today().strftime("%Y-%m-%d")
        self.assertTrue(wikimark.typed_matches(
            self.wiki_dir, wikimark.usage_text(self.wiki_dir), day))

    def test_どちらか違えば通らない(self):
        day = datetime.date.today().strftime("%Y-%m-%d")
        usage = wikimark.usage_text(self.wiki_dir)
        self.assertFalse(wikimark.typed_matches(self.wiki_dir, "999MB/999MB", day))
        self.assertFalse(wikimark.typed_matches(self.wiki_dir, usage, "2000-01-01"))


class TestNoSideEffect(WikimarkBase):
    """**見ただけでは何も書き足さない。**

    `pagedb.page_updated_at` は開くついでにDBを作るので、素直に呼ぶと
    「消す前に様子を見ただけ」のWikiに空のDBが生える。`/.delwiki` では
    それが**書庫を作り終えたあと**に起きるので、戻したときに無いファイルが
    できてしまう。"""

    def test_DBを作らない(self):
        wikimark.updated_days(self.wiki_dir)
        wikimark.marks(self.wiki_dir)
        pageinfo = os.path.join(os.path.dirname(self.wiki_dir), "pageinfo")
        self.assertFalse(os.path.exists(pageinfo))


if __name__ == "__main__":
    unittest.main(verbosity=2)
