#!/usr/bin/env python3
"""助手の操作の記録と、元に戻す（wikilib.stafflog・staffundo。Wiki設計者の指示、
2026-09-26）のテスト。

「いまの要求でログインしている人」は `stafflog._request_user` を差し替えて作る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_stafflog.py     （このファイルだけ）
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import (  # noqa: E402
    attach, groups, privilege_records, stafflog, staffundo, userdb,
)
from wikilib.adminui import TOOLS  # noqa: E402
from wikilib.editor import delete_page  # noqa: E402
from wikilib.pagesave import save_page  # noqa: E402
from wikilib.paths import STAFFLOG_URLPATH, resolve_page_ref  # noqa: E402


class Upload:
    """bottle の FileUpload の代わり（save_attachment が使うところだけ）。"""

    def __init__(self, name, data):
        self.raw_filename = name
        self.file = io.BytesIO(data)

    def save(self, path, overwrite=False):
        with open(path, "wb") as f:
            f.write(self.file.getvalue())


class StaffBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="stafflog-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        groups.ensure_staff_group(self.wiki_dir)
        userdb.add_user(self.wiki_dir, "helper", "h", "助手さん")
        userdb.add_user(self.wiki_dir, "alice", "a", "アリス")
        groups.add_members(self.wiki_dir, "staff", ["helper"])
        self.who = "helper"
        patcher = mock.patch("wikilib.stafflog._request_user",
                             side_effect=lambda wiki_dir, farm: (
                                 userdb.find_by_uid(wiki_dir, self.who) if self.who else None))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def save(self, subpath, text, ext=".md"):
        self.assertTrue(save_page(self.wiki_dir, {}, subpath, ext, text))

    def text(self, subpath, ext=".md"):
        return stafflog.read_text(os.path.join(self.wiki_dir, subpath + ext))

    def log(self):
        return stafflog.entries(self.wiki_dir)

    def undo(self, entry):
        return staffundo.undo(self.wiki_dir, {}, "testwiki", entry["id"], "admin")

    def attach_path(self, subpath, name):
        return os.path.join(self.work, "wikidata", "testwiki", "attach", subpath, name)


class TestWhoIsRecorded(StaffBase):

    def test_助手の保存は記録する(self):
        self.save("Memo", "本文\n")
        [e] = self.log()
        self.assertEqual((e["kind"], e["target"], e["actor_uid"]), ("page.save", "Memo", "helper"))
        self.assertEqual(e["before"]["text"], None)
        self.assertEqual(e["after"]["text"], "本文\n")

    def test_管理者の保存は記録しない(self):
        self.who = "admin"
        self.save("Memo", "本文\n")
        self.assertEqual(self.log(), [])

    def test_助手でない人と要求の外は記録しない(self):
        self.who = "alice"
        self.save("A", "x\n")
        self.who = None
        self.save("B", "x\n")
        self.assertEqual(self.log(), [])

    def test_quietの中は記録しない(self):
        with stafflog.quiet():
            self.save("Memo", "本文\n")
        self.assertEqual(self.log(), [])

    def test_同じ内容の保存は記録しない(self):
        self.save("Memo", "本文\n")
        self.save("Memo", "本文\n")
        self.assertEqual(len(self.log()), 1)


class TestPageUndo(StaffBase):

    def test_書き換えを戻す(self):
        self.who = "admin"
        self.save("Memo", "元\n")
        self.who = "helper"
        self.save("Memo", "間違い\n")
        ok, _msg = self.undo(self.log()[0])
        self.assertTrue(ok)
        self.assertEqual(self.text("Memo"), "元\n")
        self.assertIsNotNone(self.log()[0]["undone_at"])

    def test_後から変わっていれば戻さない(self):
        self.save("Memo", "助手\n")
        self.who = "admin"
        self.save("Memo", "あとで管理者が直した\n")
        ok, msg = self.undo(self.log()[0])
        self.assertFalse(ok)
        self.assertIn("書き換えられている", msg)
        self.assertEqual(self.text("Memo"), "あとで管理者が直した\n")

    def test_二度は戻さない(self):
        self.save("Memo", "助手\n")
        entry = self.log()[0]
        self.assertTrue(self.undo(entry)[0])
        self.assertFalse(self.undo(entry)[0])

    def test_新しく作ったページは消す(self):
        self.save("New", "作った\n")
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertIsNone(self.text("New"))

    def test_削除を戻す(self):
        self.who = "admin"
        self.save("Gone", "消される\n")
        self.who = "helper"
        ok, _ = delete_page(self.wiki_dir, {}, resolve_page_ref(self.wiki_dir, "Gone"))
        self.assertTrue(ok)
        [e] = self.log()
        self.assertEqual(e["kind"], "page.delete")
        self.assertTrue(self.undo(e)[0])
        self.assertEqual(self.text("Gone"), "消される\n")


class TestRename(StaffBase):

    def test_改名は1件にまとめて戻せる(self):
        from wikilib.pagerename import rename_page

        self.who = "admin"
        self.save("Old", "本文\n")
        self.save("Linker", "[リンク](/Old)\n")
        self.who = "helper"
        ok, _msg, _new = rename_page(self.wiki_dir, {}, "Old", "New")
        self.assertTrue(ok)
        kinds = [e["kind"] for e in self.log()]
        self.assertEqual(kinds, ["page.rename"])  # リンクを直した保存は含めない
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertEqual(self.text("Old"), "本文\n")
        self.assertIsNone(self.text("New"))
        self.assertIn("/Old", self.text("Linker"))


class TestAttachUndo(StaffBase):

    def put(self, name, data, overwrite=False):
        ok, msg = attach.save_attachment(self.wiki_dir, "Page", Upload(name, data),
                                         overwrite=overwrite)
        self.assertTrue(ok, msg)

    def read(self, name, subpath="Page"):
        with open(self.attach_path(subpath, name), "rb") as f:
            return f.read()

    def test_追加を戻すと消える(self):
        self.put("a.png", b"new")
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertFalse(os.path.exists(self.attach_path("Page", "a.png")))

    def test_上書きを戻すと元の中身(self):
        self.who = "admin"
        self.put("a.png", b"old")
        self.who = "helper"
        self.put("a.png", b"new", overwrite=True)
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertEqual(self.read("a.png"), b"old")

    def test_削除を戻す(self):
        self.who = "admin"
        self.put("a.png", b"old")
        self.who = "helper"
        self.assertTrue(attach.delete_attachment(self.wiki_dir, "Page", "a.png")[0])
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertEqual(self.read("a.png"), b"old")

    def test_名前の変更を戻す(self):
        self.who = "admin"
        self.put("a.png", b"x")
        self.who = "helper"
        self.assertTrue(attach.rename_attachment(self.wiki_dir, "Page", "a.png", "b.png")[0])
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertEqual(self.read("a.png"), b"x")
        self.assertFalse(os.path.exists(self.attach_path("Page", "b.png")))

    def test_移動を戻す(self):
        self.who = "admin"
        self.save("Other", "x\n")
        self.put("a.png", b"x")
        self.who = "helper"
        self.assertTrue(attach.move_attachment(self.wiki_dir, "Page", "a.png", "Other")[0])
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertEqual(self.read("a.png"), b"x")

    def test_後から変わっていれば戻さない(self):
        self.put("a.png", b"new")
        self.who = "admin"
        self.put("a.png", b"changed", overwrite=True)
        self.assertFalse(self.undo(self.log()[0])[0])
        self.assertEqual(self.read("a.png"), b"changed")


class TestAdminScreensUndo(StaffBase):

    def test_設定ファイル(self):
        from wikilib.configui import _staff_file

        path = os.path.join(self.work, "wikidata", "testwiki", "config", "default.yaml")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("a: 1\n")
        with _staff_file(self.wiki_dir, "testwiki", path, "a"):
            with open(path, "w", encoding="utf-8") as f:
                f.write("a: 2\n")
        [e] = self.log()
        self.assertEqual((e["kind"], e["target"]), ("config.file", "config/default.yaml"))
        self.assertTrue(self.undo(e)[0])
        self.assertEqual(stafflog.read_text(path), "a: 1\n")

    def test_アクセス制限(self):
        from wikilib.privilegesui import _page_rules

        before = _page_rules(self.wiki_dir, "Secret")
        privilege_records.add_page(self.wiki_dir, "Secret", "alice", "")
        stafflog.record(self.wiki_dir, {"uid": "helper", "uidnum": 2}, "privileges.page",
                        "Secret", "登録した", before=before,
                        after=_page_rules(self.wiki_dir, "Secret"))
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertEqual(_page_rules(self.wiki_dir, "Secret"), [])

    def test_グループ(self):
        from wikilib.groupsui import _staff_group

        with _staff_group(self.wiki_dir, "testwiki", "staff", "メンバーを加えた"):
            groups.add_members(self.wiki_dir, "staff", ["alice"])
        self.assertTrue(self.undo(self.log()[0])[0])
        self.assertEqual([m["uid"] for m in groups.members(self.wiki_dir, "staff")],
                         ["admin", "helper"])

    def test_承認と断りを戻す(self):
        from wikilib.approvalsui import _act

        userdb.add_user(self.wiki_dir, "bob", "b", "ボブ", approved=False)
        userdb.add_user(self.wiki_dir, "carol", "c", "キャロル", approved=False)
        bob = userdb.find_by_uid(self.wiki_dir, "bob")
        carol = userdb.find_by_uid(self.wiki_dir, "carol")
        self.assertEqual(_act(self.wiki_dir, "approve", bob["uidnum"])[0], "approved")
        self.assertEqual(_act(self.wiki_dir, "reject", carol["uidnum"])[0], "rejected")
        reject, approve = self.log()
        self.assertTrue(self.undo(approve)[0])
        self.assertFalse(userdb.is_approved(userdb.find_by_uid(self.wiki_dir, "bob")))
        self.assertTrue(self.undo(reject)[0])
        back = userdb.find_by_uid(self.wiki_dir, "carol")
        self.assertEqual((back["uidnum"], back["pw"], back["approved"]),
                         (carol["uidnum"], "c", 0))

    def test_戻せない操作(self):
        stafflog.record(self.wiki_dir, {"uid": "helper", "uidnum": 2}, "restart", "", "再起動した")
        entry = self.log()[0]
        self.assertFalse(staffundo.undoable(entry))
        self.assertFalse(self.undo(entry)[0])


class TestAdminMenu(unittest.TestCase):

    def test_管理者だけのメニューに並ぶ(self):
        tools = {urlpath: admin_only for urlpath, _l, _n, admin_only in TOOLS}
        self.assertTrue(tools[STAFFLOG_URLPATH])


if __name__ == "__main__":
    unittest.main()
