#!/usr/bin/env python3
"""テーマのファイル（`wikilib.themefilesui`。webFileDir を組み込んだ `/.admin/themes/`）のテスト。

  - 開けるのは管理者と助手（ふつうの人・未ログインは画面も API も 403）。助手には sitetheme を見せず、
    common の「sitetheme へコピー」も出さない。助手の slottheme での操作は stafflog に残す
  - マウントは common（全Wiki共通・読み取り専用）と sitetheme（そのWiki固有・読み書き）
  - common から sitetheme へ貼り付けで写せる。common は変えられない
  - テキストの簡易編集（edit-text）は sitetheme にだけ出る
  - sitetheme のアップロードは CSS と画像だけ、編集は CSS だけ。ほかの拡張子から html・js・svg へは
    名前を変えられない（html からほかへ、html どうしは変えられる）。html も写せる
  - slottheme は HTML・CSS・画像・フォントだけ。HTML・CSS は、取り除かれるものがあれば保存を断る
    （アップロード・編集・名前の変更・貼り付け・「slottheme へコピー」のどれでも）
  - 「sitetheme へコピー」で同じ場所へ写す。同じ名前があれば上書きを尋ねる
  - sitetheme のごみ箱は、テーマのフォルダの外（pageinfo/theme-trash）に置く
  - アップロードは sitetheme にだけ出る。1ファイルの上限は添付と同じ（attach.max_size）
  - `/.admin/themes` から `/.admin/themes/` へ送る

webFileDir（paths.WEBFILEDIR_DIR）が無い環境では飛ばす。

実行:
    _venv/bin/python3 tests/test_themefilesui.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import auth, groups, paths, slottheme, stafflog, themefilesui, themes, userdb  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

FARM = "testwiki"
BASE = "/=" + FARM + "/.admin/themes"
HAS_WEBFILEDIR = os.path.isfile(os.path.join(paths.WEBFILEDIR_DIR, "server", "__init__.py"))


@unittest.skipUnless(HAS_WEBFILEDIR, "webFileDir がありません")
class TestThemeFilesUI(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="themefiles-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("kyun", "hito"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        groups.add_members(self.wiki_dir, groups.STAFF_GROUP, ["kyun"])
        self.kept = (paths.WIKIDATA_DIR, auth.SECRET_PATH, themefilesui.THEME_DIR, themes.THEME_DIR,
                     themefilesui.SLOTTHEME_DIR, slottheme.SLOTTHEME_DIR)
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        # 全Wiki共通のテーマ（common）
        self.common = os.path.join(self.work, "theme")
        os.makedirs(self.common)
        for name, text in (("base.html", "<html>{{ body }}</html>"), ("base.css", "body{}")):
            with open(os.path.join(self.common, name), "w", encoding="utf-8") as f:
                f.write(text)
        themefilesui.THEME_DIR = themes.THEME_DIR = self.common
        # スロット型のテーマ（共通は slotbase.html を置いておく）
        self.slotcommon = os.path.join(self.work, "slottheme")
        os.makedirs(self.slotcommon)
        with open(os.path.join(self.slotcommon, "slotbase.html"), "w", encoding="utf-8") as f:
            f.write('<p class="x" data-text="site_title">見本</p>')
        themefilesui.SLOTTHEME_DIR = slottheme.SLOTTHEME_DIR = self.slotcommon
        self.slot = os.path.join(self.work, "wikidata", FARM, "slottheme")
        self.site = os.path.join(self.work, "wikidata", FARM, "theme")
        themefilesui._apps.clear()
        self.cookie = None

    def tearDown(self):
        (paths.WIKIDATA_DIR, auth.SECRET_PATH, themefilesui.THEME_DIR, themes.THEME_DIR,
         themefilesui.SLOTTHEME_DIR, slottheme.SLOTTHEME_DIR) = self.kept
        themefilesui._apps.clear()
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def login_as(self, uid):
        """そのアカウントでログインした cookie を、以後の要求に付ける（None ならログインしない）。"""
        self.cookie = None
        if uid is not None:
            user = userdb.find_by_uid(self.wiki_dir, uid)
            token = auth.session_token(uid, FARM, user["pw"])
            self.cookie = (f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
                           f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")

    config = {}

    def call(self, path, query="", method="GET", body=None, raw=None):
        env = {"PATH_INFO": BASE + path, "QUERY_STRING": query, "REQUEST_METHOD": method}
        if self.cookie:
            env["HTTP_COOKIE"] = self.cookie
        setup_testing_defaults(env)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            env.update({"CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(data)),
                        "wsgi.input": io.BytesIO(data), "HTTP_X_WEBFILEDIR": "1"})
        if raw is not None:
            env.update({"CONTENT_TYPE": "application/octet-stream", "CONTENT_LENGTH": str(len(raw)),
                        "wsgi.input": io.BytesIO(raw), "HTTP_X_WEBFILEDIR": "1"})
        bottle.request.bind(env)
        res = themefilesui.serve_themefiles(self.wiki_dir, self.config, FARM, True, "http://x" + BASE)
        text = b"".join(x if isinstance(x, bytes) else x.encode() for x in res.body or [])
        if hasattr(res.body, "close"):
            res.body.close()
        return res.status_code, res.headers, text.decode("utf-8")

    def listing(self, mount, folder="/"):
        status, _, text = self.call("/api/v1/list", f"mount={mount}&path={folder}")
        self.assertEqual(status, 200, text)
        return {e["name"] for e in json.loads(text)["entries"]}

    def command(self, cid, **body):
        status, _, text = self.call("/api/v1/commands/" + cid, method="POST", body=body)
        res = json.loads(text)
        if status != 200 or "job" not in res:
            return status, res
        for _ in range(200):
            _, _, text = self.call("/api/v1/jobs/" + res["job"])
            job = json.loads(text)
            if job["state"] == "done":
                if "error" in job:
                    return job["status"], {"error": job["error"]}
                return 200, job["result"]
            time.sleep(0.02)
        self.fail("ジョブが終わりません: " + cid)

    def test_管理者と助手でなければ断る(self):
        for uid in ("hito", None):
            for path in ("/", "/api/v1/mounts"):
                self.login_as(uid)
                status = self.call(path)[0]
                self.assertEqual(status, 403, (uid, path))
        self.assertFalse(os.path.exists(self.slot), "断るときはフォルダも作らない")
        self.login_as("kyun")
        self.assertEqual(self.call("/")[0], 200, "助手は開ける")

    def test_末尾の斜線へ送り画面を返す(self):
        self.login_as("admin")
        status, headers, _ = self.call("")
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "http://x" + BASE + "/")
        status, _, text = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn("<title>テーマのファイル - testwiki</title>", text)

    def test_四つのマウント(self):
        self.login_as("admin")
        status, _, text = self.call("/api/v1/mounts")
        self.assertEqual(status, 200, text)
        mounts = {m["id"]: m for m in json.loads(text)}
        self.assertEqual(list(mounts), ["common", "sitetheme", "slotcommon", "slottheme"])
        self.assertTrue(mounts["common"]["readonly"])
        self.assertFalse(mounts["sitetheme"]["readonly"])
        self.assertTrue(mounts["slotcommon"]["readonly"])
        self.assertFalse(mounts["slottheme"]["readonly"])
        self.assertEqual(self.listing("slotcommon"), {"slotbase.html"})
        self.assertTrue(os.path.isdir(self.slot), "slottheme のフォルダは無ければ作る")
        self.assertEqual(self.listing("common"), {"base.html", "base.css"})
        self.assertEqual(self.listing("sitetheme"), set())
        self.assertTrue(os.path.isdir(self.site), "sitetheme のフォルダは無ければ作る")

    def test_commonから貼り付けで写せる(self):
        self.login_as("admin")
        self.listing("sitetheme")
        status, res = self.command(
            "paste", mount="sitetheme",
            source={"mount": "common", "paths": ["/base.css"], "mode": "copy"},
            dest={"mount": "sitetheme", "path": "/"})
        self.assertEqual(status, 200, res)
        self.assertEqual(self.listing("sitetheme"), {"base.css"})
        status, res = self.command("rename", mount="sitetheme", paths=["/base.css"],
                                   input="mine.css")
        self.assertEqual(status, 200, res)
        self.assertTrue(os.path.isfile(os.path.join(self.site, "mine.css")))
        self.assertTrue(os.path.isfile(os.path.join(self.common, "base.css")), "元は残る")

    def test_commonは変えられない(self):
        self.login_as("admin")
        status, _ = self.command("rename", mount="common", paths=["/base.css"], input="x.css")
        self.assertNotEqual(status, 200)
        status, _ = self.command("delete", mount="common", paths=["/base.css"])
        self.assertNotEqual(status, 200)
        self.assertEqual(sorted(os.listdir(self.common)), ["base.css", "base.html"])

    def test_ごみ箱はテーマのフォルダの外(self):
        os.makedirs(self.site)
        with open(os.path.join(self.site, "old.css"), "w") as f:
            f.write("x")
        self.login_as("admin")
        status, res = self.command("delete", mount="sitetheme", paths=["/old.css"])
        self.assertEqual(status, 200, res)
        self.assertEqual(os.listdir(self.site), [])
        trash = os.path.join(self.work, "wikidata", FARM, paths.PAGEINFO_DIR, "theme-trash")
        self.assertEqual(len(os.listdir(os.path.join(trash, "files"))), 1)


    def upload(self, mount, name, data):
        status, _, text = self.call("/api/v1/commands/upload/upload",
                                    f"mount={mount}&dest=/&path={name}&kind=file", "POST", raw=data)
        return status, json.loads(text)

    def test_アップロードはsitethemeにだけ出る(self):
        self.login_as("admin")
        _, _, text = self.call("/api/v1/mounts")
        commands = {m["id"]: {c["id"] for c in m["commands"]} for m in json.loads(text)}
        self.assertIn("upload", commands["sitetheme"])
        self.assertIn("drop-upload", commands["sitetheme"])
        self.assertNotIn("upload", commands["common"])
        status, res = self.upload("sitetheme", "my.css", b"body{color:red}")
        self.assertEqual(status, 200, res)
        with open(os.path.join(self.site, "my.css"), "rb") as f:
            self.assertEqual(f.read(), b"body{color:red}")
        status, _ = self.upload("common", "my.css", b"x")
        self.assertNotEqual(status, 200)
        self.assertFalse(os.path.exists(os.path.join(self.common, "my.css")))

    def test_アップロードの上限は添付と同じ(self):
        self.config = {"attach": {"max_size": "10"}}   # 10バイト
        self.login_as("admin")
        status, res = self.upload("sitetheme", "big.css", b"x" * 11)
        self.assertEqual((status, res["error"]["code"]), (413, "too_large"), res)
        status, res = self.upload("sitetheme", "ok.css", b"x" * 10)
        self.assertEqual(status, 200, res)
        self.assertEqual(sorted(os.listdir(self.site)), ["ok.css"])


    def copy_to_site(self, *paths, answer=None):
        body = {"mount": "common", "paths": list(paths)}
        if answer:
            body["answers"] = {"overwrite": answer}
        status, res = self.command("copy-to-site", **body)
        self.assertEqual(status, 200, res)
        return res["effects"]

    def test_sitethemeへコピー(self):
        os.makedirs(os.path.join(self.common, "folder", "img"))
        with open(os.path.join(self.common, "folder", "folder.html"), "w") as f:
            f.write("f")
        self.login_as("admin")
        _, _, text = self.call("/api/v1/mounts")
        commands = {m["id"]: {c["id"] for c in m["commands"]} for m in json.loads(text)}
        self.assertIn("copy-to-site", commands["common"])
        self.assertNotIn("copy-to-site", commands["sitetheme"])
        effects = self.copy_to_site("/base.css", "/folder")
        self.assertEqual(effects[0], {"do": "browse", "mount": "sitetheme", "path": "/",
                                      "target": "_self"})
        self.assertIn("2 件", effects[1]["text"])
        self.assertTrue(os.path.isfile(os.path.join(self.site, "base.css")))
        self.assertTrue(os.path.isfile(os.path.join(self.site, "folder", "folder.html")))
        self.assertTrue(os.path.isdir(os.path.join(self.site, "folder", "img")), "空のフォルダも写す")

    def test_sitethemeへコピーは同じ場所へ(self):
        os.makedirs(os.path.join(self.common, "folder"))
        with open(os.path.join(self.common, "folder", "x.css"), "w") as f:
            f.write("x")
        self.login_as("admin")
        effects = self.copy_to_site("/folder/x.css")
        self.assertEqual(effects[0]["path"], "/folder")
        self.assertTrue(os.path.isfile(os.path.join(self.site, "folder", "x.css")))

    def test_同じ名前があれば上書きを尋ねる(self):
        os.makedirs(self.site)
        with open(os.path.join(self.site, "base.css"), "w") as f:
            f.write("mine")
        self.login_as("admin")
        effects = self.copy_to_site("/base.css", "/base.html")
        self.assertEqual(effects[0]["do"], "modal")
        self.assertEqual(effects[0]["data"]["answer"], "overwrite")
        self.assertFalse(os.path.exists(os.path.join(self.site, "base.html")), "尋ねる間は何も写さない")
        # いいえ: 同じ名前のものは飛ばし、残りを写す
        effects = self.copy_to_site("/base.css", "/base.html", answer="no")
        self.assertIn("1 件は飛ばしました", effects[1]["text"])
        with open(os.path.join(self.site, "base.css")) as f:
            self.assertEqual(f.read(), "mine")
        self.assertTrue(os.path.isfile(os.path.join(self.site, "base.html")))
        # はい: 上書きし、置き換えられたほうはごみ箱へ
        self.copy_to_site("/base.css", answer="yes")
        with open(os.path.join(self.site, "base.css")) as f:
            self.assertEqual(f.read(), "body{}")
        trash = os.path.join(self.work, "wikidata", FARM, paths.PAGEINFO_DIR, "theme-trash", "files")
        self.assertEqual(len(os.listdir(trash)), 1)


    def test_テキストの編集はsitethemeにだけ出る(self):
        os.makedirs(self.site)
        with open(os.path.join(self.site, "my.css"), "w") as f:
            f.write("old")
        self.login_as("admin")
        _, _, text = self.call("/api/v1/mounts")
        commands = {m["id"]: {c["id"] for c in m["commands"]} for m in json.loads(text)}
        self.assertIn("edit-text", commands["sitetheme"])
        self.assertNotIn("edit-text", commands["common"])
        status, res = self.command("edit-text", mount="sitetheme", paths=["/my.css"], input="body{}\n")
        self.assertEqual(status, 200, res)
        with open(os.path.join(self.site, "my.css")) as f:
            self.assertEqual(f.read(), "body{}\n")
        status, _ = self.command("edit-text", mount="common", paths=["/base.css"], input="x")
        self.assertNotEqual(status, 200)
        with open(os.path.join(self.common, "base.css")) as f:
            self.assertEqual(f.read(), "body{}")


    def put_site(self, name, text="x"):
        os.makedirs(self.site, exist_ok=True)
        with open(os.path.join(self.site, name), "w") as f:
            f.write(text)

    def test_アップロードはCSSと画像だけ(self):
        self.login_as("admin")
        for name in ("a.css", "b.png", "c.JPG", "d.webp"):
            status, res = self.upload("sitetheme", name, b"x")
            self.assertEqual(status, 200, (name, res))
        for name in ("e.html", "f.js", "g.svg", "h.txt", "i.HTML", "j.html."):
            status, res = self.upload("sitetheme", name, b"{{ 1 }}")
            self.assertEqual((status, res["error"]["code"]), (403, "forbidden"), name)
        # 置けるかを先に確かめる要求（check=1）も断る
        status, _, text = self.call("/api/v1/commands/upload/upload",
                                    "mount=sitetheme&dest=/&path=k.js&kind=file&check=1&size=1",
                                    "POST", raw=b"")
        self.assertEqual(status, 403, text)
        self.assertEqual(sorted(os.listdir(self.site)), ["a.css", "b.png", "c.JPG", "d.webp"])

    def test_編集はCSSだけ(self):
        self.put_site("a.css")
        self.put_site("b.html")
        self.login_as("admin")
        entries = {e["name"]: e for e in json.loads(
            self.call("/api/v1/list", "mount=sitetheme&path=/")[2])["entries"]}
        self.assertEqual(entries["a.css"]["writeauth"], 1)
        self.assertEqual(entries["b.html"]["writeauth"], 0, "テキストの編集を出さない")
        status, res = self.command("edit-text", mount="sitetheme", paths=["/b.html"], input="{{ 1 }}")
        self.assertNotEqual(status, 200, res)
        with open(os.path.join(self.site, "b.html")) as f:
            self.assertEqual(f.read(), "x")

    def test_名前の変更でコードの拡張子にできない(self):
        for name in ("a.css", "b.html", "c.txt", "d.html"):
            self.put_site(name)
        self.login_as("admin")
        for src, new in (("/a.css", "a.html"), ("/a.css", "base.js"), ("/c.txt", "c.svg"),
                         ("/a.css", "a.HTML"), ("/c.txt", "c.html.")):
            status, res = self.command("rename", mount="sitetheme", paths=[src], input=new)
            self.assertEqual(status, 403, (src, new, res))
        for src, new in (("/b.html", "b2.html"), ("/d.html", "d.css"), ("/c.txt", "c.css")):
            status, res = self.command("rename", mount="sitetheme", paths=[src], input=new)
            self.assertEqual(status, 200, (src, new, res))
        self.assertEqual(sorted(os.listdir(self.site)), ["a.css", "b2.html", "c.css", "d.css"])

    def test_htmlは写せる(self):
        self.login_as("admin")
        status, res = self.command(
            "paste", mount="sitetheme",
            source={"mount": "common", "paths": ["/base.html"], "mode": "copy"},
            dest={"mount": "sitetheme", "path": "/"})
        self.assertEqual(status, 200, res)
        self.copy_to_site("/base.html", answer="yes")
        self.assertTrue(os.path.isfile(os.path.join(self.site, "base.html")))


    # ---- slottheme（スロット型のテーマ） ----

    def put_slot(self, name, text="x"):
        os.makedirs(self.slot, exist_ok=True)
        with open(os.path.join(self.slot, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_slothemeのアップロード(self):
        self.login_as("admin")
        for name, data in (("a.html", b'<p class="x">ok</p>'), ("a.css", b".x{color:red}"),
                           ("b.png", b"png"), ("c.woff2", b"font")):
            status, res = self.upload("slottheme", name, data)
            self.assertEqual(status, 200, (name, res))
        for name in ("d.js", "e.svg", "f.txt"):
            status, res = self.upload("slottheme", name, b"x")
            self.assertEqual((status, res["error"]["code"]), (403, "forbidden"), name)
        status, res = self.upload("slottheme", "g.html", b"<p onclick='x'>a</p><script>1</script>")
        self.assertEqual(status, 400, res)
        self.assertIn("取り除かれる", res["error"]["message"])
        status, res = self.upload("slottheme", "h.css", b"@import 'x.css'; .a{background:url(http://e/)}")
        self.assertEqual(status, 400, res)
        self.assertEqual(sorted(os.listdir(self.slot)), ["a.css", "a.html", "b.png", "c.woff2"])

    def test_slothemeの編集(self):
        self.put_slot("t.html", "<p>old</p>")
        self.put_slot("t.css", ".a{}")
        self.put_slot("i.png", "png")
        self.login_as("admin")
        entries = {e["name"]: e for e in json.loads(
            self.call("/api/v1/list", "mount=slottheme&path=/")[2])["entries"]}
        self.assertEqual((entries["t.html"]["writeauth"], entries["t.css"]["writeauth"],
                          entries["i.png"]["writeauth"]), (1, 1, 0))
        status, res = self.command("edit-text", mount="slottheme", paths=["/t.html"],
                                   input='<p data-text="site_title">new</p>')
        self.assertEqual(status, 200, res)
        status, res = self.command("edit-text", mount="slottheme", paths=["/t.css"],
                                   input=".a{x:expression(alert(1))}")
        self.assertEqual(status, 400, res)
        self.assertIn("expression", res["error"]["message"])
        with open(os.path.join(self.slot, "t.css")) as f:
            self.assertEqual(f.read(), ".a{}", "断ったら元のまま")

    def test_slothemeの名前の変更(self):
        self.put_slot("a.css", "<script>x</script>")
        self.put_slot("b.png", "png")
        self.login_as("admin")
        for src, new in (("/b.png", "b.js"), ("/b.png", "b.txt"), ("/a.css", "a.html")):
            status, res = self.command("rename", mount="slottheme", paths=[src], input=new)
            self.assertNotEqual(status, 200, (src, new, res))
        status, res = self.command("rename", mount="slottheme", paths=["/b.png"], input="logo.png")
        self.assertEqual(status, 200, res)

    def test_slothemeの新しいファイルはCSS(self):
        self.login_as("admin")
        status, res = self.command("new-file", mount="slottheme", dir="/")
        self.assertEqual(status, 200, res)
        self.assertEqual(os.listdir(self.slot), ["新しいテキスト ドキュメント.css"])

    def test_slothemeへコピー(self):
        self.login_as("admin")
        status, res = self.command("copy-to-slottheme", mount="slotcommon", paths=["/slotbase.html"])
        self.assertEqual(status, 200, res)
        self.assertEqual(res["effects"][0]["mount"], "slottheme")
        self.assertTrue(os.path.isfile(os.path.join(self.slot, "slotbase.html")))
        # Jinja2 のテンプレートは、取り除かれるものがあるので貼り付けられない
        self.write_common_jinja()
        status, res = self.command(
            "paste", mount="slottheme",
            source={"mount": "common", "paths": ["/jinja.html"], "mode": "copy"},
            dest={"mount": "slottheme", "path": "/"})
        self.assertFalse(os.path.exists(os.path.join(self.slot, "jinja.html")), res)

    def write_common_jinja(self):
        with open(os.path.join(self.common, "jinja.html"), "w", encoding="utf-8") as f:
            f.write('<script src="{{ theme_url }}/x.js"></script>{% if a %}<p>a</p>{% endif %}')


    # ---- 助手 ----

    def staff_log(self):
        return [(e["kind"], e["target"], e["actor_uid"]) for e in stafflog.entries(self.wiki_dir)]

    def test_助手に見せるもの(self):
        self.login_as("kyun")
        _, _, text = self.call("/api/v1/mounts")
        mounts = {m["id"]: m for m in json.loads(text)}
        self.assertEqual(list(mounts), ["common", "slotcommon", "slottheme"])
        self.assertNotIn("copy-to-site", {c["id"] for c in mounts["common"]["commands"]})
        self.assertIn("copy-to-slottheme", {c["id"] for c in mounts["slotcommon"]["commands"]})
        status, _, _ = self.call("/api/v1/list", "mount=sitetheme&path=/")
        self.assertNotEqual(status, 200)
        status, res = self.upload("sitetheme", "a.css", b".a{}")
        self.assertNotEqual(status, 200, res)
        status, res = self.command("copy-to-site", mount="common", paths=["/base.css"])
        self.assertNotEqual(status, 200, res)
        self.assertFalse(os.path.exists(os.path.join(self.site, "a.css")))
        self.assertFalse(os.path.exists(os.path.join(self.site, "base.css")))

    def test_助手の操作を記録する(self):
        self.login_as("kyun")
        self.assertEqual(self.upload("slottheme", "a.css", b".a{}")[0], 200)
        status, res = self.command("edit-text", mount="slottheme", paths=["/a.css"], input=".b{}")
        self.assertEqual(status, 200, res)
        status, res = self.command("rename", mount="slottheme", paths=["/a.css"], input="b.css")
        self.assertEqual(status, 200, res)
        status, res = self.command("delete", mount="slottheme", paths=["/b.css"])   # ジョブ
        self.assertEqual(status, 200, res)
        self.assertEqual([k for k, _, _ in self.staff_log()],
                         ["theme.delete", "theme.rename", "theme.edit", "theme.put"])
        self.assertTrue(all(uid == "kyun" for _, _, uid in self.staff_log()))
        edit = next(e for e in stafflog.entries(self.wiki_dir) if e["kind"] == "theme.edit")
        with open(os.path.join(stafflog.blob_dir(self.wiki_dir, edit["id"]), "before"), "rb") as f:
            self.assertEqual(f.read(), b".a{}", "編集の前の中身を控える")

    def test_管理者の操作は記録しない(self):
        self.login_as("admin")
        self.assertEqual(self.upload("slottheme", "a.css", b".a{}")[0], 200)
        self.assertEqual(self.staff_log(), [])


if __name__ == "__main__":
    unittest.main()
