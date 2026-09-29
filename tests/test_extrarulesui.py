#!/usr/bin/env python3
"""定義ルール（COLOR()/フェイスマーク等）を設定画面から編集するところのテスト。

見ているのは次のこと。

  印           付けると共通の定義をコピー、外すと捨てて共通へ（外すときは必ず控える）
  1件ずつの編集 追加・直す・削除・並べ替え。**番号と直す前の中身を照合し、食い違えば断る**
  保存させないもの 壊れた正規表現・空に当たるパターン・足りないグループ参照
  試験欄       当たり箇所と描画結果が返る。**重い正規表現は時間で切る**
  権限         管理者と助手だけ

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_extrarulesui.py     （このファイルだけ）
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

from wikilib import auth, configui, extrarulesui, userdb  # noqa: E402
from wikilib.extrarules import load_extra_rules  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402
from wikilib.wikiconfig import config_backups, written_by_system  # noqa: E402


class Base(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="extrarulesui-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        self.path = extrarulesui.own_path(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def own(self):
        ok, _message = extrarulesui.apply_op(self.wiki_dir, {"op": "own", "on": True})
        self.assertTrue(ok)

    def rows(self, kind="line_rules"):
        return extrarulesui.entries_of(extrarulesui.effective_data(self.wiki_dir), kind)

    def old(self, kind, index):
        p, r = self.rows(kind)[index]
        return {"kind": kind, "index": index, "old_pattern": p, "old_replace": r}


class TestOwn(Base):

    def test_印が無ければ共通の定義が効く(self):
        self.assertFalse(extrarulesui.has_own(self.wiki_dir))
        self.assertGreater(len(self.rows()), 0)
        self.assertGreater(len(self.rows("facemark_rules")), 0)

    def test_印を付けると共通のコピーができる(self):
        common = list(self.rows())
        self.own()
        self.assertTrue(os.path.isfile(self.path))
        self.assertEqual(self.rows(), common)
        self.assertTrue(written_by_system(self.path))

    def test_印を付けても効くルールは共通と同じ(self):
        before = load_extra_rules({}, self.wiki_dir).rules
        self.own()
        after = load_extra_rules({}, self.wiki_dir).rules
        self.assertEqual([(c.pattern, r) for c, r in before],
                         [(c.pattern, r) for c, r in after])

    def test_印を外すと捨てて共通へ戻り_必ず控える(self):
        self.own()
        extrarulesui.apply_op(self.wiki_dir, {"op": "add", "kind": "line_rules",
                                              "pattern": "XX", "replace": "<i>x</i>"})
        # 画面が書いたままのファイルでも、捨てる前には控える
        self.assertTrue(written_by_system(self.path))
        ok, _m = extrarulesui.apply_op(self.wiki_dir, {"op": "own", "on": False})
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(self.path))
        backups = config_backups(self.path)
        self.assertEqual(len(backups), 1)
        with open(backups[0], encoding="utf-8") as f:
            self.assertIn("XX", f.read())
        self.assertNotIn("XX", [p for p, _r in self.rows()])

    def test_印が無いときの編集は断る(self):
        ok, message = extrarulesui.apply_op(self.wiki_dir, {
            "op": "add", "kind": "line_rules", "pattern": "a", "replace": "b"})
        self.assertFalse(ok)
        self.assertIn("印", message)
        self.assertFalse(os.path.exists(self.path))


class TestEdit(Base):

    def setUp(self):
        super().setUp()
        self.own()

    def test_追加すると末尾に入り_描画にも効く(self):
        n = len(self.rows())
        ok, _m = extrarulesui.apply_op(self.wiki_dir, {
            "op": "add", "kind": "line_rules",
            "pattern": r"HELLO\((\w+)\)", "replace": r"<b>\1</b>"})
        self.assertTrue(ok)
        self.assertEqual(len(self.rows()), n + 1)
        self.assertEqual(self.rows()[-1], (r"HELLO\((\w+)\)", r"<b>\1</b>"))
        rules = load_extra_rules({}, self.wiki_dir)
        self.assertTrue(any(c.pattern == r"HELLO\((\w+)\)" for c, _r in rules.rules))

    def test_直す(self):
        body = dict(self.old("line_rules", 0), op="set",
                    pattern="ZZZ", replace="<u>z</u>")
        ok, _m = extrarulesui.apply_op(self.wiki_dir, body)
        self.assertTrue(ok)
        self.assertEqual(self.rows()[0], ("ZZZ", "<u>z</u>"))

    def test_削除(self):
        n = len(self.rows())
        second = self.rows()[1]
        ok, _m = extrarulesui.apply_op(self.wiki_dir, dict(self.old("line_rules", 0), op="del"))
        self.assertTrue(ok)
        self.assertEqual(len(self.rows()), n - 1)
        self.assertEqual(self.rows()[0], second)

    def test_並べ替え(self):
        a, b = self.rows()[0], self.rows()[1]
        ok, _m = extrarulesui.apply_op(self.wiki_dir, dict(
            self.old("line_rules", 1), op="move", direction="up"))
        self.assertTrue(ok)
        self.assertEqual(self.rows()[:2], [b, a])

    def test_端では動かせない(self):
        ok, message = extrarulesui.apply_op(self.wiki_dir, dict(
            self.old("line_rules", 0), op="move", direction="up"))
        self.assertFalse(ok)
        self.assertIn("動かせません", message)

    def test_直す前の中身が食い違えば断る(self):
        """先に誰かが並びを変えたあと、古い画面から別の行を直さないため。"""
        body = dict(self.old("line_rules", 0), op="del")
        # 別の画面が先に0番目を消した
        extrarulesui.apply_op(self.wiki_dir, dict(self.old("line_rules", 0), op="del"))
        before = list(self.rows())
        ok, message = extrarulesui.apply_op(self.wiki_dir, body)
        self.assertFalse(ok)
        self.assertIn("先に書き換え", message)
        self.assertEqual(self.rows(), before)

    def test_範囲外の行は断る(self):
        ok, _m = extrarulesui.apply_op(self.wiki_dir, {
            "op": "del", "kind": "line_rules", "index": 999,
            "old_pattern": "", "old_replace": ""})
        self.assertFalse(ok)

    def test_フェイスマークの一覧も同じように編集できる(self):
        ok, _m = extrarulesui.apply_op(self.wiki_dir, {
            "op": "add", "kind": "facemark_rules", "pattern": "&yay;", "replace": "🎉"})
        self.assertTrue(ok)
        self.assertEqual(self.rows("facemark_rules")[-1], ("&yay;", "🎉"))

    def test_知らない種類や操作は断る(self):
        self.assertFalse(extrarulesui.apply_op(
            self.wiki_dir, {"op": "add", "kind": "nope", "pattern": "a", "replace": "b"})[0])
        self.assertFalse(extrarulesui.apply_op(
            self.wiki_dir, {"op": "zzz", "kind": "line_rules"})[0])


class TestValidation(Base):

    def setUp(self):
        super().setUp()
        self.own()

    def refuse(self, pattern, replace, needle):
        n = len(self.rows())
        ok, message = extrarulesui.apply_op(self.wiki_dir, {
            "op": "add", "kind": "line_rules", "pattern": pattern, "replace": replace})
        self.assertFalse(ok)
        self.assertIn(needle, message)
        self.assertEqual(len(self.rows()), n)       # 書かれていない

    def test_壊れた正規表現(self):
        self.refuse("(abc", "x", "正規表現")

    def test_空のパターン(self):
        self.refuse("", "x", "空")

    def test_空の文字列に当たるパターン(self):
        self.refuse("a*", "x", "空の文字列")
        self.refuse("(?:foo)?", "x", "空の文字列")

    def test_足りないグループ参照(self):
        self.refuse(r"(a)", r"<i>\2</i>", "\\2")

    def test_グループ参照が合っていれば通る(self):
        ok, _m = extrarulesui.apply_op(self.wiki_dir, {
            "op": "add", "kind": "line_rules", "pattern": r"(a)(b)", "replace": r"\2\1"})
        self.assertTrue(ok)

    def test_置換文字列が空でもよい(self):
        ok, _m = extrarulesui.apply_op(self.wiki_dir, {
            "op": "add", "kind": "line_rules", "pattern": "ZAP", "replace": ""})
        self.assertTrue(ok)


class TestProbe(Base):

    def test_当たり箇所が返る(self):
        found, problem = extrarulesui.probe_rules(
            [(r"a(b)", ""), (r"zzz", "")], "xab ab")
        self.assertEqual(problem, "")
        self.assertEqual([h["text"] for h in found[0]["hits"]], ["ab", "ab"])
        self.assertEqual(found[0]["hits"][0]["groups"], ["b"])
        self.assertEqual(found[1]["hits"], [])

    def test_壊れた正規表現はその1件だけエラー(self):
        found, _p = extrarulesui.probe_rules([("(", ""), ("a", "")], "a")
        self.assertIn("error", found[0])
        self.assertEqual(len(found[1]["hits"]), 1)

    def test_日本語も往復できる(self):
        found, _p = extrarulesui.probe_rules([("強(調)", "")], "これは強調です")
        self.assertEqual(found[0]["hits"][0]["text"], "強調")

    def test_重い正規表現は時間で切る(self):
        found, problem = extrarulesui.probe_rules(
            [(r"(a+)+$", "")], "a" * 40 + "b", seconds=1)
        self.assertIsNone(found)
        self.assertIn("1秒", problem)


class TestRun(Base):

    def run_test(self, text, draft=None):
        body = {"text": text}
        if draft:
            body["draft"] = draft
        return extrarulesui.run_test(self.wiki_dir, {}, "testwiki", False, body)

    def test_描画結果と当たり箇所(self):
        out = self.run_test("COLOR(red):''x''")
        self.assertTrue(out["ok"])
        self.assertIn("&lt;span style=&quot;color:red&quot;&gt;", out["result"])
        self.assertIn("COLOR(red)", out["result"])          # 当たり箇所
        self.assertIn("ユーザ定義ルール 2", out["result"])   # どの規則かが分かる

    def test_下書きも掛かる(self):
        out = self.run_test("WOW(hi)", draft={
            "kind": "line_rules", "pattern": r"WOW\((\w+)\)", "replace": r"<i>\1</i>"})
        self.assertTrue(out["ok"])
        self.assertIn("&lt;i&gt;hi&lt;/i&gt;", out["result"])
        self.assertIn("下書き", out["result"])

    def test_下書きが壊れていれば断る(self):
        out = self.run_test("x", draft={"kind": "line_rules", "pattern": "(", "replace": ""})
        self.assertFalse(out["ok"])
        self.assertIn("下書き", out["message"])

    def test_捕捉した部分の生HTMLは文字になる(self):
        out = self.run_test("COLOR(red){<script>x</script>}")
        self.assertTrue(out["ok"])
        # 結果はさらにエスケープして画面に出るので、生のタグは1つも残らない
        self.assertNotIn("<script>", out["result"])
        # 描画側（iframe の srcdoc）にも、文字として入っている
        self.assertIn("&amp;lt;script&amp;gt;", out["result"])

    def test_facemarkを切っていれば試験にも使わない(self):
        on = extrarulesui.run_test(self.wiki_dir, {}, "testwiki", False, {"text": "&smile;"})
        off = extrarulesui.run_test(
            self.wiki_dir, {"pukiwiki": {"facemark": False}}, "testwiki", False,
            {"text": "&smile;"})
        self.assertIn("😊", on["result"])
        self.assertNotIn("😊", off["result"])


class TestApi(Base):
    """窓口。**権限は管理者と助手だけ。** 断りもJSONで返す。"""

    def setUp(self):
        super().setUp()
        userdb.create_db(self.wiki_dir)
        self.kept_secret = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret
        super().tearDown()

    def call(self, payload, uid="admin"):
        body = json.dumps(payload).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)})
        if uid is not None:
            user = userdb.find_by_uid(self.wiki_dir, uid)
            token = auth.session_token(uid, "testwiki", user["pw"])
            bottle.request.environ["HTTP_COOKIE"] = (
                f"{wiki_cookie_name(LOGIN_COOKIE, 'testwiki')}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, 'testwiki')}={token}")
        out = configui.render_configwiki_api(self.wiki_dir, {}, "testwiki", False)
        raw = out.body
        return out, json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    def test_未ログインは403で何も書かれない(self):
        out, got = self.call({"op": "rx_own", "on": True}, uid=None)
        self.assertEqual(out.status_code, 403)
        self.assertFalse(got["ok"])
        self.assertFalse(os.path.exists(self.path))

    def test_管理者は印を付けて編集でき_作り直した一覧が返る(self):
        out, got = self.call({"op": "rx_own", "on": True})
        self.assertTrue(got["ok"])
        self.assertIn('data-role="own"', got["body"])
        out, got = self.call({"op": "rx_add", "kind": "line_rules",
                              "pattern": "QQQ", "replace": "<q>"})
        self.assertTrue(got["ok"])
        self.assertIn('value="QQQ"', got["body"])

    def test_断りは400(self):
        self.call({"op": "rx_own", "on": True})
        out, got = self.call({"op": "rx_add", "kind": "line_rules",
                              "pattern": "(", "replace": ""})
        self.assertEqual(out.status_code, 400)
        self.assertFalse(got["ok"])

    def test_試験の窓口(self):
        out, got = self.call({"op": "rx_test", "text": "BOLD{x}"})
        self.assertTrue(got["ok"])
        self.assertIn("wcfg-rx-out", got["result"])

    def test_画面にタブが出る(self):
        html = configui._tabs_html("extrarules")
        self.assertIn('data-tab="extrarules"', html)
        self.assertIn("定義ルール", html)


if __name__ == "__main__":
    unittest.main()
