#!/usr/bin/env python3
"""ファイル一覧（`wikilib.filesui`。webFileDir を組み込んだ `/.files/`）のテスト。

  - 閲覧の権限で絞る（読めないページ・見えるページの無いフォルダは出ない）
  - フォルダの入口（`X/index`）はフォルダの行に重ね、ファイルとしては出さない
  - Wikiの直下の入口（トップページ）は `(TopPage)` というファイルとして出す
  - 属性（タイトル・添付の数・書きかた）
  - 項目の権限（動かす＝名前を変えられるか。読む・書く・実行は 1）
  - ページの編集（ページのURLへ cmd=edit を POST。編集の権限が無ければ断る）
  - 削除（editor.delete_page。添付は trashbox へ移す。フォルダは中のページすべてに編集の権限が要る）
  - 名前の変更・移動（pagerename.rename_page。動くページすべてに編集の権限が要る）。
    まとめて動かすときは、権限の無いものだけが失敗する
  - フォルダ（入口 `index` ごと、本文 `#ls()`）・ページの新規作成（Wikiの既定の書きかた）
  - 持たない操作（ごみ箱）のコマンドは宣言せず、直接呼んでも断る
  - コピー（アクセス制限・添付・リンクも写す。読めないページを含むものは写さない）
  - ページを参照できる（新しいタブでページへ移る）。ファイルはダブルクリック、フォルダは
    Shift で入口のページを（独自のコマンド page・dir-page）。読めないページは開けない
  - 新しいタブで開く（既定の tab の代わりの new-tab）。ページ名から拡張子を切り出さない
  - ジョブで行う削除・移動でも、要求の閲覧者の権限で行う（auth.fix_viewer）
  - `/.files` から `/.files/` へ送る
  - フォルダ化（`X` → `X/index`。URL はそのまま。権限の無いものだけ飛ばす）

webFileDir 1.0 の API（操作はすべて `POST commands/<id>`。削除・移動はジョブ）で呼ぶ。

webFileDir（paths.WEBFILEDIR_DIR）が無い環境では飛ばす。

実行:
    _venv/bin/python3 tests/test_filesui.py
"""
import io
import json
import os
import sys
import time
import unittest
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pagelist import FARM, PageListTestBase  # noqa: E402

import bottle  # noqa: E402

from wikilib import filesui, paths  # noqa: E402
from wikilib.auth import act_as  # noqa: E402

BASE = "/=" + FARM + "/.files"


HAS_WEBFILEDIR = os.path.isfile(os.path.join(paths.WEBFILEDIR_DIR, "server", "__init__.py"))
# 削除の前の問い返し（webFileDir 1.2.0 から）を知っている版か
BEFORE_DELETE = bool(HAS_WEBFILEDIR and filesui._webfiledir()
                     and "before_delete" in filesui._webfiledir()["app"].KNOWN_CAPABILITIES)


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

    def command(self, cid, **body):
        """`POST commands/<cid>` を送り、(状態, 応答) を返す。ジョブなら終わるまで待ち、
        ふつうに行ったときと同じ形（成功なら result・results・effects、誤りなら error）で返す。"""
        status, _, text = self.call("/api/v1/commands/" + cid, method="POST",
                                    body=dict(body, mount="wiki"),
                                    headers={"X-WebFileDir": "1"})
        res = json.loads(text)
        if status != 200 or "job" not in res:
            return status, res
        for _ in range(200):
            _, _, text = self.call("/api/v1/jobs/" + res["job"])
            job = json.loads(text)
            if job["state"] == "done":
                if "error" in job:   # ジョブの error は中身だけ。ふつうの応答の形に包む
                    return job["status"], {"error": job["error"]}
                return 200, job["result"]
            time.sleep(0.02)
        self.fail("ジョブが終わりません: " + cid)

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

    def test_画面はWikiの名前で組み立てる(self):
        status, headers, text = self.call("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertIn("<title>ファイル一覧 - " + FARM + "</title>", text)
        # 出す操作はコマンドの宣言で決まるので、画面には機能の ON/OFF を渡さない
        self.assertIn("createShell(app);", text)

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

    def open_page(self, path, cid="page"):
        """独自のコマンド（page・dir-page・edit・new-tab）を1つの項目に送る。"""
        status, res = self.command(cid, paths=[path])
        if status == 200:
            return status, res["effects"][0]
        return status, res

    def mount(self):
        _, _, text = self.call("/api/v1/mounts")
        return json.loads(text)[0]

    def test_ページを開く(self):
        with act_as("alice"):
            commands = {c["id"]: c for c in self.mount()["commands"]}
            self.assertEqual((commands["page"]["label"], commands["page"]["open"]),
                             ("ページを参照", "default"))
            self.assertEqual(commands["edit"]["label"], "ページの編集")
            # 開き先は画面（…/.files/）からの相対。新しいタブで開く
            for path, url in (("/Open", "../Open"), ("/(TopPage)", "../"),
                              ("/Tech/Sub/Deep", "../Tech/Sub/Deep")):
                status, res = self.open_page(path)
                self.assertEqual(status, 200, res)
                self.assertEqual((res["do"], res["url"], res["target"]),
                                 ("navigate", url, "_blank"))

    def test_フォルダのページを参照する(self):
        with act_as("alice"):
            commands = {c["id"]: c for c in self.mount()["commands"]}
            # フォルダは Shift で入口のページを参照する。既定の tab（Shift を使う）は止めて、
            # Shift を使わない new-tab に作り直す
            self.assertEqual((commands["dir-page"]["label"], commands["dir-page"]["open"]),
                             ("ページを参照", "shift"))
            self.assertNotIn("tab", commands)
            self.assertIsNone(commands["new-tab"].get("open"))
            self.assertIn("pane", commands)
            status, res = self.open_page("/Tech", "dir-page")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["do"], res["url"], res["target"]),
                             ("navigate", "../Tech", "_blank"))
            # 入口の無い通り道のフォルダにはページが無い
            status, res = self.open_page("/Tech/Sub", "dir-page")
            self.assertEqual((status, res["error"]["code"]), (404, "not_found"))
            self.assertIn("ページがありません", res["error"]["message"])
            # 新しいタブで開く（フォルダを表示する）
            status, res = self.open_page("/Tech/Sub", "new-tab")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["do"], res["target"], res["path"]),
                             ("browse", "_blank", "/Tech/Sub"))

    def test_ページの編集(self):
        with act_as("alice"):
            for path, url in (("/Open", "../Open"), ("/(TopPage)", "../"), ("/Tech", "../Tech")):
                status, res = self.open_page(path, "edit")
                self.assertEqual(status, 200, res)
                self.assertEqual(
                    (res["do"], res["url"], res["target"], res["method"], res["params"]),
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
            # page はファイルのコマンド（フォルダの既定の「中に入る」は画面がする）
            status, res = self.open_page("/Tech")
            self.assertEqual((status, res["error"]["code"]), (403, "forbidden"))
        with act_as("bob"):
            status, res = self.open_page("/Tech/Secret")
            self.assertEqual(status // 100, 4, res)
            self.assertIn(res["error"]["code"], ("not_found", "forbidden"))

    def test_ページ名から拡張子を切り出さない(self):
        from wikilib import pagedb
        pagedb.record_page(self.wiki_dir, "ver.0/index", ".md", "# ver.0\n")
        with act_as("alice"):
            entries = self.listing("/")
        self.assertEqual(entries["ver.0"]["ext"], "")
        self.assertEqual(entries["Open"]["ext"], "")

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

    def test_持たない操作は宣言せず断る(self):
        with act_as("alice"):
            commands = {c["id"] for c in self.mount()["commands"]}
            # アップロードはページに当たらないので出ない（プロバイダが stream を持たない）
            for cid in ("drop-trash", "restore", "trash-purge", "trash-empty", "tab",
                        "upload", "drop-upload", "edit-text"):
                self.assertNotIn(cid, commands)
            for cid in ("copy", "paste", "drop-copy"):   # コピーは持つ（2026-10-02）
                self.assertIn(cid, commands)
            for cid, body in (("restore", {"ids": ["x"]}),
                              ("tab", {"paths": ["/Tech"]})):
                status, res = self.command(cid, **body)
                self.assertEqual((status, res["error"]["code"]), (403, "forbidden"), cid)
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
        status, res = self.command("rename", paths=[path], input=new_name)
        return status, res.get("result", res)

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

    def test_名前の前後の空白は落とす(self):
        # 末尾に空白のある名前で、変更は済んだのに 404 を返していた（2026-10-01）
        with act_as("alice"):
            status, res = self.rename("/Tech", "Tech2 ")
            self.assertEqual(status, 200, res)
            self.assertEqual((res["name"], res["kind"]), ("Tech2", "dir"))
            self.assertIn("Tech2", self.listing("/"))
        self.assertTrue(self.page_file("Tech2/index"))

    def test_名前の変更はジョブで行う(self):
        with act_as("alice"):
            _, _, text = self.call("/api/v1/mounts")
            commands = {c["id"]: c for c in json.loads(text)[0]["commands"]}
        self.assertTrue(commands["rename"]["job"])
        self.assertEqual(commands["rename"]["input"]["part"], "inlineEdit")
        self.assertTrue(commands["resume"]["job"])

    def stop_at_once(self):
        """1回で続ける時間の上限を 0 にして、名前の変更をすぐ止まるようにする。"""
        from wikilib import operations
        kept = operations.TIME_LIMIT
        operations.TIME_LIMIT = 0
        self.addCleanup(setattr, operations, "TIME_LIMIT", kept)
        return lambda: setattr(operations, "TIME_LIMIT", kept)

    def test_止まった名前の変更を続ける(self):
        restore = self.stop_at_once()
        with act_as("alice"):
            status, res = self.rename("/Tech", "Tech2")
            self.assertEqual((status, res["error"]["code"]), (409, "cancelled"))
            self.assertIn("中断した操作を続ける", res["error"]["message"])
            # 中断中は、範囲が重なる名前の変更・削除を断る
            status, res = self.rename("/Tech", "Tech3")
            self.assertEqual(status // 100, 4, res)
            res = self.delete(["/Tech"])
            self.assertIn("中断している名前の変更", res["/Tech"]["error"]["message"])
            restore()
            status, res = self.command("resume")
            self.assertEqual(status, 200, res)
            self.assertIn("1 件", res["effects"][0]["text"])
            self.assertIn("Tech2", self.listing("/"))
            self.assertNotIn("Tech", self.listing("/"))
            # もう中断している操作は無い
            status, res = self.command("resume")
            self.assertEqual(res["effects"][0]["text"], "中断している操作はありません。")
        for subpath in ("Tech2/index", "Tech2/Secret", "Tech2/Sub/Deep"):
            self.assertTrue(self.page_file(subpath), subpath)

    def test_動くページを編集できない人は続けられない(self):
        from wikilib import operations
        restore = self.stop_at_once()
        with act_as("alice"):
            status, res = self.rename("/Tech", "Tech2")
            self.assertEqual(status, 409, res)
        restore()
        with act_as("bob"):   # Tech2/Secret を編集できない
            status, res = self.command("resume")
            self.assertIn("続ける権限の無い操作が 1 件", res["effects"][0]["text"])
        self.assertEqual(len(operations.unfinished(self.wiki_dir)), 1)

    def test_使えない名前とぶつかる名前は断る(self):
        with act_as("alice"):
            status, res = self.rename("/Open", "a.txt")   # 拡張子の形
            self.assertEqual((status, res["error"]["code"]), (400, "bad_name"))
            status, res = self.rename("/Open", "Tech")
            self.assertEqual((status, res["error"]["code"]), (409, "exists"))
        self.assertTrue(self.page_file("Open"))


    def move(self, srcs, dest):
        """ドロップでの移動（ジョブ）。項目ごとの結果を元のパスで引けるようにして返す。"""
        status, res = self.command("drop-move",
                                   source={"mount": "wiki", "paths": srcs, "mode": "cut"},
                                   dest={"mount": "wiki", "path": dest})
        self.assertEqual(status, 200, res)
        return {r["src"]: r for r in res["results"]}

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

    def delete(self, paths, reply="yes"):
        """削除（ごみ箱が無いので完全に削除。ジョブ）。項目ごとの結果を元のパスで引けるようにして返す。

        サーバが［はい］［いいえ］を尋ねてきたら（webFileDir 1.2.0 から。添付の問い返し・既定の
        確認）、画面と同じく reply を答えて送り直す。尋ねられた文は self.asked に残す。"""
        self.asked, answers = [], {}
        for _ in range(5):
            status, res = self.command("delete", paths=paths, answers=answers)
            self.assertEqual(status, 200, res)
            ask = [e["data"] for e in res.get("effects", [])
                   if e.get("do") == "modal" and e["data"].get("type") == "yesno"]
            if not ask:
                break
            self.asked.append(ask[0])
            answers = dict(answers, **{ask[0]["answer"]: reply})
        return {r["src"]: r for r in res.get("results", [])}

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

    def test_ジョブの削除はcookieの閲覧者の権限で行う(self):
        # 削除はジョブ（別のスレッド）で行われ、そこでは cookie が読めない。要求の中で
        # 判定した閲覧者を固定して渡す（auth.fix_viewer）。act_as を使わず cookie で試す
        from wikilib import auth, userdb
        from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name
        user = userdb.find_by_uid(self.wiki_dir, "alice")
        token = auth.session_token("alice", FARM, user["pw"])
        cookie = (f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}=alice; "
                  f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")
        call = self.call
        self.call = lambda *a, **k: call(*a, **dict(k, headers=dict(k.get("headers") or {},
                                                                      Cookie=cookie)))
        try:
            res = self.delete(["/Tech/Secret"])   # alice だけが読める
        finally:
            self.call = call
        self.assertTrue(res["/Tech/Secret"]["ok"], res)
        self.assertFalse(self.page_file("Tech/Secret"))

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

    def test_添付はtrashboxへ移して消す(self):
        # 編集画面で本文を空にして保存したときと同じ決まり（editor.delete_page）。フォルダを
        # 消したときは、ページの無い下位フォルダに置いた添付も移す
        att = os.path.join(os.path.dirname(self.wiki_dir), "attach")
        for rel in ("Tech/Sub/Deep/a.png", "Tech/NoPage/n.png"):
            os.makedirs(os.path.dirname(os.path.join(att, rel)), exist_ok=True)
            open(os.path.join(att, rel), "w").close()
        with act_as("alice"):
            res = self.delete(["/Tech"])
            self.assertTrue(res["/Tech"]["ok"], res)
        for subpath in ("Tech/index", "Tech/Secret", "Tech/Sub/Deep"):
            self.assertFalse(self.page_file(subpath), subpath)
        self.assertFalse(os.path.exists(os.path.join(att, "Tech")))
        self.assertEqual(sorted(os.listdir(os.path.join(att, "trashbox"))),
                         ["Tech_NoPage__n.png", "Tech_Sub_Deep__a.png"])

    def put_attach(self, rel):
        path = os.path.join(os.path.dirname(self.wiki_dir), "attach", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        return path

    def asks_attach(self):
        return [a for a in self.asked if a["answer"] == filesui.TRASH_ATTACH_ANSWER]

    @unittest.skipUnless(BEFORE_DELETE, "before_delete を知らない webFileDir です")
    def test_添付があれば尋ね_はいなら消す(self):
        self.put_attach("Open/a.png")
        with act_as("alice"):
            res = self.delete(["/Open"])
        self.assertTrue(res["/Open"]["ok"], res)
        self.assertEqual([a["message"] for a in self.asks_attach()],
                         [filesui.TRASH_ATTACH_QUESTION])
        self.assertEqual(len(self.asked), 1, "既定の確認は重ねない")
        self.assertFalse(self.page_file("Open"))

    @unittest.skipUnless(BEFORE_DELETE, "before_delete を知らない webFileDir です")
    def test_添付があって_いいえなら消さない(self):
        path = self.put_attach("Open/a.png")
        with act_as("alice"):
            res = self.delete(["/Open"], reply="no")
        self.assertEqual(res, {})
        self.assertTrue(self.page_file("Open"))
        self.assertTrue(os.path.isfile(path))

    @unittest.skipUnless(BEFORE_DELETE, "before_delete を知らない webFileDir です")
    def test_フォルダはページの無い下位フォルダの添付でも尋ねる(self):
        self.put_attach("Tech/NoPage/n.png")
        with act_as("alice"):
            self.delete(["/Tech"], reply="no")
        self.assertTrue(self.asks_attach())
        self.assertTrue(self.page_file("Tech/index"))

    @unittest.skipUnless(BEFORE_DELETE, "before_delete を知らない webFileDir です")
    def test_添付が無ければ既定の確認だけ(self):
        with act_as("alice"):
            self.delete(["/Open"])
        self.assertFalse(self.asks_attach())
        self.assertEqual([a["answer"] for a in self.asked], ["confirmDelete"])

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
        """新しいフォルダ（mkdir）・新しいページ（touch）。成功なら作った項目を返す。"""
        cid = {"mkdir": "new-folder", "touch": "new-file"}[op]
        body = {"dir": parent}
        if name is not None:
            body["input"] = name
        status, res = self.command(cid, **body)
        return status, res.get("result", res)

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

    def test_名前の前後の空白は落として作る(self):
        with act_as("alice"):
            status, res = self.create("mkdir", "/Tech", " Docs ")
            self.assertEqual((status, res["name"]), (200, "Docs"), res)
            self.assertIn("Docs", self.listing("/Tech"))

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
                                           # ページ（ファイル）の中には作れない。webFileDir 1.0 は
                                           # プロバイダを呼ぶ前に「その場所に書く権限が無い」と断る
                                           ("touch", "/Open", "X", "forbidden")):
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



@unittest.skipUnless(HAS_WEBFILEDIR, "webFileDir がありません")
class TestFilesUICopy(FilesUITestBase):
    """コピー（wikilib.pagecopy）。webFileDir の既定の貼り付け・ドロップから呼ぶ。"""

    def setUp(self):
        super().setUp()
        bodies = {"Open": "# Open\n\n[tech](/Tech) [sub](./Kid) ![a](a.png)\n",
                  "Tech/index": "# Tech\n\n[secret](/Tech/Secret) [deep](./Sub/Deep)\n"}
        for subpath in self.PAGES:
            path = os.path.join(self.wiki_dir, subpath + ".md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(bodies.get(subpath, "# {}の題名\n\n本文\n".format(subpath)))
        attach = os.path.join(os.path.dirname(self.wiki_dir), "attach", "Open")
        os.makedirs(attach)
        with open(os.path.join(attach, "a.png"), "wb") as f:
            f.write(b"png")
        from wikilib.pagesync import sync_wiki
        sync_wiki(self.wiki_dir, {})

    def paste(self, srcs, dest):
        status, res = self.command("paste", source={"mount": "wiki", "paths": srcs, "mode": "copy"},
                                   dest={"mount": "wiki", "path": dest})
        self.assertEqual(status, 200, res)
        return {r["src"]: r for r in res["results"]}

    def read(self, subpath):
        with open(os.path.join(self.wiki_dir, subpath + ".md"), encoding="utf-8") as f:
            return f.read()

    def test_ページを写す(self):
        with act_as("alice"):
            res = self.paste(["/Open"], "/Tech")
            self.assertTrue(res["/Open"]["ok"], res)
            self.assertIn("Open", self.listing("/Tech"))
            self.assertIn("Open", self.listing("/"))   # 元は残る
        # 写したページのリンクは、写し先から同じページを指す（書きかたは近さで選び直す。
        # Tech/Open から /Tech は「..」、元の ./Kid（/Open/Kid）は絶対に）
        body = self.read("Tech/Open")
        self.assertIn("[tech](..)", body)
        self.assertIn("[sub](/Open/Kid)", body)
        self.assertEqual(self.read("Open"), "# Open\n\n[tech](/Tech) [sub](./Kid) ![a](a.png)\n")
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(self.wiki_dir), "attach",
                                                    "Tech", "Open", "a.png")))

    def test_アクセス制限も写す(self):
        self.rule("Open", "R", "alice")   # alice だけが読める
        with act_as("alice"):
            res = self.paste(["/Open"], "/Tech")
            self.assertTrue(res["/Open"]["ok"], res)
        from wikilib import pagelist
        with act_as("bob"):
            self.assertEqual(pagelist.judge_for(self.wiki_dir).check("Tech/Open"), "-")

    def test_フォルダを中のページごと写す(self):
        with act_as("alice"):
            status, res = self.command("drop-copy",
                                       source={"mount": "wiki", "paths": ["/Tech"], "mode": "copy"},
                                       dest={"mount": "wiki", "path": "/Tech/Sub"})
            self.assertEqual(res["results"][0]["error"]["code"], "into_self", res)
            self.paste(["/Tech"], "/Tech/Sub")   # 貼り付けでも同じく自分の中へは写さない
            self.assertNotIn("Tech", self.listing("/Tech/Sub"))
            os.makedirs(os.path.join(self.wiki_dir, "Box"))
            with open(os.path.join(self.wiki_dir, "Box", "index.md"), "w", encoding="utf-8") as f:
                f.write("# Box\n")
            from wikilib.pagesync import sync_wiki
            sync_wiki(self.wiki_dir, {})
            res = self.paste(["/Tech"], "/Box")
            self.assertTrue(res["/Tech"]["ok"], res)
        for subpath in ("Box/Tech/index", "Box/Tech/Secret", "Box/Tech/Sub/Deep"):
            self.assertTrue(os.path.isfile(os.path.join(self.wiki_dir, subpath + ".md")), subpath)
        # 写したページどうしのリンクは写しを指す（/Tech/Secret は写しの Box/Tech/Secret へ。
        # Box/Tech から近いので「./Secret」と書く）
        body = self.read("Box/Tech/index")
        self.assertIn("[secret](./Secret)", body)
        self.assertIn("[deep](./Sub/Deep)", body)

    def test_読めないページを含むものは写さない(self):
        with act_as("bob"):   # Tech/Secret は bob に見えない
            res = self.paste(["/Tech"], "/")
        self.assertIn("/Tech", res)
        self.assertFalse(res["/Tech"]["ok"])

    def test_名前がぶつかれば尋ねる_トップページは写さない(self):
        with act_as("alice"):
            # 同じフォルダへは「- コピー」を付けて写す（webFileDir の既定。エクスプローラーと同じ）
            res = self.paste(["/Open"], "/")
            self.assertEqual(res["/Open"]["entry"]["name"], "Open - コピー")
            self.assertTrue(res["/Open"]["ok"], res)
            res = self.paste(["/Open"], "/Tech")
            self.assertTrue(res["/Open"]["ok"], res)
            res = self.paste(["/Open"], "/Tech")   # 2回目はぶつかる（画面は上書きなどを尋ねる）
            self.assertEqual(res["/Open"]["error"]["code"], "exists")
            res = self.paste(["/(TopPage)"], "/Tech")
            self.assertEqual(res["/(TopPage)"]["error"]["code"], "forbidden")


@unittest.skipUnless(HAS_WEBFILEDIR, "webFileDir がありません")
class TestFilesUINumbering(FilesUITestBase):
    """見出し連番（webFileDir の見本 numbering に従う）。"""

    NAMES = ("いち", "に", "05.さん")

    def setUp(self):
        super().setUp()
        for name in self.NAMES:
            path = os.path.join(self.wiki_dir, "Ch", name + ".md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {name}\n\n[次](/Ch/に)\n")
        from wikilib.pagesync import sync_wiki
        sync_wiki(self.wiki_dir, {})

    def numbering(self, names, start):
        return self.command("page-numbering", paths=["/Ch/" + n for n in names], input=start)

    def test_宣言(self):
        with act_as("alice"):
            _, _, text = self.call("/api/v1/mounts")
        cmd = {c["id"]: c for c in json.loads(text)[0]["commands"]}["page-numbering"]
        self.assertEqual((cmd["label"], cmd["input"]["part"], cmd["input"]["value"]),
                         ("見出し連番", "prompt", "001"))
        self.assertTrue(cmd["job"])

    def test_送られた順に番号を振る(self):
        with act_as("alice"):
            status, res = self.numbering(["に", "いち", "05.さん"], "01")
            self.assertEqual(status, 200, res)
            self.assertEqual(res["effects"][0]["text"], "3 個の項目に番号を付けました。")
            self.assertEqual(sorted(self.listing("/Ch")), ["01.に", "02.いち", "03.さん"])
            self.assertEqual(res["effects"][1]["select"], ["01.に", "02.いち", "03.さん"])
        # 名前の変更と同じくリンクも直る
        with open(os.path.join(self.wiki_dir, "Ch", "02.いち.md"), encoding="utf-8") as f:
            self.assertIn("01.に", f.read())

    def test_桁あふれと振り直し(self):
        with act_as("alice"):
            self.numbering(["いち", "に"], "99")
            self.assertIn("100.に", self.listing("/Ch"))
            # 選んだもの同士で入れ替わる（99.いち → 01 の次…）
            status, res = self.numbering(["100.に", "99.いち"], "99")
            self.assertEqual(status, 200, res)
            self.assertEqual(sorted(n for n in self.listing("/Ch") if n[0].isdigit()),
                             ["05.さん", "100.いち", "99.に"])

    def test_開始値の誤りはフォームに戻す(self):
        with act_as("alice"):
            for bad in ("", "abc", "1a", "-1", "１"):
                status, res = self.numbering(["いち"], bad)
                self.assertEqual((status, res["error"]["code"]), (400, "bad_input"), bad)
        self.assertIn("いち", self.listing("/Ch"))

    def test_選んでいない項目とぶつかる名前は付けない(self):
        # 選んでいない項目とぶつかる名前は付けない（05.さん → 02.さん は、別にある 02.さん とぶつかる）
        with open(os.path.join(self.wiki_dir, "Ch", "02.さん.md"), "w", encoding="utf-8") as f:
            f.write("# 別の 02.さん\n")
        from wikilib.pagesync import sync_wiki
        sync_wiki(self.wiki_dir, {})
        with act_as("alice"):
            status, res = self.numbering(["05.さん"], "02")
            self.assertIn("05.さん（«02.さん» はすでにあります）", res["effects"][0]["text"])
            self.assertIn("05.さん", self.listing("/Ch"))


@unittest.skipUnless(HAS_WEBFILEDIR, "webFileDir がありません")
class TestFilesUIFolderize(FilesUITestBase):
    """フォルダ化（ページ `X` を入口 `X/index` へ移してフォルダにする）。"""

    def setUp(self):
        super().setUp()
        for subpath in self.PAGES:
            path = os.path.join(self.wiki_dir, subpath + ".md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("# {}の題名\n\n[隣](./Sub)\n".format(subpath))

    def folderize(self, paths):
        return self.command("page-to-folder", paths=paths)

    def page_file(self, subpath):
        return os.path.isfile(os.path.join(self.wiki_dir, subpath + ".md"))

    def test_宣言(self):
        with act_as("alice"):
            _, _, text = self.call("/api/v1/mounts")
        cmd = {c["id"]: c for c in json.loads(text)[0]["commands"]}["page-to-folder"]
        self.assertEqual((cmd["label"], cmd["when"]["kinds"], cmd["when"]["items"]["auth"]),
                         ("フォルダ化", ["file"], "move"))

    def test_ページをフォルダにする(self):
        attach = os.path.join(os.path.dirname(self.wiki_dir), "attach", "Open")
        os.makedirs(attach)
        open(os.path.join(attach, "a.png"), "w").close()
        with act_as("alice"):
            status, res = self.folderize(["/Open"])
            self.assertEqual(status, 200, res)
            self.assertEqual(res["effects"][0]["text"], "1 個のページをフォルダにしました。")
            self.assertEqual(res["effects"][1]["select"], ["Open"])
            entry = self.listing("/")["Open"]
            self.assertEqual((entry["kind"], entry["attrs"]["title"]), ("dir", "Openの題名"))
            self.assertEqual(self.listing("/Open"), {})
        self.assertFalse(self.page_file("Open"))
        self.assertTrue(self.page_file("Open/index"))
        self.assertTrue(os.path.isfile(os.path.join(attach, "index", "a.png")))
        from wikilib import pagedb
        self.assertIsNotNone(pagedb.load_page(self.wiki_dir, "Open/index"))
        self.assertIsNone(pagedb.load_page(self.wiki_dir, "Open"))

    def test_できないものだけ飛ばす(self):
        self.rule("Open", "W", "alice")   # bob は読めるが編集できない
        with act_as("bob"):
            status, res = self.folderize(["/Open", "/Tech/Sub/Deep", "/(TopPage)"])
            self.assertEqual(status, 200, res)
            self.assertEqual(res["effects"][0]["text"], "1 個のページをフォルダにしました。")
            # 「動かす」の権限の無い項目は、webFileDir が外して項目ごとの失敗として返す
            failed = {r["src"]: r["error"]["code"] for r in res["results"]}
            self.assertEqual(failed, {"/Open": "forbidden", "/(TopPage)": "forbidden"})
        self.assertTrue(self.page_file("Open"))
        self.assertTrue(self.page_file("index"))
        self.assertTrue(self.page_file("Tech/Sub/Deep/index"))


if __name__ == "__main__":
    unittest.main()
