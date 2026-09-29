#!/usr/bin/env python3
"""利用者アカウントの記録（wikilib.userdb）のテスト。

ページごとの認証を入れるための土台。**ここが間違うと、通してはいけない
相手を通す**ので、照合の可否をひととおり固定しておく。

パスワードの持ちかた（`パスワード + "wiki"` を SHA-1）はWiki設計者の指示による
もので、利用者ごとの塩を持たない・速い関数である、という弱さを承知のうえで
採っている（`wikilib.userdb` の冒頭を参照）。**このテストはその弱さを
是としているわけではなく、いまの決めごとどおりに動くことだけを見ている。**
強い持ちかたへ移すときは `hash_password` の1か所を差し替え、下の
`test_決められた作りかたのとおりに値を作る` を書き換えればよい。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_userdb.py     （このファイルだけ）
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import auth, userdb  # noqa: E402


class TestCheckUid(unittest.TestCase):
    """ログインに使う名前（uid）に使える文字。**半角の英数字だけ**（Wiki設計者の指示、
    2026-09-05）。ログインの入力欄に打つものなので、環境によって入りかたが
    変わる文字を持ち込ませないほうが、入れたつもりで入らない事故が減る。"""

    def ok(self, uid):
        self.assertIsNone(userdb.check_uid(uid), f"{uid!r} は通るはず")

    def ng(self, uid):
        self.assertIsNotNone(userdb.check_uid(uid), f"{uid!r} は弾くはず")

    def test_英数字は通る(self):
        for uid in ("admin", "yoshi2", "Y2K", "0"):
            self.ok(uid)

    def test_空は弾く(self):
        self.ng("")

    def test_空白は弾く(self):
        self.ng("yo shi")
        self.ng(" admin")

    def test_記号は弾く(self):
        for uid in ("yo-shi", "yo_shi", "user@example", "a.b", "a/b"):
            self.ng(uid)

    def test_日本語は弾く(self):
        # str.isalnum() だと「矢野」も真になってしまうので、範囲を書いた
        # 正規表現で見ている。その違いが効いていることの確認
        self.assertTrue("矢野".isalnum())
        self.ng("矢野")

    def test_全角の英数字も弾く(self):
        self.assertTrue("ｙｏｓｈｉ".isalnum())
        self.ng("ｙｏｓｈｉ")

    def test_長すぎるものは弾く(self):
        self.ok("a" * 64)
        self.ng("a" * 65)


class UserDbTestBase(unittest.TestCase):
    """記録は**用意してから**始める。画面を開いたり照合したりしても勝手には
    作られないので（`create_db` を呼ぶまで無い）、ここで明示的に用意する。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="userdb-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def uids(self):
        return [(u["uidnum"], u["uid"], u["name"]) for u in userdb.all_users(self.wiki_dir)]


class TestHashPassword(unittest.TestCase):
    """ハッシュ値の作りかた。**作りかたを知っているのはこの関数だけ。**

    `account.pw_salt`（空ならWiki名）＋ `\\x00` ＋ `uid` ＋ `\\x00` ＋ パスワードの SHA-1
    （Wiki設計者の指示、2026-09-21。区切りは同じ日の指示で足した）。旧い形は通さない。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="hashpw-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "wikiA", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def other_wiki(self, name):
        path = os.path.join(self.work, "wikidata", name, "wiki")
        os.makedirs(path, exist_ok=True)
        return path

    def write_salt(self, wiki_dir, salt):
        from wikilib import wikiconfig
        ok, _saved, message = wikiconfig.save_farm_config(
            wiki_dir, {"account": {"pw_salt": salt}})
        self.assertTrue(ok, message)

    def test_塩とIDとパスワードをNULで区切ってSHA1(self):
        # 塩を書かなければ Wiki名
        self.assertEqual(userdb.hash_password(self.wiki_dir, "yoshi", "adminpw"),
                         hashlib.sha1(b"wikiA\x00yoshi\x00adminpw").hexdigest())

    def test_日本語のパスワードも通る(self):
        self.assertEqual(userdb.hash_password(self.wiki_dir, "yoshi", "ぱすわーど"),
                         hashlib.sha1("wikiA\x00yoshi\x00ぱすわーど".encode("utf-8")).hexdigest())

    def test_IDとパスワードの境目が曖昧にならない(self):
        # 区切りが無いと ("a", "bc") と ("ab", "c") が同じ値になる（2026-09-21に区切りを入れた）
        self.assertNotEqual(userdb.hash_password(self.wiki_dir, "a", "bc"),
                            userdb.hash_password(self.wiki_dir, "ab", "c"))

    def test_区切りは入力できない文字(self):
        self.assertEqual(userdb.HASH_SEPARATOR, "\x00")
        self.assertIsNotNone(userdb.check_uid("a\x00b"))      # IDには使えない

    def test_同じパスワードでもIDが違えば値が違う(self):
        # 表を1枚見ても「この2人は同じパスワード」と分からない
        self.assertNotEqual(userdb.hash_password(self.wiki_dir, "alice", "same"),
                            userdb.hash_password(self.wiki_dir, "bob", "same"))

    def test_同じIDとパスワードでもWikiが違えば値が違う(self):
        other = self.other_wiki("wikiB")
        self.assertNotEqual(userdb.hash_password(self.wiki_dir, "alice", "same"),
                            userdb.hash_password(other, "alice", "same"))

    def test_同じ入力は同じ値になる(self):
        self.assertEqual(userdb.hash_password(self.wiki_dir, "alice", "same"),
                         userdb.hash_password(self.wiki_dir, "alice", "same"))

    def test_塩を設定に書けばそれを使う(self):
        self.write_salt(self.wiki_dir, "my-salt")
        self.assertEqual(userdb.hash_password(self.wiki_dir, "yoshi", "pw"),
                         hashlib.sha1(b"my-salt\x00yoshi\x00pw").hexdigest())

    def test_塩が同じなら別のWikiでも同じ値_名前を変えても値が変わらない(self):
        # Wiki名を変えるときは旧名を塩に固定する（wikilib.farmrename）。その効き目
        self.write_salt(self.wiki_dir, "wikiA")
        renamed = self.other_wiki("wikiRenamed")
        self.write_salt(renamed, "wikiA")
        self.assertEqual(userdb.hash_password(self.wiki_dir, "alice", "pw"),
                         userdb.hash_password(renamed, "alice", "pw"))

    def test_塩が空ならWiki名に戻る(self):
        self.write_salt(self.wiki_dir, "  ")
        self.assertEqual(userdb.password_salt(self.wiki_dir), "wikiA")

    def test_40文字の16進(self):
        value = userdb.hash_password(self.wiki_dir, "alice", "x")
        self.assertRegex(value, r"^[0-9a-f]{40}$")


class TestCreateDb(unittest.TestCase):
    """記録を用意するのは**明示的な操作のときだけ**（Wiki設計者の指示、2026-09-05）。

    以前はどの画面でも触れた時点で作っていた。そうすると「誰でも開ける画面へ
    アクセスした見ず知らずの相手が、既定のパスワードを持つ管理者アカウントを
    そのWikiに生やす」ことになる（しかもその値は一覧の画面に出る）。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="userdb-new-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def test_はじめは記録が無い(self):
        self.assertFalse(userdb.exists(self.wiki_dir))

    def test_読んでも作らない(self):
        self.assertEqual(userdb.all_users(self.wiki_dir), [])
        self.assertIsNone(userdb.get_user(self.wiki_dir, 1))
        self.assertIsNone(userdb.find_by_uid(self.wiki_dir, "admin"))
        self.assertFalse(userdb.exists(self.wiki_dir))

    def test_照合しても作らない(self):
        # ログイン画面へ送っただけで admin が生えては困る
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))
        self.assertFalse(userdb.exists(self.wiki_dir))

    def test_書き換えようとしても作らない(self):
        for call in (lambda: userdb.add_user(self.wiki_dir, "x", userdb.hash_password(self.wiki_dir, "x", "y"), ""),
                     lambda: userdb.update_user(self.wiki_dir, 1, "x", "", ""),
                     lambda: userdb.delete_user(self.wiki_dir, 2)):
            ok, message = call()
            self.assertFalse(ok)
            self.assertIn("記録がありません", message)
        self.assertFalse(userdb.exists(self.wiki_dir))

    def test_用意すればadminが入る(self):
        ok, _message = userdb.create_db(self.wiki_dir)
        self.assertTrue(ok)
        self.assertTrue(userdb.exists(self.wiki_dir))
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))

    def test_2度目は何もしない(self):
        userdb.create_db(self.wiki_dir)
        userdb.update_user(self.wiki_dir, 1, "admin",
                           userdb.hash_password(self.wiki_dir, "admin", "changed"), "管理者")
        ok, _message = userdb.create_db(self.wiki_dir)
        self.assertFalse(ok)
        # 中身を触らない（変えたパスワードが戻らない）
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "admin", "changed"))


class TestInitialAccount(UserDbTestBase):
    """用意した直後の状態。"""

    def test_adminが最初から入っている(self):
        self.assertEqual(self.uids(), [(1, "admin", "管理者")])

    def test_adminのパスワードはadminpw(self):
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))

    def test_DBはそのWikiのconfigに置く(self):
        self.assertTrue(os.path.isfile(
            os.path.join(self.work, "wikidata", "testwiki", "config", "users.db")))

    def test_何度開いてもadminは増えない(self):
        for _ in range(3):
            userdb.all_users(self.wiki_dir)
        self.assertEqual(len(self.uids()), 1)

    def test_別のWikiには作らない(self):
        # 用意したWikiの隣に勝手に生えないこと
        other = os.path.join(self.work, "wikidata", "otherwiki", "wiki")
        os.makedirs(other)
        userdb.authenticate(other, "admin", "adminpw")
        self.assertFalse(userdb.exists(other))

    def test_adminのパスワードを変えても開き直しで戻らない(self):
        # 既定のアカウントを入れ直すのは「無ければ」だけ。変えた値を
        # 毎回上書きしてしまうと、パスワードを変える意味が無くなる
        userdb.update_user(self.wiki_dir, 1, "admin",
                           userdb.hash_password(self.wiki_dir, "admin", "newpw"), "管理者")
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "admin", "newpw"))


class TestAuthenticate(UserDbTestBase):
    """照合。**通してはいけない相手を通さない**ことを見る。"""

    def test_合っていればそのアカウントを返す(self):
        user = userdb.authenticate(self.wiki_dir, "admin", "adminpw")
        self.assertEqual(user["uid"], "admin")
        self.assertEqual(user["name"], "管理者")

    def test_パスワードが違えば通さない(self):
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "admin", "adminpW"))

    def test_居ないIDは通さない(self):
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "nobody", "adminpw"))

    def test_空のパスワードでは通らない(self):
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "admin", ""))

    def test_IDが空なら通らない(self):
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "", "adminpw"))

    def test_ハッシュ値そのものを入れても通らない(self):
        # 一覧の画面にハッシュ値が出るので、それをパスワード欄へ貼れば
        # 通ってしまう、ということが無いか。**入れた値は必ずハッシュに通す**
        self.assertIsNone(userdb.authenticate(
            self.wiki_dir, "admin", userdb.hash_password(self.wiki_dir, "admin", "adminpw")))


class TestAddUser(UserDbTestBase):

    def test_足せる(self):
        ok, _message = userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        self.assertTrue(ok)
        self.assertEqual(self.uids(), [(1, "admin", "管理者"), (2, "yoshi", "矢野")])

    def test_足したアカウントで照合できる(self):
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "yoshi", "p@ss"))

    def test_同じIDは足せない(self):
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        ok, message = userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "other"), "別人")
        self.assertFalse(ok)
        self.assertIn("すでに登録", message)

    def test_IDが空なら足せない(self):
        ok, _message = userdb.add_user(self.wiki_dir, "", userdb.hash_password(self.wiki_dir, "", "x"), "名前")
        self.assertFalse(ok)

    def test_英数字以外のIDは足せない(self):
        # 決まりそのものは TestCheckUid で見ている。ここでは
        # add_user がその決まりを通していることの確認
        for uid in ("yo shi", "yo-shi", "矢野"):
            ok, _message = userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "x"), "名前")
            self.assertFalse(ok, f"{uid!r} は登録できないはず")

    def test_パスワードが空なら足せない(self):
        ok, _message = userdb.add_user(self.wiki_dir, "yoshi", "", "矢野")
        self.assertFalse(ok)

    def test_番号は続きから振る(self):
        userdb.add_user(self.wiki_dir, "a", userdb.hash_password(self.wiki_dir, "a", "x"), "")
        userdb.add_user(self.wiki_dir, "b", userdb.hash_password(self.wiki_dir, "b", "x"), "")
        userdb.delete_user(self.wiki_dir, 2)
        userdb.add_user(self.wiki_dir, "c", userdb.hash_password(self.wiki_dir, "c", "x"), "")
        # 途中の番号は埋めない
        self.assertEqual([n for n, _uid, _name in self.uids()], [1, 3, 4])


class TestUidnum(UserDbTestBase):
    """番号（uidnum）の決めかた。**いま残っている行の最大値 + 1**
    （Wiki設計者の指示、2026-09-05。管理用の表は別に持たない）。"""

    def add(self, uid):
        userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "x"), "")

    def numbers(self):
        return [n for n, _uid, _name in self.uids()]

    def test_途中の番号は埋めない(self):
        self.add("a")            # 2
        self.add("b")            # 3
        userdb.delete_user(self.wiki_dir, 2)
        self.add("c")
        self.assertEqual(self.numbers(), [1, 3, 4])

    def test_いちばん大きい番号を消すとその番号は次の人に回る(self):
        # 最大値+1で決めているので、こうなる。**番号だけを手がかりに
        # 「誰だったか」を後から辿ることはできない**、ということでもある
        self.add("a")            # 2
        userdb.delete_user(self.wiki_dir, 2)
        self.add("b")
        self.assertEqual(self.numbers(), [1, 2])
        self.assertEqual(userdb.get_user(self.wiki_dir, 2)["uid"], "b")

    def test_次の番号を見ても増えない(self):
        first = userdb.next_uidnum(self.wiki_dir)
        self.assertEqual(userdb.next_uidnum(self.wiki_dir), first)


class TestUpdateUser(UserDbTestBase):

    def setUp(self):
        super().setUp()
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")

    def test_名前を変えられる(self):
        ok, _message = userdb.update_user(self.wiki_dir, 2, "yoshi", "", "矢野（改）")
        self.assertTrue(ok)
        self.assertEqual(userdb.get_user(self.wiki_dir, 2)["name"], "矢野（改）")

    def test_パスワードを空で送ると変えない(self):
        # 一覧の画面で、変えるつもりのない行のハッシュ値を消してしまう事故よけ
        userdb.update_user(self.wiki_dir, 2, "yoshi", "", "矢野")
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "yoshi", "p@ss"))

    def test_パスワードを変えられる(self):
        userdb.update_user(self.wiki_dir, 2, "yoshi",
                           userdb.hash_password(self.wiki_dir, "yoshi", "new"), "矢野")
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "yoshi", "p@ss"))
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "yoshi", "new"))

    def test_IDを変えるときはパスワードも付け直す(self):
        # ハッシュにIDが混ざるので、IDだけ変えると誰にも通らなくなる
        ok, message = userdb.update_user(self.wiki_dir, 2, "yoshi2", "", "矢野")
        self.assertFalse(ok)
        self.assertIn("パスワードも付け直", message)
        current = userdb.get_user(self.wiki_dir, 2)
        ok, _message = userdb.update_user(self.wiki_dir, 2, "yoshi2", current["pw"], "矢野")
        self.assertFalse(ok)                               # いまと同じハッシュも「付け直していない」
        self.assertEqual(userdb.get_user(self.wiki_dir, 2)["uid"], "yoshi")

    def test_IDを変えてパスワードも付け直せば新しいIDで通る(self):
        ok, _message = userdb.update_user(
            self.wiki_dir, 2, "yoshi2",
            userdb.hash_password(self.wiki_dir, "yoshi2", "p@ss"), "矢野")
        self.assertTrue(ok)
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "yoshi2", "p@ss"))
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "yoshi", "p@ss"))

    def test_他の人が使っているIDにはできない(self):
        ok, message = userdb.update_user(self.wiki_dir, 2, "admin", "", "矢野")
        self.assertFalse(ok)
        self.assertIn("他のアカウント", message)

    def test_自分のIDのままなら通る(self):
        ok, _message = userdb.update_user(self.wiki_dir, 2, "yoshi", "", "矢野")
        self.assertTrue(ok)

    def test_英数字以外のIDには書き換えられない(self):
        ok, _message = userdb.update_user(self.wiki_dir, 2, "矢野", "", "矢野")
        self.assertFalse(ok)
        self.assertEqual(userdb.get_user(self.wiki_dir, 2)["uid"], "yoshi")

    def test_居ない番号は書き換えられない(self):
        ok, _message = userdb.update_user(self.wiki_dir, 99, "x", "", "")
        self.assertFalse(ok)


class TestDeleteUser(UserDbTestBase):

    def test_消せる(self):
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        ok, _message = userdb.delete_user(self.wiki_dir, 2)
        self.assertTrue(ok)
        self.assertEqual(self.uids(), [(1, "admin", "管理者")])

    def test_adminは消せない(self):
        # 全部消すと誰も管理できなくなるので、既定のアカウントだけは残す
        ok, message = userdb.delete_user(self.wiki_dir, 1)
        self.assertFalse(ok)
        self.assertIn("消せません", message)
        self.assertEqual(self.uids(), [(1, "admin", "管理者")])

    def test_居ない番号は消せない(self):
        ok, _message = userdb.delete_user(self.wiki_dir, 99)
        self.assertFalse(ok)


class TestFirstPassword(unittest.TestCase):
    """最初のパスワードは**作る人が決める**（Wiki設計者の指示、2026-09-08）。

    省略できるのは行きがかり上の逃げ道で、そのWikiは「誰でも知っている値で
    管理者に入れる」状態から始まってしまう。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="userdb-first-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def test_渡した値になる(self):
        ok, _message = userdb.create_db(self.wiki_dir, "1234")
        self.assertTrue(ok)
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "admin", "1234"))

    def test_渡したら既定値では通らない(self):
        userdb.create_db(self.wiki_dir, "1234")
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))

    def test_省略すると既定値のまま(self):
        # これまでどおり。**そうと分かる文言を返す**
        ok, message = userdb.create_db(self.wiki_dir)
        self.assertTrue(ok)
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))
        self.assertIn("誰でも知っています", message)

    def test_渡したときは値を文言に出さない(self):
        _ok, message = userdb.create_db(self.wiki_dir, "1234")
        self.assertNotIn("1234", message)


class TestResetAdminPassword(UserDbTestBase):
    """`./wiki.py resetpw` が使う入れ直し（Wiki設計者の指示、2026-09-08）。

    **画面からは戻れなくなったときの逃げ道。** 一覧の画面は管理者しか
    開けないので、管理者本人が入れなくなるとそこからは戻せない。"""

    def test_入れ直せる(self):
        ok, _message = userdb.reset_admin_password(self.wiki_dir, "newpw")
        self.assertTrue(ok)
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "admin", "newpw"))
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))

    def test_ロックも解ける(self):
        # ロックは pw が LOCKED なだけなので、書き直せば戻る
        userdb.lock_user(self.wiki_dir, 1)
        ok, message = userdb.reset_admin_password(self.wiki_dir, "newpw")
        self.assertTrue(ok)
        self.assertIn("ロックも解けました", message)
        self.assertFalse(userdb.is_locked(userdb.get_user(self.wiki_dir, 1)))

    def test_名前は触らない(self):
        # 管理者の名前を変えて使っている場合に、戻ってしまっては困る
        userdb.update_user(self.wiki_dir, 1, "root",
                           userdb.hash_password(self.wiki_dir, "root", "x"), "運用担当")
        userdb.reset_admin_password(self.wiki_dir, "newpw")
        got = userdb.get_user(self.wiki_dir, 1)
        self.assertEqual((got["uid"], got["name"]), ("root", "運用担当"))
        # 入れ直したパスワードは、いまのID（root）で通る
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "root", "newpw"))

    def test_空のパスワードは受けない(self):
        ok, _message = userdb.reset_admin_password(self.wiki_dir, "")
        self.assertFalse(ok)

    def test_記録が無ければ何もしない(self):
        other = os.path.join(self.work, "wikidata", "otherwiki", "wiki")
        os.makedirs(other)
        ok, _message = userdb.reset_admin_password(other, "newpw")
        self.assertFalse(ok)


class TestIsAdmin(UserDbTestBase):
    """管理者かどうかの判断（`/.admin/accounts` を開けるかに使う）。

    **見るのは `uidnum` であって `uid` ではない。** 名前は一覧の画面から
    書き換えられるので、`uid == "admin"` で見ていると、名前を `admin` に
    変えるだけで管理者になれてしまう。"""

    def test_uidnum1なら管理者(self):
        self.assertTrue(userdb.is_admin(userdb.get_user(self.wiki_dir, 1)))

    def test_他の人は管理者ではない(self):
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "x"), "矢野")
        self.assertFalse(userdb.is_admin(userdb.get_user(self.wiki_dir, 2)))

    def test_名前をadminに変えても管理者にはならない(self):
        userdb.add_user(self.wiki_dir, "x", userdb.hash_password(self.wiki_dir, "x", "x"), "")
        userdb.update_user(self.wiki_dir, 1, "root", "", "管理者")
        userdb.update_user(self.wiki_dir, 2, "admin", "", "")
        self.assertFalse(userdb.is_admin(userdb.get_user(self.wiki_dir, 2)))
        # 番号のほうは、名前が変わっても管理者のまま
        self.assertTrue(userdb.is_admin(userdb.get_user(self.wiki_dir, 1)))

    def test_ログインしていない相手を渡してよい(self):
        self.assertFalse(userdb.is_admin(None))


class TestLock(UserDbTestBase):
    """ロック（Wiki設計者の指示、2026-09-06）。**`pw` を «LOCKED» に書き換えるだけ。**

    ハッシュ値が入るはずのところに、ハッシュ値ではない文字列を置く。
    `hash_password()` は必ず40文字の16進を返すので、この値と一致することは
    ない＝どんなパスワードでも通らなくなる。

    **「ロック中」の欄を別に持たない**ので、古いDBでもそのまま動く。"""

    def setUp(self):
        super().setUp()
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")

    def test_掛けられる(self):
        ok, _message = userdb.lock_user(self.wiki_dir, 2)
        self.assertTrue(ok)
        self.assertEqual(userdb.get_user(self.wiki_dir, 2)["pw"], userdb.LOCKED_PW)

    def test_ロック中は見分けられる(self):
        self.assertFalse(userdb.is_locked(userdb.get_user(self.wiki_dir, 2)))
        userdb.lock_user(self.wiki_dir, 2)
        self.assertTrue(userdb.is_locked(userdb.get_user(self.wiki_dir, 2)))
        self.assertFalse(userdb.is_locked(None))

    def test_ロックしたら元のパスワードでは通らない(self):
        userdb.lock_user(self.wiki_dir, 2)
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "yoshi", "p@ss"))

    def test_LOCKEDと打っても通らない(self):
        # 画面に «LOCKED» と出るので、それをパスワード欄へ貼る人が居る。
        # **入れた値は必ずハッシュに通す**ので一致しない
        userdb.lock_user(self.wiki_dir, 2)
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "yoshi",
                                              userdb.LOCKED_PW))

    def test_パスワードを付け直せば戻る(self):
        # 解除のやりかた。/.admin/accounts は管理者しか開けないので、
        # **解除できるのは管理者だけ**になる
        userdb.lock_user(self.wiki_dir, 2)
        userdb.update_user(self.wiki_dir, 2, "yoshi",
                           userdb.hash_password(self.wiki_dir, "yoshi", "new"), "矢野")
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "yoshi", "new"))

    def test_adminも止める(self):
        # 例外にすると、そこだけ何回でも試せる入口が残る
        ok, _message = userdb.lock_user(self.wiki_dir, 1)
        self.assertTrue(ok)
        self.assertIsNone(userdb.authenticate(self.wiki_dir, "admin", "adminpw"))

    def test_2度掛けても壊れない(self):
        userdb.lock_user(self.wiki_dir, 2)
        ok, _message = userdb.lock_user(self.wiki_dir, 2)
        self.assertTrue(ok)
        self.assertEqual(userdb.get_user(self.wiki_dir, 2)["pw"], userdb.LOCKED_PW)

    def test_居ない番号は掛けられない(self):
        ok, _message = userdb.lock_user(self.wiki_dir, 99)
        self.assertFalse(ok)


class TestSessionToken(UserDbTestBase):
    """ログイン状態を持ち回るための合言葉（Wiki設計者の指示、2026-09-06）。

    **ここが緩むと、パスワードを知らない相手がログインできる。** 材料のどれを
    取り違えても、取り違えた側では通らないことを1つずつ固定しておく。

    設置ごとの合言葉（`config/secret.txt`）は、動かしている本物ではなく
    作業用の場所から取るように差し替えて試す。"""

    def setUp(self):
        super().setUp()
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        self.admin = userdb.find_by_uid(self.wiki_dir, "admin")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        super().tearDown()

    def token(self, uid="admin", wikiname="testwiki", pw_hash=None, now=None):
        return auth.session_token(
            uid, wikiname, self.admin["pw"] if pw_hash is None else pw_hash, now)

    def test_同じ材料なら同じ値になる(self):
        self.assertEqual(self.token(now=0), self.token(now=0))

    def test_材料がそのまま見えたりはしない(self):
        made = self.token(now=0)
        self.assertNotIn(self.admin["pw"], made)
        self.assertNotIn(auth.site_secret(), made)
        self.assertEqual(len(made), 40)   # SHA-1 の16進表記

    def test_日付が変わると値が変わる(self):
        day = auth.TOKEN_PERIOD
        self.assertEqual(self.token(now=0), self.token(now=day - 1))
        self.assertNotEqual(self.token(now=0), self.token(now=day))

    def test_人が違えば値が変わる(self):
        self.assertNotEqual(self.token(uid="admin", now=0),
                            self.token(uid="yoshi", now=0))

    def test_Wikiが違えば値が変わる(self):
        self.assertNotEqual(self.token(wikiname="testwiki", now=0),
                            self.token(wikiname="otherwiki", now=0))

    def test_パスワードが違えば値が変わる(self):
        # **パスワードを変えると、持ち出された合言葉が切れる**という
        # 仕組みそのもの
        self.assertNotEqual(self.token(now=0),
                            self.token(pw_hash=userdb.hash_password(self.wiki_dir, "admin", "other"), now=0))

    def test_設置ごとの合言葉が変われば値が変わる(self):
        made = self.token(now=0)
        os.remove(auth.SECRET_PATH)
        self.assertNotEqual(made, self.token(now=0))


class TestSiteSecret(UserDbTestBase):
    """設置ごとの合言葉（`config/secret.txt`）。

    **これは画面に出さない。** アカウント一覧に届いてハッシュ値を読めた相手
    でも、これが分からなければ合言葉は作れない、という置きかたにしてある。"""

    def setUp(self):
        super().setUp()
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        super().tearDown()

    def test_無ければ作る(self):
        self.assertFalse(os.path.exists(auth.SECRET_PATH))
        made = auth.site_secret()
        self.assertEqual(len(made), auth.SECRET_LENGTH)
        self.assertTrue(os.path.isfile(auth.SECRET_PATH))

    def test_2度目は同じ値を返す(self):
        self.assertEqual(auth.site_secret(), auth.site_secret())

    def test_他人には読ませない(self):
        auth.site_secret()
        mode = os.stat(auth.SECRET_PATH).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_紛らわしい字は使わない(self):
        # 手で書き写す場面があっても取り違えないため
        for ng in "l1I0O":
            self.assertNotIn(ng, auth.SECRET_ALPHABET)

    def test_毎回ちがう値になる(self):
        # 設置ごとに変わらなければ、混ぜる意味が無い
        made = set()
        for _ in range(5):
            os.path.exists(auth.SECRET_PATH) and os.remove(auth.SECRET_PATH)
            made.add(auth.site_secret())
        self.assertEqual(len(made), 5)


class TestVerifyToken(UserDbTestBase):
    """合言葉を確かめるほう。**通してはいけないものを通さない。**"""

    def setUp(self):
        super().setUp()
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        super().tearDown()

    def token(self, uid="admin", wikiname="testwiki", now=None):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        return auth.session_token(uid, wikiname, user["pw"], now)

    def verify(self, uid, token, wikiname="testwiki", now=None):
        return auth.verify_token(self.wiki_dir, wikiname, uid, token, now)

    def test_合っていればそのアカウントを返す(self):
        user = self.verify("admin", self.token(now=0), now=0)
        self.assertEqual(user["uid"], "admin")
        self.assertEqual(user["name"], "管理者")

    def test_他の人の合言葉では通らない(self):
        self.assertIsNone(self.verify("admin", self.token("yoshi", now=0), now=0))

    def test_別のWikiの合言葉では通らない(self):
        made = self.token(wikiname="otherwiki", now=0)
        self.assertIsNone(self.verify("admin", made, now=0))

    def test_昨日のぶんは通る(self):
        # 日付が変わった瞬間に全員が閉め出されては使いものにならない
        # （Wiki設計者の指示、2026-09-06）。通した側は、呼び出し元が今日のぶんへ
        # 置き換える（auth.remember_login）
        made = self.token(now=0)
        day = auth.TOKEN_PERIOD
        self.assertIsNotNone(self.verify("admin", made, now=day - 1))
        self.assertIsNotNone(self.verify("admin", made, now=day))
        self.assertIsNotNone(self.verify("admin", made, now=2 * day - 1))

    def test_一昨日のぶんは通らない(self):
        # **2日以上あいだが空くと切れる**、という線がここ
        made = self.token(now=0)
        self.assertIsNone(self.verify("admin", made, now=2 * auth.TOKEN_PERIOD))

    def test_パスワードを変えれば通らない(self):
        # 乗っ取られたと思ったら、パスワードを変えるだけで切れる
        made = self.token(now=0)
        userdb.update_user(self.wiki_dir, 1, "admin",
                           userdb.hash_password(self.wiki_dir, "admin", "newpw"), "管理者")
        self.assertIsNone(self.verify("admin", made, now=0))

    def test_空では通らない(self):
        self.assertIsNone(self.verify("admin", ""))
        self.assertIsNone(self.verify("", self.token(now=0), now=0))

    def test_居ないIDは通らない(self):
        self.assertIsNone(self.verify("nobody", self.token(now=0), now=0))

    def test_記録が無いWikiでは通らない(self):
        other = os.path.join(self.work, "wikidata", "otherwiki", "wiki")
        os.makedirs(other)
        self.assertIsNone(auth.verify_token(
            other, "otherwiki", "admin", self.token(now=0), 0))


class TestSeparatedPerWiki(UserDbTestBase):
    """アカウントはWikiごとに別。"""

    def test_別のWikiには影響しない(self):
        other = os.path.join(self.work, "wikidata", "otherwiki", "wiki")
        os.makedirs(other)
        userdb.create_db(other)
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        self.assertIsNone(userdb.authenticate(other, "yoshi", "p@ss"))
        self.assertIsNotNone(userdb.authenticate(other, "admin", "adminpw"))


class TestOldHashRejected(UserDbTestBase):
    """**旧い形のハッシュは通さない**（Wiki設計者の指示、2026-09-21）。移行の仕組みも持たない。

    旧い形は2つ。`パスワード + "wiki"` の SHA-1（全員共通の固定文字列）と、
    区切りなしの `塩 + uid + パスワード` の SHA-1。どちらで作られたアカウントも、
    パスワードが合っていても入れず、書き換わりもしない。"""

    def old_forms(self, uid, raw):
        salt = userdb.password_salt(self.wiki_dir)
        return {
            "固定文字列": hashlib.sha1((raw + "wiki").encode("utf-8")).hexdigest(),
            "区切りなし": hashlib.sha1((salt + uid + raw).encode("utf-8")).hexdigest(),
        }

    def test_どちらの旧い形でも通らず_書き換わらない(self):
        for name, old in self.old_forms("old", "oldpw").items():
            with self.subTest(name):
                userdb.add_user(self.wiki_dir, "old", old, "旧")
                self.assertIsNone(userdb.authenticate(self.wiki_dir, "old", "oldpw"))
                self.assertEqual(userdb.find_by_uid(self.wiki_dir, "old")["pw"], old)
                userdb.delete_user(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "old")["uidnum"])

    def test_付け直せば通る(self):
        userdb.add_user(self.wiki_dir, "old", self.old_forms("old", "oldpw")["固定文字列"], "旧")
        uidnum = userdb.find_by_uid(self.wiki_dir, "old")["uidnum"]
        userdb.update_user(self.wiki_dir, uidnum, "old",
                           userdb.hash_password(self.wiki_dir, "old", "oldpw"), "旧")
        self.assertIsNotNone(userdb.authenticate(self.wiki_dir, "old", "oldpw"))

    def test_旧い形のハッシュ値そのものを入れても通らない(self):
        userdb.add_user(self.wiki_dir, "old", self.old_forms("old", "oldpw")["固定文字列"], "旧")
        self.assertIsNone(userdb.authenticate(
            self.wiki_dir, "old", self.old_forms("old", "oldpw")["固定文字列"]))

    def test_旧い形を通す関数は残っていない(self):
        self.assertFalse(hasattr(userdb, "legacy_hash_password"))


if __name__ == "__main__":
    unittest.main()
