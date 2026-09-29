#!/usr/bin/env python3
"""中身の無いフォルダの扱い（Wiki設計者の指示、2026-09-25）のテスト。

ページの一覧（`pagetree.build_page_tree`）は空のフォルダを表示から外すだけで、
消すのは取り込み（`pagesync.prune_empty_folders`、`sync_wiki` から呼ぶ）が行う。
どちらも、書きかけがある・入口（`X/index`）に添付があるフォルダは残す。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_emptyfolders.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.draft import save_draft  # noqa: E402
from wikilib.pagesync import (  # noqa: E402
    EMPTY_FOLDER_MIN_AGE, format_result, prune_empty_attach_folders, prune_empty_folders,
    sync_wiki,
)
from wikilib.pagetree import build_page_tree  # noqa: E402

OLD = time.time() - EMPTY_FOLDER_MIN_AGE - 60


class EmptyFolderBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="emptyfolders-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        self.put("index")
        self.put("Tech/Notes")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, subpath):
        path = os.path.join(self.wiki_dir, subpath + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 見出し\n\n本文\n")

    def folder(self, subpath, old=True):
        """空のフォルダを作る。old なら、作られたばかりではない時刻にする。"""
        path = os.path.join(self.wiki_dir, subpath)
        os.makedirs(path, exist_ok=True)
        if old:
            parts = subpath.split("/")
            for i in range(1, len(parts) + 1):
                p = os.path.join(self.wiki_dir, *parts[:i])
                os.utime(p, (OLD, OLD))
        return path

    def attach(self, subpath, name="a.png"):
        directory = os.path.join(self.work, "wikidata", "testwiki", "attach", subpath)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), "wb") as f:
            f.write(b"x")

    def exists(self, subpath):
        return os.path.isdir(os.path.join(self.wiki_dir, subpath))

    def names(self, node=None):
        node = node or build_page_tree(self.wiki_dir)
        return [c["name"] for c in node["children"]]


class TestPageTree(EmptyFolderBase):
    """一覧は空のフォルダを出さない（ファイルには触らない）。"""

    def test_空のフォルダは出さない(self):
        self.folder("sandbox")
        self.assertNotIn("sandbox", self.names())
        self.assertTrue(self.exists("sandbox"))  # 消すのは一覧の役目ではない

    def test_空のフォルダしか無いフォルダも出さない(self):
        self.folder("a/b/c")
        self.assertNotIn("a", self.names())

    def test_ページのあるフォルダは出す(self):
        self.assertIn("Tech", self.names())

    def test_入口に添付があれば出す(self):
        self.folder("Box")
        self.attach("Box/index")
        tree = build_page_tree(self.wiki_dir)
        box = next(c for c in tree["children"] if c["name"] == "Box")
        self.assertEqual(self.names(box), ["index"])

    def test_書きかけがあれば出す(self):
        self.folder("Draft")
        save_draft(self.wiki_dir, "Draft/New", "書きかけ")
        self.assertIn("Draft", self.names())


class TestPrune(EmptyFolderBase):
    """取り込みが空のフォルダを消す。"""

    def test_空のフォルダを消す(self):
        self.folder("sandbox")
        self.assertEqual(prune_empty_folders(self.wiki_dir), ["sandbox"])
        self.assertFalse(self.exists("sandbox"))

    def test_空のフォルダしか無いフォルダもまとめて消す(self):
        self.folder("a/b/c")
        self.assertEqual(prune_empty_folders(self.wiki_dir), ["a", "a/b", "a/b/c"])
        self.assertFalse(self.exists("a"))

    def test_ページのあるフォルダは残す(self):
        prune_empty_folders(self.wiki_dir)
        self.assertTrue(self.exists("Tech"))

    def test_作られたばかりなら残す(self):
        # 保存の途中（階層を作ってからファイルを書くまで）かもしれない
        self.folder("Fresh", old=False)
        self.assertEqual(prune_empty_folders(self.wiki_dir), [])
        self.assertTrue(self.exists("Fresh"))

    def test_入口に添付があれば残す(self):
        self.folder("Box")
        self.attach("Box/index")
        self.assertEqual(prune_empty_folders(self.wiki_dir), [])

    def test_書きかけがあれば残す(self):
        self.folder("Draft")
        save_draft(self.wiki_dir, "Draft/New", "書きかけ")
        self.assertEqual(prune_empty_folders(self.wiki_dir), [])

    def test_ルートは消さない(self):
        empty = os.path.join(self.work, "wikidata", "empty", "wiki")
        os.makedirs(empty)
        os.utime(empty, (OLD, OLD))
        self.assertEqual(prune_empty_folders(empty), [])
        self.assertTrue(os.path.isdir(empty))


class TestPruneAttach(EmptyFolderBase):
    """添付の置き場（attach/）の空のフォルダも取り込みが消す。"""

    def attach_folder(self, subpath, old=True):
        root = os.path.join(self.work, "wikidata", "testwiki", "attach")
        path = os.path.join(root, subpath)
        os.makedirs(path, exist_ok=True)
        if old:
            parts = subpath.split("/")
            for i in range(1, len(parts) + 1):
                p = os.path.join(root, *parts[:i])
                os.utime(p, (OLD, OLD))
        return path

    def test_空の置き場を消す(self):
        path = self.attach_folder("sandbox")
        self.assertEqual(prune_empty_attach_folders(self.wiki_dir), ["sandbox"])
        self.assertFalse(os.path.isdir(path))

    def test_空のフォルダしか無いフォルダもまとめて消す(self):
        self.attach_folder("講義/第01回/ガイダンス")
        self.assertEqual(prune_empty_attach_folders(self.wiki_dir),
                         ["講義", "講義/第01回", "講義/第01回/ガイダンス"])

    def test_添付のある置き場は残す(self):
        self.attach("Tech/Notes")
        self.attach_folder("Tech")
        self.assertEqual(prune_empty_attach_folders(self.wiki_dir), [])

    def test_作られたばかりなら残す(self):
        self.attach_folder("Fresh", old=False)
        self.assertEqual(prune_empty_attach_folders(self.wiki_dir), [])

    def test_置き場が無くても落ちない(self):
        self.assertEqual(prune_empty_attach_folders(self.wiki_dir), [])

    def test_全体の取り込みで片付けてログに出す(self):
        self.attach_folder("sandbox")
        result = sync_wiki(self.wiki_dir, config={})
        self.assertEqual(result["pruned_attach"], ["sandbox"])
        self.assertIn("[testwiki] attach/sandbox/", format_result({"testwiki": result}))


class TestSyncWiki(EmptyFolderBase):
    """Wiki全体の取り込みでだけ片付け、起動ログに出す。"""

    def test_全体の取り込みで片付ける(self):
        self.folder("sandbox")
        result = sync_wiki(self.wiki_dir, config={})
        self.assertEqual(result["pruned"], ["sandbox"])
        self.assertIn("中身の無いフォルダを1件片付けました", format_result({"testwiki": result}))
        self.assertIn("[testwiki] /sandbox/", format_result({"testwiki": result}))

    def test_1ページだけの取り込みでは片付けない(self):
        self.folder("sandbox")
        result = sync_wiki(self.wiki_dir, config={}, subpath="index")
        self.assertEqual(result["pruned"], [])
        self.assertTrue(self.exists("sandbox"))


if __name__ == "__main__":
    unittest.main()
