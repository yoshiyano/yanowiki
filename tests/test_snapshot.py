#!/usr/bin/env python3
"""ある時点のWikiの姿（wikilib.snapshot）のテスト。

保存・削除は pagesave と同じ順（差分を記録してからDBを書き換える）で、
backup と pagedb を直接呼んで再現する（レンダラやプラグインを要らなくするため）。

実行:
    .venv/bin/python3 tests/test_snapshot.py
"""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import backup, pagedb, snapshot  # noqa: E402


def at(stamp):
    return datetime.datetime.strptime(stamp, backup.BACKUP_STAMP)


class SnapshotTestBase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="wikitest-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def save(self, subpath, text, stamp):
        """保存（新規作成も）。統合させないよう merge=False で残す。"""
        old = pagedb.published_body(self.wiki_dir, subpath, "")
        backup.backup_page(self.wiki_dir, subpath, old, text, now=at(stamp), merge=False)
        pagedb.record_page(self.wiki_dir, subpath, ".md", text, now=at(stamp).timestamp())

    def delete(self, subpath, stamp):
        old = pagedb.published_body(self.wiki_dir, subpath, "")
        backup.backup_page(self.wiki_dir, subpath, old, "", now=at(stamp), merge=False)
        pagedb.remove_page(self.wiki_dir, subpath)

    def move(self, old, new, stamp):
        """改名（pagemove.move_page_records のうち、ここで効く2つ）。"""
        backup.move_backups(self.wiki_dir, old, new, now=at(stamp))
        pagedb.rename_page(self.wiki_dir, old, new, ".md")

    def names(self, folder, when):
        return [e["name"] for e in snapshot.folder_entries_at(self.wiki_dir, folder, when)]


class TestStamp(unittest.TestCase):
    def test_区切りはハイフンでも下線でもよい(self):
        self.assertEqual(snapshot.stamp_of_when("260928-101500"), "260928_101500")
        self.assertEqual(snapshot.stamp_of_when("260928_101500"), "260928_101500")

    def test_書式違いは断る(self):
        for bad in ("2609281015", "261328-101500", "", None):
            with self.assertRaises(ValueError):
                snapshot.stamp_of_when(bad)


class TestPageText(SnapshotTestBase):
    def test_各時点の本文(self):
        self.save("foo/bar", "一\n", "260901_100000")
        self.save("foo/bar", "一\n二\n", "260902_100000")
        self.save("foo/bar", "三\n", "260903_100000")
        get = lambda w: snapshot.page_text_at(self.wiki_dir, "/foo/bar", w)
        self.assertIsNone(get("260831-235959"))        # 作る前
        self.assertEqual(get("260901-100000"), "一\n")  # 保存したその秒を含む
        self.assertEqual(get("260902-095959"), "一\n")
        self.assertEqual(get("260902-120000"), "一\n二\n")
        self.assertEqual(get("260930-000000"), "三\n")

    def test_いまは消えたページも当時の本文が読める(self):
        self.save("foo/gone", "消える\n", "260901_100000")
        self.delete("foo/gone", "260905_100000")
        self.assertEqual(
            snapshot.page_text_at(self.wiki_dir, "/foo/gone", "260903-000000"), "消える\n")
        self.assertIsNone(
            snapshot.page_text_at(self.wiki_dir, "/foo/gone", "260906-000000"))

    def test_フォルダの入口を読む(self):
        self.save("foo/index", "入口\n", "260901_100000")
        self.assertEqual(snapshot.page_text_at(self.wiki_dir, "/foo", "260902-000000"), "入口\n")
        self.save("index", "トップ\n", "260901_100000")
        self.assertEqual(snapshot.page_text_at(self.wiki_dir, "/", "260902-000000"), "トップ\n")

    def test_記録の無いページはDBに入った日時で判断する(self):
        pagedb.record_page(self.wiki_dir, "old", ".md", "古い\n",
                           created="2026-09-10 00:00:00")
        state = snapshot.subpath_state_at(self.wiki_dir, "old", "260905-000000")
        self.assertFalse(state["exists"])
        state = snapshot.subpath_state_at(self.wiki_dir, "old", "260911-000000")
        self.assertEqual(state["text"], "古い\n")
        self.assertTrue(state["exact"])

    def test_記録より前の時点は最古の内容をexact無しで返す(self):
        # 記録が始まる前からあったページ（最古の記録の「前」が空でない）
        backup.backup_page(self.wiki_dir, "p", "前から\n", "後\n", now=at("260910_000000"))
        pagedb.record_page(self.wiki_dir, "p", ".md", "後\n")
        state = snapshot.subpath_state_at(self.wiki_dir, "p", "260901-000000")
        self.assertEqual(state["text"], "前から\n")
        self.assertFalse(state["exact"])


class TestFolderEntries(SnapshotTestBase):
    def setUp(self):
        super().setUp()
        self.save("foo/a", "A\n", "260901_100000")
        self.save("foo/b", "B\n", "260902_100000")
        self.save("foo/sub/c", "C\n", "260901_100000")
        self.save("foo/sub/index", "入口\n", "260903_100000")
        self.save("foo/deep/x/y", "Y\n", "260901_100000")
        self.save("other", "O\n", "260901_100000")
        self.delete("foo/a", "260904_100000")
        self.delete("foo/deep/x/y", "260904_100000")

    def test_削除済みのページもその時点に在れば一覧に出る(self):
        self.assertEqual(self.names("foo", "260903-120000"), ["a", "b", "deep", "sub"])

    def test_削除後の時点には出ない(self):
        self.assertEqual(self.names("/foo/", "260905-000000"), ["b", "sub"])

    def test_作る前の時点には出ない(self):
        self.assertEqual(self.names("foo", "260901-120000"), ["a", "deep", "sub"])

    def test_入口と下位ページ(self):
        entries = {e["name"]: e for e in
                   snapshot.folder_entries_at(self.wiki_dir, "foo", "260903-120000")}
        self.assertEqual(entries["sub"]["subpath"], "foo/sub/index")
        self.assertEqual(entries["sub"]["pagepath"], "foo/sub")
        self.assertTrue(entries["sub"]["has_more"])
        # 入口の無いフォルダ（通り道）。いまは中身ごと消えている
        self.assertIsNone(entries["deep"]["subpath"])
        self.assertEqual(entries["deep"]["pagepath"], "foo/deep")
        self.assertTrue(entries["deep"]["has_more"])
        self.assertEqual(entries["a"]["subpath"], "foo/a")
        self.assertFalse(entries["a"]["has_more"])
        # 入口を作る前は、sub は開けないフォルダ
        entries = {e["name"]: e for e in
                   snapshot.folder_entries_at(self.wiki_dir, "foo", "260902-120000")}
        self.assertIsNone(entries["sub"]["subpath"])

    def test_Wikiの直下(self):
        self.assertEqual(self.names("", "260903-120000"), ["foo", "other"])


class TestMoves(SnapshotTestBase):
    def test_改名前の時点では古い名前で見える(self):
        self.save("foo/a", "A1\n", "260901_100000")
        self.move("foo/a", "bar/b", "260902_100000")
        self.save("bar/b", "A2\n", "260903_100000")
        text = lambda p, w: snapshot.page_text_at(self.wiki_dir, p, w)  # noqa: E731
        self.assertEqual(text("/foo/a", "260901-120000"), "A1\n")
        self.assertIsNone(text("/bar/b", "260901-120000"))
        self.assertIsNone(text("/foo/a", "260902-120000"))
        self.assertEqual(text("/bar/b", "260902-120000"), "A1\n")
        self.assertEqual(text("/bar/b", "260904-000000"), "A2\n")
        self.assertEqual(self.names("foo", "260901-120000"), ["a"])
        self.assertEqual(self.names("bar", "260901-120000"), [])
        self.assertEqual(self.names("", "260901-120000"), ["foo"])
        self.assertEqual(self.names("", "260902-120000"), ["bar"])

    def test_改名のあと同じ名前で作り直したページと混ざらない(self):
        self.save("a", "旧\n", "260901_100000")
        self.move("a", "b", "260902_100000")
        self.save("a", "新\n", "260903_100000")
        text = lambda p, w: snapshot.page_text_at(self.wiki_dir, p, w)  # noqa: E731
        self.assertEqual(text("/a", "260901-120000"), "旧\n")
        self.assertIsNone(text("/a", "260902-120000"))
        self.assertEqual(text("/a", "260904-000000"), "新\n")
        self.assertEqual(self.names("", "260901-120000"), ["a"])
        self.assertEqual(self.names("", "260902-120000"), ["b"])
        self.assertEqual(self.names("", "260904-000000"), ["a", "b"])

    def test_続けて改名しても最初の名前まで戻る(self):
        self.save("a", "A\n", "260901_100000")
        self.move("a", "b", "260902_100000")
        self.move("b", "c/d", "260903_100000")
        self.assertEqual(self.names("", "260901-120000"), ["a"])
        self.assertEqual(self.names("", "260902-120000"), ["b"])
        self.assertEqual(self.names("c", "260903-120000"), ["d"])

    def test_記録の無いページの改名も戻る(self):
        pagedb.record_page(self.wiki_dir, "x", ".md", "X\n", created="2026-09-01 00:00:00")
        self.move("x", "x/index", "260905_100000")   # 入口へ移す（フォルダ化）
        entries = snapshot.folder_entries_at(self.wiki_dir, "", "260902-000000")
        self.assertEqual([(e["name"], e["subpath"]) for e in entries], [("x", "x")])
        entries = snapshot.folder_entries_at(self.wiki_dir, "", "260906-000000")
        self.assertEqual([(e["name"], e["subpath"]) for e in entries], [("x", "x/index")])
        self.assertEqual(snapshot.page_text_at(self.wiki_dir, "/x", "260902-000000"), "X\n")


if __name__ == "__main__":
    unittest.main()
