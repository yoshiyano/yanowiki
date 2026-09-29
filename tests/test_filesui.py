#!/usr/bin/env python3
"""ファイル一覧（`wikilib.filesui`。webFileDir を組み込んだ `/.files/`）のテスト。

  - 閲覧の権限で絞る（読めないページ・見えるページの無いフォルダは出ない）
  - フォルダの入口（`X/index`）はフォルダの行に重ね、ファイルとしては出さない
  - Wikiの直下の入口（トップページ）は `(TopPage)` というファイルとして出す
  - 属性（タイトル・添付の数・記法）
  - 項目の権限（動かす＝名前を変えられるか。読む・書く・実行は 1）
  - ページの編集（ページのURLへ cmd=edit を POST。編集の権限が無ければ断る）
  - 削除（editor.delete_page。フォルダは中のページすべてに編集の権限・添付なしが要る）
  - 名前の変更・移動（pagerename.rename_page。動くページすべてに編集の権限が要る）。
    まとめて動かすときは、権限の無いものだけが失敗する
  - フォルダ（入口 `index` ごと、本文 `#ls()`）・ページの新規作成（Wikiの既定の記法）
  - ほかの変更の操作は断る。画面も名前の変更・新規作成のほかは出さない（features を直接渡す）
  - ページを参照できる（新しいタブでページへ移る）。フォルダは入口のページを、Shift の経路で
    （フォルダの経路を持つ webFileDir のときだけ試す）。読めないページは開けない
  - `/.files` から `/.files/` へ送る

webFileDir（paths.WEBFILEDIR_DIR）が無い環境では飛ばす。

実行:
    .venv/bin/python3 tests/test_filesui.py
"""
import io
import json
import os
import sys
import unittest
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pagelist import FARM, PageListTestBase  # noqa: E402

import bottle  # noqa: E402

from wikilib import filesui, paths  # noqa: E402
from wikilib.auth import act_as  # noqa: E402

BASE = "/=" + FARM + "/.files"


HAS_WEBFILEDIR = os.path.isfile(os.path.join(paths.WEBFILEDIR_DIR, "server", "__init__.py"))


class FilesUITestBase(PageListTestBase):
    """`/.files/` へ要求を渡す道具（試験は持たない）。"""

    def call(self, path, query="", method="GET", body=None, headers=None):
        """`/=testwiki/.files<path>` を dispatch と同じ形で渡し、(状態, ヘッダ, 本体) を返す。"""
        env = {"PATH_INFO": BASE + path, "QUERY_STRING": query, "REQUEST_METHOD": method}
        setup_testing_defaults(env)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            env.update({"CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(data)),
                        "wsgi.input": io.BytesIO(data)})
        for k, v in (headers or {}).items():
            env["HTTP_" + k.upper().replace("-", "_")] = v
        bottle.request.bind(env)
        res = filesui.serve_files(self.wiki_dir, FARM, "http://x" + BASE)
        text = b"".join(x if isinstance(x, bytes) else x.encode() for x in res.body or [])
        if hasattr(res.body, "close"):
            res.body.close()   # WSGI サーバがするのと同じく、読み終えたら閉じる
        return res.status_code, res.headers, text.decode("utf-8")

    def listing(self, folder):
        status, _, text = self.call("/api/v1/list", "mount=wiki&path=" + folder)
        self.assertEqual(status, 200, text)
        return {e["name"]: e for e in json.loads(text)["entries"]}

@unittest.skipUnless(HAS_WEBFILEDIR, "webFileDir がありません")
class TestFilesUI(FilesUITestBase):

    def test_末尾のスラッシュへ送る(self):
        status, headers, _ = self.call("")
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "http://x" + BASE + "/")

    def test_画面を返す(self):
        status, _, text = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn("<html", text.lower())

    def test_画面は変更の機能を止めて組み立てる(self):
        status, headers, text = self.call("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertIn("<title>ファイル一覧 - " + FARM + "</title>", text)
        features = json.loads(text.split("features: ", 1)[1].split(" });", 1)[0])
        self.assertEqual(features, {name: False for name in filesui.DISABLED_FEATURES})
        self.assertNotIn("dual", features)
        self.assertEqual(features, {"copy": False, "trash": False})
        # webFileDir の画面の部品と、機能の名前が食い違っていない
        with open(os.path.join(paths.WEBFILEDIR_DIR, "static", "js", "features.js"),
                  encoding="utf-8") as f:
            known = f.read()
        for name in features:
            self.assertIn(f"\n  {name}: ", known, name)

    def test_読める人には見える(self):
        with act_as("alice"):
            top = self.listing("/")
            self.assertEqual(sorted(top), ["(TopPage)", "Open", "Tech"])
            self.assertEqual(sorted(self.listing("/Tech")), ["Secret", "Sub"])

    def test_読めないページと空になるフォルダは出ない(self):
        with act_as("bob"):
            self.assertEqual(sorted(self.listing("/Tech")), ["Sub"])
        with act_as("carol"):
            self.assertIn("Locked", self.listing("/"))

    def test_入口はフォルダの行に重なる(self):
        with act_as("alice"):
            tech = self.listing("/")["Tech"]
            self.assertEqual(tech["kind"], "dir")
            self.assertEqual(tech["attrs"]["title"], "Tech/indexの題名")
            self.assertEqual(tech["extra"]["pagepath"], "Tech")
            self.assertNotIn("index", self.listing("/Tech"))
            sub = self.listing("/Tech")["Sub"]   # 通り道でしかないフォルダ
            self.assertEqual(sub["kind"], "dir")
            self.assertIsNone(sub["attrs"]["title"])
            self.assertIsNone(sub["extra"]["pagepath"])

    def test_トップページはTopPageという名前のファイル(self):
        with act_as("alice"):
            top = self.listing("/")["(TopPage)"]
            self.assertEqual(top["kind"], "file")
            self.assertEqual(top["attrs"]["title"], "indexの題名")
            self.assertEqual(top["extra"]["pagepath"], "")
            self.assertNotIn("index", self.listing("/"))
            status, _, text = self.call("/api/v1/stat", "mount=wiki&path=/(TopPage)")
            self.assertEqual(status, 200, text)
            # フォルダの中の入口は、これまでどおりフォルダの行に重なる
            self.assertNotIn("(TopPage)", self.listing("/Tech"))

    def test_詳細表示の列の順(self):
        status, _, text = self.call("/api/v1/mounts")
        self.assertEqual(status, 200, text)
        keys = [a["key"] for a in json.loads(text)[0]["attributes"]]
        self.assertEqual(keys, ["title", "mtime", "size", "attach", "markup"])

    def test_ページの属性(self):
        attach = os.path.join(os.path.dirname(self.wiki_dir), "attach", "Open")
        os.makedirs(os.path.join(attach, "kid"))   # 下のフォルダは数えない
        for name in ("a.png", "b.txt"):
            open(os.path.join(attach, name), "w").close()
        with act_as("alice"):
            page = self.listing("/")["Open"]
        self.assertEqual(page["kind"], "file")
        self.assertEqual(page["attrs"]["title"], "Openの題名")
        self.assertEqual(page["attrs"]["attach"], 2)
        self.assertEqual(page["attrs"]["markup"], paths.MARKUP_FORMATS["markdown"]["label"])
        self.assertIsInstance(page["attrs"]["mtime"], float)
        self.assertGreater(page["attrs"]["size"], 0)

    def open_page(self, path, method=None):
        body = {"mount": "wiki", "path": path}
        if method is not None:
            body["method"] = method
        status, _, text = self.call("/api/v1/open", method="POST", body=body,
                                    headers={"X-WebFileDir": "1"})
        return status, json.loads(text)

    def mount(self):
        _, _, text = self.call("/api/v1/mounts")
        return json.loads(text)[0]

    def test_ページを開く(self):
        with act_as("alice"):
            mount = self.mount()
            self.assertEqual(mount["capabilities"],
                             ["delete", "mkdir", "move", "open", "rename", "touch"])
            self.assertEqual(mount["openMethods"],
                             [{"id": "page", "label": "ページを参照", "modifier": None},
                              {"id": "edit", "label": "ページの編集", "modifier": None}])
            # 開き先は画面（…/.files/）からの相対。新しいタブで開く
            for path, url in (("/Open", "../Open"), ("/(TopPage)", "../"),
                              ("/Tech/Sub/Deep", "../Tech/Sub/Deep")):
                status, res = self.open_page(path)
                self.assertEqual(status, 200, res)
                self.assertEqual((res["action"], res["url"], res["target"]),
                                 ("navigate", url, "_blank"))

    def test_フォルダのページを参照する(self):
        with act_as("alice"):
            if "dirOpenMethods" not in self.mount():
                self.skipTest("webFileDir がフォルダの開く経路を持っていません")
            self.assertEqual(
                [(o["id"], o["label"], o["modifier"]) for o in self.mount()["dirOpenMethods"]],
                [("page", "ページを参照", "shift"), ("edit", "ページの編集", None),
                 ("tab", "新しいタブで開く", None), ("pane", "隣の画面で開く", None)])
            status, res = self.open_page("/Tech", "page")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["action"], res["url"], res["target"]),
                             ("navigate", "../Tech", "_blank"))
            # 入口の無い通り道のフォルダにはページが無い
            status, res = self.open_page("/Tech/Sub", "page")
            self.assertEqual((status, res["error"]["code"]), (404, "not_found"))
            self.assertIn("ページがありません", res["error"]["message"])
            # tab・pane は webFileDir に任せる（フォルダを表示する）
            status, res = self.open_page("/Tech/Sub", "tab")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["action"], res["target"], res["path"]),
                             ("browse", "_blank", "/Tech/Sub"))

    def test_ページの編集(self):
        with act_as("alice"):
            for path, url in (("/Open", "../Open"), ("/(TopPage)", "../"), ("/Tech", "../Tech")):
                status, res = self.open_page(path, "edit")
                self.assertEqual(status, 200, res)
                self.assertEqual(
                    (res["action"], res["url"], res["target"], res["method"], res["params"]),
                    ("navigate", url, "_blank", "POST", {"cmd": "edit"}))
            status, res = self.open_page("/Tech/Sub", "edit")   # 入口の無いフォルダ
            self.assertEqual((status, res["error"]["code"]), (404, "not_found"))
        self.rule("Open", "W", "alice")   # bob は読めるが編集できない
        with act_as("bob"):
            status, res = self.open_page("/Open", "edit")
            self.assertEqual((status, res["error"]["code"]), (403, "forbidden"))
            status, res = self.open_page("/Open", "page")   # 参照はできる
            self.assertEqual(status, 200, res)

    def test_フォルダと読めないページは開けない(self):
        with act_as("alice"):
            # 経路を言わずにフォルダは開けない（既定の「中に入る」は画面がする）
            status, res = self.open_page("/Tech")
            self.assertEqual(status, 400, res)
        with act_as("bob"):
            status, res = self.open_page("/Tech/Secret")
            self.assertEqual((status, res["error"]["code"]), (404, "not_found"))

    def auth_of(self, entry):
        return tuple(entry[k] for k in ("moveauth", "readauth", "writeauth", "execauth"))

    def test_項目の権限(self):
        with act_as("alice"):
            top = self.listing("/")
            self.assertEqual(self.auth_of(top["Open"]), (1, 1, 1, 1))
            self.assertEqual(self.auth_of(top["Tech"]), (1, 1, 1, 1))
            self.assertEqual(self.auth_of(top["(TopPage)"]), (0, 1, 1, 1))
            _, _, text = self.call("/api/v1/list", "mount=wiki&path=/")
            self.assertEqual(self.auth_of(json.loads(text)["dir"]), (0, 1, 1, 1))   # 一覧の根
        with act_as("bob"):
            # Tech を動かすと、bob が編集できない Tech/Secret も動くので動かせない
            self.assertEqual(self.auth_of(self.listing("/")["Tech"])[0], 0)
            self.assertEqual(self.auth_of(self.listing("/Tech")["Sub"])[0], 1)
            _, _, text = self.call("/api/v1/stat", "mount=wiki&path=/Tech")
            self.assertEqual(json.loads(text)["moveauth"], 0)

    def test_変更の操作は断る(self):
        headers = {"X-WebFileDir": "1"}
        with act_as("alice"):
            for op, body in (("copy", {"srcs": ["/Open"], "dest": "/Tech"}),
                             ("delete", {"paths": ["/Open"]})):   # ごみ箱へ（持たない）
                status, _, text = self.call("/api/v1/" + op, method="POST",
                                            body=dict(body, mount="wiki"), headers=headers)
                self.assertEqual(status, 403, (op, text))
        # 何も動いていない（このテストのWikiは平文を置かずDBだけなので、DBの行を見る）
        from wikilib import pagedb
        self.assertIsNotNone(pagedb.load_page(self.wiki_dir, "Open"))



@unittest.skipUnless(HAS_WEBFILEDIR, "webFileDir がありません")
class TestFilesUIRename(FilesUITestBase):
    """名前の変更。rename_page は実体のファイルを動かすので、本文も置く。"""

    def setUp(self):
        super().setUp()
        for subpath in self.PAGES:
            path = os.path.join(self.wiki_dir, subpath + ".md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("# {}の題名\n\n本文\n".format(subpath))

    def rename(self, path, new_name):
        status, _, text = self.call("/api/v1/rename", method="POST",
                                    body={"mount": "wiki", "path": path, "newName": new_name},
                                    headers={"X-WebFileDir": "1"})
        return status, json.loads(text)

    def test_更新日時とサイズはDBの値(self):
        # 更新日時・サイズは DB の値（ファイルを stat しない）。取り込む前の直接編集は、一覧には出ない
        path = os.path.join(self.wiki_dir, "Open.md")
        with open(path, "a", encoding="utf-8") as f:
            f.write("DB にはまだ取り込んでいない追記\n")
        os.utime(path, (1_700_000_000, 1_700_000_000))
        from wikilib import pagedb
        row = pagedb.load_page(self.wiki_dir, "Open")
        with act_as("alice"):
            attrs = self.listing("/")["Open"]["attrs"]
        self.assertEqual(attrs["size"], row["size"])
        self.assertNotEqual(attrs["mtime"], 1_700_000_000)

    def page_file(self, subpath):
        return os.path.isfile(os.path.join(self.wiki_dir, subpath + ".md"))

    def test_ページの名前を変える(self):
        with act_as("alice"):
            status, res = self.rename("/Open", "Opened")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["name"], res["kind"]), ("Opened", "file"))
            self.assertIn("Opened", self.listing("/"))
            self.assertNotIn("Open", self.listing("/"))
        self.assertTrue(self.page_file("Opened"))
        self.assertFalse(self.page_file("Open"))

    def test_フォルダの名前を変えると中のページごと動く(self):
        with act_as("alice"):
            status, res = self.rename("/Tech", "Tech2")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["name"], res["kind"]), ("Tech2", "dir"))
            self.assertEqual(sorted(self.listing("/Tech2")), ["Secret", "Sub"])
        for subpath in ("Tech2/index", "Tech2/Secret", "Tech2/Sub/Deep"):
            self.assertTrue(self.page_file(subpath), subpath)
        self.assertFalse(os.path.exists(os.path.join(self.wiki_dir, "Tech")))

    def test_入口の無いフォルダも動かせる(self):
        with act_as("alice"):
            status, res = self.rename("/Tech/Sub", "Sub2")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["name"], res["kind"]), ("Sub2", "dir"))
        self.assertTrue(self.page_file("Tech/Sub2/Deep"))

    def test_編集できないページが中にあれば断る(self):
        # bob には Tech/Secret が見えも書けもしない。Tech を動かすとそれも動くので断る
        with act_as("bob"):
            status, res = self.rename("/Tech", "Tech2")
            self.assertEqual((status, res["error"]["code"]), (403, "forbidden"))
            self.assertNotIn("Secret", res["error"]["message"])
        self.assertTrue(self.page_file("Tech/Secret"))

    def test_トップページは変えられない(self):
        with act_as("alice"):
            status, res = self.rename("/(TopPage)", "Top")
            self.assertEqual((status, res["error"]["code"]), (403, "forbidden"))
        self.assertTrue(self.page_file("index"))

    def test_使えない名前とぶつかる名前は断る(self):
        with act_as("alice"):
            status, res = self.rename("/Open", "a.txt")   # 拡張子の形
            self.assertEqual((status, res["error"]["code"]), (400, "bad_name"))
            status, res = self.rename("/Open", "Tech")
            self.assertEqual((status, res["error"]["code"]), (409, "exists"))
        self.assertTrue(self.page_file("Open"))


    def move(self, srcs, dest):
        status, _, text = self.call("/api/v1/move", method="POST",
                                    body={"mount": "wiki", "srcs": srcs, "dest": dest},
                                    headers={"X-WebFileDir": "1"})
        self.assertEqual(status, 200, text)
        return {r["src"]: r for r in json.loads(text)["results"]}

    def test_ページとフォルダを動かす(self):
        with act_as("alice"):
            res = self.move(["/Open", "/Tech/Sub"], "/")
            self.assertTrue(res["/Open"]["ok"], res)            # 同じ場所は何もしない
            self.assertTrue(res["/Tech/Sub"]["ok"], res)
            res = self.move(["/Open"], "/Tech")
            self.assertTrue(res["/Open"]["ok"], res)
            self.assertEqual(res["/Open"]["entry"]["name"], "Open")
            self.assertIn("Open", self.listing("/Tech"))
            self.assertIn("Sub", self.listing("/"))
        self.assertTrue(self.page_file("Tech/Open"))
        self.assertTrue(self.page_file("Sub/Deep"))
        self.assertFalse(self.page_file("Open"))

    def test_まとめて動かすと権限の無いものだけ失敗する(self):
        self.rule("Open", "W", "alice")   # bob は読めるが編集できない
        with act_as("bob"):
            self.assertEqual(self.auth_of(self.listing("/")["Open"])[0], 0)
            res = self.move(["/Open", "/Tech/Sub/Deep"], "/Tech")
            self.assertFalse(res["/Open"]["ok"])
            self.assertEqual(res["/Open"]["error"]["code"], "forbidden")
            self.assertTrue(res["/Tech/Sub/Deep"]["ok"], res)
        self.assertTrue(self.page_file("Open"))
        self.assertTrue(self.page_file("Tech/Deep"))

    def test_動かせないもの(self):
        with act_as("alice"):
            res = self.move(["/(TopPage)", "/Tech", "/Open"], "/Tech/Sub")
            self.assertEqual(res["/(TopPage)"]["error"]["code"], "forbidden")
            self.assertEqual(res["/Tech"]["error"]["code"], "into_self")
            self.assertTrue(res["/Open"]["ok"], res)
            # 同じ名前があれば exists（webFileDir の on_conflict の既定は error）
            res = self.move(["/Tech/Sub/Open"], "/Tech")
            self.assertTrue(res["/Tech/Sub/Open"]["ok"], res)
            self.put_page("Tech/Sub/Open")
            res = self.move(["/Tech/Sub/Open"], "/Tech")
            self.assertEqual(res["/Tech/Sub/Open"]["error"]["code"], "exists")

    def delete(self, paths):
        status, _, text = self.call("/api/v1/delete", method="POST",
                                    body={"mount": "wiki", "paths": paths, "permanent": True},
                                    headers={"X-WebFileDir": "1"})
        self.assertEqual(status, 200, text)
        return {r["src"]: r for r in json.loads(text)["results"]}

    def test_ページを消す(self):
        with act_as("alice"):
            res = self.delete(["/Open"])
            self.assertTrue(res["/Open"]["ok"], res)
            self.assertNotIn("Open", self.listing("/"))
        self.assertFalse(self.page_file("Open"))
        # 消す前の内容は「全文→空」の差分として残る
        from wikilib import backup
        con = backup.connect(self.wiki_dir)
        try:
            diff = backup._rows_of(con, "Open")[-1]["diff"]
        finally:
            con.close()
        self.assertIn("-# Openの題名", diff)

    def test_フォルダは中のページごと消す(self):
        with act_as("alice"):
            res = self.delete(["/Tech"])
            self.assertTrue(res["/Tech"]["ok"], res)
            self.assertNotIn("Tech", self.listing("/"))
        for subpath in ("Tech/index", "Tech/Secret", "Tech/Sub/Deep"):
            self.assertFalse(self.page_file(subpath), subpath)
        self.assertFalse(os.path.exists(os.path.join(self.wiki_dir, "Tech")))
        self.assertTrue(self.page_file("Open"))

    def test_消せないものと_まとめて消すと失敗したものだけ残る(self):
        self.rule("Open", "W", "alice")   # bob は読めるが編集できない
        with act_as("bob"):
            res = self.delete(["/Open", "/Tech", "/(TopPage)", "/Tech/Sub/Deep"])
            self.assertEqual(res["/Open"]["error"]["code"], "forbidden")
            # 見えない Tech/Secret を含むので、フォルダごと断る（名前は言わない）
            self.assertEqual(res["/Tech"]["error"]["code"], "forbidden")
            self.assertNotIn("Secret", res["/Tech"]["error"]["message"])
            self.assertEqual(res["/(TopPage)"]["error"]["code"], "forbidden")
            self.assertTrue(res["/Tech/Sub/Deep"]["ok"], res)
        for subpath in ("Open", "Tech/index", "Tech/Secret", "index"):
            self.assertTrue(self.page_file(subpath), subpath)
        self.assertFalse(self.page_file("Tech/Sub/Deep"))

    def test_添付のあるページは消さない(self):
        attach = os.path.join(os.path.dirname(self.wiki_dir), "attach", "Tech", "Sub", "Deep")
        os.makedirs(attach)
        open(os.path.join(attach, "a.png"), "w").close()
        with act_as("alice"):
            res = self.delete(["/Tech"])
            self.assertEqual(res["/Tech"]["error"]["code"], "bad_request")
            self.assertIn("添付", res["/Tech"]["error"]["message"])
        for subpath in ("Tech/index", "Tech/Secret", "Tech/Sub/Deep"):
            self.assertTrue(self.page_file(subpath), subpath)

    def put_page(self, subpath):
        path = os.path.join(self.wiki_dir, subpath + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("本文\n")
        from wikilib.pagesave import save_page
        save_page(self.wiki_dir, {}, subpath, ".md", "本文\n", write=False)

    def auth_of(self, entry):
        return tuple(entry[k] for k in ("moveauth", "readauth", "writeauth", "execauth"))


@unittest.skipUnless(HAS_WEBFILEDIR, "webFileDir がありません")
class TestFilesUICreate(FilesUITestBase):
    """フォルダ・ページの新規作成。"""

    def create(self, op, parent, name=None):
        body = {"mount": "wiki", "parent": parent}
        if name is not None:
            body["name"] = name
        status, _, text = self.call("/api/v1/" + op, method="POST", body=body,
                                    headers={"X-WebFileDir": "1"})
        return status, json.loads(text)

    def ext(self):
        from wikilib.paths import default_markup_ext
        from wikilib.wikiconfig import default_markup, load_wiki_config
        return default_markup_ext(default_markup(load_wiki_config(self.wiki_dir)))

    def body_of(self, subpath):
        with open(os.path.join(self.wiki_dir, subpath + self.ext()), encoding="utf-8") as f:
            return f.read()

    def test_フォルダは入口のページごと作る(self):
        with act_as("alice"):
            status, res = self.create("mkdir", "/")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["name"], res["kind"]), ("新しいフォルダ", "dir"))
            self.assertEqual(self.body_of("新しいフォルダ/index"), filesui.NEW_FOLDER_BODY)
            self.assertEqual(self.body_of("新しいフォルダ/index"), "#ls()\n")
            self.assertIn("新しいフォルダ", self.listing("/"))
            # 入口のページがあるので、フォルダからページを参照できる
            self.assertEqual(self.listing("/")["新しいフォルダ"]["extra"]["pagepath"], "新しいフォルダ")
            status, res = self.create("mkdir", "/")
            self.assertEqual(res["name"], "新しいフォルダ (2)")
            status, res = self.create("mkdir", "/Tech", "Docs")
            self.assertEqual((status, res["name"]), (200, "Docs"))
            self.assertEqual(sorted(self.listing("/Tech/Docs")), [])

    def test_ページを作る(self):
        with act_as("alice"):
            # webFileDir の既定の名前（拡張子付き）は「新しいページ」に置き換える
            status, res = self.create("touch", "/Tech")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["name"], res["kind"]), ("新しいページ", "file"))
            self.assertEqual(self.body_of("Tech/新しいページ"), filesui.NEW_PAGE_BODY)
            self.assertIsNone(res["attrs"]["title"])   # 見出しが無いのでタイトルはページ名
            status, res = self.create("touch", "/Tech")
            self.assertEqual(res["name"], "新しいページ (2)")
            status, res = self.create("touch", "/", "Memo")
            self.assertEqual((status, res["name"]), (200, "Memo"))
            self.assertIn("Memo", self.listing("/"))

    def test_ぶつかる名前と使えない名前は断る(self):
        with act_as("alice"):
            for op, parent, name, code in (("touch", "/", "Open", "exists"),
                                           ("mkdir", "/", "Tech", "exists"),
                                           ("touch", "/", "(TopPage)", "exists"),
                                           ("touch", "/", "a.txt", "bad_name"),
                                           ("mkdir", "/", ".x", "bad_name"),
                                           ("touch", "/Open", "X", "bad_path")):
                status, res = self.create(op, parent, name)
                self.assertEqual(res["error"]["code"], code, (op, parent, name, res))
        with act_as("bob"):
            # bob には見えないページでも、名前はふさがっている
            status, res = self.create("touch", "/Tech", "Secret")
            self.assertEqual(res["error"]["code"], "exists")

    def test_編集できない場所には作らない(self):
        self.rule("Tech/Blocked", "R", "alice")
        with act_as("bob"):
            status, res = self.create("mkdir", "/Tech", "Blocked")
            self.assertEqual((status, res["error"]["code"]), (403, "forbidden"))
        self.assertFalse(os.path.exists(os.path.join(self.wiki_dir, "Tech", "Blocked")))


if __name__ == "__main__":
    unittest.main()
