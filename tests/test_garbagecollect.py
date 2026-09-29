#!/usr/bin/env python3
"""削除したページの添付を trashbox へ集める（wikilib.garbagecollect、`/.garbagecollect`。
Wiki設計者の指示、2026-09-25）のテスト。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_garbagecollect.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import privilege_records, userdb  # noqa: E402
from wikilib.adminui import TOOLS  # noqa: E402
from wikilib.draft import save_draft  # noqa: E402
from wikilib.garbagecollect import (  # noqa: E402
    TRASHBOX_BODY, collect, find_orphans, trash_name,
)
from wikilib.paths import GARBAGECOLLECT_URLPATH  # noqa: E402


class GarbageBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="garbagecollect-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        self.attach_root = os.path.join(self.work, "wikidata", "testwiki", "attach")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        self.put("index")
        self.put("Live")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, subpath, ext=".md"):
        path = os.path.join(self.wiki_dir, subpath + ext)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("本文\n")

    def attach(self, subpath, name="a.png", data=b"x"):
        directory = os.path.join(self.attach_root, subpath)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), "wb") as f:
            f.write(data)

    def trash(self):
        directory = os.path.join(self.attach_root, "trashbox")
        return sorted(os.listdir(directory)) if os.path.isdir(directory) else []

    def rule(self, kind):
        return privilege_records.find(privilege_records.load(self.wiki_dir), "trashbox", kind)


class TestFindOrphans(GarbageBase):

    def test_ページが無い添付を拾う(self):
        self.attach("Gone")
        self.assertEqual(find_orphans(self.wiki_dir), [("Gone", ["a.png"])])

    def test_ページがある添付は拾わない(self):
        self.attach("Live")
        self.put("Tech/index", ".txt")
        self.attach("Tech/index")
        self.assertEqual(find_orphans(self.wiki_dir), [])

    def test_書きかけがあれば拾わない(self):
        self.attach("Writing")
        save_draft(self.wiki_dir, "Writing", "書きかけ")
        self.assertEqual(find_orphans(self.wiki_dir), [])

    def test_trashbox自身と移動の途中は拾わない(self):
        self.attach("trashbox")
        self.attach("Moving.moving")
        self.assertEqual(find_orphans(self.wiki_dir), [])

    def test_attach直下のファイルは拾わない(self):
        os.makedirs(self.attach_root)
        with open(os.path.join(self.attach_root, "README.txt"), "w") as f:
            f.write("説明")
        self.assertEqual(find_orphans(self.wiki_dir), [])


class TestTrashName(unittest.TestCase):

    def test_区切りを下線にして2本の下線でつなぐ(self):
        self.assertEqual(trash_name("講義/第01回", "a.png"), "講義_第01回__a.png")
        self.assertEqual(trash_name("Gone", "a.png"), "Gone__a.png")


class TestCollect(GarbageBase):

    def test_trashboxへ移す(self):
        self.attach("講義/第01回", "a.png")
        result = collect(self.wiki_dir, {})
        self.assertTrue(result["ready"])
        self.assertEqual(result["moved"], [("講義/第01回", "a.png", "講義_第01回__a.png")])
        self.assertEqual(self.trash(), ["講義_第01回__a.png"])
        # 空になった元の置き場は片付ける
        self.assertFalse(os.path.exists(os.path.join(self.attach_root, "講義")))

    def test_trashboxのページはattachlsだけ(self):
        self.attach("Gone")
        collect(self.wiki_dir, {})
        with open(os.path.join(self.wiki_dir, "trashbox.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), TRASHBOX_BODY)
        self.assertEqual(TRASHBOX_BODY, "#attachls\n")

    def test_trashboxは管理者と助手だけ(self):
        self.attach("Gone")
        collect(self.wiki_dir, {})
        for kind in (privilege_records.READ, privilege_records.WRITE):
            self.assertEqual(self.rule(kind)["who"], ["admin", "g:staff"])

    def test_決めてある権限は上書きしない(self):
        privilege_records.put(self.wiki_dir, "trashbox", privilege_records.READ, "g:all")
        self.attach("Gone")
        collect(self.wiki_dir, {})
        self.assertEqual(self.rule(privilege_records.READ)["who"], ["g:all"])
        self.assertEqual(self.rule(privilege_records.WRITE)["who"], ["admin", "g:staff"])

    def test_同じ名前があれば番号を付ける(self):
        self.attach("trashbox", "Gone__a.png", b"old")
        self.put("trashbox", ".txt")
        self.attach("Gone", "a.png", b"new")
        collect(self.wiki_dir, {})
        self.assertEqual(self.trash(), ["Gone__a.png", "Gone__a_2.png"])
        with open(os.path.join(self.attach_root, "trashbox", "Gone__a.png"), "rb") as f:
            self.assertEqual(f.read(), b"old")

    def test_権限を書けなければ移さない(self):
        # アカウントの記録が無い（admin が居ない）Wikiでは行を書けない
        os.remove(userdb.db_path(self.wiki_dir))
        self.attach("Gone")
        result = collect(self.wiki_dir, {})
        self.assertFalse(result["ready"])
        self.assertEqual(result["moved"], [])
        self.assertTrue(os.path.isfile(os.path.join(self.attach_root, "Gone", "a.png")))
        self.assertFalse(os.path.exists(os.path.join(self.wiki_dir, "trashbox.txt")))

    def test_移すものが無ければ何も作らない(self):
        result = collect(self.wiki_dir, {})
        self.assertEqual(result, {"moved": [], "ready": True})
        self.assertFalse(os.path.exists(os.path.join(self.wiki_dir, "trashbox.txt")))
        self.assertIsNone(self.rule(privilege_records.READ))

    def test_trashboxのページだけ消されていたら作り直す(self):
        self.attach("trashbox", "Gone__a.png")
        collect(self.wiki_dir, {})
        self.assertTrue(os.path.isfile(os.path.join(self.wiki_dir, "trashbox.txt")))
        self.assertIsNotNone(self.rule(privilege_records.READ))


class TestAdminMenu(unittest.TestCase):

    def test_管理者メニューに並ぶ(self):
        tools = {urlpath: admin_only for urlpath, _l, _n, admin_only in TOOLS}
        self.assertIn(GARBAGECOLLECT_URLPATH, tools)
        self.assertFalse(tools[GARBAGECOLLECT_URLPATH])  # 管理者と助手


if __name__ == "__main__":
    unittest.main()
