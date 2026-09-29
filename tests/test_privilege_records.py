#!/usr/bin/env python3
"""ページごとのアクセス制限の記録（`wikilib.privilege_records`）のテスト。

**ここが間違うと、見せてはいけない相手に見せる**ので、行の読み書きと、
指定として受け付ける・受け付けないの線引きを固定しておく。

形式は `ページ名:種類:許可者,許可者,…:登録日`（Wiki設計者の指示、2026-09-13）。
**許可者には `g:staff` のように `:` を含む値が入る**ので、読みかたは
「左から2つ・右から1つ」になっている。そこがいちばん壊れやすい。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_privilege_records.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import privilege_records, userdb  # noqa: E402


class PrivilegesTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="privileges-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        userdb.add_user(self.wiki_dir, "alice", userdb.hash_password(self.wiki_dir, "alice", "p"), "アリス")
        userdb.add_user(self.wiki_dir, "bob", userdb.hash_password(self.wiki_dir, "bob", "p"), "ボブ")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, page, kind, who, **kw):
        return privilege_records.put(self.wiki_dir, page, kind, who, **kw)

    def raw(self):
        with open(privilege_records.path_of(self.wiki_dir), encoding="utf-8") as f:
            return f.read()


class TestLine(unittest.TestCase):
    """1行の読み書き。"""

    def test_ふつうの行を読む(self):
        e = privilege_records.parse_line("Tech/Secret:R:alice,bob:260913_103000")
        self.assertEqual(e["page"], "Tech/Secret")
        self.assertEqual(e["kind"], "R")
        self.assertEqual(e["who"], ["alice", "bob"])
        self.assertEqual(e["stamp"], "260913_103000")

    def test_許可者にコロンを含むグループが入っても読める(self):
        # **ここがこの形式のいちばん危ういところ。** g: が区切りと紛らわしい
        e = privilege_records.parse_line("Tech/Secret:R:alice,g:staff:260913_103000")
        self.assertEqual(e["page"], "Tech/Secret")
        self.assertEqual(e["who"], ["alice", "g:staff"])
        self.assertEqual(e["stamp"], "260913_103000")

    def test_グループだけの行も読める(self):
        e = privilege_records.parse_line("Tech/*:W:g:editors:260913_103100")
        self.assertEqual(e["page"], "Tech/*")
        self.assertEqual(e["kind"], "W")
        self.assertEqual(e["who"], ["g:editors"])

    def test_書いて読み直すと同じになる(self):
        for line in ("Tech/Secret:R:alice,g:staff:260913_103000",
                     "Tech/*:W:g:editors:260913_103100",
                     "*:R:alice:260913_103200"):
            self.assertEqual(privilege_records.format_line(privilege_records.parse_line(line)), line)

    def test_読めない行はNone(self):
        for line in ("", "   ", "# これは注記", "ページ名だけ",
                     "Tech/Secret:X:alice:260913_103000",   # 種類が違う
                     "Tech/Secret:R::260913_103000"):       # 許可者が空
            self.assertIsNone(privilege_records.parse_line(line), line)


class TestCheck(unittest.TestCase):
    """指定として受け付けるかどうか。"""

    def test_ワイルドカードは先頭か末尾だけ(self):
        self.assertIsNone(privilege_records.check_page("Tech/*"))
        self.assertIsNone(privilege_records.check_page("*/Secret"))
        self.assertIsNone(privilege_records.check_page("*"))
        self.assertIsNotNone(privilege_records.check_page("Te*ch"))
        self.assertIsNotNone(privilege_records.check_page("*Tech*"))

    def test_コロンを含むページ名は断る(self):
        # 行の区切りと混ざるため（モジュール冒頭「行の読みかた」）
        self.assertIsNotNone(privilege_records.check_page("Tech:Secret"))

    def test_許可者の形(self):
        self.assertEqual(privilege_records.check_who("alice, g:staff")[0], ["alice", "g:staff"])
        self.assertIsNotNone(privilege_records.check_who("")[1])
        self.assertIsNotNone(privilege_records.check_who("あいうえお")[1])
        self.assertIsNotNone(privilege_records.check_who("g:大文字")[1])

    def test_同じ相手を2度書いても1つになる(self):
        self.assertEqual(privilege_records.check_who("alice,alice")[0], ["alice"])

    def test_知らない相手は弾く(self):
        who, problem = privilege_records.check_who("alice", known={"bob"})
        self.assertIsNotNone(problem)
        self.assertEqual(who, [])


class TestPut(PrivilegesTestBase):
    """登録・上書き・削除。"""

    def test_登録できる(self):
        ok, _msg, entries = self.put("Tech/Secret", "R", "alice")
        self.assertTrue(ok)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["who"], ["alice"])

    def test_知らない相手は登録できない(self):
        ok, msg, _ = self.put("Tech/Secret", "R", "carol")
        self.assertFalse(ok)
        self.assertIn("carol", msg)

    def test_助手グループは誰も入っていなくても書ける(self):
        ok, _msg, _ = self.put("Tech/Secret", "R", "g:staff")
        self.assertTrue(ok)

    def test_同じページと種類は上書きになる(self):
        self.put("Tech/Secret", "R", "alice")
        ok, _msg, entries = self.put("Tech/Secret", "R", "bob")
        self.assertTrue(ok)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["who"], ["bob"])

    def test_種類が違えば別の行(self):
        self.put("Tech/Secret", "R", "alice")
        _ok, _msg, entries = self.put("Tech/Secret", "W", "alice")
        self.assertEqual(len(entries), 2)

    def test_登録で他の行は消えない(self):
        # **ここが消えると、見せてはいけない相手に見せる側へ倒れる。**
        # 画面で既存の行を「編集」で開いたあと、入力欄を別の内容へ打ち直して
        # 登録すると、開いただけの行が黙って消えていた（2026-09-18に直した）。
        # `put` が足すか上書きするかしかしないので、仕組みの上から起こらない
        self.put("Tech/Secret", "R", "alice")
        ok, _msg, entries = self.put("Tech/Other", "R", "alice")
        self.assertTrue(ok)
        self.assertEqual(sorted(e["page"] for e in entries),
                         ["Tech/Other", "Tech/Secret"])

    def test_種類を変えて登録しても元の種類は残る(self):
        # 「閲覧」の行を開いて「閲覧・編集」で登録しても、閲覧の行は消えない。
        # 消すなら delete（画面の「削除」）を通す
        self.put("Tech/Secret", "R", "alice")
        _ok, _msg, entries = self.put("Tech/Secret", "W", "alice")
        self.assertEqual(sorted(e["kind"] for e in entries), ["R", "W"])

    def test_消せる(self):
        self.put("Tech/Secret", "R", "alice")
        ok, _msg, entries = privilege_records.delete(self.wiki_dir, "Tech/Secret", "R")
        self.assertTrue(ok)
        self.assertEqual(entries, [])

    def test_無い記録は消せない(self):
        ok, _msg, _ = privilege_records.delete(self.wiki_dir, "Tech/Secret", "R")
        self.assertFalse(ok)

    def test_書き出しに説明が付く(self):
        # 手で開いた人が、何のファイルか分かるように
        self.put("Tech/Secret", "R", "alice")
        self.assertIn("# ページごとのアクセス制限", self.raw())

    def test_壊れた行は読み飛ばして数える(self):
        self.put("Tech/Secret", "R", "alice")
        with open(privilege_records.path_of(self.wiki_dir), "a", encoding="utf-8") as f:
            f.write("これは壊れた行\n")
        self.assertEqual(len(privilege_records.load(self.wiki_dir)), 1)
        self.assertEqual(privilege_records.broken_lines(self.wiki_dir), 1)


class TestRows(PrivilegesTestBase):
    """ファイルの行を、ページ1件にまとめる（画面の単位）。"""

    def test_RとWが1行にまとまる(self):
        self.put("Tech/Secret", "R", "alice")
        self.put("Tech/Secret", "W", "bob")
        self.put("Memo", "R", "alice")
        rows = privilege_records.load_rows(self.wiki_dir)
        self.assertEqual([r["page"] for r in rows], ["Memo", "Tech/Secret"])
        secret = rows[1]
        self.assertEqual((secret["r"], secret["w"]), (["alice"], ["bob"]))

    def test_片側が無ければ空のリスト(self):
        self.put("Memo", "R", "alice")
        row = privilege_records.load_rows(self.wiki_dir)[0]
        self.assertEqual((row["r"], row["w"]), (["alice"], []))

    def test_手で同じ組を2行書いても許可者は合わさる(self):
        with open(privilege_records.path_of(self.wiki_dir), "w", encoding="utf-8") as f:
            f.write("Memo:R:alice:260913_103000\nMemo:R:bob:260913_103100\n")
        row = privilege_records.load_rows(self.wiki_dir)[0]
        self.assertEqual(row["r"], ["alice", "bob"])


class TestAddPage(PrivilegesTestBase):
    """新規の入力。同じページ名があれば古い情報とマージする。"""

    def add(self, page, r, w, **kw):
        return privilege_records.add_page(self.wiki_dir, page, r, w, **kw)

    def test_新しいページを登録できる(self):
        ok, msg, rows = self.add("Tech/Secret", "alice", "bob")
        self.assertTrue(ok, msg)
        self.assertEqual((rows[0]["r"], rows[0]["w"]), (["alice"], ["bob"]))
        # ファイルの項目はこれまでどおり（1行1件）
        lines = [l for l in self.raw().splitlines() if not l.startswith("#")]
        self.assertEqual(sorted(l.rsplit(":", 1)[0] for l in lines),
                         ["Tech/Secret:R:alice", "Tech/Secret:W:bob"])

    def test_片側だけでも登録できる(self):
        ok, _msg, rows = self.add("Memo", "alice", "")
        self.assertTrue(ok)
        self.assertEqual((rows[0]["r"], rows[0]["w"]), (["alice"], []))
        self.assertNotIn("Memo:W", self.raw())

    def test_同じページ名は古い情報とマージされる(self):
        self.add("Memo", "alice", "alice")
        ok, msg, rows = self.add("Memo", "bob", "bob")
        self.assertTrue(ok)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["r"], rows[0]["w"]),
                         (["alice", "bob"], ["alice", "bob"]))
        # 何が足されたかを、文言で知らせる
        self.assertIn("まとめ", msg)
        self.assertIn("bob", msg)

    def test_マージは片側だけにも効く(self):
        self.add("Memo", "alice", "alice")
        _ok, _msg, rows = self.add("Memo", "", "bob")
        self.assertEqual((rows[0]["r"], rows[0]["w"]), (["alice"], ["alice", "bob"]))

    def test_マージで既存の許可者は消えない(self):
        # **同じページ名を入れ直したとき、既にいる人が黙って消えない**
        userdb.add_user(self.wiki_dir, "carol", userdb.hash_password(self.wiki_dir, "carol", "p"), "キャロル")
        self.add("Memo", "alice,bob", "")
        ok, msg, rows = self.add("Memo", "carol", "")
        self.assertTrue(ok, msg)
        self.assertEqual(rows[0]["r"], ["alice", "bob", "carol"])

    def test_同じ内容の再登録は変更なしで登録日も変えない(self):
        self.add("Memo", "alice", "", now=1_000_000_000)
        before = self.raw()
        ok, msg, _ = self.add("Memo", "alice", "", now=2_000_000_000)
        self.assertTrue(ok)
        self.assertIn("変更なし", msg)
        self.assertEqual(self.raw(), before)

    def test_他のページの行には触らない(self):
        self.add("Memo", "alice", "")
        _ok, _msg, rows = self.add("Diary", "bob", "")
        self.assertEqual([r["page"] for r in rows], ["Diary", "Memo"])

    def test_RもWも空なら断る(self):
        ok, _msg, rows = self.add("Memo", "", "  ")
        self.assertFalse(ok)
        self.assertEqual(rows, [])

    def test_知らない相手はどちらの側でも断る(self):
        ok, msg, _ = self.add("Memo", "alice", "nobody")
        self.assertFalse(ok)
        self.assertIn("編集", msg)
        self.assertIn("nobody", msg)
        self.assertEqual(privilege_records.load_rows(self.wiki_dir), [])

    def test_ページ名が不正なら断る(self):
        ok, _msg, _ = self.add("Tech:Secret", "alice", "")
        self.assertFalse(ok)


class TestSetPage(PrivilegesTestBase):
    """既存の行の書き換え。そのページのR・Wを置き換える。"""

    def setUp(self):
        super().setUp()
        privilege_records.add_page(self.wiki_dir, "Memo", "alice,bob", "alice",
                                   now=1_000_000_000)
        privilege_records.add_page(self.wiki_dir, "Other", "alice", "",
                                   now=1_000_000_000)

    def row(self, page="Memo"):
        return next(r for r in privilege_records.load_rows(self.wiki_dir)
                    if r["page"] == page)

    def set(self, page, r, w, **kw):
        return privilege_records.set_page(self.wiki_dir, page, r, w, **kw)

    def test_置き換えで許可者を外せる(self):
        ok, _msg, _ = self.set("Memo", "alice", "alice")
        self.assertTrue(ok)
        self.assertEqual(self.row()["r"], ["alice"])

    def test_他のページの行には触らない(self):
        self.set("Memo", "bob", "bob")
        self.assertEqual(self.row("Other")["r"], ["alice"])

    def test_片側を空にするとその種類の行が無くなる(self):
        ok, _msg, _ = self.set("Memo", "alice,bob", "")
        self.assertTrue(ok)
        self.assertEqual(self.row()["w"], [])
        self.assertNotIn("Memo:W", self.raw())

    def test_両方を空にはできない(self):
        # 行ごと消える操作は delete_page だけ
        before = self.raw()
        ok, msg, _ = self.set("Memo", "", "")
        self.assertFalse(ok)
        self.assertIn("削除", msg)
        self.assertEqual(self.raw(), before)

    def test_中身が同じ側の登録日は変わらない(self):
        old = self.row()["version"]
        self.set("Memo", "alice,bob", "bob", now=2_000_000_000)   # Wだけ変える
        r_stamp, w_stamp = self.row()["version"].split("/")
        self.assertEqual(r_stamp, old.split("/")[0])
        self.assertNotEqual(w_stamp, old.split("/")[1])

    def test_変更が無ければ書かない(self):
        before = self.raw()
        ok, msg, _ = self.set("Memo", "bob,alice", "alice")
        self.assertTrue(ok)
        self.assertIn("変更はありません", msg)
        self.assertEqual(self.raw(), before)

    def test_無い行は作らない(self):
        ok, _msg, rows = self.set("Nothing", "alice", "")
        self.assertFalse(ok)
        self.assertNotIn("Nothing", [r["page"] for r in rows])

    def test_開いたあとに変わった行は断る(self):
        opened = self.row()["version"]
        privilege_records.add_page(self.wiki_dir, "Memo", "", "bob", now=2_000_000_000)
        before = self.raw()
        ok, msg, rows = self.set("Memo", "alice", "alice", version=opened)
        self.assertFalse(ok)
        self.assertIn("別の操作", msg)
        self.assertEqual(self.raw(), before)
        # 応答には、いまの内容が入っている（画面が読み込み直せる）
        self.assertEqual(next(r for r in rows if r["page"] == "Memo")["w"],
                         ["alice", "bob"])

    def test_変わっていなければversion付きでも通る(self):
        ok, _msg, _ = self.set("Memo", "alice", "alice", version=self.row()["version"])
        self.assertTrue(ok)

    def test_知らない相手なら断る(self):
        ok, _msg, _ = self.set("Memo", "alice", "nobody")
        self.assertFalse(ok)
        self.assertEqual(self.row()["w"], ["alice"])


class TestDeletePage(PrivilegesTestBase):

    def setUp(self):
        super().setUp()
        privilege_records.add_page(self.wiki_dir, "Memo", "alice", "bob")
        privilege_records.add_page(self.wiki_dir, "Other", "alice", "")

    def test_RもWも消える(self):
        ok, _msg, rows = privilege_records.delete_page(self.wiki_dir, "Memo")
        self.assertTrue(ok)
        self.assertEqual([r["page"] for r in rows], ["Other"])
        self.assertNotIn("Memo:", self.raw())

    def test_無い行は消せない(self):
        ok, _msg, _ = privilege_records.delete_page(self.wiki_dir, "Nothing")
        self.assertFalse(ok)

    def test_開いたあとに変わった行は消さない(self):
        opened = privilege_records.load_rows(self.wiki_dir)[0]["version"]
        privilege_records.add_page(self.wiki_dir, "Memo", "bob", "", now=2_000_000_000)
        ok, msg, _ = privilege_records.delete_page(self.wiki_dir, "Memo", version=opened)
        self.assertFalse(ok)
        self.assertIn("別の操作", msg)
        self.assertIn("Memo:R:", self.raw())


class TestMatches(unittest.TestCase):
    """ページ名の指定が、どのページに当たるか。"""

    def test_フルパスは完全一致(self):
        self.assertTrue(privilege_records.matches("Tech/Secret", "Tech/Secret"))
        self.assertFalse(privilege_records.matches("Tech/Secret", "Tech/Secret2"))

    def test_前方一致(self):
        self.assertTrue(privilege_records.matches("Tech/*", "Tech/Secret"))
        self.assertTrue(privilege_records.matches("Tech/*", "Tech/Sub/Deep"))
        # フォルダの入口（Tech/index＝Tech という単体のページ）にも当たる（2026-09-21）
        self.assertTrue(privilege_records.matches("Tech/*", "Tech"))
        self.assertTrue(privilege_records.matches("Tech/Sub/*", "Tech/Sub"))
        self.assertFalse(privilege_records.matches("Tech/*", "Tec"))
        self.assertFalse(privilege_records.matches("Tech/*", "TechNotes"))    # 別のページ
        self.assertFalse(privilege_records.matches("Tech/Sub/*", "Tech"))     # 親には当たらない
        # `/` の無い前方一致は、これまでどおり Tech で始まる名前すべて
        self.assertTrue(privilege_records.matches("Tech*", "Tech"))
        self.assertTrue(privilege_records.matches("Tech*", "TechNotes"))
        self.assertFalse(privilege_records.matches("Tech/*", "Other/Secret"))

    def test_後方一致(self):
        self.assertTrue(privilege_records.matches("*/Secret", "Tech/Secret"))
        self.assertFalse(privilege_records.matches("*/Secret", "Tech/Open"))

    def test_星だけならすべて(self):
        self.assertTrue(privilege_records.matches("*", "Tech/Secret"))
        self.assertTrue(privilege_records.matches("*", ""))


if __name__ == "__main__":
    unittest.main()
