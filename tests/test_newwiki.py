#!/usr/bin/env python3
"""Wikiを作るときに選ぶ「利用形態」（`wikilib.newwiki.USAGES`）のテスト。

Wiki設計者が挙げた5つの使いかた（2026-09-20）を、**権限の既定値（既定の行 `*`）と
ユーザ登録の受け入れかた（`account.policy`）の組**で作るときに与える
（2026-09-21）。ここでは、作った直後のWikiに何が置かれるかと、そのWikiで実際に
誰が読めて誰が書けるかを見る。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_newwiki.py     （このファイルだけ）
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import newwiki, paths, privilege_records, userdb, wikiconfig  # noqa: E402
from wikilib.auth import PAGE_NONE, PAGE_READ, PAGE_WRITE, page_privilege  # noqa: E402


class NewWikiTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="newwiki-")
        self.kept = (paths.WIKIDATA_DIR, newwiki.WIKIDATA_DIR)
        paths.WIKIDATA_DIR = newwiki.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        os.makedirs(paths.WIKIDATA_DIR)

    def tearDown(self):
        paths.WIKIDATA_DIR, newwiki.WIKIDATA_DIR = self.kept
        shutil.rmtree(self.work, ignore_errors=True)

    def make(self, usage=None, independent=False, name="w1"):
        kwargs = {} if usage is None else {"usage": usage}
        ok, message = newwiki.create_wiki(name, "", independent, "adminpw", **kwargs)
        self.assertTrue(ok, message)
        return os.path.join(paths.WIKIDATA_DIR, name, "wiki")

    def rows(self, wiki_dir):
        return [(e["page"], e["kind"], e["who"]) for e in privilege_records.load(wiki_dir)]

    def policy(self, wiki_dir):
        return wikiconfig.account_policy(wikiconfig.load_wiki_config(wiki_dir))


class TestUsages(NewWikiTestBase):
    """作った直後に置かれるもの。"""

    def test_形態の一覧(self):
        self.assertEqual(list(newwiki.USAGES), ["free", "named", "public", "members"])
        self.assertEqual(newwiki.USAGE_DEFAULT, "free")

    def test_省略すると何も置かない_これまでの動き(self):
        wiki_dir = self.make()
        self.assertEqual(self.rows(wiki_dir), [])
        self.assertEqual(self.policy(wiki_dir), "open")
        self.assertFalse(os.path.exists(wikiconfig.farm_config_path(wiki_dir)))

    def test_free(self):
        wiki_dir = self.make("free")
        self.assertEqual(self.rows(wiki_dir), [])
        self.assertEqual(self.policy(wiki_dir), "open")

    def test_named(self):
        wiki_dir = self.make("named")
        self.assertEqual(self.rows(wiki_dir), [
            ("*", "R", ["g:any"]), ("*", "W", ["g:all"])])
        self.assertEqual(self.policy(wiki_dir), "open")

    def test_public(self):
        wiki_dir = self.make("public")
        self.assertEqual(self.rows(wiki_dir), [
            ("*", "R", ["g:any"]), ("*", "W", ["g:all"])])
        self.assertEqual(self.policy(wiki_dir), "approval")

    def test_members(self):
        wiki_dir = self.make("members")
        self.assertEqual(self.rows(wiki_dir), [
            ("*", "R", ["g:all"]), ("*", "W", ["admin", "g:staff"])])
        self.assertEqual(self.policy(wiki_dir), "approval")

    def test_知らない形態は何も作らずに断る(self):
        ok, _message = newwiki.create_wiki("w2", "", False, "adminpw", usage="nope")
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(os.path.join(paths.WIKIDATA_DIR, "w2")))

    def test_全形態が説明を持つ(self):
        for key, item in newwiki.USAGES.items():
            for field in ("title", "label", "read", "write", "signup", "rules", "policy"):
                self.assertIn(field, item, key)
            self.assertIn(item["policy"], (None,) + wikiconfig.ACCOUNT_POLICIES, key)


class TestPolicyFile(NewWikiTestBase):
    """`account.policy` の書きかた。独立させた設定の写しでは、コメントを残す。"""

    def test_独立させない場合は_policyだけを持つ設定ができる(self):
        wiki_dir = self.make("public", independent=False)
        data = wikiconfig.read_yaml(wikiconfig.farm_config_path(wiki_dir))
        self.assertEqual(data, {"account": {"policy": "approval"}})
        # 設定画面が書いたものと同じ形なので、あとで直しても控えが増えない
        self.assertTrue(wikiconfig.written_by_system(wikiconfig.farm_config_path(wiki_dir)))

    def test_独立させた場合は写しの1行だけを置き換える(self):
        wiki_dir = self.make("public", independent=True)
        path = wikiconfig.farm_config_path(wiki_dir)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("  policy: approval\n", text)
        self.assertNotIn("  policy: open\n", text)
        self.assertIn("# ユーザ登録", text)            # コメントは残っている
        self.assertIn("markdown:", text)                # ほかの項目も残っている
        self.assertEqual(self.policy(wiki_dir), "approval")
        self.assertEqual(text.count("policy:"), 1)

    def test_独立させて_openの形態でも_openと書く(self):
        wiki_dir = self.make("named", independent=True)
        self.assertEqual(self.policy(wiki_dir), "open")


class TestBehavior(NewWikiTestBase):
    """作ったWikiで、誰が何をできるか。"""

    def add(self, wiki_dir, uid):
        userdb.add_user(wiki_dir, uid, userdb.hash_password(wiki_dir, uid, "p"), uid)

    def check(self, wiki_dir, uid, page="Tech/A"):
        return page_privilege(wiki_dir, uid).check(page)

    def test_freeは未ログインでも読み書きできる(self):
        wiki_dir = self.make("free")
        self.assertEqual(self.check(wiki_dir, None), PAGE_WRITE)

    def test_named_publicは未ログインは閲覧だけで登録ユーザは編集できる(self):
        for usage in ("named", "public"):
            wiki_dir = self.make(usage, name="w-" + usage)
            self.add(wiki_dir, "alice")
            self.assertEqual(self.check(wiki_dir, None), PAGE_READ, usage)
            self.assertEqual(self.check(wiki_dir, "alice"), PAGE_WRITE, usage)
            self.assertEqual(self.check(wiki_dir, "admin"), PAGE_WRITE, usage)

    def test_membersは閲覧にもログインが要り_編集は管理者と助手だけ(self):
        wiki_dir = self.make("members")
        self.add(wiki_dir, "alice")
        self.add(wiki_dir, "helper")
        from wikilib import groups
        groups.add_members(wiki_dir, "staff", ["helper"])
        self.assertEqual(self.check(wiki_dir, None), PAGE_NONE)
        self.assertEqual(self.check(wiki_dir, "alice"), PAGE_READ)
        self.assertEqual(self.check(wiki_dir, "helper"), PAGE_WRITE)
        self.assertEqual(self.check(wiki_dir, "admin"), PAGE_WRITE)


class TestMarkupAndTitle(NewWikiTestBase):
    """作るときに選ぶ既定の書きかた（`edit.defaultwiki`）と、見出しをサイト名にも使うこと。"""

    def create(self, name="w1", title="", independent=False, markup=None):
        ok, message = newwiki.create_wiki(name, title, independent, "adminpw",
                                          markup=markup)
        self.assertTrue(ok, message)
        return os.path.join(paths.WIKIDATA_DIR, name, "wiki")

    def conf(self, wiki_dir):
        return wikiconfig.load_wiki_config(wiki_dir)

    def read(self, wiki_dir, filename):
        with open(os.path.join(wiki_dir, filename), encoding="utf-8") as f:
            return f.read()

    def test_省略すると共通の既定の書きかたで_設定も書かない(self):
        wiki_dir = self.create()
        common = wikiconfig.default_markup(wikiconfig.load_config())
        ext = paths.default_markup_ext(common)
        self.assertTrue(os.path.isfile(os.path.join(wiki_dir, "index" + ext)))
        self.assertFalse(os.path.exists(wikiconfig.farm_config_path(wiki_dir)))

    def test_markdownを選ぶと_mdで置き_Markdownで書く(self):
        wiki_dir = self.create(markup="markdown", title="Top")
        self.assertEqual(sorted(f for f in os.listdir(wiki_dir) if not f.startswith(".")),
                         ["index.md", "mainmenu.md"])
        self.assertTrue(self.read(wiki_dir, "index.md").startswith("# Top\n"))
        menu = self.read(wiki_dir, "mainmenu.md")
        self.assertIn("## メニュー", menu)
        self.assertIn("[トップ](/)", menu)
        self.assertEqual(wikiconfig.default_markup(self.conf(wiki_dir)), "markdown")

    def test_pukiwikiを選ぶと_txtで置く(self):
        wiki_dir = self.create(markup="pukiwiki", title="Top")
        self.assertTrue(self.read(wiki_dir, "index.txt").startswith("* Top\n"))
        self.assertIn("[[トップ>/]]", self.read(wiki_dir, "mainmenu.txt"))
        self.assertEqual(wikiconfig.default_markup(self.conf(wiki_dir)), "pukiwiki")

    def test_独立させた写しでは書きかたの行を置き換える(self):
        wiki_dir = self.create(markup="markdown", independent=True)
        with open(wikiconfig.farm_config_path(wiki_dir), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("  defaultwiki: markdown\n", text)
        self.assertEqual(text.count("defaultwiki:"), 1)
        self.assertEqual(wikiconfig.default_markup(self.conf(wiki_dir)), "markdown")

    def test_知らない書きかたは何も作らずに断る(self):
        ok, _message = newwiki.create_wiki("w2", "", False, "adminpw", markup="plain")
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(os.path.join(paths.WIKIDATA_DIR, "w2")))

    def test_見出しはサイト名にもなる(self):
        for independent in (False, True):
            title = "研究室の Wiki: #1"
            wiki_dir = self.create(name=f"t{int(independent)}", title=title,
                                   independent=independent)
            self.assertEqual(self.conf(wiki_dir)["theme"]["site_title"], title, independent)

    def test_見出しが空ならサイト名は共通の既定値のまま(self):
        wiki_dir = self.create(independent=True)
        common = (wikiconfig.load_config().get("theme") or {}).get("site_title")
        self.assertEqual(self.conf(wiki_dir)["theme"]["site_title"], common)

    def test_見出しと利用形態を独立させずに書くと_両方を1つの設定に持つ(self):
        ok, message = newwiki.create_wiki("w3", "Lab", False, "adminpw", usage="public",
                                          markup="markdown")
        self.assertTrue(ok, message)
        wiki_dir = os.path.join(paths.WIKIDATA_DIR, "w3", "wiki")
        data = wikiconfig.read_yaml(wikiconfig.farm_config_path(wiki_dir))
        common = wikiconfig.default_markup(wikiconfig.load_config())
        expected = {"account": {"policy": "approval"}, "theme": {"site_title": "Lab"}}
        if common != "markdown":
            expected["edit"] = {"defaultwiki": "markdown"}
        self.assertEqual(data, expected)



class TestNewWikiForm(NewWikiTestBase):
    """作成画面（`/.newwiki`）から作ったとき。画面で選んだ書きかたが、置く index の
    拡張子と書きかたまで届くこと。誰が開けるかの関門は `tests/test_servicegate.py`。"""

    def setUp(self):
        super().setUp()
        from wikilib import sysui
        self.sysui = sysui
        self.kept_gate = sysui.require_on_default_farm
        sysui.require_on_default_farm = lambda *args: None
        self.home = os.path.join(paths.WIKIDATA_DIR, "home", "wiki")
        os.makedirs(self.home)

    def tearDown(self):
        self.sysui.require_on_default_farm = self.kept_gate
        bottle.request.environ.clear()
        super().tearDown()

    def post(self, **fields):
        form = {"name": "w1", "title": "", "admin_pw": "pw", "admin_pw2": "pw",
                "usage": "free"}
        form.update(fields)
        body = urlencode(form).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST", "PATH_INFO": "/.newwiki",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
        })
        return newwiki.render_newwiki(self.home, {}, "home", False)

    def get(self):
        bottle.request.environ.clear()
        bottle.request.environ.update({"REQUEST_METHOD": "GET", "PATH_INFO": "/.newwiki"})
        return newwiki.render_newwiki(self.home, {}, "home", False)

    def test_初めて開くと共通の既定の書きかたに印が付いている(self):
        common = wikiconfig.default_markup(wikiconfig.load_config())
        html = self.get()
        html = html if isinstance(html, str) else html.body
        self.assertIn(f'value="{common}" checked', html)

    def test_画面で選んだ書きかたでindexを作る(self):
        for markup, ext, head in (("markdown", ".md", "# "), ("pukiwiki", ".txt", "* ")):
            name = "w-" + markup
            out = self.post(name=name, markup=markup, title="Top")
            self.assertEqual(out.status_code, 303, markup)
            wiki_dir = os.path.join(paths.WIKIDATA_DIR, name, "wiki")
            with open(os.path.join(wiki_dir, "index" + ext), encoding="utf-8") as f:
                self.assertTrue(f.read().startswith(head + "Top\n"), markup)
            self.assertEqual(wikiconfig.default_markup(
                wikiconfig.load_wiki_config(wiki_dir)), markup)


if __name__ == "__main__":
    unittest.main()
