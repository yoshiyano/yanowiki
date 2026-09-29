#!/usr/bin/env python3
"""バックアップ（差分の記録・復元・上限）のテスト。

**保存の形（ファイルかDBか）に依らず、外から見た振る舞いを固定する**ために
書いてある。2026-08-31に差分の置き場所をファイルからsqliteへ移す作業を
行ったが、その前後で同じこのテストが通ることを確かめている。
そのため、テストは `wikilib.backup` の公開関数だけを使い、
`pageinfo/backup/` の中身を直接のぞかない。

背景: `backup_history` と `reverse_diff` の境界条件（新規作成・記録が1件だけ・
壊れた差分・世代の統合）は、2026-08-30から08-31にかけて何度も直し直す
原因になった。自動テストが無く、その都度sandboxのページで手作業で
確かめていたため。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_backup.py     （このファイルだけ）
"""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import backup  # noqa: E402


class BackupTestBase(unittest.TestCase):
    """Wiki1つ分の置き場所を作って片付けるだけの土台。

    backup_page などが受け取る wiki_dir は wikidata/<Wiki名>/wiki のことで、
    差分の置き場所はその隣（pageinfo/）から組み立てられる。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="wikitest-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        self._limit = backup.BACKUP_TOTAL_BYTES

    def tearDown(self):
        backup.BACKUP_TOTAL_BYTES = self._limit
        shutil.rmtree(self.work, ignore_errors=True)

    def save(self, subpath, old, new, at=None, merge=True):
        """1回の保存を記録する。at は "260831_120000" の形でも渡せる。"""
        if isinstance(at, str):
            at = datetime.datetime.strptime(at, backup.BACKUP_STAMP)
        backup.backup_page(self.wiki_dir, subpath, old, new, now=at, merge=merge)

    def history(self, subpath, current):
        return backup.backup_history(self.wiki_dir, subpath, current)

    def stamps(self, subpath, current):
        return [h["stamp"] for h in self.history(subpath, current)]


class TestReverseDiff(unittest.TestCase):
    """差分の逆適用そのもの。履歴の組み立ては、すべてこれの上に乗っている。"""

    def roundtrip(self, old, new):
        diff = backup.make_diff(old, new, "page", "", "260831_120000")
        return backup.reverse_diff(new, diff)

    def test_行の追加を戻せる(self):
        self.assertEqual(self.roundtrip("あ\nい\n", "あ\nい\nう\n"), "あ\nい\n")

    def test_行の削除を戻せる(self):
        self.assertEqual(self.roundtrip("あ\nい\nう\n", "あ\nう\n"), "あ\nい\nう\n")

    def test_行の書き換えを戻せる(self):
        self.assertEqual(self.roundtrip("あ\nい\n", "あ\nX\n"), "あ\nい\n")

    def test_空からの新規作成を戻すと空になる(self):
        self.assertEqual(self.roundtrip("", "あ\nい\n"), "")

    def test_すべて消す変更を戻せる(self):
        self.assertEqual(self.roundtrip("あ\nい\n", ""), "あ\nい\n")

    def test_末尾に改行が無い場合も戻せる(self):
        # 末尾の改行の有無は "\ No newline at end of file" の印で表す。
        # ここを取り違えると、戻した内容が1行つながってしまう
        self.assertEqual(self.roundtrip("あ\nい", "あ\nい\nう"), "あ\nい")
        self.assertEqual(self.roundtrip("あ\nい\n", "あ\nい"), "あ\nい\n")

    def test_日本語や記号が混じっていても戻せる(self):
        old = "# 見出し\n\n本文です。\n- 箇条書き\n"
        new = "# 見出し（改）\n\n本文です。\n- 箇条書き\n- 追加した行\n"
        self.assertEqual(self.roundtrip(old, new), old)

    def test_辻褄の合わない差分はNoneを返す(self):
        # 差分が想定している「変更後」と、渡されたテキストが食い違う場合。
        # ここでNoneを返せることが、履歴の打ち切り（broken）の土台になっている
        diff = backup.make_diff("あ\nい\n", "あ\nう\n", "page", "", "260831_120000")
        self.assertIsNone(backup.reverse_diff("まったく別の内容\n", diff))

    def test_hunkの無い差分は壊れているとみなす(self):
        # `@@` を1つも含まない（＝壊れた・途中で切れた）差分。
        # 「変更なし」と解釈して黙って通すと、さかのぼれていないのに
        # さらに古い差分を当ててしまい、実在しない内容が履歴に出る
        # （2026-09-01に修正。それまでは渡したテキストをそのまま返していた）
        self.assertIsNone(backup.reverse_diff("あ\n", "壊れた差分\n"))
        self.assertIsNone(backup.reverse_diff("あ\n", "--- page\n+++ page\n"))

    def test_空の差分は変更なしとして扱う(self):
        # 中身が無いものは「壊れている」とは言えない。記録には残らない
        # （backup_pageは差分が空なら書かない）が、区別はしておく
        self.assertEqual(backup.reverse_diff("あ\n", ""), "あ\n")


class TestHistory(BackupTestBase):
    """履歴の組み立て。各項目が「その保存の前」を指す、という決まりを固定する。"""

    def test_各項目はその保存の前の内容を指す(self):
        # 「後」ではなく「前」。一覧に出る増減がちょうど打ち消される先になる
        # （Wiki設計者の指示、2026-08-31）
        self.save("Page", "", "1行目\n", at="260801_100000")
        self.save("Page", "1行目\n", "1行目\n2行目\n", at="260802_100000")
        self.save("Page", "1行目\n2行目\n", "1行目\n2行目\n3行目\n", at="260803_100000")
        current = "1行目\n2行目\n3行目\n"

        hist = self.history("Page", current)
        self.assertEqual([h["stamp"] for h in hist],
                         ["260803_100000", "260802_100000"])
        # いちばん新しい項目を選ぶと、その保存の前＝2行目まで
        self.assertEqual(hist[0]["text"], "1行目\n2行目\n")
        # その次は、さらに前＝1行目まで
        self.assertEqual(hist[1]["text"], "1行目\n")

    def test_増減の数と内容の差が一致する(self):
        # 一覧の "+N -M" と、選んだときに見える差が同じものを指していること
        self.save("Page", "", "a\n", at="260801_100000")
        self.save("Page", "a\n", "a\nb\nc\n", at="260802_100000")
        hist = self.history("Page", "a\nb\nc\n")
        self.assertEqual(len(hist), 1)
        item = hist[0]
        self.assertEqual(item["added"], 2)     # b と c が増えた
        self.assertEqual(item["removed"], 0)
        # その項目の内容と現在の行数の差が、ちょうど +2 -0 になっている
        self.assertEqual(len(item["text"].splitlines()), 1)

    def test_本文が記号で始まる行も増減に数える(self):
        # 本文の `++ x`／`-- x` は差分では `+++ x`／`--- x` になり、ヘッダ行と
        # 見分けが付かない書きかたをすると数え落とす（PukiWikiの入れ子の箇条書き）
        self.save("Page", "", "a\n", at="260801_100000")
        new = "a\n++ x\n-- y\n+ z\n"
        self.save("Page", "a\n", new, at="260802_100000")
        item = self.history("Page", new)[0]
        self.assertEqual((item["added"], item["removed"]), (3, 0))
        self.assertEqual(backup.count_changed_lines(
            "--- p\n+++ p\tx\n@@ -1,2 +1,2 @@\n-- old\n+++ new\n keep\n"), (1, 1))

    def test_新規作成だけのページは履歴が空(self):
        # その「前」はページが無かった状態で、戻す先として意味が無いため
        self.save("Page", "", "できたて\n", at="260801_100000")
        self.assertEqual(self.history("Page", "できたて\n"), [])

    def test_新規作成の記録は一覧に出ない(self):
        self.save("Page", "", "1\n", at="260801_100000")
        self.save("Page", "1\n", "1\n2\n", at="260802_100000")
        # 2本記録したが、新規作成のぶんは出ないので1件
        self.assertEqual(self.stamps("Page", "1\n2\n"), ["260802_100000"])

    def test_作り直したページは前の一生の履歴も続けて見える(self):
        """同じ名前で作り直したときは「再作成」として履歴を続ける
        （Wiki設計者の指示、2026-09-01）。

        一生を2回ぶん（作る→編集→消す→作り直す→編集）記録し、
        現在から最初まで途切れずに辿れること。"""
        self.save("Page", "", "一代目\n", at="260801_100000", merge=False)
        self.save("Page", "一代目\n", "一代目 改\n", at="260802_100000", merge=False)
        self.save("Page", "一代目 改\n", "", at="260803_100000", merge=False)
        self.save("Page", "", "二代目\n", at="260804_100000", merge=False)
        self.save("Page", "二代目\n", "二代目 改\n", at="260805_100000", merge=False)

        hist = self.history("Page", "二代目 改\n")
        stamps = [h["stamp"] for h in hist]
        # 作り直しの記録（260804）だけは出ない（その「前」はページが無い状態）。
        # 消した記録（260803）から先、前の一生ぶんも並ぶ
        self.assertEqual(stamps, ["260805_100000", "260803_100000", "260802_100000"])
        self.assertEqual(hist[0]["text"], "二代目\n")        # いまの一生
        self.assertEqual(hist[1]["text"], "一代目 改\n")     # 消える直前
        self.assertEqual(hist[2]["text"], "一代目\n")        # その前

    def test_作り直しの境目が分かる(self):
        """どこから前の一生かを、画面が示せるようにしておく。"""
        self.save("Page", "", "一代目\n", at="260801_100000", merge=False)
        self.save("Page", "一代目\n", "", at="260802_100000", merge=False)
        self.save("Page", "", "二代目\n", at="260803_100000", merge=False)

        hist = self.history("Page", "二代目\n")
        self.assertEqual([h["stamp"] for h in hist], ["260802_100000"])
        # この項目より古いものは、作り直す前のもの
        self.assertTrue(hist[0]["recreated"])

    def test_履歴が無ければこれまでどおり新規作成(self):
        """前の履歴が無いときの振る舞いは変えない（Wiki設計者の指示）。"""
        self.save("Page", "", "はじめて\n", at="260801_100000")
        self.assertEqual(self.history("Page", "はじめて\n"), [])
        self.save("Page", "はじめて\n", "はじめて\n2行目\n", at="260802_100000")
        hist = self.history("Page", "はじめて\n2行目\n")
        self.assertEqual([h["stamp"] for h in hist], ["260802_100000"])
        self.assertFalse(hist[0]["recreated"])

    def test_同じ内容の保存は記録しない(self):
        self.save("Page", "同じ\n", "同じ\n", at="260801_100000")
        self.assertEqual(self.history("Page", "同じ\n"), [])

    def test_記録の無いページは空(self):
        self.assertEqual(self.history("Nothing", "なにか\n"), [])

    def test_削除された内容もさかのぼれる(self):
        # 本文を空にする＝ページの削除。消える直前の内容が残っている必要がある
        self.save("Page", "", "中身\n", at="260801_100000")
        self.save("Page", "中身\n", "", at="260802_100000", merge=False)
        hist = self.history("Page", "")
        self.assertEqual([h["stamp"] for h in hist], ["260802_100000"])
        self.assertEqual(hist[0]["text"], "中身\n")

    def test_find_backup_versionで1件取り出せる(self):
        self.save("Page", "", "1\n", at="260801_100000")
        self.save("Page", "1\n", "1\n2\n", at="260802_100000")
        item = backup.find_backup_version(
            self.wiki_dir, "Page", "260802_100000", "1\n2\n")
        self.assertIsNotNone(item)
        self.assertEqual(item["text"], "1\n")
        self.assertIsNone(backup.find_backup_version(
            self.wiki_dir, "Page", "無い日時", "1\n2\n"))

    def test_階層のあるページ名を扱える(self):
        # 置き場所の都合で "/" を含む名前をどう持つかは実装によるが、
        # 外から見た振る舞いは他のページと同じでなければならない
        self.save("Tech/My_Page", "", "1\n", at="260801_100000")
        self.save("Tech/My_Page", "1\n", "1\n2\n", at="260802_100000")
        self.assertEqual(self.stamps("Tech/My_Page", "1\n2\n"), ["260802_100000"])
        self.assertIn("Tech/My_Page", backup.backed_up_subpaths(self.wiki_dir))

    def test_似た名前のページが混ざらない(self):
        # "foo" と "foo.bar" のように、名前自身が区切り文字を含む場合
        self.save("foo", "", "A\n", at="260801_100000")
        self.save("foo", "A\n", "A\nA2\n", at="260802_100000")
        self.save("foo.bar", "", "B\n", at="260801_110000")
        self.save("foo.bar", "B\n", "B\nB2\n", at="260802_110000")
        self.assertEqual(self.stamps("foo", "A\nA2\n"), ["260802_100000"])
        self.assertEqual(self.stamps("foo.bar", "B\nB2\n"), ["260802_110000"])


class TestBrokenDiff(BackupTestBase):
    """壊れた記録があったときの振る舞い。

    実際に起きていた不具合（2026-09-01に修正）を再現している。壊れた差分を
    「変更なし」として素通りすると、さかのぼれていないのにさらに古い差分を
    当ててしまい、**そのページが一度も持ったことのない内容**が、復元できる
    項目として履歴に並んでいた。"""

    def break_record(self, subpath, stamp):
        """記録の中身を壊す（途中で切れた・化けた差分の代わり）。"""
        with backup.connect(self.wiki_dir) as con:
            con.execute("UPDATE backup SET diff = ? WHERE subpath = ? AND stamp = ?",
                        ("これは壊れた差分です\n", subpath, stamp))

    def test_壊れた記録から先はたどらない(self):
        self.save("Page", "", "1行目\n", at="260801_100000")
        self.save("Page", "1行目\n", "1行目\n2行目\n", at="260802_100000")
        self.save("Page", "1行目\n2行目\n", "1行目\n2行目\n3行目\n", at="260803_100000")
        current = "1行目\n2行目\n3行目\n"
        # まん中の記録が壊れた場合
        self.break_record("Page", "260802_100000")

        hist = self.history("Page", current)
        stamps = [h["stamp"] for h in hist]
        # 壊れたところより前には行けないので、新しい1件だけが残る
        self.assertEqual(stamps, ["260803_100000"])
        # そこが行き止まりであることが分かるようになっている
        self.assertTrue(hist[-1]["broken"])

    def test_実在しない内容が履歴に出ない(self):
        self.save("Page", "", "A\nB\nC\n", at="260801_100000")
        self.save("Page", "A\nB\nC\n", "A\nB\nC\nD\n", at="260802_100000")
        current = "A\nB\nC\nD\n"
        self.break_record("Page", "260802_100000")

        # 壊れた記録より前は出さない（出すと、逆適用のずれた偽の内容になる）
        for item in self.history("Page", current):
            self.assertIn(item["text"], (current, "A\nB\nC\n"),
                          "ページが持ったことのない内容が履歴に出ている")

    def test_いちばん新しい記録が壊れていたら履歴は空(self):
        self.save("Page", "", "1\n", at="260801_100000")
        self.save("Page", "1\n", "1\n2\n", at="260802_100000")
        self.break_record("Page", "260802_100000")
        # 現在からの1歩目が踏めないので、たどれる時点が1つも無い
        self.assertEqual(self.history("Page", "1\n2\n"), [])


class TestUnreachable(BackupTestBase):
    """辿れなくなった記録の扱い（Wiki設計者の判断、2026-09-01）。

    「辿れない」には2種類あり、**扱いが違う**。

      - つながりが切れている: 逆適用が当たらない。復元先にも比較相手にも
        できないので捨てる
      - 新規作成で打ち切っているだけ: 差分としては続いており機械的には
        辿れる（ページを消して作り直す前の履歴）。見せていないだけなので残す
    """

    def counts(self, subpath):
        with backup.connect(self.wiki_dir) as con:
            return con.execute(
                "SELECT COUNT(*) AS n FROM backup WHERE subpath = ?",
                (subpath,)).fetchone()["n"]

    def test_作り直す前の記録は掃除の対象にならない(self):
        # 作る → 編集 → 消す → 作り直す → 編集、という一生を2回ぶん。
        # 一覧に出るかどうかは TestHistory 側で見ている。ここでは
        # **掃除で消されないこと**（差分としてつながっていること）を確かめる
        self.save("Page", "", "一代目\n", at="260801_100000", merge=False)
        self.save("Page", "一代目\n", "一代目 改\n", at="260802_100000", merge=False)
        self.save("Page", "一代目 改\n", "", at="260803_100000", merge=False)
        self.save("Page", "", "二代目\n", at="260804_100000", merge=False)
        self.save("Page", "二代目\n", "二代目 改\n", at="260805_100000", merge=False)
        self.assertEqual(self.counts("Page"), 5)

    def test_つながりが切れた記録は捨てる(self):
        self.save("Page", "", "1\n", at="260801_100000", merge=False)
        self.save("Page", "1\n", "1\n2\n", at="260802_100000", merge=False)
        # 内容のある状態から、差分を残さずに空になった状況を作る
        # （システムを通さずDBを作り直したときに起きる形）。
        # 掃除は、つながりを切ったその保存の時点で走る
        self.save("Page", "", "新しい人生\n", at="260803_100000", merge=False)
        with backup.connect(self.wiki_dir) as con:
            left = [r["stamp"] for r in con.execute(
                "SELECT stamp FROM backup WHERE subpath = ? ORDER BY stamp", ("Page",))]
        self.assertEqual(left, ["260803_100000"])

    def test_壊れた記録より古いものも捨てる(self):
        self.save("Page", "", "1\n", at="260801_100000", merge=False)
        self.save("Page", "1\n", "1\n2\n", at="260802_100000", merge=False)
        self.save("Page", "1\n2\n", "1\n2\n3\n", at="260803_100000", merge=False)
        with backup.connect(self.wiki_dir) as con:   # まん中を壊す
            con.execute("UPDATE backup SET diff = ? WHERE subpath = ? AND stamp = ?",
                        ("壊れた\n", "Page", "260802_100000"))

        self.save("Page", "1\n2\n3\n", "1\n2\n3\n4\n", at="260804_100000", merge=False)
        with backup.connect(self.wiki_dir) as con:
            left = [r["stamp"] for r in con.execute(
                "SELECT stamp FROM backup WHERE subpath = ? ORDER BY stamp", ("Page",))]
        # 壊れた記録と、それより古いものが消える
        self.assertEqual(left, ["260803_100000", "260804_100000"])

    def test_他のページには手を出さない(self):
        self.save("Broken", "", "1\n", at="260801_100000", merge=False)
        self.save("Broken", "", "作り直し\n", at="260802_100000", merge=False)
        self.save("Other", "", "無事\n", at="260801_110000", merge=False)
        self.save("Other", "無事\n", "無事 改\n", at="260802_110000", merge=False)

        self.save("Broken", "作り直し\n", "作り直し 改\n", at="260803_100000", merge=False)
        self.assertEqual(self.counts("Other"), 2)

    def test_つながりが無事なら何も消えない(self):
        for i in range(5):
            self.save("Page", "行{}\n".format(i), "行{}\n".format(i + 1),
                      at="26080{}_100000".format(i + 1), merge=False)
        self.assertEqual(self.counts("Page"), 5)


class TestMergeWindow(BackupTestBase):
    """10分以内の連続した保存を1本にまとめる仕組み。"""

    def test_10分以内の保存はまとめられる(self):
        self.save("Page", "", "1\n", at="260801_100000")
        self.save("Page", "1\n", "1\n2\n", at="260801_100100")   # 1分後
        self.save("Page", "1\n2\n", "1\n2\n3\n", at="260801_100200")  # さらに1分後
        # 3回保存したが、まとめられて「新規作成の1本」だけになる。
        # 新規作成は一覧に出ないので履歴は空
        self.assertEqual(self.history("Page", "1\n2\n3\n"), [])

    def test_10分を超えると別の記録になる(self):
        self.save("Page", "", "1\n", at="260801_100000")
        self.save("Page", "1\n", "1\n2\n", at="260801_101100")  # 11分後
        self.assertEqual(self.stamps("Page", "1\n2\n"), ["260801_101100"])

    def test_mergeFalseならまとめない(self):
        # 復元・部分復元・削除は「そうした事実」を必ず残したいのでまとめない
        self.save("Page", "", "1\n", at="260801_100000")
        self.save("Page", "1\n", "1\n2\n", at="260801_100100", merge=False)
        self.assertEqual(self.stamps("Page", "1\n2\n"), ["260801_100100"])

    def test_まとめた結果もとに戻ったら記録を取り下げる(self):
        self.save("Page", "", "1\n", at="260801_100000")
        self.save("Page", "1\n", "1\n2\n", at="260801_100100")
        # 直前の変更を打ち消して元に戻す
        self.save("Page", "1\n2\n", "1\n", at="260801_100200")
        # 記録は「空→1行」だけが残る（新規作成なので一覧には出ない）
        self.assertEqual(self.history("Page", "1\n"), [])

    def test_同じ秒に2回保存しても両方残る(self):
        # 日時をそのまま識別子に使うので、衝突したらずらす必要がある
        self.save("Page", "", "1\n", at="260801_100000", merge=False)
        self.save("Page", "1\n", "1\n2\n", at="260801_100000", merge=False)
        self.save("Page", "1\n2\n", "1\n2\n3\n", at="260801_100000", merge=False)
        stamps = self.stamps("Page", "1\n2\n3\n")
        # 新規作成のぶんを除いた2件が、別々の日時として残っている
        self.assertEqual(len(stamps), 2)
        self.assertEqual(len(set(stamps)), 2)


class TestPurge(BackupTestBase):
    """履歴の削除（バックアップ管理画面の「履歴を削除」）。"""

    def test_そのページの記録だけを消す(self):
        self.save("A", "", "1\n", at="260801_100000")
        self.save("A", "1\n", "1\n2\n", at="260802_100000")
        self.save("B", "", "1\n", at="260801_110000")
        self.save("B", "1\n", "1\n2\n", at="260802_110000")

        removed = backup.purge_backups(self.wiki_dir, "A")
        self.assertEqual(removed, 2)  # 新規作成のぶんも含めて2本消える
        self.assertEqual(self.history("A", "1\n2\n"), [])
        self.assertEqual(self.stamps("B", "1\n2\n"), ["260802_110000"])
        self.assertEqual(backup.backed_up_subpaths(self.wiki_dir), ["B"])


class TestMoveBackups(BackupTestBase):
    """ページの改名にともなう履歴の引き継ぎ。"""

    def test_改名すると履歴も付いていく(self):
        self.save("Old", "", "1\n", at="260801_100000")
        self.save("Old", "1\n", "1\n2\n", at="260802_100000")
        moved = backup.move_backups(self.wiki_dir, "Old", "New")
        self.assertEqual(moved, 2)
        self.assertEqual(backup.backed_up_subpaths(self.wiki_dir), ["New"])
        self.assertEqual(self.stamps("New", "1\n2\n"), ["260802_100000"])
        self.assertEqual(self.history("Old", "1\n2\n"), [])

    def test_移動先に同じ日時があれば触らない(self):
        self.save("Old", "", "A\n", at="260801_100000", merge=False)
        self.save("New", "", "B\n", at="260801_100000", merge=False)
        backup.move_backups(self.wiki_dir, "Old", "New")
        # 同じ日時なので移せず、どちらの記録もそのまま残る
        self.assertEqual(backup.backed_up_subpaths(self.wiki_dir), ["New", "Old"])


class TestTotalSizeLimit(BackupTestBase):
    """全体の大きさによる上限と、上限に達したときの掃除。

    決まりは3つ（Wiki設計者の指示、2026-09-01）。

      - 上限に達したら、**半分まで**減らしにいく（減らしたそばから
        すぐまた上限に触れる、を繰り返さないため）
      - **記録が20件に満たないページからは消さない**（履歴の浅いページを
        巻き添えにしない）
      - 古い保存から順に。減らし切れなくても、消せる候補が尽きたら打ち切る
    """

    def setUp(self):
        super().setUp()
        self._text, self._filled = {}, {}

    def total(self):
        return backup.total_backup_bytes(self.wiki_dir)

    def counts(self):
        """ページごとの記録の本数。"""
        with backup.connect(self.wiki_dir) as con:
            return {r["subpath"]: r["n"] for r in con.execute(
                "SELECT subpath, COUNT(*) AS n FROM backup GROUP BY subpath")}

    def fill(self, page, times, at_day=1, size=200):
        """1ページに times 件ぶんの記録を作る。

        **前回の続きから積む。** ページの内容を覚えておき、次の保存の
        「変更前」に使う。ここを繋げずに積むと、差分の連なりが合わない
        記録ができてしまい、掃除の対象になってしまう。"""
        body = "行\n" * size
        done = self._filled.get(page, 0)
        for i in range(times):
            old = self._text.get(page, "")
            new = body + "編集{}\n".format(done + i + 1)
            self.save(page, old, new,
                      at="2608{:02d}_{:02d}{:02d}{:02d}".format(
                          at_day, i // 3600, (i // 60) % 60, i % 60),
                      merge=False)
            self._text[page] = new
        self._filled[page] = done + times

    def test_上限内なら何も消えない(self):
        backup.BACKUP_TOTAL_BYTES = 10 * 1024 * 1024
        self.fill("Page", 25)
        before = self.total()
        self.assertEqual(self.counts()["Page"], 25)
        self.assertGreater(before, 0)

    def test_上限に達したら半分まで減らす(self):
        # まず十分な数を貯めてから、上限をいまの大きさに合わせて発火させる
        backup.BACKUP_TOTAL_BYTES = 10 * 1024 * 1024
        self.fill("Page", 60)
        backup.BACKUP_TOTAL_BYTES = self.total()
        # もう1件保存すると上限を超えるので掃除が走る
        self.fill("Page", 1, at_day=2)
        # 上限ぎりぎりではなく、半分あたりまで減っている
        self.assertLessEqual(self.total(), backup.BACKUP_TOTAL_BYTES * 0.5)

    def test_記録が20件に満たないページからは消さない(self):
        backup.BACKUP_TOTAL_BYTES = 10 * 1024 * 1024
        self.fill("Few", 5)          # 浅いページ（古い側にある）
        self.fill("Many", 40, at_day=2)
        backup.BACKUP_TOTAL_BYTES = self.total()
        self.fill("Many", 1, at_day=3)

        counts = self.counts()
        # 浅いページは、いちばん古くても手つかず
        self.assertEqual(counts["Few"], 5)
        # 減らされたのは記録の多いページのほう
        self.assertLess(counts["Many"], 41)

    def test_消しても19件は残る(self):
        # 「20未満は対象としない」ので、20件から1件消すと19件になり、
        # そこで対象から外れる（どのページにも19件は残る）
        backup.BACKUP_TOTAL_BYTES = 10 * 1024 * 1024
        self.fill("Page", 40)
        backup.BACKUP_TOTAL_BYTES = 1        # 極端に小さくして消せるだけ消させる
        self.fill("Page", 1, at_day=2)
        self.assertEqual(self.counts()["Page"], 19)

    def test_消せる候補が尽きたら打ち切る(self):
        # どのページも20件に満たないので、上限を割っていても1件も消せない
        backup.BACKUP_TOTAL_BYTES = 10 * 1024 * 1024
        for p in range(3):
            self.fill("Page{}".format(p), 10, at_day=p + 1)
        before = self.counts()
        backup.BACKUP_TOTAL_BYTES = 1
        self.fill("Page0", 1, at_day=9)      # 掃除は走るが消す先が無い
        after = self.counts()
        self.assertEqual(after["Page1"], before["Page1"])
        self.assertEqual(after["Page2"], before["Page2"])

    def test_古い側から消し目標に届いたら新しい側は残る(self):
        # 古いページだけで目標まで減らせる規模にしておく。
        # 古い順に消していくので、新しいページには手が付かない
        backup.BACKUP_TOTAL_BYTES = 10 * 1024 * 1024
        self.fill("Old", 80, at_day=1)
        self.fill("New", 25, at_day=5)
        backup.BACKUP_TOTAL_BYTES = self.total()
        self.fill("New", 1, at_day=6)

        counts = self.counts()
        self.assertLess(counts["Old"], 80)      # 古い側が削られ
        self.assertEqual(counts["New"], 26)     # 新しい側は手つかず
        self.assertLessEqual(self.total(), backup.BACKUP_TOTAL_BYTES * 0.5)

    def test_書いたばかりの記録は残す(self):
        # 1回の保存が上限より大きい、という極端な場合でも、
        # 書いた直後の記録が自分で自分を消してしまわないこと
        backup.BACKUP_TOTAL_BYTES = 10 * 1024 * 1024
        self.fill("A", 40)
        backup.BACKUP_TOTAL_BYTES = 1
        self.save("B", "", "b\n" * 100, at="260901_100000", merge=False)
        self.assertIn("B", backup.backed_up_subpaths(self.wiki_dir))


class TestContentRev(unittest.TestCase):
    """復元・取り込みの楽観ロックに使うハッシュ。"""

    def test_同じ内容なら同じ値(self):
        self.assertEqual(backup.content_rev("あいう"), backup.content_rev("あいう"))

    def test_少しでも違えば別の値(self):
        self.assertNotEqual(backup.content_rev("あいう"), backup.content_rev("あいえ"))

    def test_空文字でも値が出る(self):
        self.assertTrue(backup.content_rev(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
