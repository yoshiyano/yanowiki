#!/usr/bin/env python3
"""名前の変更を作業の手順のファイルに沿って行い、止めて続きから再開する（wikilib.operations、
pagerename。2026-10-01）のテスト。

- ［中止］・時間切れで、ページとページの間で止まり、手順のファイルが "paused" で残る
- 再開すると最後まで済み、止めずに行った場合とページのファイルが同じになる
- 動いたページ自身のリンクを二重に直さない（中断中に編集されても、もう直さない）
- 中断中は、範囲が重なる名前の変更を断る（重ならないものは通す）
- サーバーが途中で止まった形（"running" のまま残ったファイル）からも続けられる

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_operations.py     （このファイルだけ）
"""
import filecmp
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import operations, paths  # noqa: E402
from wikilib.pagerename import rename_page, resume_operation  # noqa: E402
from wikilib.pagesync import sync_wiki  # noqa: E402

FARM = "testwiki"
REFS = 6   # 動かすページを指すページの数


class CancelAfter(operations.Progress):
    """手順・ページに n 回手を付けたら（begin）、［中止］が押されたことにする。
    済んで飛ばした手順は数えない（再開のたびに少しずつ進むように）。"""

    def __init__(self, n):
        self.n, self.count, self.total = n, 0, 0

    def add_total(self, n):
        self.total += n

    def begin(self, item):
        self.count += 1

    def cancelled(self):
        return self.count >= self.n


def pages(work):
    return {
        "Doc/index": "# Doc\n\n[sub](./Sub) と [ref](/Ref1)\n",
        "Doc/Sub": "# Sub\n\n[兄弟](../Other) [上](/Doc) [外](/Ref2)\n",
        "Doc/Other": "# Other\n",
        **{f"Ref{i}": f"# Ref{i}\n\n[doc](/Doc) と [sub](/Doc/Sub)\n" for i in range(1, REFS + 1)},
        "Far": "# Far\n",
    }


class OperationsTestBase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="operations-")
        self.kept = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        bottle.request.bind({})
        self.wiki_dir = self.make_wiki("main")

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept
        shutil.rmtree(self.work, ignore_errors=True)

    def make_wiki(self, name):
        wiki_dir = os.path.join(self.work, "wikidata", name, "wiki")
        for subpath, body in pages(self.work).items():
            path = os.path.join(wiki_dir, subpath + ".md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
        sync_wiki(wiki_dir, {})
        return wiki_dir

    def read(self, wiki_dir, subpath):
        with open(os.path.join(wiki_dir, subpath + ".md"), encoding="utf-8") as f:
            return f.read()

    def same_tree(self, a, b):
        """2つの Wiki のページのファイルが同じか（ファイルの並びと中身）。"""
        cmp = filecmp.dircmp(a, b)
        stack = [cmp]
        while stack:
            c = stack.pop()
            self.assertEqual((c.left_only, c.right_only), ([], []), c.left)
            _, mismatch, errors = filecmp.cmpfiles(c.left, c.right, c.common_files, shallow=False)
            self.assertEqual((mismatch, errors), ([], []), c.left)
            stack.extend(c.subdirs.values())


class TestStopAndResume(OperationsTestBase):
    def test_中止して再開すると止めずに行ったのと同じになる(self):
        reference = self.make_wiki("reference")
        ok, message, _ = rename_page(reference, {}, "Doc/index", "Book")
        self.assertTrue(ok, message)

        progress = CancelAfter(10)   # 手順（7）を終え、直すページの途中で止まる
        ok, message, _ = rename_page(self.wiki_dir, {}, "Doc/index", "Book", progress=progress)
        self.assertFalse(ok)
        self.assertIn("中止しました", message)
        op = progress.paused
        self.assertIsNotNone(op)
        saved = operations.load(self.wiki_dir, op["id"])
        self.assertEqual(saved["state"], "paused")
        self.assertIn("move", saved["done"])
        self.assertNotIn("fix", saved["done"])
        self.assertGreater(progress.total, 7)

        ok, message, pagepath = resume_operation(self.wiki_dir, {}, op["id"])
        self.assertTrue(ok, message)
        self.assertEqual(pagepath, "Book")
        self.assertIsNone(operations.load(self.wiki_dir, op["id"]))   # 済んだら消える
        self.same_tree(reference, self.wiki_dir)

    def test_何度止めても同じになる(self):
        reference = self.make_wiki("reference")
        rename_page(reference, {}, "Doc/index", "Book")
        progress = CancelAfter(8)
        rename_page(self.wiki_dir, {}, "Doc/index", "Book", progress=progress)
        op_id = progress.paused["id"]
        for _ in range(REFS + 5):
            progress = CancelAfter(2)
            ok, message, _ = resume_operation(self.wiki_dir, {}, op_id, progress=progress)
            if ok:
                break
        self.assertTrue(ok, message)
        self.same_tree(reference, self.wiki_dir)

    def test_時間切れで止まる(self):
        progress = operations.Progress()
        ok, message, _ = rename_page(self.wiki_dir, {}, "Doc/index", "Book",
                                     progress=progress, time_limit=0)
        self.assertFalse(ok)
        self.assertIn("時間がかかるため", message)
        self.assertEqual(operations.load(self.wiki_dir, progress.paused["id"])["state"], "paused")
        ok, message, _ = resume_operation(self.wiki_dir, {}, progress.paused["id"])
        self.assertTrue(ok, message)

    def test_中断中に編集された動いたページは直さない(self):
        # 動いたページ Book/Sub を直したところで止め、編集してから再開する
        for n in range(8, 8 + REFS + 4):
            wiki_dir = self.make_wiki(f"w{n}")
            progress = CancelAfter(n)
            ok, _, _ = rename_page(wiki_dir, {}, "Doc/index", "Book", progress=progress)
            if not ok and "Book/Sub" in progress.paused["fixed"]:
                break
        else:
            self.fail("Book/Sub を直したところで止められませんでした")
        from wikilib.pagesave import save_page
        edited = self.read(wiki_dir, "Book/Sub") + "\n追記\n"
        save_page(wiki_dir, {}, "Book/Sub", ".md", edited)
        ok, message, _ = resume_operation(wiki_dir, {}, progress.paused["id"])
        self.assertTrue(ok, message)
        self.assertEqual(self.read(wiki_dir, "Book/Sub"), edited)

    def test_サーバーが止まった形からも続けられる(self):
        reference = self.make_wiki("reference")
        rename_page(reference, {}, "Doc/index", "Book")
        progress = CancelAfter(9)
        rename_page(self.wiki_dir, {}, "Doc/index", "Book", progress=progress)
        op = operations.load(self.wiki_dir, progress.paused["id"])
        op["state"] = "running"   # 止めた記録の無いまま残った（サーバーが途中で止まった）
        operations.save(self.wiki_dir, op)
        self.assertEqual(operations.resumable_done(op), {"privileges_copy", "move", "attach"})
        ok, message, _ = resume_operation(self.wiki_dir, {}, op["id"])
        self.assertTrue(ok, message)
        self.same_tree(reference, self.wiki_dir)


class TestOverlap(OperationsTestBase):
    def setUp(self):
        super().setUp()
        progress = CancelAfter(9)
        rename_page(self.wiki_dir, {}, "Doc/index", "Book", progress=progress)
        self.op_id = progress.paused["id"]

    def test_中断中は範囲が重なる名前の変更を断る(self):
        for subpath, name, folder in (("Book/Sub", "Sub2", None),      # 移し先の中
                                      ("Far", "Doc", ""),             # 移し元の名前へ
                                      ("Ref1", "Ref1", "Book")):      # 移し先の中へ
            ok, message, _ = rename_page(self.wiki_dir, {}, subpath, name, folder)
            self.assertFalse(ok, subpath)
            self.assertIn("中断している名前の変更", message)

    def test_重ならないものは通す(self):
        ok, message, _ = rename_page(self.wiki_dir, {}, "Far", "Far2")
        self.assertTrue(ok, message)

    def test_済めば断らない(self):
        ok, message, _ = resume_operation(self.wiki_dir, {}, self.op_id)
        self.assertTrue(ok, message)
        ok, message, _ = rename_page(self.wiki_dir, {}, "Book/Sub", "Sub2")
        self.assertTrue(ok, message)

    def test_無い操作は続けられない(self):
        ok, message, _ = resume_operation(self.wiki_dir, {}, "0" * 32)
        self.assertFalse(ok)
        self.assertIn("ありません", message)



class TestAdminScreen(OperationsTestBase):
    """管理の画面の「中断した操作」（/.admin/operations）。管理者と助手が開ける。"""

    def setUp(self):
        super().setUp()
        from wikilib import auth, groups, userdb
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("kyun", "hito"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["kyun"])
        self.kept_secret = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        self.addCleanup(setattr, auth, "SECRET_PATH", self.kept_secret)
        progress = CancelAfter(9)
        rename_page(self.wiki_dir, {}, "Doc/index", "Book", progress=progress)
        self.op_id = progress.paused["id"]

    def open(self, uid, form=None):
        """uid でログインして画面を開く（form があれば POST）。本文を返す。"""
        import io
        from urllib.parse import urlencode
        from wikilib import auth, userdb
        from wikilib.operationsui import render_operations
        from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name
        env = {"REQUEST_METHOD": "POST" if form else "GET", "PATH_INFO": "/.admin/operations"}
        if uid:
            user = userdb.find_by_uid(self.wiki_dir, uid)
            token = auth.session_token(uid, "main", user["pw"])
            env["HTTP_COOKIE"] = (f"{wiki_cookie_name(LOGIN_COOKIE, 'main')}={uid}; "
                                  f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, 'main')}={token}")
        if form:
            data = urlencode(form).encode()
            env.update({"CONTENT_TYPE": "application/x-www-form-urlencoded",
                        "CONTENT_LENGTH": str(len(data)), "wsgi.input": io.BytesIO(data)})
        bottle.request.bind(env)
        out = render_operations(self.wiki_dir, {}, "main", False)
        raw = out.body if hasattr(out, "body") else out
        return raw.decode("utf-8") if isinstance(raw, bytes) else "".join(raw)

    def test_助手は一覧を開いて続けられる(self):
        html = self.open("kyun")
        self.assertIn("/Doc → /Book", html)
        self.assertIn("続ける</button>", html)
        html = self.open("kyun", {"id": self.op_id})
        self.assertIn("名前を «Book» に変えました", html)
        self.assertIn("中断している操作はありません。", html)
        self.assertIsNone(operations.load(self.wiki_dir, self.op_id))

    def test_ただの利用者は開けない(self):
        html = self.open("hito")
        self.assertNotIn("/Doc → /Book", html)
        html = self.open(None)
        self.assertNotIn("/Doc → /Book", html)
        self.assertIsNotNone(operations.load(self.wiki_dir, self.op_id))

    def test_窓口に並ぶ(self):
        from wikilib.adminui import TOOLS
        from wikilib.paths import OPERATIONS_URLPATH
        self.assertIn(OPERATIONS_URLPATH, [t[0] for t in TOOLS])

if __name__ == "__main__":
    unittest.main()
