#!/usr/bin/env python3
"""ページの一覧を作る層（`wikilib.pagelist`）のテスト。

**一覧を得る道を4本に決め、そこで必ず閲覧の権限を見る**（Wiki設計者の指示、
2026-09-17）。ここでは次を確かめる。

  - `scandir`（1階層）・`walk`（下位すべて）・`glob`（パターン）・`filter`（手元の並び）
  - どの道も、読めないページ（`-`）を落とす。`need=PAGE_WRITE` なら編集できるものだけ、
    `need=None` なら絞らない（アクセス権は入れて返す）
  - 返すのは名前ではなく `PageItem`（タイトル・更新日時などを持つ）
  - 出どころは公開された内容（DB）が既定で、平文ファイル側も選べる
  - 成り代わり（`act_as`）にも従う

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pagelist.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import auth, pagedb, pagelist, paths, privilege_records, userdb  # noqa: E402
from wikilib.auth import PAGE_NONE, PAGE_READ, PAGE_WRITE, SYSTEM_UID, act_as  # noqa: E402

FARM = "testwiki"


class PageListTestBase(unittest.TestCase):
    """次の形のWikiを作る。

        index                    トップ
        Open                     設定の無いページ
        Tech/index               フォルダ Tech の入口（ページ /Tech）
        Tech/Secret              alice だけが読める（R）
        Tech/Sub/Deep            通り道でしかないフォルダ Tech/Sub の下
        Locked                   carol だけが読める（alice も bob も読めない）
    """

    PAGES = ("index", "Open", "Tech/index", "Tech/Secret", "Tech/Sub/Deep", "Locked")

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pagelist-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob", "carol"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        bottle.request.bind({})
        for i, subpath in enumerate(self.PAGES):
            body = "# {}の題名\n\n本文\n".format(subpath)
            self.assertTrue(pagedb.record_page(self.wiki_dir, subpath, ".md", body))
            self.assertTrue(pagedb.record_page_info(
                self.wiki_dir, subpath, subpath + "の題名", [], []))
        self.rule("Tech/Secret", "R", "alice")
        self.rule("Locked", "R", "carol")

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def rule(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)

    def names(self, items):
        return [i.pagepath for i in items]


class TestWalk(PageListTestBase):

    def test_下位すべてをページパスで返す(self):
        with act_as("alice"):
            self.assertEqual(self.names(pagelist.walk(self.wiki_dir)),
                             ["", "Open", "Tech", "Tech/Secret", "Tech/Sub/Deep"])

    def test_読めないページは落ちる(self):
        with act_as("bob"):
            got = self.names(pagelist.walk(self.wiki_dir))
        self.assertNotIn("Tech/Secret", got)
        self.assertNotIn("Locked", got)

    def test_範囲を絞れる(self):
        with act_as("alice"):
            self.assertEqual(self.names(pagelist.walk(self.wiki_dir, under="Tech")),
                             ["Tech", "Tech/Secret", "Tech/Sub/Deep"])

    def test_項目はタイトルと更新日時を持つ(self):
        with act_as("alice"):
            item = [i for i in pagelist.walk(self.wiki_dir) if i.pagepath == "Open"][0]
        self.assertEqual(item.title, "Openの題名")
        self.assertTrue(item.updated)
        self.assertTrue(item.exists)
        self.assertEqual(item.privilege, PAGE_WRITE)


class TestScandir(PageListTestBase):

    def test_1階層だけ返す(self):
        with act_as("alice"):
            self.assertEqual(self.names(pagelist.scandir(self.wiki_dir)),
                             ["", "Open", "Tech"])   # Locked は carol だけ

    def test_フォルダの入口は1件にまとまる(self):
        with act_as("alice"):
            tech = [i for i in pagelist.scandir(self.wiki_dir) if i.pagepath == "Tech"][0]
        self.assertEqual(tech.subpath, "Tech/index")
        self.assertTrue(tech.exists)
        self.assertTrue(tech.has_children)   # Tech/Secret と Tech/Sub/Deep がある

    def test_通り道でしかないフォルダも返す(self):
        with act_as("alice"):
            items = pagelist.scandir(self.wiki_dir, under="Tech")
        sub = [i for i in items if i.pagepath == "Tech/Sub"][0]
        self.assertFalse(sub.exists)         # そこ自身は開けない
        self.assertTrue(sub.has_children)
        self.assertEqual(sub.title, "")

    def test_読めないページは落ちる(self):
        with act_as("bob"):
            self.assertNotIn("Tech/Secret",
                             self.names(pagelist.scandir(self.wiki_dir, under="Tech")))

    def test_中身が全部隠れた通り道のフォルダは出さない(self):
        # Tech/Sub の下は Tech/Sub/Deep だけ。それを読めなくすると、
        # 開いても何も無い「Tech/Sub」を出しても仕方がない
        self.rule("Tech/Sub/Deep", "R", "carol")
        with act_as("bob"):
            self.assertNotIn("Tech/Sub",
                             self.names(pagelist.scandir(self.wiki_dir, under="Tech")))
        with act_as("carol"):
            self.assertIn("Tech/Sub",
                          self.names(pagelist.scandir(self.wiki_dir, under="Tech")))

    def test_has_childrenは見える範囲で決まる(self):
        # Tech の下は Tech/Secret（alice だけ）と Tech/Sub/Deep（carol だけ）
        self.rule("Tech/Sub/Deep", "R", "carol")
        with act_as("bob"):
            tech = [i for i in pagelist.scandir(self.wiki_dir) if i.pagepath == "Tech"][0]
        self.assertFalse(tech.has_children)   # bob にはどちらも見えない
        with act_as("alice"):
            tech = [i for i in pagelist.scandir(self.wiki_dir) if i.pagepath == "Tech"][0]
        self.assertTrue(tech.has_children)


class TestGlob(PageListTestBase):

    def test_星は階層も跨ぐ(self):
        with act_as("alice"):
            self.assertEqual(self.names(pagelist.glob(self.wiki_dir, "Tech/*")),
                             ["Tech/Secret", "Tech/Sub/Deep"])

    def test_大文字小文字を区別しない(self):
        with act_as("alice"):
            self.assertEqual(self.names(pagelist.glob(self.wiki_dir, "open")), ["Open"])

    def test_読めないページは落ちる(self):
        with act_as("bob"):
            self.assertEqual(self.names(pagelist.glob(self.wiki_dir, "Tech/*")),
                             ["Tech/Sub/Deep"])


class TestFilter(PageListTestBase):

    def test_並び順はそのまま(self):
        with act_as("alice"):
            got = pagelist.filter(self.wiki_dir, ["Tech/Secret", "Open", "Tech"])
        self.assertEqual(self.names(got), ["Tech/Secret", "Open", "Tech"])

    def test_読めないものだけ落ちる(self):
        with act_as("bob"):
            got = pagelist.filter(self.wiki_dir, ["Tech/Secret", "Open", "Locked"])
        self.assertEqual(self.names(got), ["Open"])

    def test_実体パスでも渡せる(self):
        with act_as("alice"):
            got = pagelist.filter(self.wiki_dir, ["Tech/index"], by="subpath")
        self.assertEqual(self.names(got), ["Tech"])

    def test_同じ名前は1度だけ(self):
        with act_as("alice"):
            got = pagelist.filter(self.wiki_dir, ["Open", "Open"])
        self.assertEqual(len(got), 1)

    def test_まだ無いページはexistsが偽(self):
        with act_as("alice"):
            got = pagelist.filter(self.wiki_dir, ["NoSuchPage"])
        self.assertEqual(self.names(got), ["NoSuchPage"])
        self.assertFalse(got[0].exists)


class TestNeed(PageListTestBase):
    """`need` の3通り。既定は `PAGE_READ`（読めるもの）。"""

    def test_既定は読めるもの(self):
        with act_as("alice"):
            got = pagelist.walk(self.wiki_dir)
        self.assertIn("Tech/Secret", self.names(got))   # alice は R

    def test_WRITEなら編集できるものだけ(self):
        # alice は Tech/Secret を読めるが、書ける人ではない（W は bob だけ。W の指定が無ければ
        # 読める人は書ける）
        privilege_records.put(self.wiki_dir, "Tech/Secret", "W", "bob")
        with act_as("alice"):
            got = pagelist.walk(self.wiki_dir, need=PAGE_WRITE)
        self.assertNotIn("Tech/Secret", self.names(got))
        self.assertIn("Open", self.names(got))

    def test_Noneなら絞らないがアクセス権は入る(self):
        with act_as("bob"):
            got = pagelist.walk(self.wiki_dir, need=None)
        names = self.names(got)
        self.assertIn("Tech/Secret", names)
        secret = [i for i in got if i.pagepath == "Tech/Secret"][0]
        self.assertEqual(secret.privilege, PAGE_NONE)

    def test_システムはすべて見える(self):
        with act_as(SYSTEM_UID):
            got = pagelist.walk(self.wiki_dir)
        self.assertEqual(len(got), len(self.PAGES))   # Locked も含めて全部
        self.assertTrue(all(i.privilege == PAGE_WRITE for i in got))

    def test_判定器を渡せば作り直さない(self):
        judge = auth.page_privilege(self.wiki_dir, "alice")
        got = pagelist.walk(self.wiki_dir, privilege=judge)   # 未ログインのまま
        self.assertIn("Tech/Secret", self.names(got))          # alice として判定された


class TestSourceFiles(PageListTestBase):
    """平文ファイル側（編集の道具が使う）。"""

    def setUp(self):
        super().setUp()
        # DBには無く、平文だけあるページ（取り込み前）
        with open(os.path.join(self.wiki_dir, "Draft.md"), "w", encoding="utf-8") as f:
            f.write("まだ取り込んでいない\n")

    def test_平文だけのページも出る(self):
        with act_as("alice"):
            got = self.names(pagelist.walk(self.wiki_dir, source=pagelist.SOURCE_FILES))
        self.assertEqual(got, ["Draft"])   # DBのページは平文ファイルを持たない

    def test_公開された内容には出ない(self):
        with act_as("alice"):
            self.assertNotIn("Draft", self.names(pagelist.walk(self.wiki_dir)))

    def test_平文側でも権限で絞る(self):
        with open(os.path.join(self.wiki_dir, "Locked.md"), "w", encoding="utf-8") as f:
            f.write("読めないページの平文\n")
        with act_as("bob"):
            got = self.names(pagelist.walk(self.wiki_dir, source=pagelist.SOURCE_FILES))
        self.assertNotIn("Locked", got)


if __name__ == "__main__":
    unittest.main()
