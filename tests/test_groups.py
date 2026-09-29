#!/usr/bin/env python3
"""グループの記録（wikilib.groups）と、その権限判断（wikilib.auth）のテスト。

助手グループの管理もこの仕組みに統合されている（`STAFF_GROUP` = `"staff"`。
Wiki設計者の指示、2026-09-12）。見ているのは、グループそのものの作成・追加・削除と、
**`staff`の特別さは削除時の挙動だけ**であること、そして**権限展開**
（`auth.expand_principal`/`auth.can_edit_group`。「g:XXXXはXXXXに所属の
ユーザを展開したもの」）。

判断の置き場所は2026-09-13に整理した——記録は`groups`、権限は`auth`。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_groups.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import auth, groups, userdb  # noqa: E402


class GroupsTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="groups-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir)
        userdb.add_user(self.wiki_dir, "yoshi", userdb.hash_password(self.wiki_dir, "yoshi", "p@ss"), "矢野")
        userdb.add_user(self.wiki_dir, "moe", userdb.hash_password(self.wiki_dir, "moe", "m@ss"), "萌")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def uidnum(self, uid):
        return userdb.find_by_uid(self.wiki_dir, uid)["uidnum"]


class TestCheckGname(unittest.TestCase):
    """グループ名として使える文字（Wiki設計者の指示、2026-09-12。「半角小文字と
    数字、ハイフンとアンダースコアで構成される名称」）。"""

    def ok(self, gname):
        self.assertIsNone(groups.check_gname(gname), f"{gname!r} は通るはず")

    def ng(self, gname):
        self.assertIsNotNone(groups.check_gname(gname), f"{gname!r} は弾くはず")

    def test_小文字数字ハイフンアンダースコアは通る(self):
        for gname in ("team", "team-2", "team_2", "a1-b_2"):
            self.ok(gname)

    def test_空は弾く(self):
        self.ng("")

    def test_大文字は弾く(self):
        self.ng("Team")

    def test_日本語は弾く(self):
        self.ng("チーム")

    def test_空白は弾く(self):
        self.ng("te am")

    def test_記号は弾く(self):
        for gname in ("team!", "team.x", "team/x"):
            self.ng(gname)


class TestCreateGroup(GroupsTestBase):
    """`create_group`。**既にあるグループは作れない**（Wiki設計者の指示）。
    **作成時に作成者をそのグループへ加える**（同）。"""

    def test_作れる(self):
        ok, message = groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))
        self.assertTrue(ok, message)
        self.assertTrue(groups.exists(self.wiki_dir, "team-a"))

    def test_作成者がメンバーに加わる(self):
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))
        self.assertTrue(groups.is_member(self.wiki_dir, "team-a", self.uidnum("yoshi")))

    def test_同じ名前は二度作れない(self):
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))
        ok, message = groups.create_group(self.wiki_dir, "team-a", self.uidnum("moe"))
        self.assertFalse(ok)
        self.assertIn("team-a", message)

    def test_使えない名前では作れない(self):
        ok, message = groups.create_group(self.wiki_dir, "Team!", self.uidnum("yoshi"))
        self.assertFalse(ok)

    def test_存在しないグループはis_memberが偽(self):
        self.assertFalse(groups.is_member(self.wiki_dir, "no-such-group", self.uidnum("yoshi")))

    def test_未ログインNoneはis_memberが偽(self):
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))
        self.assertFalse(groups.is_member(self.wiki_dir, "team-a", None))


class TestMembers(GroupsTestBase):
    """メンバーの追加・削除・一覧（`add_members`/`remove_members`/`members`）。"""

    def setUp(self):
        super().setUp()
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))

    def test_追加できる(self):
        added, failed = groups.add_members(self.wiki_dir, "team-a", ["moe"])
        self.assertEqual([m["uid"] for m in added], ["moe"])
        self.assertEqual(failed, [])
        self.assertTrue(groups.is_member(self.wiki_dir, "team-a", self.uidnum("moe")))

    def test_登録されていないIDは失敗として返る(self):
        added, failed = groups.add_members(self.wiki_dir, "team-a", ["nobody"])
        self.assertEqual(added, [])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0][0], "nobody")

    def test_すでにメンバーなら失敗として返る(self):
        added, failed = groups.add_members(self.wiki_dir, "team-a", ["yoshi"])
        self.assertEqual(added, [])
        self.assertEqual(failed[0][0], "yoshi")

    def test_一部成功一部失敗が混在してもよい(self):
        added, failed = groups.add_members(self.wiki_dir, "team-a", ["moe", "nobody"])
        self.assertEqual([m["uid"] for m in added], ["moe"])
        self.assertEqual(failed[0][0], "nobody")

    def test_一覧に出る(self):
        groups.add_members(self.wiki_dir, "team-a", ["moe"])
        uids = {m["uid"] for m in groups.members(self.wiki_dir, "team-a")}
        self.assertEqual(uids, {"yoshi", "moe"})

    def test_一覧には登録日時が入る(self):
        found = groups.members(self.wiki_dir, "team-a")[0]
        self.assertIn("joined_at", found)
        self.assertIsInstance(found["joined_at"], int)

    def test_削除できる(self):
        groups.add_members(self.wiki_dir, "team-a", ["moe"])
        removed = groups.remove_members(self.wiki_dir, "team-a", [self.uidnum("moe")])
        self.assertEqual(removed, 1)
        self.assertFalse(groups.is_member(self.wiki_dir, "team-a", self.uidnum("moe")))

    def test_全員消えるとグループも無くなる(self):
        removed = groups.remove_members(self.wiki_dir, "team-a", [self.uidnum("yoshi")])
        self.assertEqual(removed, 1)
        self.assertFalse(groups.exists(self.wiki_dir, "team-a"))

    def test_存在しないグループのmembersは空(self):
        self.assertEqual(groups.members(self.wiki_dir, "no-such-group"), [])

    def test_アカウントを消すとグループからも消える(self):
        # 番号は最大値+1で決まるので、消したあと別人に同じ番号が回ると
        # その人が入ってしまう（userdb.delete_userのdocstring参照）
        groups.add_members(self.wiki_dir, "team-a", ["moe"])
        userdb.delete_user(self.wiki_dir, self.uidnum("moe"))
        self.assertEqual([m["uid"] for m in groups.members(self.wiki_dir, "team-a")],
                         ["yoshi"])


class TestStaffGroup(GroupsTestBase):
    """助手グループ（`staff`）の特別扱い（Wiki設計者の指示、2026-09-12）。

    「助手の管理も作成したグループと同様に扱う。助手グループは (staff) と
    し、admin を管理者にしておく。staff が削除された場合は admin のみを
    追加したグループとして再登録。」"""

    def test_事前に作られたstaffは再作成できない(self):
        # staff固有の分岐はcreate_groupに無い。「すでにある名前は作れない」
        # という、他のグループにも効く通常のexists判定がそのまま効く
        groups.ensure_staff_group(self.wiki_dir)
        ok, message = groups.create_group(self.wiki_dir, groups.STAFF_GROUP,
                                          self.uidnum("yoshi"))
        self.assertFalse(ok)
        self.assertIn("すでに存在します", message)

    def test_ensureされていなければ通常のグループとして作れる(self):
        # 「予約名」の特別チェックは無い。事前にensureされていない状態なら、
        # ただのグループ名として通る（Wiki設計者の指示、2026-09-12。事前作成を
        # 保証するのはnewwiki.create_wiki/run_initusersの役目で、
        # create_group自身の責務ではない）
        ok, _message = groups.create_group(self.wiki_dir, groups.STAFF_GROUP,
                                           self.uidnum("yoshi"))
        self.assertTrue(ok)

    def test_ensureでadminだけの状態が作られる(self):
        self.assertFalse(groups.exists(self.wiki_dir, groups.STAFF_GROUP))
        groups.ensure_staff_group(self.wiki_dir)
        uids = {m["uid"] for m in groups.members(self.wiki_dir, groups.STAFF_GROUP)}
        self.assertEqual(uids, {"admin"})

    def test_全員抜けてもadminだけの状態に戻る(self):
        groups.ensure_staff_group(self.wiki_dir)
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["yoshi"])
        groups.remove_members(self.wiki_dir, groups.STAFF_GROUP,
                              [self.uidnum("admin"), self.uidnum("yoshi")])
        uids = {m["uid"] for m in groups.members(self.wiki_dir, groups.STAFF_GROUP)}
        self.assertEqual(uids, {"admin"})

    def test_誰か残っていれば自動では増えない(self):
        # adminを含めず、yoshi・moeの2人だけにしておく
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["yoshi", "moe"])
        groups.remove_members(self.wiki_dir, groups.STAFF_GROUP,
                              [self.uidnum("yoshi")])
        # yoshiを外してもmoeが残っているので、adminの再登録は起きない
        uids = {m["uid"] for m in groups.members(self.wiki_dir, groups.STAFF_GROUP)}
        self.assertEqual(uids, {"moe"})

    def test_is_staffは管理者を助手として扱う(self):
        admin = userdb.get_user(self.wiki_dir, userdb.ADMIN_UIDNUM)
        self.assertTrue(auth.is_staff(self.wiki_dir, admin))

    def test_is_staffはstaffのメンバーも通す(self):
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["yoshi"])
        self.assertTrue(auth.is_staff(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "yoshi")))

    def test_is_staffはただの利用者を通さない(self):
        self.assertFalse(auth.is_staff(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "moe")))
        self.assertFalse(auth.is_staff(self.wiki_dir, None))


class TestExpandPrincipal(GroupsTestBase):
    """プリンシパルの展開（Wiki設計者の指示、2026-09-12。「g:XXXX とは XXXX に
    所属のユーザを展開したものを意味する。この表現は今後も利用するので、
    関数化してユーザ展開ができるように」）。"""

    def test_adminは管理者番号1人(self):
        self.assertEqual(auth.expand_principal(self.wiki_dir, "admin"),
                         {userdb.ADMIN_UIDNUM})

    def test_gコロンはグループのメンバー全員(self):
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))
        groups.add_members(self.wiki_dir, "team-a", ["moe"])
        self.assertEqual(auth.expand_principal(self.wiki_dir, "g:team-a"),
                         {self.uidnum("yoshi"), self.uidnum("moe")})

    def test_gコロンstaffも展開のついでに作ったりしない(self):
        # 「予め作る」のは呼び出し側（`newwiki.create_wiki`・`run_initusers`）の
        # 役目で、展開のついでに保証したりはしない（Wiki設計者の指示、2026-09-13。
        # 同じことをあちこちで確かめる作りをやめ、単純なルールを保つ）
        self.assertFalse(groups.exists(self.wiki_dir, groups.STAFF_GROUP))
        self.assertEqual(auth.expand_principal(self.wiki_dir, f"g:{groups.STAFF_GROUP}"),
                         set())
        groups.ensure_staff_group(self.wiki_dir)
        self.assertEqual(auth.expand_principal(self.wiki_dir, f"g:{groups.STAFF_GROUP}"),
                         {userdb.ADMIN_UIDNUM})

    def test_未知の書きかたは空集合(self):
        self.assertEqual(auth.expand_principal(self.wiki_dir, "yoshi"), set())
        self.assertEqual(auth.expand_principal(self.wiki_dir, ""), set())

    def test_複数のプリンシパルは和集合(self):
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))
        got = auth.expand_principals(self.wiki_dir, ["admin", "g:team-a"])
        self.assertEqual(got, {userdb.ADMIN_UIDNUM, self.uidnum("yoshi")})


class TestCanEdit(GroupsTestBase):
    """グループの編集権（Wiki設計者の指示、2026-09-12。「foo グループの編集権は、
    g:foo, admin, g:staff とする」）。"""

    def setUp(self):
        super().setUp()
        groups.create_group(self.wiki_dir, "team-a", self.uidnum("yoshi"))

    def test_メンバーは編集できる(self):
        self.assertTrue(auth.can_edit_group(self.wiki_dir, "team-a", self.uidnum("yoshi")))

    def test_管理者は自分が入っていなくても編集できる(self):
        self.assertTrue(auth.can_edit_group(self.wiki_dir, "team-a", userdb.ADMIN_UIDNUM))

    def test_助手も自分が入っていなくても編集できる(self):
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["moe"])
        self.assertTrue(auth.can_edit_group(self.wiki_dir, "team-a", self.uidnum("moe")))

    def test_無関係な利用者は編集できない(self):
        userdb.add_user(self.wiki_dir, "carol", userdb.hash_password(self.wiki_dir, "carol", "p"), "キャロル")
        self.assertFalse(auth.can_edit_group(self.wiki_dir, "team-a", self.uidnum("carol")))

    def test_staff自身の編集権はadminとg_staffの合併になる(self):
        self.assertTrue(auth.can_edit_group(self.wiki_dir, groups.STAFF_GROUP, userdb.ADMIN_UIDNUM))
        self.assertFalse(auth.can_edit_group(self.wiki_dir, groups.STAFF_GROUP, self.uidnum("yoshi")))

    def test_未ログインは編集できない(self):
        self.assertFalse(auth.can_edit_group(self.wiki_dir, "team-a", None))


if __name__ == "__main__":
    unittest.main()
