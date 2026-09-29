#!/usr/bin/env python3
"""アカウントの受け入れかた（設定 `account.policy`）のテスト。

**見ているのは、設定として持てること・画面から書き換えられること・
書き損じで今の動きに戻ること**。この値を読んだ動き（「アカウント作成」が承認待ちで
始まること、承認する画面）は `tests/test_approval.py` が見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_accountpolicy.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

from wikilib import configui, paths, userdb, wikiconfig  # noqa: E402


class TestAccountPolicy(unittest.TestCase):
    """設定を読むところ。"""

    def config(self, value):
        return {"account": {"policy": value}}

    def test_既定は_open(self):
        self.assertEqual(wikiconfig.account_policy({}), "open")
        self.assertEqual(wikiconfig.account_policy(None), "open")
        self.assertEqual(wikiconfig.account_policy({"account": None}), "open")
        self.assertEqual(wikiconfig.account_policy({"account": {}}), "open")

    def test_2つの値を読める(self):
        for value in ("open", "approval"):
            self.assertEqual(wikiconfig.account_policy(self.config(value)), value)

    def test_大文字と前後の空白は許す(self):
        self.assertEqual(wikiconfig.account_policy(self.config(" Approval ")), "approval")

    def test_書き損じは_open_に戻す(self):
        # 締めるつもりで書き損じると開いてしまうが、既存のWikiの動きを
        # 変えないことを優先している（他の設定と同じ考えかた）。
        # closed は2026-09-21に外した値なので、これも open に戻る
        for value in ("closed", "invite", "", "true", 1, True, None, ["approval"]):
            self.assertEqual(wikiconfig.account_policy(self.config(value)), "open",
                             repr(value))

    def test_値の並びは緩い順(self):
        self.assertEqual(wikiconfig.ACCOUNT_POLICIES, ("open", "approval"))
        self.assertEqual(wikiconfig.DEFAULT_ACCOUNT_POLICY, "open")

    def test_雛形には_open_で入っている(self):
        example = wikiconfig.read_yaml(wikiconfig.example_of(paths.CONFIG_PATH))
        self.assertEqual(example["account"]["policy"], "open")

    def test_共通の設定を読むと_open(self):
        self.assertEqual(wikiconfig.account_policy(wikiconfig.load_config()), "open")


class TestPwSalt(unittest.TestCase):
    """パスワードの塩（設定 `account.pw_salt`。空ならWiki名）。"""

    def salt(self, config, name="wikiA"):
        return wikiconfig.account_pw_salt(config, name)

    def test_書かなければWiki名(self):
        for config in ({}, None, {"account": None}, {"account": {}},
                       {"account": {"pw_salt": ""}}, {"account": {"pw_salt": "  "}}):
            self.assertEqual(self.salt(config), "wikiA", config)

    def test_書けばそれを使う(self):
        self.assertEqual(self.salt({"account": {"pw_salt": " abc "}}), "abc")

    def test_数も文字列として使う(self):
        self.assertEqual(self.salt({"account": {"pw_salt": 123}}), "123")

    def test_真偽値や配列は使わずWiki名に戻る(self):
        for value in (True, False, ["x"], {"a": 1}, None):
            self.assertEqual(self.salt({"account": {"pw_salt": value}}), "wikiA", value)

    def test_雛形には空で入っている(self):
        example = wikiconfig.read_yaml(wikiconfig.example_of(paths.CONFIG_PATH))
        self.assertEqual(example["account"]["pw_salt"], "")


class TestPwSaltScreen(unittest.TestCase):
    """パスワードの塩を設定画面に出す。**警告と「理解して編集」のチェックを入れたときだけ**書ける
    （Wiki設計者の指示、2026-09-21。変えると全員のパスワードが通らなくなり、取り返しが付かない）。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pwsalt-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "wikiA", "wiki")
        os.makedirs(self.wiki_dir)
        os.makedirs(os.path.dirname(wikiconfig.farm_config_path(self.wiki_dir)), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def html(self, own=None):
        path = wikiconfig.farm_config_path(self.wiki_dir)
        return configui._screen_html(wikiconfig.load_config(), own or {}, path, "wikiA",
                                     "", "account", self.wiki_dir)

    def salt_box(self, html):
        start = html.index('data-path="account.pw_salt"')
        rest = html[start:]
        end = rest.find('<div class="wcfg-field', 10)
        return rest if end < 0 else rest[:end]

    def test_画面に出す(self):
        field = configui.fields_by_path()["account.pw_salt"]
        self.assertEqual(field["type"], "text")
        self.assertIn("通らなく", field["guard"])            # 警告の文言

    def test_警告とチェックがあり_チェックまで印も入力欄も無効(self):
        box = self.salt_box(self.html())
        self.assertEqual(box.count('data-role="guard"'), 1)
        self.assertIn("理解したうえで編集する", box)
        self.assertIn("wcfg-guard-warn", box)
        use = box[box.index('data-role="use"'):]
        self.assertIn("disabled", use[:use.index(">")])        # 印
        value = box[box.index('data-role="value"'):]
        self.assertIn("disabled", value[:value.index(">")])    # 入力欄

    def test_書いてあるWikiでも印と入力欄は無効から始まる(self):
        box = self.salt_box(self.html({"account": {"pw_salt": "mine"}}))
        use = box[box.index('data-role="use"'):]
        self.assertIn("checked", use[:use.index(">")])
        self.assertIn("disabled", use[:use.index(">")])
        self.assertIn('value="mine"', box)

    def test_いま効いている塩を出す(self):
        self.assertIn("いま効いている塩: <code>wikiA</code>", self.html())           # 空なら Wiki名
        self.assertIn("いま効いている塩: <code>mine</code>",
                      self.html({"account": {"pw_salt": "mine"}}))

    def test_ほかの項目には警告も無効も付かない(self):
        html = self.html()
        self.assertEqual(html.count('data-role="guard"'), 1)
        start = html.index('data-path="account.policy"')
        policy = html[start:html.index('<div class="wcfg-field', start)]
        self.assertNotIn("wcfg-guard", policy)
        use = policy[policy.index('data-role="use"'):]
        self.assertNotIn("disabled", use[:use.index(">")])

    def test_確認済みの印が無ければ書かない(self):
        path = wikiconfig.farm_config_path(self.wiki_dir)
        ok, message, _shown = configui.apply_change(self.wiki_dir, "account.pw_salt", True, "x")
        self.assertFalse(ok)
        self.assertEqual(message, configui.GUARD_REFUSED)
        self.assertFalse(os.path.exists(path))                 # 何も書いていない

    def test_印を外すのも確認が要る(self):
        configui.apply_change(self.wiki_dir, "account.pw_salt", True, "x", ack=True)
        ok, _message, _shown = configui.apply_change(self.wiki_dir, "account.pw_salt", False, "")
        self.assertFalse(ok)
        self.assertEqual(wikiconfig.read_yaml(
            wikiconfig.farm_config_path(self.wiki_dir))["account"]["pw_salt"], "x")

    def test_確認済みなら書ける_塩が変わる(self):
        ok, _message, shown = configui.apply_change(
            self.wiki_dir, "account.pw_salt", True, "new-salt", ack=True)
        self.assertTrue(ok)
        self.assertEqual(shown, "new-salt")
        self.assertEqual(userdb.password_salt(self.wiki_dir), "new-salt")
        ok, _message, _shown = configui.apply_change(
            self.wiki_dir, "account.pw_salt", False, "", ack=True)
        self.assertTrue(ok)
        self.assertEqual(userdb.password_salt(self.wiki_dir), "wikiA")      # Wiki名に戻る

    def test_警告のない項目は確認なしで書ける(self):
        ok, _message, _shown = configui.apply_change(
            self.wiki_dir, "account.policy", True, "approval")
        self.assertTrue(ok)

    def test_窓口も確認済みの印が無ければ断る(self):
        import io
        import json
        import bottle
        from wikilib import auth, sysui
        def call(payload):
            data = json.dumps(payload).encode("utf-8")
            bottle.request.bind({"REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
                                 "CONTENT_LENGTH": str(len(data)), "wsgi.input": io.BytesIO(data)})
            with mock.patch.object(auth, "allows", return_value=True), \
                    mock.patch.object(configui, "farm_config_path",
                                      return_value=wikiconfig.farm_config_path(self.wiki_dir)):
                return configui.render_configwiki_api(self.wiki_dir, {}, "wikiA", False)
        res = call({"op": "set", "path": "account.pw_salt", "use": True, "value": "x"})
        self.assertEqual(res.status_code, 400)
        res = call({"op": "set", "path": "account.pw_salt", "use": True, "value": "x", "ack": True})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(userdb.password_salt(self.wiki_dir), "x")

    def test_画面のJSとCSSが対応している(self):
        base = os.path.join(ROOT, "_sys", "configui")
        with open(os.path.join(base, "configui.js"), encoding="utf-8") as f:
            js = f.read()
        with open(os.path.join(base, "configui.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertIn('[data-role="guard"]', js)
        self.assertIn("ack:", js)
        self.assertIn(".wcfg-guard", css)


class TestPerWiki(unittest.TestCase):
    """Wikiごとに書き分けられる。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="accountpolicy-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        os.makedirs(os.path.dirname(wikiconfig.farm_config_path(self.wiki_dir)),
                    exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def policy(self):
        return wikiconfig.account_policy(wikiconfig.load_wiki_config(self.wiki_dir))

    def test_書かなければ共通の設定の_open(self):
        self.assertEqual(self.policy(), "open")

    def test_そのWikiに書けばそちらが効く(self):
        with open(wikiconfig.farm_config_path(self.wiki_dir), "w",
                  encoding="utf-8") as f:
            f.write("account:\n  policy: approval\n")
        self.assertEqual(self.policy(), "approval")

    def test_画面の書き込みで変えて_印を外せば戻る(self):
        ok, _message, shown = configui.apply_change(
            self.wiki_dir, "account.policy", True, "approval")
        self.assertTrue(ok)
        self.assertEqual(shown, "approval")
        self.assertEqual(self.policy(), "approval")
        ok, _message, shown = configui.apply_change(
            self.wiki_dir, "account.policy", False, "")
        self.assertTrue(ok)
        self.assertEqual(shown, "open")
        self.assertEqual(self.policy(), "open")

    def test_選択肢にない値は書かない(self):
        ok, _message, _shown = configui.apply_change(
            self.wiki_dir, "account.policy", True, "closed")
        self.assertFalse(ok)
        self.assertEqual(self.policy(), "open")


class TestScreen(unittest.TestCase):
    """設定画面の項目。"""

    def field(self):
        return configui.fields_by_path()["account.policy"]

    def test_画面の項目がある(self):
        self.assertEqual(self.field()["type"], "choice")

    def test_選択肢は設定の値と同じ(self):
        # 画面だけ・読む側だけに値が増えて食い違わないように
        self.assertEqual(tuple(v for v, _label in self.field()["choices"]),
                         wikiconfig.ACCOUNT_POLICIES)

    def test_承認制の意味を画面に書いてある(self):
        # 動きは実装済み（wikilib.auth.do_signup・wikilib.approvalsui）。
        # 「動きは変わらない」という古い断りが残っていないことも見る
        help_text = self.field()["help"]
        self.assertIn("承認", help_text)
        self.assertIn("/.admin/approvals", help_text)
        self.assertNotIn("動きは変わりません", help_text)

    def test_アカウントのタブが編集の次にある(self):
        keys = [key for key, _title, _fields in configui.SECTIONS]
        self.assertEqual(keys[keys.index("edit") + 1], "account")


if __name__ == "__main__":
    unittest.main()
