#!/usr/bin/env python3
"""ページ本文のDB（wikiall.db）の控えと、そこからの復元のテスト。

**DBを失うと履歴が過去へたどれなくなる**という問題への手当てを固定する
（2026-09-01）。控えを取るだけでは足りず、失ったときに控えから戻すところまで
できて初めて「過去へ参照できる」状態になる。

実行:
    .venv/bin/python3 -m unittest discover -s tests
"""
import datetime
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import backup, dbbackup, pagedb  # noqa: E402
from wikilib.pagesave import save_page  # noqa: E402


class DbBackupTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="dbbk-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def save(self, text, at, page="Page"):
        """ふだんの保存（差分の「変更前」はDBの内容）。"""
        when = datetime.datetime.strptime(at, backup.BACKUP_STAMP)
        known = pagedb.published_body(self.wiki_dir, page, "")
        backup.backup_page(self.wiki_dir, page, known, text, now=when, merge=False)
        with open(os.path.join(self.wiki_dir, page + ".md"), "w") as f:
            f.write(text)
        pagedb.record_page(self.wiki_dir, page, ".md", text)

    def reimport(self, page="Page"):
        """updatepage / adopt_page と同じ道（「変更前」はDBの内容）。"""
        with open(os.path.join(self.wiki_dir, page + ".md")) as f:
            text = f.read()
        save_page(self.wiki_dir, {}, page, ".md", text, write=False)

    def history(self, page="Page"):
        current = pagedb.published_body(self.wiki_dir, page, "")
        return backup.backup_history(self.wiki_dir, page, current)


class TestTakeBackup(DbBackupTestBase):
    """控えを取るところ。"""

    def prepare(self):
        self.save("行0\n", "260801_100000")
        self.save("行0\n行1\n", "260802_100000")

    def test_控えが無ければ取る(self):
        self.prepare()
        self.assertTrue(dbbackup.is_stale(self.wiki_dir))
        self.assertTrue(dbbackup.write_backup(self.wiki_dir))
        self.assertTrue(os.path.isfile(dbbackup.zip_path(self.wiki_dir)))

    def test_今日取ったばかりなら何もしない(self):
        self.prepare()
        dbbackup.write_backup(self.wiki_dir)
        self.assertFalse(dbbackup.is_stale(self.wiki_dir))

    def test_前日以前なら取り直す(self):
        self.prepare()
        dbbackup.write_backup(self.wiki_dir)
        old = time.time() - 60 * 60 * 24 * 2
        os.utime(dbbackup.zip_path(self.wiki_dir), (old, old))
        self.assertTrue(dbbackup.is_stale(self.wiki_dir))

    def test_壊れたDBでは控えを上書きしない(self):
        self.prepare()
        dbbackup.write_backup(self.wiki_dir)
        zip_file = dbbackup.zip_path(self.wiki_dir)
        before = os.path.getmtime(zip_file)

        with open(dbbackup.db_path(self.wiki_dir), "r+b") as f:
            f.seek(100)
            f.write(b"\x00" * 4096)
        self.assertFalse(dbbackup.healthy(dbbackup.db_path(self.wiki_dir)))
        self.assertFalse(dbbackup.write_backup(self.wiki_dir))
        # 無事だった控えはそのまま残っている
        self.assertEqual(os.path.getmtime(zip_file), before)

    def test_控えから中身を取り出せる(self):
        self.prepare()
        dbbackup.write_backup(self.wiki_dir)
        with zipfile.ZipFile(dbbackup.zip_path(self.wiki_dir)) as z:
            self.assertIn("wikiall.db", z.namelist())
            # どこまでの記録に対応する控えかの目印も入っている
            self.assertEqual(z.read(dbbackup.MARK_NAME).decode(), "260802_100000")


class TestRestore(DbBackupTestBase):
    """DBを失ったときに、控えから戻して過去へ辿れるようにするところ。

    これが要点。控えを取るだけでは、失った瞬間に履歴が消えてしまう。"""

    def build(self):
        """3回保存 → 控え → さらに2回保存、という形を作る。"""
        self.save("行0\n", "260801_100000")
        self.save("行0\n行1\n", "260802_100000")
        self.save("行0\n行1\n行2\n", "260803_100000")
        dbbackup.write_backup(self.wiki_dir)
        self.save("行0\n行1\n行2\n行3\n", "260804_100000")
        self.save("行0\n行1\n行2\n行3\n行4\n", "260805_100000")

    def test_控えを戻さないと履歴が失われる(self):
        """**戻さずに取り込み直すと過去へ辿れなくなる**、という前提の確認。

        控えを戻す仕組みが要る理由そのもの。"""
        self.build()
        self.assertEqual(len(self.history()), 4)
        os.remove(dbbackup.db_path(self.wiki_dir))
        os.remove(dbbackup.zip_path(self.wiki_dir))   # 控えも無い状態にする
        self.reimport()
        self.assertEqual(self.history(), [])

    def test_控えがあれば戻して過去へ辿れる(self):
        self.build()
        os.remove(dbbackup.db_path(self.wiki_dir))
        # DBを開こうとした時点で控えから戻る（pagedb.connect が呼ぶ）
        self.reimport()

        hist = self.history()
        stamps = [h["stamp"] for h in hist]
        # 橋渡しの1本（取り込み）と、控えより前の履歴が並ぶ
        self.assertGreaterEqual(len(stamps), 3)
        self.assertIn("260803_100000", stamps)
        self.assertIn("260802_100000", stamps)
        # いちばん古くまで戻ると、最初の1行だけの状態になる
        self.assertEqual(hist[-1]["text"], "行0\n")

    def test_控えより後の記録も捨てずに使える(self):
        """控えの時点より後の記録は、捨てずに当てて進める（Wiki設計者の指示）。

        進めずに捨てると、その期間の細かい履歴が丸ごと失われていた。"""
        self.build()
        os.remove(dbbackup.db_path(self.wiki_dir))
        self.reimport()

        with backup.connect(self.wiki_dir) as con:
            left = [r["stamp"] for r in con.execute(
                "SELECT stamp FROM backup WHERE subpath = ? ORDER BY stamp", ("Page",))]
        # 控え以後の記録も残っている
        self.assertIn("260804_100000", left)
        self.assertIn("260805_100000", left)
        self.assertIn("260801_100000", left)

    def test_失う前と同じ履歴が並ぶ(self):
        """DBを失う前後で、見える履歴が変わらないこと。"""
        self.build()
        before = [(h["stamp"], h["text"]) for h in self.history()]
        os.remove(dbbackup.db_path(self.wiki_dir))
        self.reimport()
        after = [(h["stamp"], h["text"]) for h in self.history()]
        self.assertEqual(after, before)

    def test_当てられない記録は消える(self):
        """控え以後の記録が壊れていたら、そこから先は使えないので消す。"""
        self.build()
        with backup.connect(self.wiki_dir) as con:   # 控え以後の1本を壊す
            con.execute("UPDATE backup SET diff = ? WHERE subpath = ? AND stamp = ?",
                        ("壊れた\n", "Page", "260804_100000"))
        os.remove(dbbackup.db_path(self.wiki_dir))
        self.reimport()

        with backup.connect(self.wiki_dir) as con:
            left = [r["stamp"] for r in con.execute(
                "SELECT stamp FROM backup WHERE subpath = ? ORDER BY stamp", ("Page",))]
        # 壊れたものと、それに続くものは消える。控えより前は残る
        self.assertNotIn("260804_100000", left)
        self.assertNotIn("260805_100000", left)
        self.assertIn("260803_100000", left)
        # 控えの時点までは辿れる
        self.assertIn("260802_100000", [h["stamp"] for h in self.history()])

    def test_履歴DBの控えも一緒に取る(self):
        """履歴のDBも同じ瞬間に控える（Wiki設計者の指示、2026-09-01）。

        2つの控えが同じ時点でないと、戻したときに辻褄が合わない。"""
        self.build()
        self.assertTrue(os.path.isfile(dbbackup.zip_path(self.wiki_dir)))
        self.assertTrue(os.path.isfile(dbbackup.hist_zip_path(self.wiki_dir)))
        with zipfile.ZipFile(dbbackup.hist_zip_path(self.wiki_dir)) as z:
            self.assertIn("backup.db", z.namelist())
            # 目印は本文の控えと同じ値
            with zipfile.ZipFile(dbbackup.zip_path(self.wiki_dir)) as pz:
                self.assertEqual(z.read(dbbackup.MARK_NAME),
                                 pz.read(dbbackup.MARK_NAME))

    def test_履歴DBを失っても控えから戻って過去へ辿れる(self):
        self.build()
        os.remove(dbbackup.hist_db_path(self.wiki_dir))
        self.reimport()

        hist = self.history()
        stamps = [h["stamp"] for h in hist]
        # 控えまでの履歴が残り、そこからいまへの橋渡しが1本足されている
        self.assertIn("260802_100000", stamps)
        self.assertIn("260803_100000", stamps)
        self.assertEqual(hist[-1]["text"], "行0\n")
        # 控え以後の記録は、失ったDBにしか無かったので戻らない
        self.assertNotIn("260805_100000", stamps)

    def test_両方失っても過去へ辿れる(self):
        self.build()
        os.remove(dbbackup.db_path(self.wiki_dir))
        os.remove(dbbackup.hist_db_path(self.wiki_dir))
        self.reimport()

        hist = self.history()
        self.assertIn("260803_100000", [h["stamp"] for h in hist])
        self.assertEqual(hist[-1]["text"], "行0\n")

    def test_履歴DBの控えが無ければ戻さない(self):
        self.build()
        os.remove(dbbackup.hist_zip_path(self.wiki_dir))
        os.remove(dbbackup.hist_db_path(self.wiki_dir))
        self.assertFalse(dbbackup.restore_history_from_zip(self.wiki_dir))

    def test_DBがあるときは戻さない(self):
        self.build()
        self.assertFalse(dbbackup.restore_from_zip(self.wiki_dir))

    def test_控えが無ければ戻さない(self):
        self.save("行0\n", "260801_100000")
        os.remove(dbbackup.db_path(self.wiki_dir))
        self.assertFalse(dbbackup.restore_from_zip(self.wiki_dir))

    def test_壊れた控えからは戻さない(self):
        self.build()
        os.remove(dbbackup.db_path(self.wiki_dir))
        with open(dbbackup.zip_path(self.wiki_dir), "wb") as f:
            f.write("これはzipではない".encode("utf-8"))
        self.assertFalse(dbbackup.restore_from_zip(self.wiki_dir))
        self.assertFalse(os.path.exists(dbbackup.db_path(self.wiki_dir)))



class TestSweepLeftovers(DbBackupTestBase):
    """控えを作る途中で止められた一時ファイルの片づけ（起動時に呼ぶ）。"""

    def touch(self, name):
        path = os.path.join(os.path.dirname(dbbackup.zip_path(self.wiki_dir)), name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("x")
        return path

    def test_作りかけだけを消す(self):
        self.save("行0\n", "260801_100000")
        self.assertTrue(dbbackup.write_backup(self.wiki_dir))
        leftovers = [self.touch("dbbackup-abc.copy"), self.touch("dbbackup-def.zip")]
        others = [self.touch("tmpxyz.copy"), self.touch("dbbackup-note.txt")]
        self.assertEqual(dbbackup.sweep_leftovers(self.wiki_dir), 2)
        for path in leftovers:
            self.assertFalse(os.path.exists(path))
        for path in others + [dbbackup.zip_path(self.wiki_dir), dbbackup.db_path(self.wiki_dir)]:
            self.assertTrue(os.path.exists(path), path)

    def test_控えを取り終えれば作りかけは残らない(self):
        self.save("行0\n", "260801_100000")
        self.assertTrue(dbbackup.write_backup(self.wiki_dir))
        self.assertEqual(dbbackup.sweep_leftovers(self.wiki_dir), 0)

    def test_pageinfoが無くても動く(self):
        self.assertEqual(dbbackup.sweep_leftovers(self.wiki_dir), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
