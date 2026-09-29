#!/usr/bin/env python3
"""ページごとのアクセス制限の画面（`/.admin/privileges`。`wikilib.privilegesui`）のテスト。

これまでこの画面自体のテストが無く（記録の読み書きは `test_privilege_records.py` が
見ている）、判定はブラウザでの手作業確認だけに頼っていた。**評価フォーム
（「アクセス権を評価する」。Wiki設計者の指示、2026-09-22）を足すのを機に、画面の
組み立てとAPIの受け口のテストを新設する**。

評価フォームは**ページ名だけを入れる**（2026-09-22、Wiki設計者の指示で「その他の
ユーザ」欄を外した）。登録されている全ユーザ＋未認証、それぞれの判定を表で返す。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_privilegesui.py     （このファイルだけ）
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import auth, groups, privilege_records, privilegesui, userdb  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

FARM = "testwiki"


class PrivilegesUiTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="privilegesui-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid, name in (("alice", "アリス"), ("bob", "")):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), name)
        groups.add_members(self.wiki_dir, "staff", ["alice"])
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        bottle.request.bind({})

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def rule(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)

    def login_cookie(self, uid):
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        return (f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")

    def login_as(self, uid):
        bottle.request.bind({"HTTP_COOKIE": self.login_cookie(uid)} if uid else {})

    def html(self):
        res = privilegesui.render_privileges(self.wiki_dir, {}, FARM, False)
        raw = res.body if hasattr(res, "body") else res
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def api(self, payload, uid="alice"):
        self.login_as(uid)
        data = json.dumps(payload).encode("utf-8")
        bottle.request.bind({
            "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(data)), "wsgi.input": io.BytesIO(data),
            "HTTP_COOKIE": self.login_cookie(uid) if uid else "",
        })
        return privilegesui.render_privileges_api(self.wiki_dir, {}, FARM, False)


class TestScreen(PrivilegesUiTestBase):
    """画面の組み立て（評価フォームまわり）。管理者と助手だけが開ける。"""

    def test_一般のアカウントは断る(self):
        self.login_as("bob")
        res = privilegesui.render_privileges(self.wiki_dir, {}, FARM, False)
        self.assertEqual(res.status_code, 403)

    def test_助手は開ける(self):
        self.login_as("alice")
        res = privilegesui.render_privileges(self.wiki_dir, {}, FARM, False)
        self.assertEqual(res.status_code, 200)

    def test_評価フォームが出る(self):
        self.login_as("alice")
        html = self.html()
        self.assertIn("アクセス権を評価する", html)
        self.assertIn('id="prv-eval-page"', html)
        self.assertIn('id="prv-eval-result"', html)

    def test_ユーザを選ぶ欄は無い(self):
        # 2026-09-22: 「その他のユーザ」欄と、ユーザ選択の欄を外した
        # （未登録のIDは、判定の上ではどれも未認証と同じ答えになるため）
        self.login_as("alice")
        html = self.html()
        self.assertNotIn("prv-eval-who", html)
        self.assertNotIn("prv-eval-other", html)
        self.assertNotIn("その他のユーザ", html)

    def test_テーマを使わない独自のページになっている(self):
        # 2026-09-23: 編集画面・バックアップ管理画面と同じ理由・同じ形にした
        self.login_as("alice")
        html = self.html()
        self.assertTrue(html.lstrip().startswith("<!doctype html>"))
        self.assertIn("<title>アクセス制限", html)
        # テーマ側の画面組み立て（render_theme）が出す目印が無い
        self.assertNotIn("site-header", html)
        self.assertNotIn("site-footer", html)
        self.assertNotIn("page-title", html)
        # 中身（表・評価フォーム）は変わらず出る
        self.assertIn('data-api=', html)
        self.assertIn('id="prv-table"', html)

    def test_断りの画面は管理ページ共通の外枠でテーマは使わない(self):
        # 断りは sysui.require が出す。管理ページ共通の外枠（sysui.page）で、
        # テーマは通さない（Wiki設計者の指示、2026-09-24）
        self.login_as("bob")
        res = privilegesui.render_privileges(self.wiki_dir, {}, FARM, False)
        raw = res.body if hasattr(res, "body") else res
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        self.assertIn('class="sys-body"', html)
        self.assertNotIn("site-header", html)

    def test_書きかたと決まりごとはdetailsで既定は閉じている(self):
        self.login_as("alice")
        html = self.html()
        self.assertIn('<details class="prv-help">', html)
        self.assertIn("書きかたと決まりごと", html)

    def test_評価フォームはdetailsで既定は閉じ_表の下にある(self):
        self.login_as("alice")
        html = self.html()
        self.assertIn('<details class="prv-eval" id="prv-eval">', html)
        # 「開いた状態」の open 属性が付いていない
        self.assertNotIn('<details class="prv-eval" id="prv-eval" open>', html)
        self.assertLess(html.index('id="prv-table"'), html.index('id="prv-eval"'))


class TestEvaluatePageApi(PrivilegesUiTestBase):
    """評価API（`op: "evaluate"`）。ページ名だけを受け取り、未認証・一般の認証済み
    ユーザ＋**このページに直接影響するアカウントだけ**の表を返す（Wiki設計者の
    指示、2026-09-23。「アカウント登録者全員を表示する必要はない、該当ページに
    直接影響するアカウントだけ表示してほしい」）。記録は書き換えない。"""

    def setUp(self):
        super().setUp()
        self.rule("Tech/Secret", "R", "alice,bob")
        self.rule("Tech/Secret", "W", "alice")

    def evaluate(self, page, as_uid="alice"):
        res = self.api({"op": "evaluate", "page": page}, uid=as_uid)
        self.assertEqual(res.status_code, 200)
        raw = res.body if hasattr(res, "body") else res
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    def by_uid(self, got, uid):
        return next(u for u in got["users"] if u["uid"] == uid)

    def test_一般のアカウントは断る(self):
        res = self.api({"op": "evaluate", "page": "Tech/Secret"}, uid="bob")
        self.assertEqual(res.status_code, 403)

    def test_先頭は未認証(self):
        got = self.evaluate("Tech/Secret")
        self.assertEqual(got["users"][0], {
            "uid": "", "label": "未認証", "account": None, "result": "-",
        })

    def test_2番目は一般の認証済みユーザ(self):
        got = self.evaluate("Tech/Secret")
        self.assertEqual(got["users"][1], {
            "uid": "$any", "label": "一般の認証済みユーザ", "account": None, "result": "-",
        })

    def test_直接影響するアカウントだけ出る(self):
        # Tech/Secret は R: alice,bob / W: alice。admin は名指しされていないので出ない
        got = self.evaluate("Tech/Secret")
        uids = [u["uid"] for u in got["users"]]
        # uidnum順。先頭は未認証、2番目は一般の認証済みユーザ
        self.assertEqual(uids, ["", "$any", "alice", "bob"])

    def test_名指しされていないアカウントは出ない(self):
        got = self.evaluate("Tech/Secret")
        self.assertNotIn("admin", [u["uid"] for u in got["users"]])

    def test_規則の無いページは登録アカウントが出ない(self):
        # 未認証・一般の認証済みユーザの2行だけ（誰にも直接は影響しない）
        got = self.evaluate("No/Such/Page")
        self.assertEqual([u["uid"] for u in got["users"]], ["", "$any"])

    def test_g_all_g_anyだけでは実在アカウントは出ない(self):
        # g:all・g:any は「一般の認証済みユーザ」「未認証」の2行でまかなえるので展開しない
        self.rule("Open", "R", "g:any")
        self.rule("Open", "W", "g:all")
        got = self.evaluate("Open")
        self.assertEqual([u["uid"] for u in got["users"]], ["", "$any"])

    def test_カスタムグループのメンバーは出る(self):
        groups.create_group(self.wiki_dir, "editors",
                            userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"])
        groups.add_members(self.wiki_dir, "editors", ["bob"])
        self.rule("Open", "W", "g:editors")
        got = self.evaluate("Open")
        # editors（alice・bob）が出る。admin・「規則に無関係な人」は出ない
        self.assertEqual(sorted(u["uid"] for u in got["users"] if u["uid"] not in ("", "$any")),
                         ["alice", "bob"])

    def test_それぞれの結果(self):
        got = self.evaluate("Tech/Secret")
        self.assertEqual(self.by_uid(got, "alice")["result"], "W")
        self.assertEqual(self.by_uid(got, "bob")["result"], "R")

    def test_一般の認証済みユーザはg_allの行に当たる(self):
        # 未認証とは違い、g:all にも当たる。W は個別指定（alice だけ）なので、
        # 一般の認証済みユーザは読めても書けない
        self.rule("Open", "R", "g:all")
        self.rule("Open", "W", "alice")
        got = self.evaluate("Open")
        self.assertEqual(self.by_uid(got, "$any")["result"], "R")
        self.assertEqual(self.by_uid(got, "")["result"], "-")   # 未認証は g:all に当たらない

    def test_一般の認証済みユーザはカスタムグループには当たらない(self):
        groups.create_group(self.wiki_dir, "editors",
                            userdb.find_by_uid(self.wiki_dir, "alice")["uidnum"])
        self.rule("Tech/Secret", "R", "g:editors")
        got = self.evaluate("Tech/Secret")
        self.assertEqual(self.by_uid(got, "$any")["result"], "-")
        self.assertEqual(self.by_uid(got, "alice")["result"], "W")   # editors のメンバーなので読み書きできる

    def test_アカウントの状態が分かる(self):
        got = self.evaluate("Tech/Secret")
        alice = self.by_uid(got, "alice")
        self.assertEqual(alice["account"]["uid"], "alice")
        self.assertEqual(alice["account"]["name"], "アリス")
        self.assertTrue(alice["account"]["staff"])
        self.assertFalse(alice["account"]["admin"])
        self.assertTrue(alice["account"]["approved"])
        self.assertFalse(alice["account"]["locked"])

    def test_名指しされていればadminでも出る(self):
        # 管理者・助手というだけでは出ないが（判定器はこの2つを特別扱いしない）、
        # 規則に名指しされていれば、admin でも他のアカウントと同じに出る
        self.rule("Open", "R", "admin")
        got = self.evaluate("Open")
        self.assertTrue(self.by_uid(got, "admin")["account"]["admin"])

    def test_名前が無ければ空文字(self):
        got = self.evaluate("Tech/Secret")
        self.assertEqual(self.by_uid(got, "bob")["account"]["name"], "")

    def test_ロック中は未認証と同じ結果になる(self):
        userdb.lock_user(self.wiki_dir, userdb.find_by_uid(self.wiki_dir, "bob")["uidnum"])
        got = self.evaluate("Tech/Secret")
        bob = self.by_uid(got, "bob")
        self.assertTrue(bob["account"]["locked"])
        self.assertEqual(bob["result"], self.by_uid(got, "")["result"])   # R の行に載っていても不許可

    def test_承認待ちは未認証と同じ結果になる(self):
        userdb.add_user(self.wiki_dir, "waiting", userdb.hash_password(self.wiki_dir, "waiting", "p"),
                        "", approved=False)
        self.rule("Tech/Secret", "R", "alice,bob,waiting")   # 名指ししないと表に出ない
        got = self.evaluate("Tech/Secret")
        waiting = self.by_uid(got, "waiting")
        self.assertFalse(waiting["account"]["approved"])
        self.assertEqual(waiting["result"], self.by_uid(got, "")["result"])

    def test_ページの当たった行は誰が見ても同じ(self):
        # rules/who はページだけで決まる（利用者を問わない）ので、表とは別に1回だけ出す
        got = self.evaluate("Tech/Secret")
        self.assertEqual(got["system"]["read"], {"rules": ["Tech/Secret"], "who": ["alice", "bob"]})
        self.assertEqual(got["system"]["write"], {"rules": ["Tech/Secret"], "who": ["alice"]})

    def test_指定の無いページはNone(self):
        got = self.evaluate("No/Such/Page")
        self.assertIsNone(got["system"]["read"])
        self.assertIsNone(got["system"]["write"])
        self.assertIsNone(got["plugin"]["read"])
        self.assertIsNone(got["plugin"]["write"])
        self.assertTrue(all(u["result"] == "W" for u in got["users"]))

    def test_pluginの記録も反映される(self):
        # readauth/writeauth自体は使わず、config/privileges.plugin へ直接1件足す
        path = privilege_records.plugin_path_of(self.wiki_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        entry = {"page": "Open", "kind": "R", "who": ["bob"], "stamp": privilege_records.now_stamp()}
        with open(path, "w", encoding="utf-8") as f:
            f.write(privilege_records.format_line(entry) + "\n")
        got = self.evaluate("Open")
        self.assertEqual(got["plugin"]["read"], {"rules": ["Open"], "who": ["bob"]})
        # bob（plugin側で名指し）は出るが、alice（どちらにも無関係）は出ない
        uids = [u["uid"] for u in got["users"]]
        self.assertIn("bob", uids)
        self.assertNotIn("alice", uids)
        # W の指定は無いので、plugin側でも「読める人は書ける」。bob は読めるので W
        self.assertEqual(self.by_uid(got, "bob")["result"], "W")
        self.assertEqual(self.by_uid(got, "")["result"], "-")   # 未認証は絞られる（緩和されない）

    def test_ページ名の前後のスラッシュは無視する(self):
        got = self.evaluate("/Tech/Secret/")
        self.assertEqual(got["page"], "Tech/Secret")

    def test_記録を書き換えない(self):
        before = privilege_records.load(self.wiki_dir)
        self.evaluate("Tech/Secret")
        self.evaluate("New/Page")
        self.assertEqual(privilege_records.load(self.wiki_dir), before)


if __name__ == "__main__":
    unittest.main()
