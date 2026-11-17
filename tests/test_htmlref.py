#!/usr/bin/env python3
"""`htmlref` プラグイン（添付の HTML を、管理者が承認したものだけスクリプトを動かして開く）の試験。

決まり（設計者の指示、2026-11-16。詳しくは `plugin/htmlref.py` の技術資料）:

- 印もキーも無い `#htmlref` は、閲覧中のページを描いたときに `reqXX` を書き足して保存する。
  ページの中で `reqXX` が重なっていたら、後のほうを振り直す
- 管理者が閲覧中のページで見たときだけ、`reqXX` に［承認］を出す（メニュー・`#include`・
  部分プレビューでは出さないし、書き足しもしない）
- ［承認］は、`reqXX` が本文中で一意に特定できたときだけキーに書き換える。複数一致なら
  振り直す。見つからなければリロードだけ
- キーが合わない（承認後に添付が変わった等）とエラー。合えばスクリプトが動く形で配る

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_htmlref.py     （このファイルだけ）
"""
import importlib.util
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlsplit
from html import unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import auth, paths, userdb  # noqa: E402
from wikilib.pagesave import save_page, watch_writes  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, farm_plugin_dir, wiki_cookie_name  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import render_source  # noqa: E402
from wikilib.themes import render_menu  # noqa: E402

FARM = "t"
REQ = r"req[0-9A-Za-z]{2}"
# エラーの理由は plugin.debug のときだけ表示される（`plugins.plugin_error_html`）
DEBUG = {"plugin": {"debug": True}}


def load_plugin(name):
    spec = importlib.util.spec_from_file_location(
        "plugin_under_test_" + name, os.path.join(ROOT, "plugin", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


htmlref = load_plugin("htmlref")


class HtmlRefTestBase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="htmlref-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        userdb.add_user(self.wiki_dir, "alice", userdb.hash_password(self.wiki_dir, "alice", "p"),
                        "alice")
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        self.uid = None
        self.put("Top/demo.html", b"<script>alert(1)</script>")
        bottle.request.bind({})

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    # ---- 用意 ----

    def put(self, rel, data):
        path = os.path.join(self.work, "wikidata", FARM, "attach", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def write(self, page, text, ext=".md"):
        save_page(self.wiki_dir, {}, page, ext, text)

    def read(self, page, ext=".md"):
        with open(os.path.join(self.wiki_dir, page + ext), encoding="utf-8") as f:
            return f.read()

    def environ(self, path, method="GET"):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path}
        if self.uid is not None:
            user = userdb.find_by_uid(self.wiki_dir, self.uid)
            token = auth.session_token(self.uid, FARM, user["pw"])
            env["HTTP_COOKIE"] = (f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={self.uid}; "
                                  f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")
        return env

    # ---- 描く ----

    def render(self, page, ext=".md", url=None, partial=False, menu=None, config=None):
        """`page` を URL `url`（既定は `/=t/<page>`）で開いたときと同じく描く。描画の中で
        本文が書き換わったら描き直す（`views.render_page` と同じ）。メニューも描くなら
        (本文, メニュー)。"""
        bottle.request.bind(self.environ(url or f"/={FARM}/{page}"))
        try:
            for _ in range(5):
                with watch_writes() as written:
                    context = PluginContext(config=config or {}, farm=FARM, wiki_dir=self.wiki_dir,
                                            page=page, base_url=f"/={FARM}", ext=ext,
                                            partial=partial)
                    md = build_markdown_renderer(config or {}, farm_plugin_dir(self.wiki_dir),
                                                 context)
                    html, _, _ = render_source(md, self.read(page, ext), ext, True, context)
                    menu_html = (render_menu(md, self.wiki_dir, f"/={FARM}", menu, context)
                                 if menu else None)
                if not written:
                    break
        finally:
            bottle.request.bind({})
        return (html, menu_html) if menu else html

    def action(self, method="GET", query=None, form=None):
        env = self.environ(f"/={FARM}/.plugin/htmlref", method)
        if query:
            env["QUERY_STRING"] = urlencode(query)
        if form is not None:
            data = urlencode(form).encode("utf-8")
            env.update({"CONTENT_TYPE": "application/x-www-form-urlencoded",
                        "CONTENT_LENGTH": str(len(data)), "wsgi.input": io.BytesIO(data)})
        bottle.request.bind(env)
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page="",
                                base_url=f"/={FARM}")
        try:
            return htmlref._action(context)
        finally:
            bottle.request.bind({})

    @staticmethod
    def approve_fields(html):
        """描いた HTML の［承認］フォームの値。[{"page", "req", "sha"}]"""
        out = []
        for form in re.findall(r'<form class="plugin-htmlref-approve".*?</form>', html, re.S):
            out.append({k: unescape(v) for k, v in re.findall(r'name="(\w+)" value="([^"]*)"', form)})
        return out

    def key_of(self, page="Top", target="Top/demo.html"):
        path = htmlref._attach_path(self.wiki_dir, target)
        return htmlref.allow_key(self.wiki_dir, page, target, htmlref._sha256(path))


class TestTag(HtmlRefTestBase):
    def test_印の無い呼び出しにreqXXを書き足す(self):
        self.write("Top", "#htmlref(demo.html)\n\n#htmlref(demo.html, title=説明)\n")
        html = self.render("Top")
        text = self.read("Top")
        self.assertRegex(text, r"^#htmlref\(demo\.html, (" + REQ + r")\)\n\n"
                               r"#htmlref\(demo\.html, title=説明, (" + REQ + r")\)\n$")
        a, b = re.findall(REQ, text)
        self.assertNotEqual(a, b)
        self.assertIn("スクリプト承認待ち", html)
        # 添付の書きかた（`::`）。本体が表示の最後に /.attach/… へ書き換える（`ref` と同じ）
        self.assertIn('href="::demo.html"', html)

    def test_重なったreqXXは後のほうを振り直す(self):
        self.write("Top", "#htmlref(demo.html, reqAB)\n#htmlref(demo.html, reqAB)\n")
        self.render("Top")
        lines = self.read("Top").split("\n")
        self.assertEqual(lines[0], "#htmlref(demo.html, reqAB)")
        m = re.fullmatch(r"#htmlref\(demo\.html, (" + REQ + r")\)", lines[1])
        self.assertIsNotNone(m, lines[1])
        self.assertNotEqual(m.group(1), "reqAB")

    def test_描かれない所は書き換えない(self):
        self.write("Top", "#code(){{\n#htmlref(demo.html)\n}}\n\n#note(){{\n#htmlref(demo.html)\n}}\n")
        self.render("Top")
        text = self.read("Top")
        self.assertIn("#code(){{\n#htmlref(demo.html)\n}}", text)
        self.assertRegex(text, r"#note\(\)\{\{\n#htmlref\(demo\.html, " + REQ + r"\)\n\}\}")

    def test_PukiWiki記法のページでも書き足す(self):
        self.write("Top", "#htmlref(demo.html)\n", ext=".txt")
        self.render("Top", ext=".txt")
        self.assertRegex(self.read("Top", ".txt"), r"^#htmlref\(demo\.html, " + REQ + r"\)\n$")

    def test_部分プレビューでは書き足さない(self):
        self.write("Top", "#htmlref(demo.html)\n")
        self.render("Top", partial=True)
        self.assertEqual(self.read("Top"), "#htmlref(demo.html)\n")

    def test_includeした先では書き足さない(self):
        self.put("Inc/demo.html", b"x")
        self.write("Inc", "#htmlref(demo.html)\n")
        self.write("Top", "#include(Inc)\n")
        self.uid = "admin"
        html = self.render("Top")
        self.assertEqual(self.read("Inc"), "#htmlref(demo.html)\n")
        self.assertNotIn("plugin-htmlref-approve", html)
        self.assertIn("スクリプト承認待ち", html)

    def test_URLのページと違えば書き足さない(self):
        self.write("Top", "#htmlref(demo.html)\n")
        self.render("Top", url="/=t/.plugin/ls")
        self.assertEqual(self.read("Top"), "#htmlref(demo.html)\n")


class TestApproveButton(HtmlRefTestBase):
    def setUp(self):
        super().setUp()
        self.write("Top", "#htmlref(demo.html, reqAB)\n")

    def test_管理者には承認を出す(self):
        self.uid = "admin"
        html = self.render("Top")
        fields = self.approve_fields(html)
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["page"], "Top")
        self.assertEqual(fields[0]["req"], "reqAB")
        self.assertEqual(fields[0]["sha"], htmlref._sha256(
            htmlref._attach_path(self.wiki_dir, "Top/demo.html")))
        self.assertIn('action="/=t/.plugin/htmlref"', html)

    def test_管理者以外には出さない(self):
        for uid in (None, "alice"):
            self.uid = uid
            self.assertNotIn("plugin-htmlref-approve", self.render("Top"))

    def test_メニューの中では出さない(self):
        self.uid = "admin"
        self.write("mainmenu", "#htmlref(/Top/demo.html, reqCD)\n")
        self.write("Other", "本文\n")
        body, menu = self.render("Other", menu="mainmenu")
        self.assertIn("スクリプト承認待ち", menu)
        self.assertNotIn("plugin-htmlref-approve", menu)
        self.assertEqual(self.read("mainmenu"), "#htmlref(/Top/demo.html, reqCD)\n")

    def test_部分プレビューでは出さない(self):
        self.uid = "admin"
        self.assertNotIn("plugin-htmlref-approve", self.render("Top", partial=True))


class TestApprove(HtmlRefTestBase):
    def post(self, **form):
        return self.action("POST", form=form)

    def sha(self):
        return htmlref._sha256(htmlref._attach_path(self.wiki_dir, "Top/demo.html"))

    def test_一意ならキーに書き換える(self):
        self.write("Top", "前\n\n#htmlref(demo.html, reqAB, title=説明)\n")
        self.uid = "admin"
        r = self.post(page="Top", req="reqAB", sha=self.sha())
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["Location"], "/=t/Top")
        self.assertEqual(self.read("Top"),
                         f"前\n\n#htmlref(demo.html, {self.key_of()}, title=説明)\n")

    def test_管理者でなければ断る(self):
        self.write("Top", "#htmlref(demo.html, reqAB)\n")
        for uid in (None, "alice"):
            self.uid = uid
            r = self.post(page="Top", req="reqAB", sha=self.sha())
            self.assertEqual(r.status_code, 403)
        self.assertEqual(self.read("Top"), "#htmlref(demo.html, reqAB)\n")

    def test_複数一致なら振り直すだけ(self):
        self.write("Top", "#htmlref(demo.html, reqAB)\n#htmlref(demo.html, reqAB)\n")
        self.uid = "admin"
        r = self.post(page="Top", req="reqAB", sha=self.sha())
        self.assertEqual(r.status_code, 303)
        lines = self.read("Top").split("\n")
        self.assertEqual(lines[0], "#htmlref(demo.html, reqAB)")
        self.assertRegex(lines[1], r"^#htmlref\(demo\.html, " + REQ + r"\)$")
        self.assertNotIn("reqAB", lines[1])
        self.assertNotIn("as_", "\n".join(lines))

    def test_見つからなければ書き換えない(self):
        self.write("Top", "#htmlref(demo.html, reqAB)\n#code(){{\n#htmlref(demo.html, reqZZ)\n}}\n")
        before = self.read("Top")
        self.uid = "admin"
        r = self.post(page="Top", req="reqZZ", sha=self.sha())
        self.assertEqual(r.status_code, 303)
        self.assertEqual(self.read("Top"), before)

    def test_押す前に添付が変わっていたら書き換えない(self):
        self.write("Top", "#htmlref(demo.html, reqAB)\n")
        sha = self.sha()
        self.put("Top/demo.html", b"<script>changed()</script>")
        self.uid = "admin"
        r = self.post(page="Top", req="reqAB", sha=sha)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(self.read("Top"), "#htmlref(demo.html, reqAB)\n")


class TestKey(HtmlRefTestBase):
    def test_キーが合えば承認済みのリンク(self):
        key = self.key_of()
        self.write("Top", f"#htmlref(demo.html, {key})\n")
        html = self.render("Top")
        self.assertIn("スクリプト許可", html)
        href = unescape(re.search(r'<a href="([^"]*)" class="plugin-htmlref-file"', html).group(1))
        parts = urlsplit(href)
        self.assertEqual(parts.path, "/=t/.plugin/htmlref")
        self.assertEqual(parse_qs(parts.query), {"page": ["Top"], "src": ["demo.html"], "key": [key]})
        self.assertEqual(self.read("Top"), f"#htmlref(demo.html, {key})\n")

    def test_キーが合わなければエラー(self):
        self.write("Top", "#htmlref(demo.html, as_AAAAAAAAAA)\n")
        html = self.render("Top", config=DEBUG)
        self.assertIn("承認し直しが必要です", html)
        self.assertNotIn("plugin-htmlref-file", html)

    def test_承認後に上書きされたらエラー(self):
        key = self.key_of()
        self.write("Top", f"#htmlref(demo.html, {key})\n")
        self.put("Top/demo.html", b"<script>evil()</script>")
        self.assertIn("承認し直しが必要です", self.render("Top", config=DEBUG))

    def test_別のページへ書き写したキーは合わない(self):
        self.put("Other/demo.html", b"<script>alert(1)</script>")
        self.write("Other", f"#htmlref(demo.html, {self.key_of()})\n")
        self.assertIn("承認し直しが必要です", self.render("Other", config=DEBUG))

    def test_形の崩れた値は引数のエラー(self):
        self.write("Top", "#htmlref(demo.html, as_short)\n")
        html = self.render("Top")
        self.assertNotIn("plugin-htmlref-file", html)
        self.assertEqual(self.read("Top"), "#htmlref(demo.html, as_short)\n")

    def test_HTML以外は引数のエラー(self):
        self.put("Top/a.zip", b"x")
        self.put("Top/b.Html", b"x")
        self.write("Top", "#htmlref(a.zip)\n\n#htmlref(b.Html)\n")
        html = self.render("Top", config=DEBUG)
        self.assertEqual(html.count("HTML の添付ファイル"), 2)
        self.assertEqual(self.read("Top"), "#htmlref(a.zip)\n\n#htmlref(b.Html)\n")


class TestServe(HtmlRefTestBase):
    def fetch(self, **query):
        with mock.patch("bottle.request", bottle.request):
            res = self.action("GET", query=query)
        body = res.body
        if hasattr(body, "read"):
            body = body.read()
            res.body.close()
        return res, body

    def test_キーが合えばスクリプトを許して配る(self):
        res, body = self.fetch(page="Top", src="demo.html", key=self.key_of())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(body, b"<script>alert(1)</script>")
        self.assertEqual(res.headers["Content-Security-Policy"], "sandbox allow-scripts")
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(res.headers["Content-Type"].startswith("text/html"))

    def test_キーが合わなければ404(self):
        res, body = self.fetch(page="Top", src="demo.html", key="as_AAAAAAAAAA")
        self.assertEqual(res.status_code, 404)
        self.assertNotIn("Content-Security-Policy", res.headers)

    def test_上書き後は404(self):
        key = self.key_of()
        self.put("Top/demo.html", b"<script>evil()</script>")
        res, _ = self.fetch(page="Top", src="demo.html", key=key)
        self.assertEqual(res.status_code, 404)

    def test_閲覧できない添付は404(self):
        from wikilib import privilege_records
        ok, message, _ = privilege_records.put(self.wiki_dir, "Top", "R", "alice")
        self.assertTrue(ok, message)
        key = self.key_of()
        self.uid = None
        res, _ = self.fetch(page="Top", src="demo.html", key=key)
        self.assertEqual(res.status_code, 404)
        self.uid = "alice"
        res, _ = self.fetch(page="Top", src="demo.html", key=key)
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
