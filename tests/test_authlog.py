#!/usr/bin/env python3
"""認証の履歴（wikilib.authlog）のテスト。

パスワードで照合したことを残す（Wiki設計者の指示、2026-09-06）。いまは
**記録だけで、止める仕組みは無い**ので、ここで見ているのも

  - 表の形の決めごとと、値の読みかた
  - **連続失敗回数の数えかた**（`fail_count`）——別に数えを持たず、
    記録そのものから数える

の2つである。回数制限とロックを作るときは、この数えを見て決めることになる。

`authstate` の意味（Wiki設計者の指示、2026-09-06）。

    0        成功
    1〜99    失敗。**値はその時点の連続失敗回数**
    100      ロック
    101      そのIDが登録されていない
    102      無視した（止めているあいだ。パスワードは違っていた）
    103      無視した（止めているあいだ。**パスワードは合っていた**）

101〜103 の意味は2026-09-06に付け替えた（Wiki設計者の指示）。**古い記録は古い意味の
まま残っている**（当時は 101:無視、102:未登録）。ここで見るのはいまの意味。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_authlog.py     （このファイルだけ）
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import authlog  # noqa: E402


class TestDescribe(unittest.TestCase):
    """値を画面の言葉にするところ。"""

    def test_成功(self):
        self.assertEqual(authlog.describe(0), "成功")

    def test_失敗は回数も出す(self):
        # **数字を落とすと、5回で止まる仕組みを追えなくなる**
        self.assertEqual(authlog.describe(1), "失敗（1回目）")
        self.assertEqual(authlog.describe(15), "失敗（15回目）")
        self.assertEqual(authlog.describe(99), "失敗（99回目）")

    def test_ロックと未登録と無視(self):
        self.assertEqual(authlog.describe(100), "ロック")
        self.assertEqual(authlog.describe(101), "未登録のID")
        self.assertEqual(authlog.describe(102), "無視（パスワードも違う）")
        self.assertEqual(authlog.describe(103), "無視（パスワードは合っていた）")

    def test_番号の対応(self):
        # 2026-09-06に付け替えた（Wiki設計者の指示）。**古い記録は直していない**
        self.assertEqual(authlog.STATE_OK, 0)
        self.assertEqual(authlog.STATE_LOCK, 100)
        self.assertEqual(authlog.STATE_NO_USER, 101)
        self.assertEqual(authlog.STATE_IGNORED, 102)
        self.assertEqual(authlog.STATE_IGNORED_OK, 103)

    def test_知らない値も落とさずに出す(self):
        # 記録は残っているのに画面から消える、という状態を作らない
        self.assertEqual(authlog.describe(255), "不明（255）")
        self.assertEqual(authlog.describe(-1), "不明（-1）")


class TestRecord(unittest.TestCase):
    """残すほう。**積むだけで、消したり書き換えたりしない。**"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="authlog-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def states(self, uid=None):
        rows = authlog.recent(self.wiki_dir, 100)
        return [r["authstate"] for r in rows if uid is None or r["uid"] == uid]

    def test_無ければDBを作る(self):
        # config/users.db を勝手に作らないのとは逆の構え。こちらは
        # **作られて困るものが無い**
        self.assertFalse(authlog.exists(self.wiki_dir))
        self.assertTrue(authlog.record(self.wiki_dir, "admin", "127.0.0.1", 0))
        self.assertTrue(authlog.exists(self.wiki_dir))

    def test_残した4つが読める(self):
        authlog.record(self.wiki_dir, "yoshi", "10.0.0.1", 7)
        got = authlog.recent(self.wiki_dir)[0]
        self.assertEqual((got["uid"], got["remote"], got["authstate"]),
                         ("yoshi", "10.0.0.1", 7))
        self.assertGreater(got["unixtime"], 0)

    def test_IDは打たれたそのまま残す(self):
        # **こちらで整えない**（Wiki設計者の指示、2026-09-06）。何が打たれたかを
        # 見るための記録なので、整えると元が分からなくなる
        authlog.record(self.wiki_dir, "  admin  ", "127.0.0.1", 1)
        self.assertEqual(authlog.recent(self.wiki_dir)[0]["uid"], "  admin  ")

    def test_IDもIPも空で残せる(self):
        # IDを入れずに送られた場合。**記録が落ちるほうが困る**
        self.assertTrue(authlog.record(self.wiki_dir, "", None, 1))
        self.assertEqual(authlog.recent(self.wiki_dir)[0]["uid"], "")

    def test_置けなくても諦めるだけ(self):
        # 履歴が残らないことと、ログインできないことは別の話
        blocked = os.path.join(self.work, "no", "such", "wiki")
        os.makedirs(blocked)
        os.chmod(os.path.dirname(blocked), 0o500)
        try:
            self.assertFalse(authlog.record(blocked, "admin", "127.0.0.1", 0))
        finally:
            os.chmod(os.path.dirname(blocked), 0o700)


class TestFailCount(unittest.TestCase):
    """連続失敗回数。**別に数えを持たず、記録から数える。**

    回数制限とロックは、この数えを見て決めることになる。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="authlog-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def attempt(self, uid, passed, known=True):
        authlog.note_attempt(self.wiki_dir, uid, "127.0.0.1", passed, known)

    def last(self, uid):
        for row in authlog.recent(self.wiki_dir, 100):
            if row["uid"] == uid:
                return row["authstate"]
        return None

    def test_記録が無ければ0(self):
        self.assertEqual(authlog.fail_count(self.wiki_dir, "admin"), 0)

    def test_失敗するたびに増える(self):
        for want in (1, 2, 3):
            self.attempt("admin", False)
            self.assertEqual(self.last("admin"), want)

    def test_成功でリセットされる(self):
        self.attempt("admin", False)
        self.attempt("admin", False)
        self.attempt("admin", True)
        self.assertEqual(authlog.fail_count(self.wiki_dir, "admin"), 0)
        self.attempt("admin", False)
        self.assertEqual(self.last("admin"), 1)

    def test_人ごとに数える(self):
        self.attempt("admin", False)
        self.attempt("admin", False)
        self.attempt("yoshi", False)
        self.assertEqual(self.last("yoshi"), 1)
        self.assertEqual(authlog.fail_count(self.wiki_dir, "admin"), 2)

    def test_成功のときは0を残す(self):
        self.attempt("admin", True)
        self.assertEqual(self.last("admin"), authlog.STATE_OK)

    def test_99で止める(self):
        # 100以上は別の意味（ロック・無視）。**そこまで届かせない**
        for _ in range(120):
            authlog.record(self.wiki_dir, "admin", "127.0.0.1", 1)
        self.assertEqual(authlog.fail_count(self.wiki_dir, "admin"), 120)
        self.attempt("admin", False)
        self.assertEqual(self.last("admin"), 99)

    def test_ロックや無視は失敗として数えない(self):
        # あれは「試みを止めた」記録であって、まちがえた回数ではない
        authlog.record(self.wiki_dir, "admin", "127.0.0.1", authlog.STATE_LOCK)
        authlog.record(self.wiki_dir, "admin", "127.0.0.1", authlog.STATE_IGNORED)
        self.assertEqual(authlog.fail_count(self.wiki_dir, "admin"), 0)

    def test_登録されていないIDは101(self):
        # Wiki設計者の指示、2026-09-06
        self.attempt("しらないひと", False, known=False)
        self.assertEqual(self.last("しらないひと"), authlog.STATE_NO_USER)

    def test_無視したぶんは合っていたかで分ける(self):
        # **応答は同じ**（どちらも通さない）。記録にだけ残す
        authlog.note_ignored(self.wiki_dir, "admin", "127.0.0.1", passed=False)
        self.assertEqual(self.last("admin"), authlog.STATE_IGNORED)
        authlog.note_ignored(self.wiki_dir, "admin", "127.0.0.1", passed=True)
        self.assertEqual(self.last("admin"), authlog.STATE_IGNORED_OK)

    def test_登録されていないIDは回数に数えない(self):
        # 無いアカウントは止めようがない。「打ち間違い・当てずっぽう」と
        # 「あるアカウントへの試み」は別々に見たい
        for _ in range(3):
            self.attempt("nobody", False, known=False)
        self.assertEqual(authlog.fail_count(self.wiki_dir, "nobody"), 0)
        self.assertEqual(self.last("nobody"), authlog.STATE_NO_USER)


# 止めに入る回数（運用値は5回。試験のあいだは3回だった）。**テストは数字を直接
# 書かず、ここから導く**——値を変えるたびにテストを直して回らなくて済むように
N = authlog.IGNORE_AFTER


class TestIgnore(unittest.TestCase):
    """IGNORE_AFTER 回まちがえたら、最後の失敗から IGNORE_SECONDS は無視する
    （Wiki設計者の指示、2026-09-06）。運用の値は5回・10分。

    **呼ぶ側はこれが真のとき、照合そのものを行わない**（合っていても
    通さない）。ここで見ているのは、いつ止まっていつ明けるか。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="authlog-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        self.now = 1_000_000

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, state, uid="admin", when=None):
        """時刻を指定して1件置く（`record` は「いま」で入れてしまうため）。"""
        path = authlog.db_path(self.wiki_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        con = sqlite3.connect(path)
        with con:
            con.executescript(authlog.SCHEMA)
            con.execute(f"INSERT INTO {authlog.TABLE} VALUES (?, ?, ?, ?)",
                        (self.now if when is None else when, uid, "127.0.0.1", state))
        con.close()

    def fails(self, n, uid="admin", when=None):
        for i in range(n):
            self.put(i + 1, uid, when)

    def ignored(self, uid="admin", at=None):
        return authlog.is_ignored(self.wiki_dir, uid,
                                  self.now if at is None else at)

    def test_出しはじめの残り回数(self):
        # **止めに入る回（残りがIGNORE_AFTERの倍数になる回）では出さない**
        # ——あそこで出すと、止めているあいだ消えることで読めてしまう
        self.assertEqual(authlog.WARN_LEFT, authlog.IGNORE_AFTER - 1)
        self.assertEqual(authlog.RESCUE_LEFT, 2)

    def test_設定値(self):
        # **運用の値「5回・10分・3セット」**（Wiki設計者の指示、2026-09-06。
        # 試験のあいだは3回・2分・2ターンに縮めていたのを、2026-09-21に戻した）
        self.assertEqual(authlog.IGNORE_AFTER, 5)
        self.assertEqual(authlog.IGNORE_SECONDS, 10 * 60)
        # 判断から古い失敗を落とすまで。**無視時間の倍**（Wiki設計者の指示）
        self.assertEqual(authlog.FORGET_SECONDS, 20 * 60)
        # 何ターン止めたらロックするか（3セット）
        self.assertEqual(authlog.LOCK_TURNS, 3)
        self.assertEqual(authlog.LOCK_AFTER, 15)

    def test_記録が無ければ止めない(self):
        self.assertFalse(self.ignored())

    def test_止めに入る回数の手前までは止めない(self):
        self.fails(N - 1)
        self.assertFalse(self.ignored())

    def test_止めに入る回数で止まる(self):
        self.fails(N)
        self.assertTrue(self.ignored())

    def test_止まったあとの次の回は止まらない(self):
        # IGNORE_AFTER回**ごと**なので、次の倍数の手前までは通す。
        # 無視のあいだはそもそも無視されるので、明けたあとの話
        self.fails(2 * N - 1)
        self.assertFalse(self.ignored(at=self.now + authlog.IGNORE_SECONDS))

    def test_無視時間がすぎれば明ける(self):
        self.fails(N)
        self.assertTrue(self.ignored(at=self.now + authlog.IGNORE_SECONDS - 1))
        self.assertFalse(self.ignored(at=self.now + authlog.IGNORE_SECONDS))

    def test_明けるのは最後の失敗から無視時間ぶん(self):
        self.fails(N - 1, when=self.now - 10)
        self.put(N, when=self.now)
        self.assertTrue(self.ignored(at=self.now + authlog.IGNORE_SECONDS - 1))
        self.assertFalse(self.ignored(at=self.now + authlog.IGNORE_SECONDS))

    def test_明けたらまた同じ回数まで試せる(self):
        """Wiki設計者の指示、2026-09-06。**明けた直後に1回で止まり直さない。**"""
        self.fails(N)
        after = self.now + authlog.IGNORE_SECONDS      # 明けた
        self.assertFalse(self.ignored(at=after))
        t = after
        for i in range(N + 1, 2 * N):                  # 通してよい回
            self.put(i, when=t)
            self.assertFalse(self.ignored(at=t + 1))
            t += 1
        self.put(2 * N, when=t)                        # 次の倍数でまた止まる
        self.assertTrue(self.ignored(at=t + 1))

    def test_倍の時間が空けば数え直す(self):
        """**過去の失敗が無視時間の倍だけ経過したら、判断の数は0から。**

        Wiki設計者の指示、2026-09-06。ただし記録に残す通算はリセットしない
        （下の `test_記録に残す通算はリセットしない`）。"""
        self.fails(N)
        far = self.now + authlog.FORGET_SECONDS + 1
        self.put(N + 1, when=far)      # 久しぶりの1回。判断では「1回目」
        self.assertFalse(self.ignored(at=far + 1))
        t = far
        for i in range(N + 2, 2 * N):  # 判断では2回目〜(N-1)回目
            t += 1
            self.put(i, when=t)
            self.assertFalse(self.ignored(at=t + 1))
        t += 1
        self.put(2 * N, when=t)        # 判断ではN回目。ここで止まる
        self.assertTrue(self.ignored(at=t + 1))

    def test_記録に残す通算はリセットしない(self):
        # 「ただし、失敗回数はリセットしません」（Wiki設計者の指示）。
        # authstate は最後に通るまで伸びる
        self.fails(N)
        self.put(N + 1, when=self.now + authlog.FORGET_SECONDS + 1)
        self.assertEqual(authlog.fail_count(self.wiki_dir, "admin"), N + 1)

    def test_倍の時間に届かなければ落ちない(self):
        self.fails(N)
        near = self.now + authlog.FORGET_SECONDS - 1
        for i in range(N + 1, 2 * N + 1):
            self.put(i, when=near)     # 判断では2N回目（Nの倍数）
        self.assertTrue(self.ignored(at=near + 1))

    def test_通れば数えが切れる(self):
        self.fails(N)
        self.put(authlog.STATE_OK, when=self.now + 1)
        self.assertFalse(self.ignored(at=self.now + 2))

    def test_無視したぶんは数を進めない(self):
        # 待ってもらえば、また試せる。**正解が来ていた（103）ぶんも同じ**。
        # ここが数に入ると、止められている人は永久に明けない
        self.fails(N)
        for _ in range(5):
            self.put(authlog.STATE_IGNORED)
        self.put(authlog.STATE_IGNORED_OK)
        self.assertEqual(authlog.fail_count(self.wiki_dir, "admin"), N)
        self.assertFalse(self.ignored(at=self.now + authlog.IGNORE_SECONDS))

    def test_未登録のIDでは止まらない(self):
        # 止めようのない相手。102 は数に入らない
        for _ in range(5):
            self.put(authlog.STATE_NO_USER, uid="nobody")
        self.assertFalse(self.ignored("nobody"))

    def test_人ごとに止める(self):
        self.fails(N)
        self.assertFalse(self.ignored("yoshi"))

    def test_空白を足しても逃げられない(self):
        # 記録には打たれたまま残す（Wiki設計者の指示）ので、素直に比べると
        # «admin» と «admin␣» が別人になり、**空白1つで数えを逃げられる**
        self.fails(N)
        self.assertTrue(self.ignored(" admin "))
        self.assertTrue(self.ignored("admin "))

    def test_空白を足した失敗も同じ数えに入る(self):
        spellings = ("admin", " admin", "admin ")
        for i in range(1, N + 1):
            self.put(i, uid=spellings[i % 3])
        self.assertEqual(authlog.fail_count(self.wiki_dir, "admin"), N)
        self.assertTrue(self.ignored())


class TestLockCount(TestIgnore):
    """ロックまでの数え（Wiki設計者の指示、2026-09-06）。

    **掛けるのは `wikilib.userdb.lock_user`**（`pw` を `LOCKED` に書き換える）。
    ここが受け持つのは「あと何回か」「次でロックか」を数えるところまで。"""

    def left(self, uid="admin", at=None):
        return authlog.lock_left(self.wiki_dir, uid,
                                 self.now if at is None else at)

    def test_はじめは満タン(self):
        self.assertEqual(self.left(), authlog.LOCK_AFTER)

    def test_まちがえるたびに減る(self):
        for i in range(1, 6):
            self.put(i)
            self.assertEqual(self.left(), authlog.LOCK_AFTER - i)

    def test_次でロックかを知らせる(self):
        self.fails(authlog.LOCK_AFTER - 2)
        self.assertFalse(authlog.should_lock(self.wiki_dir, "admin", self.now))
        self.put(authlog.LOCK_AFTER - 1)
        self.assertTrue(authlog.should_lock(self.wiki_dir, "admin", self.now))

    def test_無視しているあいだは減らない(self):
        # 止めているぶん（102/103）は数に入らないので、残りも動かない。
        # **画面に同じ数が出続ける**のはこのため
        self.fails(N)
        before = self.left()
        for _ in range(4):
            self.put(authlog.STATE_IGNORED)
        self.put(authlog.STATE_IGNORED_OK)
        self.assertEqual(self.left(), before)

    def test_ロックの数えは間を空けても戻らない(self):
        """**「失敗回数はリセットしません」**（Wiki設計者の指示、2026-09-06）。

        無視の判断は最近のぶんで数え直すが、ロックまでの数えは通算のまま。
        戻るのは通ったときだけ。"""
        self.fails(authlog.LOCK_AFTER - 2)
        self.assertEqual(self.left(), 2)
        self.assertEqual(self.left(at=self.now + authlog.FORGET_SECONDS + 1), 2)

    def test_数え直しで残り1回のときは2回に戻す(self):
        """久しぶりに1回まちがえただけでロック、を避ける（Wiki設計者の指示、
        2026-09-07）。**戻すのは `RESCUE_LEFT` 回まで**で、通算そのものは
        戻らない。"""
        self.fails(authlog.LOCK_AFTER - 1)
        self.assertEqual(self.left(), 1)
        far = self.now + authlog.FORGET_SECONDS + 1
        self.assertEqual(self.left(at=far), authlog.RESCUE_LEFT)
        self.assertFalse(authlog.should_lock(self.wiki_dir, "admin", far))

    def test_戻したあとは2回でロックに届く(self):
        # 間を空けるたびに2回まで買えるが、それ以上は増えない
        self.fails(authlog.LOCK_AFTER - 1)
        far = self.now + authlog.FORGET_SECONDS + 1
        self.put(authlog.LOCK_AFTER, when=far)
        self.assertEqual(self.left(at=far), 1)
        self.assertTrue(authlog.should_lock(self.wiki_dir, "admin", far))

    def test_途中のターンだけ判断から落ちても残りは減らない(self):
        """運用の値（5回ごとに10分、3ターン）で、3ターン目の途中に1ターン目の失敗が
        判断から落ちる。通算はロックの一歩手前（残り1回）なので、残りは1のまま
        （救済の式が残りを0へ減らしていた。最後の警告が出なくなる）。"""
        self.fails(N)                                   # 1ターン目（あとで落ちる）
        later = self.now + authlog.FORGET_SECONDS + 1
        for i in range(N + 1, authlog.LOCK_AFTER):      # 通算は LOCK_AFTER - 1
            self.put(i, when=later)
        self.assertEqual(self.left(at=later), 1)
        self.assertTrue(authlog.should_lock(self.wiki_dir, "admin", later))

    def test_通れば戻る(self):
        self.fails(authlog.LOCK_AFTER - 1)
        self.put(authlog.STATE_OK, when=self.now + 1)
        self.assertEqual(self.left(at=self.now + 2), authlog.LOCK_AFTER)


class TestReadEmpty(unittest.TestCase):
    """記録がまだ無いWiki。**開いても作らない。**"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="authlog-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def test_はじめは無い(self):
        self.assertFalse(authlog.exists(self.wiki_dir))

    def test_読んでも作らない(self):
        self.assertEqual(authlog.recent(self.wiki_dir), [])
        self.assertEqual(authlog.count(self.wiki_dir), 0)
        self.assertFalse(authlog.exists(self.wiki_dir))

    def test_置き場所はそのWikiのlog(self):
        self.assertEqual(
            authlog.db_path(self.wiki_dir),
            os.path.join(self.work, "wikidata", "testwiki", "log", "auth.log.db"))


class TestRead(unittest.TestCase):
    """記録があるとき。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="authlog-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        path = authlog.db_path(self.wiki_dir)
        os.makedirs(os.path.dirname(path))
        self.con = sqlite3.connect(path)
        self.con.executescript(authlog.SCHEMA)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, unixtime, uid="admin", remote="127.0.0.1", state=0):
        self.con.execute(f"INSERT INTO {authlog.TABLE} VALUES (?, ?, ?, ?)",
                         (unixtime, uid, remote, state))
        self.con.commit()

    def test_記録した4つが読める(self):
        self.put(1000, "yoshi", "10.0.0.1", 3)
        got = authlog.recent(self.wiki_dir)[0]
        self.assertEqual((got["unixtime"], got["uid"], got["remote"],
                          got["authstate"]), (1000, "yoshi", "10.0.0.1", 3))

    def test_新しいほうから並ぶ(self):
        for t in (100, 300, 200):
            self.put(t)
        self.assertEqual([r["unixtime"] for r in authlog.recent(self.wiki_dir)],
                         [300, 200, 100])

    def test_既定は20件(self):
        # **最新の20件で十分**（Wiki設計者の指示、2026-09-06）
        self.assertEqual(authlog.DEFAULT_LIMIT, 20)
        for t in range(30):
            self.put(t)
        rows = authlog.recent(self.wiki_dir)
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[0]["unixtime"], 29)   # 新しいほうを残す

    def test_件数を増やせる(self):
        for t in range(30):
            self.put(t)
        self.assertEqual(len(authlog.recent(self.wiki_dir, 25)), 25)

    def test_件数には上限がある(self):
        self.put(1)
        self.assertEqual(authlog.recent(self.wiki_dir, 10 ** 9), authlog.recent(self.wiki_dir, 1))

    def test_おかしな件数でも落ちない(self):
        self.put(1)
        for bad in (0, -5, None, ""):
            self.assertEqual(len(authlog.recent(self.wiki_dir, bad)), 1)

    def test_全部の件数(self):
        for t in range(25):
            self.put(t)
        self.assertEqual(authlog.count(self.wiki_dir), 25)

    def test_表が無くても落ちない(self):
        # DBだけあって中身が違う場合。**空のWikiと同じに見えればよい**
        self.con.execute(f"DROP TABLE {authlog.TABLE}")
        self.con.commit()
        self.assertEqual(authlog.recent(self.wiki_dir), [])
        self.assertEqual(authlog.count(self.wiki_dir), 0)


if __name__ == "__main__":
    unittest.main()
