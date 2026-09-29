#!/usr/bin/env python3
"""ページごとのアクセス権の判定器（`wikilib.auth` の `page_privilege`）のテスト。

**ここが間違うと、見せてはいけない相手に見せる・書かせてはいけない相手に
書かせる。** 返すのは `"W"`（読み書き）・`"R"`（閲覧だけ）・`"-"`（どちらも
禁止）の3つで、決めかたは `PagePrivilege` のdocstringにある（Wiki設計者が確定、
2026-09-14）。

    R と W を**ページごとに別々に判断**する（Wiki設計者の指示、2026-09-21）。
    「指定がある」とは、そのページに当たる行が1つでもあること（既定の行 `*` も1行）。

        読める  = R の指定が無い、または R の行に載っている
        書ける  = 読める、かつ（W の指定が無い、または W の行に載っている）

    **書けるのは読める人だけ**（R が無ければ W も無い）。指定が無い側は誰にでも許す。
    かつては「W は R を含む」で、R に載っていない人が W の行だけで読み書きできたが、
    R の行を W の天井にした。設定 edit.no_onlooker_permission は削除した。

許可者には `g:all`（登録ユーザ全員。未ログインを含まない）と `g:any`（誰でも。
未ログインを含む）が書ける。記録に持たない特別なグループで、名前でグループを
作ることはできない。

1ページでも複数ページでも、判定器を作ってから聞く（Wiki設計者の指示、2026-09-14）。

    privilege = page_privilege(wiki_dir, uid)
    privilege.check("Tech/Secret")

下ごしらえを済ませた判定器が正しい答えを返すことは、ばらばらに作った規則で
素朴な参照実装と突き合わせて確かめる。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pageprivilege.py     （このファイルだけ）
"""
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import auth, groups, privilege_records, userdb  # noqa: E402
from wikilib.auth import (  # noqa: E402
    PAGE_NONE, PAGE_READ, PAGE_WRITE, PagePrivilege, explain_privilege,
    explain_privilege_generic, page_privilege, page_privilege_rules,
)


class PagePrivilegeTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pageprivilege-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob", "carol"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        groups.create_group(self.wiki_dir, "editors",
                            userdb.find_by_uid(self.wiki_dir, "carol")["uidnum"])

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def rule(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)

    def plugin_rule(self, page, kind, who):
        """`config/privileges.plugin`（`#readauth`・`#writeauth`が書き出す記録）に
        1件足す・上書きする。プラグイン自体は使わず、記録だけを直接作る。"""
        path = privilege_records.plugin_path_of(self.wiki_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        entries = privilege_records.load_plugin(self.wiki_dir)
        entries = [e for e in entries if not (e["page"] == page and e["kind"] == kind)]
        entries.append({"page": page, "kind": kind,
                        "who": [w.strip() for w in who.split(",")],
                        "stamp": privilege_records.now_stamp()})
        text = "".join(privilege_records.format_line(e) + "\n" for e in entries)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def check(self, page, uid, tight=False):
        """規則を足したあとの状態で、判定器を作り直して1ページを聞く。

        `tight` は既定の行（`*:R:g:any`・`*:W:g:all`）を置いた状態で聞く
        （未ログインから編集権限を取り上げる）。"""
        if tight:
            self.rule("*", "R", "g:any")
            self.rule("*", "W", "g:all")
        return page_privilege(self.wiki_dir, uid).check(page)


class TestValues(unittest.TestCase):

    def test_返す値(self):
        self.assertEqual((PAGE_WRITE, PAGE_READ, PAGE_NONE), ("W", "R", "-"))


class TestNoRules(PagePrivilegeTestBase):
    """設定が無いページ。"""

    def test_未ログインも既定では閲覧と編集(self):
        # Wikiを作った直後はアカウントが無く、編集できないと何も始められない
        self.assertEqual(self.check("Tech/Open", None), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Open", ""), PAGE_WRITE)

    def test_既定の行で締めると未ログインは閲覧だけ(self):
        self.assertEqual(self.check("Tech/Open", None, tight=True), PAGE_READ)
        self.assertEqual(self.check("Tech/Open", "", tight=True), PAGE_READ)

    def test_ログイン中は締めても閲覧と編集(self):
        self.assertEqual(self.check("Tech/Open", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Open", "alice", tight=True), PAGE_WRITE)

    def test_記録に無いIDは未ログインと同じ(self):
        self.assertEqual(self.check("Tech/Open", "nobody"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Open", "nobody", tight=True), PAGE_READ)

    def test_ロックされたアカウントは未ログインと同じ(self):
        userdb.lock_user(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"])
        self.assertEqual(self.check("Tech/Open", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Open", "alice", tight=True), PAGE_READ)


class TestReadRule(PagePrivilegeTestBase):
    """R の行だけがあるページ。"""

    def setUp(self):
        super().setUp()
        self.rule("Tech/Secret", "R", "alice")

    def test_載っている人は編集もできる(self):
        # W の指定が無ければ、読める人は書ける（2026-09-21。以前は「R の行だけの
        # ページは誰も編集できない」だったが、指定が無い側は誰にでも許す形に変えた）
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)

    def test_載っていない人は禁止(self):
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)

    def test_未ログインは禁止(self):
        self.assertEqual(self.check("Tech/Secret", None), PAGE_NONE)

    def test_ほかのページには効かない(self):
        self.assertEqual(self.check("Tech/Open", "bob"), PAGE_WRITE)


class TestWriteRule(PagePrivilegeTestBase):
    """W の行があるページ。"""

    def test_Wだけのページは載っていない人も閲覧だけできる(self):
        # R の指定が無いので、読むほうは誰にでも許す。W の行は書く権利だけを絞る
        # （以前は、載っていない人は閲覧もできなかった）
        self.rule("Tech/Wiki", "W", "alice")
        self.assertEqual(self.check("Tech/Wiki", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Wiki", "bob"), PAGE_READ)
        self.assertEqual(self.check("Tech/Wiki", None), PAGE_READ)

    def test_書けるのは読める人だけ(self):
        # R の行で読めない人は、W の行に載っていても何も付かない（R の行が W の天井）。
        # 以前は「W は R を含む」で、bob が読み書きできた
        self.rule("Tech/Secret", "R", "alice")
        self.rule("Tech/Secret", "W", "bob")
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_READ)   # W に載っていない
        self.assertEqual(self.check("Tech/Secret", "carol"), PAGE_NONE)

    def test_Rに載っていてもWに載っていなければ閲覧だけ(self):
        self.rule("Tech/Secret", "R", "alice,bob")
        self.rule("Tech/Secret", "W", "alice")
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_READ)
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "carol"), PAGE_NONE)


class TestGroups(PagePrivilegeTestBase):
    """`g:グループ名` の許可者。"""

    def test_グループのメンバーは当たる(self):
        self.rule("Tech/Secret", "W", "g:editors")
        self.assertEqual(self.check("Tech/Secret", "carol"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_READ)    # 読むだけ

    def test_グループから外すと当たらなくなる(self):
        self.rule("Tech/Secret", "R", "g:editors")
        carol = userdb.find_by_uid(self.wiki_dir, "carol")["uidnum"]
        groups.add_members(self.wiki_dir, "editors", ["alice"])   # 空にしないため
        groups.remove_members(self.wiki_dir, "editors", [carol])
        self.assertEqual(self.check("Tech/Secret", "carol"), PAGE_NONE)


class TestWildcards(PagePrivilegeTestBase):
    """ワイルドカードと、同じ種類の行が複数当たるとき。"""

    def test_前方一致(self):
        self.rule("Tech/*", "R", "alice")
        self.assertEqual(self.check("Tech/Sub/Deep", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Sub/Deep", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Other/Page", "bob"), PAGE_WRITE)

    def test_後方一致(self):
        self.rule("*/Secret", "R", "alice")
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Open", "bob"), PAGE_WRITE)

    def test_星だけならすべてのページ(self):
        self.rule("*", "W", "alice")
        self.assertEqual(self.check("Tech/Any", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("", "bob"), PAGE_READ)
        self.assertEqual(self.check("Tech/Any", None), PAGE_READ)

    def test_完全一致はワイルドカードより優先する(self):
        self.rule("Tech/*", "R", "g:editors")
        self.rule("Tech/Secret", "R", "alice")
        self.assertEqual(self.check("Tech/Secret", "carol"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Other", "carol"), PAGE_WRITE)

    def test_長いワイルドカードが優先する(self):
        self.rule("Tech/*", "R", "alice")
        self.rule("Tech/Sub/*", "R", "bob")
        self.assertEqual(self.check("Tech/Sub/Page", "alice"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Sub/Page", "bob"), PAGE_WRITE)

    def test_同じ具体さなら合わせる(self):
        # Tech/* と *ecret は、どちらも * 以外が5文字（「Tech/」と「ecret」）
        self.rule("Tech/*", "R", "alice")
        self.rule("*ecret", "R", "bob")
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "carol"), PAGE_NONE)

    def test_ページ名の前後のスラッシュは無視する(self):
        self.rule("Tech/Secret", "R", "alice")
        self.assertEqual(self.check("/Tech/Secret/", "bob"), PAGE_NONE)


class TestReadWriteTable(PagePrivilegeTestBase):
    """R の指定と W の指定の組み合わせごとの答え（Wiki設計者の指示、2026-09-21）。

    ページ `P` に、R の行と W の行を（あれば）1つずつ書く。答えは alice・bob・carol・未ログインの順。
    **書けるのは読める人だけ**（R の行が W の天井）。指定が無い側は誰にでも許す。"""

    W, R, N = PAGE_WRITE, PAGE_READ, PAGE_NONE

    #  (R の指定, W の指定): (alice, bob, carol, 未ログイン)
    TABLE = {
        (None, None):                 (W, W, W, W),
        (None, "alice"):              (W, R, R, R),
        (None, "bob"):                (R, W, R, R),
        ("alice", None):              (W, N, N, N),
        ("alice", "alice"):           (W, N, N, N),
        ("alice", "bob"):             (R, N, N, N),     # bob は W に載っていても、読めないので何も付かない
        ("alice,bob", None):          (W, W, N, N),
        ("alice,bob", "alice"):       (W, R, N, N),
        ("alice,bob", "bob"):         (R, W, N, N),
    }

    def test_組み合わせごとの答え(self):
        for (r_who, w_who), want in self.TABLE.items():
            with self.subTest(R=r_who, W=w_who):
                # 行を入れ直す（組み合わせごとに、まっさらな状態から）
                privilege_records.save(self.wiki_dir, [])
                if r_who:
                    self.rule("P", "R", r_who)
                if w_who:
                    self.rule("P", "W", w_who)
                got = tuple(page_privilege(self.wiki_dir, uid).check("P")
                            for uid in ("alice", "bob", "carol", None))
                self.assertEqual(got, want)

    def test_書ける人は必ず読める(self):
        # R が無ければ W も無い。どの組み合わせでも、W の人は R の条件も満たしている
        for (r_who, w_who) in self.TABLE:
            privilege_records.save(self.wiki_dir, [])
            if r_who:
                self.rule("P", "R", r_who)
            if w_who:
                self.rule("P", "W", w_who)
            for uid in ("alice", "bob", "carol", None):
                if page_privilege(self.wiki_dir, uid).check("P") == PAGE_WRITE and r_who:
                    self.assertIn(uid, r_who.split(","), (r_who, w_who, uid))


class TestFolderPage(PagePrivilegeTestBase):
    """`Tech/*` は、フォルダの入口ページ `Tech`（`Tech/index`）にも当たる
    （Wiki設計者の指示、2026-09-21）。`Tech` だけ別に決めたいときは、完全一致の行を書く。"""

    def test_フォルダの指定は入口のページにも効く(self):
        self.rule("Tech/*", "R", "alice")
        self.assertEqual(self.check("Tech", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech", None), PAGE_NONE)
        self.assertEqual(self.check("Tech", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)      # 中のページはこれまでどおり

    def test_別のページには効かない(self):
        self.rule("Tech/*", "R", "alice")
        self.assertEqual(self.check("TechNotes", "bob"), PAGE_WRITE)
        self.assertEqual(self.check("Tec", "bob"), PAGE_WRITE)
        self.assertEqual(self.check("Other", "bob"), PAGE_WRITE)

    def test_深い階層の入口にも効く(self):
        self.rule("Tech/Sub/*", "R", "alice")
        self.assertEqual(self.check("Tech/Sub", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech", "bob"), PAGE_WRITE)            # 親には効かない

    def test_入口だけ許可するには完全一致の行を書く(self):
        # Tech/* を閉じても、Tech だけ開けたい。完全一致はワイルドカードより常に上
        self.rule("Tech/*", "R", "alice")
        self.rule("Tech", "R", "g:any")
        # W の指定は無いので、読める人は書ける。読むだけにしたければ W の行も足す（次のテスト）
        self.assertEqual(self.check("Tech", None), PAGE_WRITE)
        self.assertEqual(self.check("Tech", "bob"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)      # 中は閉じたまま
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)

    def test_入口だけ編集も許可できる(self):
        self.rule("Tech/*", "R", "alice")
        self.rule("Tech", "R", "g:any")
        self.rule("Tech", "W", "g:all")
        self.assertEqual(self.check("Tech", "bob"), PAGE_WRITE)
        self.assertEqual(self.check("Tech", None), PAGE_READ)
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)

    def test_スラッシュの無い前方一致はこれまでどおり(self):
        self.rule("Tech*", "R", "alice")
        self.assertEqual(self.check("Tech", "bob"), PAGE_NONE)
        self.assertEqual(self.check("TechNotes", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)

    def test_フォルダの指定が2つ重なれば長いほうが上(self):
        self.rule("Tech/*", "R", "alice")
        self.rule("Tech/Sub/*", "R", "bob")
        self.assertEqual(self.check("Tech/Sub", "bob"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Sub", "alice"), PAGE_NONE)
        self.assertEqual(self.check("Tech", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech", "bob"), PAGE_NONE)

    def test_既定の行より優先する(self):
        # 入口にも Tech/* の行が当たるので、R はそちら（既定の行 * より具体的）で決まる
        self.rule("*", "R", "g:any")
        self.rule("*", "W", "g:all")
        self.rule("Tech/*", "R", "alice")
        self.assertEqual(self.check("Tech", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech", "alice"), PAGE_WRITE)          # W は既定（g:all）
        self.assertEqual(self.check("Other", "bob"), PAGE_WRITE)


class TestAnyAll(PagePrivilegeTestBase):
    """特別なグループ `g:any`（誰でも）と `g:all`（登録ユーザ全員）。"""

    def test_g_anyは未ログインにも当たる(self):
        self.rule("Tech/Pub", "R", "g:any")
        # 読める。W の指定が無いので、読める人は書ける（読むだけにしたければ W の行も足す）
        for uid in (None, "", "nobody", "alice"):
            self.assertEqual(self.check("Tech/Pub", uid), PAGE_WRITE, uid)
        self.rule("Tech/Pub", "W", "alice")
        for uid in (None, "", "nobody"):
            self.assertEqual(self.check("Tech/Pub", uid), PAGE_READ, uid)

    def test_g_allは登録ユーザだけ(self):
        self.rule("Tech/Members", "W", "g:all")
        self.assertEqual(self.check("Tech/Members", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Members", "carol"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Members", None), PAGE_READ)      # 読むだけ
        self.assertEqual(self.check("Tech/Members", "nobody"), PAGE_READ)

    def test_あとから作ったアカウントも_g_allに入る(self):
        self.rule("Tech/Members", "W", "g:all")
        userdb.add_user(self.wiki_dir, "dave", userdb.hash_password(self.wiki_dir, "dave", "p"), "dave")
        self.assertEqual(self.check("Tech/Members", "dave"), PAGE_WRITE)

    def test_ロックされたアカウントは_g_allに入らない(self):
        self.rule("Tech/Members", "W", "g:all")
        userdb.lock_user(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"])
        self.assertEqual(self.check("Tech/Members", "alice"), PAGE_READ)   # 未ログインと同じ

    def test_グループを作って名乗ることはできない(self):
        # 作れると、g:all と書いた権限が、そのグループのメンバーだけに効いてしまう
        for name in ("all", "any"):
            self.assertIsNotNone(groups.check_gname(name), name)
            ok, _message = groups.create_group(
                self.wiki_dir, name, userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"])
            self.assertFalse(ok, name)

    def test_権限の許可者に書ける(self):
        known = privilege_records.known_principals(self.wiki_dir)
        self.assertIn("g:all", known)
        self.assertIn("g:any", known)
        self.rule("Tech/X", "R", "g:any")           # 書けなければ rule() が失敗する

    def test_展開すると登録ユーザ全員(self):
        everyone = {u["uidnum"] for u in userdb.all_users(self.wiki_dir)}
        self.assertEqual(auth.expand_principal(self.wiki_dir, "g:all"), everyone)
        self.assertEqual(auth.expand_principal(self.wiki_dir, "g:any"), everyone)


class TestDefaultRows(PagePrivilegeTestBase):
    """既定の行（ページ名が `*` だけの行）。**ほかの行が当たらないページの既定**。"""

    def test_既定の行だけなら全ページに効く(self):
        self.rule("*", "R", "g:any")
        self.rule("*", "W", "g:all")
        for page in ("Tech/A", "B", ""):
            self.assertEqual(self.check(page, None), PAGE_READ, page)
            self.assertEqual(self.check(page, "alice"), PAGE_WRITE, page)

    def test_閲覧もログインを求める形(self):
        # 利用形態5: 閲覧にもログインが要る。書けるのは特定のユーザだけ
        self.rule("*", "R", "g:all")
        self.rule("*", "W", "g:editors")
        self.assertEqual(self.check("Tech/A", None), PAGE_NONE)
        self.assertEqual(self.check("Tech/A", "alice"), PAGE_READ)
        self.assertEqual(self.check("Tech/A", "carol"), PAGE_WRITE)

    def test_Wの既定だけなら載っていない人は閲覧だけできる(self):
        # R の指定が無いので、読むほうは誰にでも許す（以前は閲覧もできなかった）
        self.rule("*", "W", "g:all")
        self.assertEqual(self.check("Tech/A", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/A", None), PAGE_READ)

    def test_Rの既定だけなら書くほうは誰にでも許す(self):
        # W の指定が無いので、読める人は書ける（以前は「誰も編集できない」だった）
        self.rule("*", "R", "g:any")
        self.assertEqual(self.check("Tech/A", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/A", None), PAGE_WRITE)

    def test_具体的なRの行は既定のWと合わさって_Rが天井になる(self):
        # Tech/Secret の R は alice だけ（完全一致）。W は既定（g:all）。
        # bob は g:all に入っているが、読めないので書けない（以前の穴: 既定の W が入り込んだ）
        self.rule("*", "R", "g:any")
        self.rule("*", "W", "g:all")
        self.rule("Tech/Secret", "R", "alice")
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Secret", None), PAGE_NONE)
        self.assertEqual(self.check("Tech/Open", "bob"), PAGE_WRITE)     # ほかは既定

    def test_ワイルドカードのWの行は既定のRと合わさる(self):
        # Tech/* の W は g:editors、R は既定（g:any）。editors 以外は読むだけ
        self.rule("*", "R", "g:any")
        self.rule("*", "W", "g:all")
        self.rule("Tech/*", "W", "g:editors")
        self.assertEqual(self.check("Tech/A", "carol"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/A", "bob"), PAGE_READ)
        self.assertEqual(self.check("Tech/A", None), PAGE_READ)
        self.assertEqual(self.check("Other", "bob"), PAGE_WRITE)


class TestCheck(PagePrivilegeTestBase):
    """判定器（`page_privilege`）と `check`。"""

    def test_作る関数はPagePrivilegeを返す(self):
        self.assertIsInstance(page_privilege(self.wiki_dir, "alice"), PagePrivilege)

    def test_複数ページ用のメソッドは無い(self):
        # check を回すだけなので置かない（Wiki設計者の指示、2026-09-14）
        privilege = page_privilege(self.wiki_dir, "alice")
        self.assertFalse(hasattr(privilege, "multi"))
        self.assertFalse(hasattr(privilege, "single"))

    def test_判定器は使い回せる(self):
        self.rule("Tech/Secret", "R", "alice")
        privilege = page_privilege(self.wiki_dir, "alice")
        self.assertEqual(privilege.check("Tech/Secret"), PAGE_WRITE)
        self.assertEqual(privilege.check("Other"), PAGE_WRITE)
        self.assertEqual(privilege.check("Tech/Secret"), PAGE_WRITE)
        bob = page_privilege(self.wiki_dir, "bob")
        self.assertEqual(bob.check("Tech/Secret"), PAGE_NONE)
        self.assertEqual(bob.check("Other"), PAGE_WRITE)

    def test_ばらばらの規則でも参照実装と一致する(self):
        """前方一致・後方一致・完全一致・星が同じ長さでぶつかる形を、乱数で大量に作る。"""
        rnd = random.Random(20260914)
        segs = ["A", "B", "AB", "Sec", "Sub", "x"]
        names = ["alice", "bob", "carol", "g:editors", "g:all", "g:any"]

        def randpage():
            return "/".join(rnd.choice(segs) for _ in range(rnd.randint(1, 3)))

        entries = []
        for _ in range(120):
            base = randpage()
            shape = rnd.random()
            if shape < 0.2:
                page = base + "*"
            elif shape < 0.35:
                page = base + "/*"          # フォルダの指定（入口ページにも当たる）
            elif shape < 0.55:
                page = "*" + base
            elif shape < 0.58:
                page = "*"
            else:
                page = base
            entries.append({"page": page, "kind": rnd.choice("RW"),
                            "who": rnd.sample(names, rnd.randint(1, 2)), "stamp": ""})
        # (ページ名, 種類) は1件だけ、という記録の決まりに合わせる
        seen, rows = set(), []
        for e in entries:
            if (e["page"], e["kind"]) not in seen:
                seen.add((e["page"], e["kind"]))
                rows.append(e)
        privilege_records.save(self.wiki_dir, rows)
        pages = [randpage() for _ in range(400)] + ["", "A", "AB/Sub/x"]

        for uid in ("alice", "bob", "carol", None):
            with self.subTest(uid=uid):
                want = tuple(reference(self.wiki_dir, rows, p, uid) for p in pages)
                privilege = page_privilege(self.wiki_dir, uid)
                self.assertEqual(tuple(privilege.check(p) for p in pages), want)


def reference(wiki_dir, rows, page, uid):
    """確定した決めかたをそのまま書いた、遅いが素直な参照実装。

    R と W を別々に、いちばん具体的な行で判断し（既定の行 `*` はいちばん下）、
    書けるのは読める人だけにする（2026-09-21）。"""
    page = page.strip("/")
    user = userdb.find_by_uid(wiki_dir, uid) if uid else None

    def spec(rule):
        return (0, len(rule) - 1) if "*" in rule else (1, len(rule))

    def listed(who):
        for w in who:
            if w == "g:any":
                return True
            if user is None:
                continue
            if w == "g:all":
                return True
            if w.startswith("g:"):
                if groups.is_member(wiki_dir, w[2:], user["uidnum"]):
                    return True
            elif w == user["uid"]:
                return True
        return False

    def best(kind):
        hits = [r for r in rows if r["kind"] == kind and privilege_records.matches(r["page"], page)]
        if not hits:
            return None                                   # 指定が無い
        top = max(spec(r["page"]) for r in hits)
        return [w for r in hits if spec(r["page"]) == top for w in r["who"]]

    readers, writers = best("R"), best("W")
    can_read = readers is None or listed(readers)
    can_write = can_read and (writers is None or listed(writers))
    return PAGE_WRITE if can_write else (PAGE_READ if can_read else PAGE_NONE)


class TestExplainPrivilege(PagePrivilegeTestBase):
    """`explain_privilege`。`page_privilege(...).check(...)` と同じ答えを、当たった行つきで返す
    （`/.admin/privileges` の「アクセス権を評価する」向け。Wiki設計者の指示、2026-09-22）。

    system（`config/privileges`）・plugin（`config/privileges.plugin`）を別々に
    判定し、`system`/`plugin` キーに分けて返す（2026-09-23。`plugin_rule` は
    `PagePrivilegeTestBase` で、プラグイン自体は使わず記録だけを直接作る）。"""

    def explain(self, page, uid):
        return explain_privilege(self.wiki_dir, uid, page)

    def test_指定が無ければreadもwriteもNone(self):
        got = self.explain("Open", "alice")
        self.assertEqual(got["result"], PAGE_WRITE)
        self.assertIsNone(got["system"]["read"])
        self.assertIsNone(got["system"]["write"])
        self.assertIsNone(got["plugin"]["read"])
        self.assertIsNone(got["plugin"]["write"])
        self.assertTrue(got["logged_in"])

    def test_未ログインはlogged_inがFalse(self):
        self.assertFalse(self.explain("Open", None)["logged_in"])
        self.assertFalse(self.explain("Open", "")["logged_in"])

    def test_記録に無いIDやロック中も未ログインと同じ扱い(self):
        self.assertFalse(self.explain("Open", "nobody")["logged_in"])
        userdb.lock_user(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"])
        self.assertFalse(self.explain("Open", "alice")["logged_in"])

    def test_当たった行と許可者が分かる(self):
        self.rule("Tech/Secret", "R", "alice,bob")
        self.rule("Tech/Secret", "W", "alice")
        got = self.explain("Tech/Secret", "bob")
        self.assertEqual(got["result"], PAGE_READ)
        self.assertEqual(got["system"]["read"], {
            "rules": ["Tech/Secret"], "who": ["alice", "bob"],
            "listed": True, "matched_by": ["bob"],
        })
        self.assertEqual(got["system"]["write"], {
            "rules": ["Tech/Secret"], "who": ["alice"],
            "listed": False, "matched_by": [],
        })

    def test_グループで当たったときはグループ名が出る(self):
        self.rule("Tech/Secret", "W", "g:editors")
        got = self.explain("Tech/Secret", "carol")
        self.assertEqual(got["system"]["write"]["matched_by"], ["g:editors"])

    def test_g_anyで当たる(self):
        self.rule("Tech/Pub", "R", "g:any")
        got = self.explain("Tech/Pub", None)
        self.assertEqual(got["system"]["read"]["matched_by"], ["g:any"])
        self.assertTrue(got["system"]["read"]["listed"])

    def test_同じ具体さで複数当たれば両方出る(self):
        self.rule("Tech/*", "R", "alice")
        self.rule("*ecret", "R", "bob")
        got = self.explain("Tech/Secret", "alice")
        self.assertEqual(got["system"]["read"]["rules"], ["*ecret", "Tech/*"])

    def test_既定の行も指定ありとして扱う(self):
        self.rule("*", "R", "g:any")
        self.rule("*", "W", "g:all")
        got = self.explain("Tech/A", "alice")
        self.assertEqual(got["system"]["read"]["rules"], ["*"])
        self.assertEqual(got["system"]["write"]["rules"], ["*"])
        self.assertEqual(got["result"], PAGE_WRITE)

    def test_フォルダの入口にも当たる(self):
        self.rule("Tech/*", "R", "alice")
        got = self.explain("Tech", "alice")
        self.assertEqual(got["system"]["read"]["rules"], ["Tech/*"])
        self.assertTrue(got["system"]["read"]["listed"])

    def test_page_privilegeのcheckと同じ答えになる(self):
        rnd = random.Random(2026)
        for page, kind, who in (
            ("Tech/Secret", "R", "alice"), ("Tech/Secret", "W", "bob"),
            ("Tech/*", "W", "g:editors"), ("*", "R", "g:any"),
        ):
            self.rule(page, kind, who)
        for uid in ("alice", "bob", "carol", None):
            privilege = page_privilege(self.wiki_dir, uid)
            for _ in range(30):
                page = "/".join(rnd.choice(["A", "B", "Sec", "Sub"])
                                for _ in range(rnd.randint(1, 2)))
                self.assertEqual(self.explain(page, uid)["result"], privilege.check(page),
                                 (uid, page))

    def test_pluginの記録も出る(self):
        # plugin_rule はプラグイン自体を使わず、config/privileges.plugin へ
        # 直接1件足すテストヘルパー（PagePrivilegeTestBase）
        self.plugin_rule("Tech/Secret", "R", "alice")
        got = self.explain("Tech/Secret", "bob")
        self.assertEqual(got["result"], PAGE_NONE)
        self.assertEqual(got["plugin"]["read"], {
            "rules": ["Tech/Secret"], "who": ["alice"],
            "listed": False, "matched_by": [],
        })
        self.assertIsNone(got["plugin"]["write"])

    def test_pluginが緩めてもsystemの答えのまま(self):
        self.rule("Tech/Secret", "R", "alice")
        self.plugin_rule("Tech/Secret", "R", "g:any")
        got = self.explain("Tech/Secret", "bob")
        self.assertEqual(got["system"]["result"], PAGE_NONE)
        self.assertEqual(got["plugin"]["result"], PAGE_WRITE)
        self.assertEqual(got["result"], PAGE_NONE)   # 厳しいほう（system）が勝つ


class TestExplainPrivilegeGeneric(PagePrivilegeTestBase):
    """`explain_privilege_generic`。「特別な立場を持たない、ふつうの認証済みユーザ」の判定
    （`/.admin/privileges` の「一般の認証済みユーザ」向け。Wiki設計者の指摘、2026-09-23。
    「一般の認証済みユーザへの権限が現れない」）。"""

    def generic(self, page):
        return explain_privilege_generic(self.wiki_dir, page)

    def test_指定が無ければ誰でも読み書きできる(self):
        self.assertEqual(self.generic("Open")["result"], PAGE_WRITE)

    def test_常にログイン中(self):
        self.assertTrue(self.generic("Open")["logged_in"])

    def test_g_allの行に当たる(self):
        # 未認証との違い。g:all は登録ユーザ全員が対象で、ここは「ログインはしている」
        # という立場なので当たる。W はまだ指定していないので、read が listed なら
        # 誰にでも書けてしまう（下の test で確かめる）——ここは read だけを見る
        self.rule("Open", "R", "g:all")
        got = self.generic("Open")
        self.assertEqual(got["system"]["read"]["listed"], True)
        self.assertEqual(got["system"]["read"]["matched_by"], ["g:all"])
        self.assertEqual(got["result"], PAGE_WRITE)   # W 未指定なので、読める人は書ける

    def test_g_allは読めてもWが個別指定なら書けない(self):
        self.rule("Open", "R", "g:all")
        self.rule("Open", "W", "alice")   # alice だけ。一般の認証済みユーザは当たらない
        self.assertEqual(self.generic("Open")["result"], PAGE_READ)

    def test_g_anyの行にも当たる(self):
        self.rule("Open", "R", "g:any")
        self.rule("Open", "W", "alice")
        self.assertEqual(self.generic("Open")["result"], PAGE_READ)

    def test_個別に名指しされた許可者には当たらない(self):
        self.rule("Tech/Secret", "R", "alice,bob")
        self.assertEqual(self.generic("Tech/Secret")["result"], PAGE_NONE)

    def test_カスタムグループには当たらない(self):
        self.rule("Tech/Secret", "R", "g:editors")
        self.assertEqual(self.generic("Tech/Secret")["result"], PAGE_NONE)

    def test_未認証と結果が違うことがある(self):
        from wikilib.auth import explain_privilege as ep
        self.rule("Open", "R", "g:all")
        self.rule("Open", "W", "alice")
        self.assertEqual(self.generic("Open")["result"], PAGE_READ)
        self.assertEqual(ep(self.wiki_dir, None, "Open")["result"], PAGE_NONE)

    def test_rowsを渡すと読み直さない(self):
        self.rule("Open", "R", "g:all")
        self.rule("Open", "W", "alice")
        rows = privilege_records.load(self.wiki_dir)
        # rows を渡したあとに記録を変えても、その rows での判定には反映されない
        privilege_records.save(self.wiki_dir, [])
        self.assertEqual(
            explain_privilege_generic(self.wiki_dir, "Open", rows=rows)["result"], PAGE_READ)
        # rows を渡さなければ、最新（空になった記録）を読む
        self.assertEqual(self.generic("Open")["result"], PAGE_WRITE)


class TestPagePrivilegeRules(PagePrivilegeTestBase):
    """`page_privilege_rules`。ページだけで決まる「当たった行」（誰が見るかには関係ない）。"""

    def test_指定が無ければ両方None(self):
        got = page_privilege_rules(self.wiki_dir, "Open")
        self.assertEqual(got, {"read": None, "write": None})

    def test_rules_whoはexplain_privilegeと同じ(self):
        self.rule("Tech/Secret", "R", "alice,bob")
        self.rule("Tech/Secret", "W", "alice")
        got = page_privilege_rules(self.wiki_dir, "Tech/Secret")
        self.assertEqual(got["read"], {"rules": ["Tech/Secret"], "who": ["alice", "bob"]})
        self.assertEqual(got["write"], {"rules": ["Tech/Secret"], "who": ["alice"]})
        # explain_privilege 側（system）も、"listed"/"matched_by" を除けば同じ
        ex = explain_privilege(self.wiki_dir, "carol", "Tech/Secret")
        self.assertEqual(
            {k: v for k, v in ex["system"]["read"].items() if k in ("rules", "who")}, got["read"])

    def test_誰で聞いても同じ答え(self):
        # ページだけで決まるので、uid という引数自体を持たない
        self.rule("Tech/*", "W", "g:editors")
        got = page_privilege_rules(self.wiki_dir, "Tech/A")
        self.assertEqual(got["write"]["rules"], ["Tech/*"])

    def test_rowsを渡すと読み直さない(self):
        self.rule("Tech/Secret", "R", "alice")
        rows = privilege_records.load(self.wiki_dir)
        # 渡した rows のあとに記録を変えても、rows 引数を渡した呼び出しには反映されない
        self.rule("Tech/Secret", "R", "alice,bob")
        got = page_privilege_rules(self.wiki_dir, "Tech/Secret", rows=rows)
        self.assertEqual(got["read"]["who"], ["alice"])
        # rows を渡さなければ、最新の記録を読む
        fresh = page_privilege_rules(self.wiki_dir, "Tech/Secret")
        self.assertEqual(fresh["read"]["who"], ["alice", "bob"])

    def test_explain_privilegeもrowsを受け取れる(self):
        self.rule("Tech/Secret", "R", "alice")
        rows = privilege_records.load(self.wiki_dir)
        self.rule("Tech/Secret", "R", "alice,bob")
        got = explain_privilege(self.wiki_dir, "bob", "Tech/Secret", rows=rows)
        self.assertEqual(got["result"], PAGE_NONE)   # 渡した rows の時点ではまだ bob は載っていない


class TestPluginRecords(PagePrivilegeTestBase):
    """`config/privileges.plugin`（`#readauth`・`#writeauth`が描画のときに書き出す
    記録）との優先順位（Wiki設計者の指示、2026-09-23）。

    プラグインは `config/privileges`（system）より優先されるが、**緩和する方向
    には働かない**。実装は system・plugin をそれぞれ独立に判定し、厳しいほうを
    答えにする（`PagePrivilege.check`）。プラグイン自体は使わず、`plugin_rule`
    （`PagePrivilegeTestBase`）で記録だけを直接作る。"""

    def test_プラグインの記録が無ければsystemの答えのまま(self):
        self.rule("Tech/Open", "R", "alice")
        self.assertEqual(self.check("Tech/Open", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Open", "bob"), PAGE_NONE)

    def test_プラグインが絞ればsystemより優先する(self):
        # system は規則なし（誰でも W）。プラグインが読める人を alice だけに絞る
        self.plugin_rule("Tech/Secret", "R", "alice")
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Secret", None), PAGE_NONE)

    def test_プラグインが緩めても効かない(self):
        # system は alice だけが読める。プラグイン（#readauth の空呼びと逆に、
        # g:any へ緩める想定）があっても、system の制限は緩まない
        self.rule("Tech/Secret", "R", "alice")
        self.plugin_rule("Tech/Secret", "R", "g:any")
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)

    def test_writeauth相当_書く権限だけプラグインで絞る(self):
        self.plugin_rule("Tech/Wiki", "W", "alice")
        self.assertEqual(self.check("Tech/Wiki", "alice"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Wiki", "bob"), PAGE_READ)
        self.assertEqual(self.check("Tech/Wiki", None), PAGE_READ)

    def test_プラグインのRがsystemのWより優先する(self):
        self.plugin_rule("Tech/Secret", "R", "bob")
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_WRITE)
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_NONE)

    def test_systemで読めなければプラグインのWだけでは書けない(self):
        # system: R は alice だけ。plugin: W は bob。bob は system の R に
        # 載っていないので、plugin の W があっても読めも書けもしない
        self.rule("Tech/Secret", "R", "alice")
        self.plugin_rule("Tech/Secret", "W", "bob")
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_READ)   # W の指定は alice に無い

    def test_両方に規則があれば厳しいほうが勝つ(self):
        self.rule("Tech/Secret", "R", "alice,bob")
        self.plugin_rule("Tech/Secret", "R", "alice,carol")
        self.assertEqual(self.check("Tech/Secret", "alice"), PAGE_WRITE)   # 両方で読める
        self.assertEqual(self.check("Tech/Secret", "bob"), PAGE_NONE)      # system OK・plugin NG
        self.assertEqual(self.check("Tech/Secret", "carol"), PAGE_NONE)    # system NG・plugin OK


if __name__ == "__main__":
    unittest.main()
