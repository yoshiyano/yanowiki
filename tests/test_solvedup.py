#!/usr/bin/env python3
"""同じ名前の `.txt` と `.md` を整理する画面（wikilib.solvedup、`/.solveDupPage/<ページ名>`）。

**整理の中身**（どちらかを採用し、もう一方を `_bak` のページとして残す）と、
**画面の出し分け**（編集の権限・許可者の一覧）を見る。特に守りたいのは次の3つ。

- どこで失敗しても、ファイル・添付が整理の前に戻ること
- 添付を、ファイルごとに選んだページへ引き継ぐこと（.txt 側・.md 側は、そのファイルのページ）
- **アクセス制限の記録は書き換えず**、違いを案内する（別ウィンドウで制限の画面へ移れる）こと

実行:
    _venv/bin/python3 tests/test_solvedup.py
"""
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from html import escape as html_escape
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import auth, pagedb, paths, privilege_records, solvedup, userdb  # noqa: E402
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402
from wikilib.wikiconfig import load_config  # noqa: E402

FARM = "testwiki"
# アクセス制限の画面を別ウィンドウで開く onclick（属性値として escape した形）
OPEN = html_escape(solvedup.OPEN_PRIVILEGES)


class SolveBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="solvedup-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        self.attach_root = os.path.join(self.work, "wikidata", FARM, "attach")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        self.kept_wikidata = paths.WIKIDATA_DIR
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        self.kept_secret_path = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        self.config = load_config()

    def tearDown(self):
        paths.WIKIDATA_DIR = self.kept_wikidata
        auth.SECRET_PATH = self.kept_secret_path
        bottle.request.environ.clear()
        shutil.rmtree(self.work, ignore_errors=True)

    # ---- 用意 ----
    def put(self, name, text="本文\n"):
        path = os.path.join(self.wiki_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def dup(self, stem="A", txt="* txt版\n", md="# md版\n"):
        self.put(stem + ".txt", txt)
        self.put(stem + ".md", md)

    def attach(self, subpath, name="pic.png", data=b"xx"):
        directory = os.path.join(self.attach_root, subpath)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), "wb") as f:
            f.write(data)

    def attached(self, subpath):
        directory = os.path.join(self.attach_root, subpath)
        return sorted(e for e in os.listdir(directory)
                      if os.path.isfile(os.path.join(directory, e))) if os.path.isdir(directory) else []

    def rules(self, rows):
        """手で書くアクセス制限を、`ページ名:種類:許可者` の並びで書く。"""
        entries = [{"page": p, "kind": k, "who": w.split(","), "stamp": "261013_090000"}
                   for p, k, w in rows]
        self.assertTrue(privilege_records.save(self.wiki_dir, entries))

    def rule_pages(self):
        return sorted((e["page"], e["kind"]) for e in privilege_records.load(self.wiki_dir))

    def files(self):
        return sorted(f for f in os.listdir(self.wiki_dir))

    def hashes(self, stem="A"):
        plan = solvedup.inspect_duplicate(self.wiki_dir, stem)
        return {f["ext"]: f["hash"] for f in plan["files"]}

    def solve(self, keep, dests=None, uid="admin", stem="A", hashes=None):
        return solvedup.solve(self.wiki_dir, self.config, stem, keep,
                              self.hashes(stem) if hashes is None else hashes, uid, dests)


class TestInspect(SolveBase):

    def test_ファイルが1つなら重複ではない(self):
        self.put("A.txt")
        self.assertIsNone(solvedup.inspect_duplicate(self.wiki_dir, "A"))

    def test_2つなら_読まれる順に返す(self):
        self.dup()
        plan = solvedup.inspect_duplicate(self.wiki_dir, "A")
        self.assertEqual([f["name"] for f in plan["files"]], ["A.txt", "A.md"])
        self.assertEqual(plan["bak_subpath"], "A_bak")
        self.assertEqual(plan["pagepath"], "A")

    def test_空きの名前を探す(self):
        self.dup()
        for taken in ("A_bak.md", "A_bak2.txt"):
            self.put(taken)
        self.assertEqual(solvedup.inspect_duplicate(self.wiki_dir, "A")["bak_subpath"], "A_bak3")

    def test_フォルダ_添付_アクセス制限の行がある名前も使わない(self):
        self.dup()
        os.makedirs(os.path.join(self.wiki_dir, "A_bak"))           # フォルダ
        self.attach("A_bak2")                                        # 添付
        self.rules([("A_bak3", "R", "alice")])                       # アクセス制限の行
        self.assertEqual(solvedup.inspect_duplicate(self.wiki_dir, "A")["bak_subpath"], "A_bak4")

    def test_フォルダの入口は_index_を_bak_にする(self):
        self.dup("Tech/index")
        plan = solvedup.inspect_duplicate(self.wiki_dir, "Tech/index")
        self.assertEqual(plan["pagepath"], "Tech")
        self.assertEqual(plan["bak_subpath"], "Tech/index_bak")


class TestSolve(SolveBase):

    def test_mdを採用_txtは_bak_txt_に残る(self):
        self.dup()
        ok, message, result = self.solve(".md")
        self.assertTrue(ok, message)
        self.assertEqual(self.files(), ["A.md", "A_bak.txt"])
        self.assertEqual((result["kept"], result["bak_name"], result["bak_pagepath"]),
                         ("A.md", "A_bak.txt", "A_bak"))
        # DB: 元のページは採用した内容、_bak は新しいページとして入る。取り込みの食い違いは残らない
        row = pagedb.load_page(self.wiki_dir, "A")
        self.assertEqual((row["path"], row["body"]), ("A.md", "# md版\n"))
        row = pagedb.load_page(self.wiki_dir, "A_bak")
        self.assertEqual((row["path"], row["body"]), ("A_bak.txt", "* txt版\n"))
        self.assertEqual(pagedb.stale_pages(self.wiki_dir), [])

    def test_txtを採用_mdは_bak_md_に残る(self):
        self.dup()
        ok, message, result = self.solve(".txt")
        self.assertTrue(ok, message)
        self.assertEqual(self.files(), ["A.txt", "A_bak.md"])
        self.assertEqual(pagedb.load_page(self.wiki_dir, "A")["path"], "A.txt")
        self.assertEqual(pagedb.load_page(self.wiki_dir, "A_bak")["path"], "A_bak.md")

    def test_残ったほうは_重複の知らせが出なくなる(self):
        self.dup()
        self.solve(".md")
        self.assertIsNone(solvedup.inspect_duplicate(self.wiki_dir, "A"))

    def test_空き名がぶつかれば_bak2(self):
        self.dup()
        self.put("A_bak.md", "前の _bak\n")
        ok, _m, result = self.solve(".md")
        self.assertTrue(ok)
        self.assertEqual(result["bak_pagepath"], "A_bak2")
        # 前の _bak は触らない
        with open(os.path.join(self.wiki_dir, "A_bak.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "前の _bak\n")

    def test_フォルダの入口(self):
        self.dup("Tech/index")
        ok, _m, result = self.solve(".txt", stem="Tech/index")
        self.assertTrue(ok)
        self.assertEqual(result["bak_pagepath"], "Tech/index_bak")
        self.assertTrue(os.path.isfile(os.path.join(self.wiki_dir, "Tech", "index_bak.md")))

    def test_開いたあとに書き換えられていたら断る(self):
        self.dup()
        hashes = self.hashes()
        self.put("A.md", "# 誰かが書き換えた\n")
        ok, message, _r = self.solve(".md", hashes=hashes)
        self.assertFalse(ok)
        self.assertIn("書き換えられました", message)
        self.assertEqual(self.files(), ["A.md", "A.txt"])

    def test_選ばれていなければ断る(self):
        self.dup()
        self.assertFalse(self.solve(".png")[0])
        self.assertFalse(self.solve(".md", {"pic.png": "????"})[0])
        self.assertEqual(self.files(), ["A.md", "A.txt"])

    def test_重複していなければ断る(self):
        self.put("A.txt")
        ok, message, _r = solvedup.solve(self.wiki_dir, self.config, "A", ".txt", {}, "admin")
        self.assertFalse(ok)

    def test_名前に空きが無ければ断る(self):
        self.dup()
        with mock.patch.object(solvedup, "MAX_BAK_TRIES", 2):
            self.put("A_bak.md")
            self.put("A_bak2.md")
            ok, message, _r = self.solve(".md")
        self.assertFalse(ok)
        self.assertEqual(self.files(), ["A.md", "A.txt", "A_bak.md", "A_bak2.md"])


class TestAttachments(SolveBase):
    """添付は、ファイルごとに移動先（両方・.txt 側・.md 側）を選ぶ。`.txt` 側・`.md` 側は、
    そのファイルのページ。採用したほうが元のページ（A）、しなかったほうが A_bak。"""

    def setUp(self):
        super().setUp()
        self.dup()
        self.attach("A", "pic.png")
        self.attach("A", "memo.txt")

    def test_既定は両方(self):
        ok, _m, result = self.solve(".md")
        self.assertTrue(ok)
        self.assertEqual(self.attached("A"), ["memo.txt", "pic.png"])
        self.assertEqual(self.attached("A_bak"), ["memo.txt", "pic.png"])
        self.assertEqual(result["attach"], {"both": 2, "keep": 0, "move": 0})

    def test_mdを採用_md側は元のページ_txt側は_bak(self):
        # .txt 側=.txt のページ=A_bak、.md 側=.md のページ=A
        ok, _m, result = self.solve(".md", {"pic.png": "md", "memo.txt": "txt"})
        self.assertTrue(ok)
        self.assertEqual(self.attached("A"), ["pic.png"])
        self.assertEqual(self.attached("A_bak"), ["memo.txt"])
        self.assertEqual(result["attach"], {"both": 0, "keep": 1, "move": 1})

    def test_txtを採用_txt側は元のページ_md側は_bak(self):
        ok, _m, _r = self.solve(".txt", {"pic.png": "txt", "memo.txt": "md"})
        self.assertTrue(ok)
        self.assertEqual(self.attached("A"), ["pic.png"])
        self.assertEqual(self.attached("A_bak"), ["memo.txt"])

    def test_ファイルごとに両方と片側を混ぜる(self):
        ok, _m, result = self.solve(".txt", {"pic.png": "both", "memo.txt": "md"})
        self.assertTrue(ok)
        self.assertEqual(self.attached("A"), ["pic.png"])
        self.assertEqual(self.attached("A_bak"), ["memo.txt", "pic.png"])
        self.assertEqual(result["attach"], {"both": 1, "keep": 0, "move": 1})

    def test_全部を採用した側だけに残す(self):
        ok, _m, result = self.solve(".md", {"pic.png": "md", "memo.txt": "md"})
        self.assertTrue(ok)
        self.assertEqual(self.attached("A"), ["memo.txt", "pic.png"])
        self.assertFalse(os.path.exists(os.path.join(self.attach_root, "A_bak")))
        self.assertEqual(result["attach"], {"both": 0, "keep": 2, "move": 0})

    def test_全部を_bak_へ移すと_元の置き場所は残さない(self):
        ok, _m, _r = self.solve(".md", {"pic.png": "txt", "memo.txt": "txt"})
        self.assertTrue(ok)
        self.assertEqual(self.attached("A_bak"), ["memo.txt", "pic.png"])
        self.assertFalse(os.path.exists(os.path.join(self.attach_root, "A")))

    def test_指定の無いファイルは両方(self):
        ok, _m, _r = self.solve(".md", {"pic.png": "md"})
        self.assertTrue(ok)
        self.assertEqual(self.attached("A"), ["memo.txt", "pic.png"])
        self.assertEqual(self.attached("A_bak"), ["memo.txt"])

    def test_下位ページの添付は動かさない(self):
        self.attach("A/kid", "kid.png")
        ok, _m, _r = self.solve(".md", {"pic.png": "txt", "memo.txt": "txt"})
        self.assertTrue(ok)
        self.assertEqual(self.attached("A/kid"), ["kid.png"])
        self.assertEqual(self.attached("A_bak"), ["memo.txt", "pic.png"])

    def test_添付が無くても動く(self):
        shutil.rmtree(os.path.join(self.attach_root, "A"))
        ok, _m, result = self.solve(".md", {"pic.png": "txt"})
        self.assertTrue(ok)
        self.assertEqual(result["attach"], {"both": 0, "keep": 0, "move": 0})

    def test_日本語のファイル名(self):
        self.attach("A", "写真 1.png")
        ok, _m, _r = self.solve(".md", {"写真 1.png": "txt"})
        self.assertTrue(ok)
        self.assertIn("写真 1.png", self.attached("A_bak"))
        self.assertNotIn("写真 1.png", self.attached("A"))


class TestRollback(SolveBase):
    """ファイルを動かせなかったとき、添付が整理の前に戻る。"""

    def setUp(self):
        super().setUp()
        self.dup()
        self.attach("A", "pic.png")

    def fail_page_move(self, real=os.replace):
        def replace(src, dst, *a, **k):
            if os.path.basename(dst) == "A_bak.txt":
                raise OSError("simulated")
            return real(src, dst, *a, **k)
        return mock.patch("os.replace", side_effect=replace)

    def check_unchanged(self):
        self.assertEqual(self.files(), ["A.md", "A.txt"])
        self.assertEqual(self.attached("A"), ["pic.png"])
        self.assertFalse(os.path.exists(os.path.join(self.attach_root, "A_bak")))

    def test_写したあとに失敗しても_戻る(self):
        with self.fail_page_move():
            ok, _m, _r = self.solve(".md", {"pic.png": "both"})
        self.assertFalse(ok)
        self.check_unchanged()

    def test_移したあとに失敗しても_戻る(self):
        with self.fail_page_move():
            ok, _m, _r = self.solve(".md", {"pic.png": "txt"})
        self.assertFalse(ok)
        self.check_unchanged()

    def test_移す途中で失敗しても元へ戻る(self):
        self.attach("A", "second.png")
        real = os.replace
        calls = []

        def replace(src, dst, *a, **k):
            calls.append(dst)
            if len(calls) == 2:  # 2つ目のファイルで失敗
                raise OSError("simulated")
            return real(src, dst, *a, **k)
        with mock.patch("os.replace", side_effect=replace):
            ok, _m, _r = self.solve(".md", {"pic.png": "txt", "second.png": "txt"})
        self.assertFalse(ok)
        self.assertEqual(self.attached("A"), ["pic.png", "second.png"])
        self.assertFalse(os.path.exists(os.path.join(self.attach_root, "A_bak")))
        self.assertEqual(self.files(), ["A.md", "A.txt"])

    def test_bak_を編集できなければ断る(self):
        # 後方一致の W の指定が _bak に当たる。bob は _bak を編集できない
        self.rules([("*_bak", "W", "admin")])
        ok, message, _r = self.solve(".md", uid="bob")
        self.assertFalse(ok)
        self.assertIn("編集する権限", message)
        self.assertEqual(self.files(), ["A.md", "A.txt"])
        self.assertEqual(self.rule_pages(), [("*_bak", "W")])
        self.check_unchanged()


class TestAccess(SolveBase):
    """アクセス制限は**書き換えない**。元のページと `_bak` に当たる指定を並べ、違いを案内する。"""

    def test_整理してもアクセス制限の記録は変わらない(self):
        self.dup()
        self.rules([("A", "R", "admin,alice"), ("A", "W", "admin"), ("*Secret", "R", "admin")])
        with open(privilege_records.path_of(self.wiki_dir), encoding="utf-8") as f:
            before = f.read()
        ok, _m, _r = self.solve(".md")
        self.assertTrue(ok)
        with open(privilege_records.path_of(self.wiki_dir), encoding="utf-8") as f:
            self.assertEqual(f.read(), before)

    def test_プラグインの記録も書き換えない(self):
        self.dup()
        entries = [{"page": "A", "kind": "R", "who": ["admin"], "stamp": "261013_090000"}]
        path = privilege_records.plugin_path_of(self.wiki_dir)
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(privilege_records.format_line(e) + "\n" for e in entries))
        with open(path, encoding="utf-8") as f:
            before = f.read()
        ok, _m, result = self.solve(".md")
        self.assertTrue(ok)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(result["access"]["plugin"], ["R"])  # 事実だけ。内容は出さない

    def test_完全一致の指定は_bak_に当たらない_と案内する(self):
        self.dup()
        self.rules([("A", "R", "admin,alice"), ("A", "W", "admin")])
        ok, _m, result = self.solve(".md")
        self.assertTrue(ok)
        self.assertEqual(result["access"]["differs"], ["read", "write"])
        # 実際にも、整理した直後の _bak は誰でも読める（案内しないと気づけない）
        self.assertEqual(auth.page_privilege(self.wiki_dir, "bob").check("A_bak"), auth.PAGE_WRITE)

    def test_後方一致でも_bak_に当たらない(self):
        self.dup("MySecret")
        self.rules([("*Secret", "R", "admin,alice")])
        ok, _m, result = self.solve(".md", stem="MySecret")
        self.assertTrue(ok)
        self.assertEqual(result["access"]["differs"], ["read"])

    def test_両方に当たる指定なら違いは無い(self):
        self.dup("Tech/A")
        self.rules([("Tech/*", "R", "admin,alice")])
        ok, _m, result = self.solve(".md", stem="Tech/A")
        self.assertTrue(ok)
        self.assertEqual(result["access"]["differs"], [])

    def test_指定が無ければ違いは無い(self):
        self.dup()
        ok, _m, result = self.solve(".md")
        self.assertTrue(ok)
        self.assertEqual(result["access"]["differs"], [])
        self.assertEqual(result["access"]["plugin"], [])

    def test_bak_のほうが厳しいだけなら違いに数えない(self):
        self.dup()
        self.rules([("*_bak", "R", "admin")])
        ok, _m, result = self.solve(".md")
        self.assertTrue(ok)
        self.assertEqual(result["access"]["differs"], [])


# ---- 画面 --------------------------------------------------------------------

class ScreenBase(SolveBase):

    def login_environ(self, uid):
        if uid is None:
            return {}
        user = userdb.find_by_uid(self.wiki_dir, uid)
        token = auth.session_token(uid, FARM, user["pw"])
        return {"HTTP_COOKIE": (f"{wiki_cookie_name(LOGIN_COOKIE, FARM)}={uid}; "
                                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, FARM)}={token}")}

    def call(self, pagepath, uid="admin", form=None):
        """`/.solveDupPage/<pagepath>` を呼ぶ。`form` があればPOST。(状態, 本文) を返す。"""
        import urllib.parse
        environ = dict(self.login_environ(uid))
        if form is None:
            environ["REQUEST_METHOD"] = "GET"
        else:
            body = urllib.parse.urlencode(form).encode()
            environ.update({"REQUEST_METHOD": "POST", "wsgi.input": io.BytesIO(body),
                            "CONTENT_LENGTH": str(len(body)),
                            "CONTENT_TYPE": "application/x-www-form-urlencoded"})
        bottle.request.environ.clear()
        bottle.request.bind(environ)
        response = solvedup.serve_solve_dup(self.wiki_dir, self.config, FARM, False, pagepath)
        body = response.body
        return response.status_code, body if isinstance(body, str) else body.decode("utf-8")

    def post_form(self, keep, dests=None, stem="A"):
        form = {"keep": keep}
        form.update({"dest:" + name: dest for name, dest in (dests or {}).items()})
        form.update({"hash" + ext: h for ext, h in self.hashes(stem).items()})
        return form


class TestScreen(ScreenBase):

    def setUp(self):
        super().setUp()
        self.dup(txt="* txt版の本文\n", md="# md版のタイトル\n\nmd版の本文\n")
        self.attach("A", "pic.png")

    def test_先頭に状況の説明と詳しい説明へのリンク_そのあとにプレビュー(self):
        status, html = self.call("A")
        self.assertEqual(status, 200)
        guide = html.index('href="/=_system/UsageGuide/Edit/Duplicate"')
        self.assertLess(html.index("同じ名前のファイルが"), guide)
        self.assertLess(guide, html.index("md版の本文"))
        self.assertLess(guide, html.index("txt版の本文"))

    def test_プレビューは左右2画面_その下に添付とアクセス制限_いちばん下に採用のボタン(self):
        _s, html = self.call("A")
        self.assertEqual(html.count('class="dup-col"'), 2)
        order = [html.index(word) for word in (
            'class="dup-col"', "添付ファイル</h2>", "アクセス制限</h2>", 'name="keep"')]
        self.assertEqual(order, sorted(order))
        self.assertIn("pic.png", html)
        self.assertIn("repeat(2, minmax(0, 1fr))", html)
        # プレビューの縦幅は 720px まで（超えたらプレビューの中でスクロール）
        self.assertRegex(html, r"\.dup-preview \{[^}]*max-height: 720px;[^}]*overflow: auto")

    def test_添付は_ファイルごとに移動先を選ばせる(self):
        self.attach("A", "memo.txt")
        _s, html = self.call("A")
        self.assertIn("移動先</th>", html)
        for name in ("pic.png", "memo.txt"):
            for value in ("both", "txt", "md"):
                self.assertIn('name="dest:{}" value="{}"'.format(name, value), html)
            self.assertIn('name="dest:{}" value="both" checked'.format(name), html)
        # 「.txt 側」「.md 側」は、そのファイルのページ。採用すると元のページ／_bak になる
        self.assertIn("「.txt 側」「.md 側」は、そのファイルのページです。"
                      "採用したファイルのページが /A、採用しなかったほうが /A_bak になります。", html)
        for label in (".txt 側", ".md 側", "両方"):
            self.assertIn("> {}</label>".format(label), html)
        # 左右の説明は出さない（煩雑なため）
        attach_part = html.split("添付ファイル</h2>")[1].split("アクセス制限</h2>")[0]
        self.assertNotIn("左側", attach_part)
        self.assertNotIn("右側", attach_part)

    def test_添付の一括設定の行がある(self):
        _s, html = self.call("A")
        self.assertIn("すべて（一括）", html)
        for value in ("both", "txt", "md"):
            self.assertIn('name="dest-all" value="{}"'.format(value), html)
        self.assertRegex(html, r'name="dest-all" value="both" checked')
        # 一括のラジオボタンの内容を、各ファイルへコピーする動き
        self.assertIn("input[name=\"dest-all\"]", html)
        self.assertIn("r.checked = (r.value === b.value)", html)

    def test_画像の名前にだけ_マウスを重ねるプレビューを付ける(self):
        self.attach("A", "memo.txt")
        self.attach("A", "写真.JPG")
        _s, html = self.call("A")
        self.assertIn('data-img="/=testwiki/.attach/A/pic.png"', html)
        self.assertIn('data-img="/=testwiki/.attach/A/%E5%86%99%E7%9C%9F.JPG"', html)
        self.assertNotIn("memo.txt\" data-img", html)
        self.assertEqual(html.count("data-img="), 2)
        self.assertIn("mouseenter", html)

    def test_添付が無ければ選ばせない(self):
        shutil.rmtree(os.path.join(self.attach_root, "A"))
        _s, html = self.call("A")
        self.assertIn("添付ファイルはありません", html)
        self.assertNotIn('name="dest:', html)
        self.assertNotIn("dest-all", html.split("<script>")[0])

    def test_許可者の一覧は_管理者にだけ見せる(self):
        self.rules([("A", "R", "admin,alice,bob"), ("A", "W", "admin,alice")])
        _s, html = self.call("A", uid="admin")
        self.assertIn("admin、alice、bob", html)
        _s, html = self.call("A", uid="alice")
        self.assertNotIn("bob", html.split("アクセス制限</h2>")[1])
        self.assertIn("許可者: 3 件", html)
        self.assertIn("許可者: 2 件", html)

    def test_アクセス制限の文面と別ウィンドウのリンク(self):
        _s, html = self.call("A")
        text = html.split("アクセス制限</h2>")[1]
        link = '<a href="/=testwiki/.admin/privileges" onclick="{}">アクセス制限</a>'.format(OPEN)
        self.assertIn(
            "この修正では案内のみで修正を行いません。お手数をおかけしますが、本情報をもとに別途 "
            + link + " の対応をお願いいたします。", text)
        # 管理は開いた先の画面に任せる。ここには編集の入力欄を置かない
        self.assertNotIn("<input", text.split("</table>")[0].split("<h2>")[0])

    def link_tag(self, html):
        """アクセス制限の画面へのリンクの開始タグ。"""
        return re.search(r'<a href="[^"]*/\.admin/privileges"[^>]*>', html).group(0)

    def check_window_open(self, link):
        self.assertNotIn("target=", link)  # 別タブの設定は使わない
        # onclick の window.open で、popup（ウィンドウ）として開く。noopener は features に入れる
        # （rel="noopener" は window.open には効かない）
        self.assertRegex(link, r"window\.open\(this\.href, &#x27;_blank&#x27;, "
                               r"&#x27;popup,noopener,width=\d+,height=\d+&#x27;\)")
        self.assertIn("return false", link)
        self.assertNotIn("rel=", link)

    def test_リンクは_window_open_で別ウィンドウに開く(self):
        _s, html = self.call("A")
        self.check_window_open(self.link_tag(html))
        # 整理の前の画面にある3か所（文面・警告）すべてが同じ形
        self.rules([("A", "R", "admin,alice")])
        _s, html = self.call("A")
        links = re.findall(r'<a href="[^"]*/\.admin/privileges"[^>]*>', html)
        self.assertEqual(len(links), 2)  # 文面のリンクと、警告の中のリンク
        for link in links:
            self.check_window_open(link)

    def test_結果の画面のリンクも_window_open(self):
        self.rules([("A", "R", "admin,alice")])
        _s, html = self.call("A", form=self.post_form(".md"))
        self.check_window_open(self.link_tag(html))

    def test_元のページと_bak_に当たる指定を並べる(self):
        self.rules([("A", "R", "admin,alice"), ("*_bak", "W", "admin")])
        _s, html = self.call("A")
        text = html.split("アクセス制限</h2>")[1]
        self.assertIn("/A（元のページ）", text)
        self.assertIn("/A_bak（整理後）", text)
        self.assertIn("右は、整理でできる /A_bak に当たる指定", text)
        self.assertIn("<code>A</code>", text)       # 元のページに当たっている指定
        self.assertIn("<code>*_bak</code>", text)   # _bak に当たる指定

    def test_制限が違うときは_目立つ形で知らせる(self):
        self.rules([("A", "R", "admin,alice")])
        _s, html = self.call("A")
        self.assertIn("dup-alert", html.split("アクセス制限</h2>")[1])
        self.assertIn("/A_bak には、/A と同じアクセス制限が付きません", html)
        # 採用ボタンの確認にも出す
        self.assertIn("同じアクセス制限が付きません（案内のみで、修正は行いません）", html)

    def test_制限が違わなければ_知らせない(self):
        _s, html = self.call("A")
        self.assertNotIn('<p class="dup-alert">', html)
        self.assertNotIn("同じアクセス制限が付きません", html)

    def plugin_part(self, html):
        """アクセス制限の欄のうち、本文のプラグインの表。"""
        return html.split("アクセス制限</h2>")[1].split("本文のプラグイン（#readauth・#writeauth）")[1]

    def test_プラグインのアクセス制限は_どちらのファイルに何があるかを示す(self):
        self.put("A.txt", "#readauth(admin)\n* txt版の本文\n")
        self.put("A.md", "# md版のタイトル\n\nmd版の本文\n")
        _s, html = self.call("A")
        part = self.plugin_part(html)
        self.assertIn("<tr><th>A.txt</th><td>閲覧（#readauth）</td></tr>", part)
        self.assertIn("<tr><th>A.md</th><td>なし</td></tr>", part)

    def test_プラグインのアクセス制限_両方のファイルにあれば_種類も示す(self):
        self.put("A.txt", "#readauth(admin)\n#writeauth(admin)\n* txt版の本文\n")
        self.put("A.md", "#writeauth(admin)\n# md版のタイトル\n")
        _s, html = self.call("A")
        part = self.plugin_part(html)
        self.assertIn("<tr><th>A.txt</th><td>閲覧（#readauth）、編集（#writeauth）</td></tr>", part)
        self.assertIn("<tr><th>A.md</th><td>編集（#writeauth）</td></tr>", part)

    def test_プラグインのアクセス制限が無ければ_どちらも_なし(self):
        _s, html = self.call("A")
        part = self.plugin_part(html)
        self.assertIn("<tr><th>A.txt</th><td>なし</td></tr>", part)
        self.assertIn("<tr><th>A.md</th><td>なし</td></tr>", part)

    def test_プラグインの許可者は書かない_記録も書き換えない(self):
        self.put("A.txt", "#readauth(alice,g:staff)\n* txt版の本文\n")
        _s, html = self.call("A")
        part = self.plugin_part(html)
        self.assertNotIn("alice", part)
        self.assertNotIn("g:staff", part)
        self.assertNotIn("許可者", part)
        # プレビューの描画は、プラグインの記録（config/privileges.plugin）を書かない
        self.assertEqual(privilege_records.load_plugin(self.wiki_dir), [])

    def test_コードブロックの中の_readauth_は数えない(self):
        self.put("A.md", "# md版\n\n```\n#readauth(admin)\n```\n")
        _s, html = self.call("A")
        self.assertIn("<tr><th>A.md</th><td>なし</td></tr>", self.plugin_part(html))

    def test_編集の権限が無ければ_説明だけ(self):
        self.rules([("A", "R", "admin,bob"), ("A", "W", "admin")])
        status, html = self.call("A", uid="bob")
        self.assertEqual(status, 403)
        self.assertIn("編集の権限が必要", html)
        self.assertIn('href="/=_system/UsageGuide/Edit/Duplicate"', html)
        # 公開前のほうの中身も、選ぶボタンも出さない
        for word in ("md版の本文", "txt版の本文", 'name="keep"', 'class="dup-preview"'):
            self.assertNotIn(word, html)

    def test_閲覧できなければ閲覧できないページと同じ(self):
        self.rules([("A", "R", "admin")])
        status, html = self.call("A", uid="bob")
        self.assertEqual(status, 403)
        for word in ("md版の本文", 'name="keep"'):
            self.assertNotIn(word, html)

    def test_重複していなければそう伝える(self):
        os.remove(os.path.join(self.wiki_dir, "A.md"))
        status, html = self.call("A")
        self.assertEqual(status, 200)
        self.assertIn("重複はありません", html)
        self.assertNotIn('name="keep"', html)

    def test_フォルダの入口はページ名で開く(self):
        self.dup("Tech/index")
        status, html = self.call("Tech")
        self.assertEqual(status, 200)
        self.assertIn("index.txt", html)
        self.assertIn("index_bak.md", html)

    def test_使えない名前は無いページ(self):
        status, _html = self.call("=x/A")
        self.assertEqual(status, 404)

    def test_採用すると整理されて_結果の画面が出る(self):
        status, html = self.call("A", form=self.post_form(".md", {"pic.png": "txt"}))
        self.assertEqual(status, 200)
        self.assertIn("A.md</strong> を採用しました", html)
        self.assertIn("A_bak.txt", html)
        self.assertIn("添付ファイル: 1 件は /A_bak へ移した", html)
        self.assertEqual(self.files(), ["A.md", "A_bak.txt"])
        self.assertEqual(self.attached("A_bak"), ["pic.png"])
        # 編集はPOSTの cmd=edit で開く（GETでは開けない）
        self.assertIn('<input type="hidden" name="cmd" value="edit">', html)

    def test_結果の画面から_別ウィンドウでアクセス制限へ移れる(self):
        _s, html = self.call("A", form=self.post_form(".md"))
        self.assertIn('href="/=testwiki/.admin/privileges" onclick="{}"'.format(OPEN), html)
        self.assertIn("アクセス制限は、修正していません", html)

    def test_制限が付かなかったときは_結果の画面で目立つ形で知らせる(self):
        self.rules([("A", "R", "admin,alice"), ("A", "W", "admin")])
        _s, html = self.call("A", form=self.post_form(".md"))
        self.assertIn('<p class="dup-alert">', html)
        self.assertIn("/A_bak には、/A と同じアクセス制限が付いていません", html)
        self.assertIn('onclick="{}"'.format(OPEN), html)
        # 書き換えていない
        self.assertEqual(self.rule_pages(), [("A", "R"), ("A", "W")])

    def test_結果の画面は_プラグインの制限があることだけ示す(self):
        entries = [{"page": "A", "kind": "R", "who": ["admin", "secretuser"],
                    "stamp": "261013_090000"}]
        with open(privilege_records.plugin_path_of(self.wiki_dir), "w", encoding="utf-8") as f:
            f.write("".join(privilege_records.format_line(e) + "\n" for e in entries))
        _s, html = self.call("A", form=self.post_form(".md"))
        self.assertIn("本文のプラグイン（#readauth・#writeauth）によるアクセス制限も設定されています", html)
        self.assertNotIn("secretuser", html)

    def test_日本語のファイル名の移動先を受け取る(self):
        self.attach("A", "写真 1.png")
        status, html = self.call("A", form=self.post_form(".txt", {"写真 1.png": "md"}))
        self.assertEqual(status, 200)
        self.assertIn("写真 1.png", self.attached("A_bak"))
        self.assertNotIn("写真 1.png", self.attached("A"))

    def test_確かめ直すよう断ると_画面を出し直す(self):
        form = self.post_form(".md")
        self.put("A.md", "# 書き換えられた\n")
        status, html = self.call("A", form=form)
        self.assertEqual(status, 409)
        self.assertIn("書き換えられました", html)
        self.assertIn('name="keep"', html)  # 続けて選び直せる
        self.assertEqual(self.files(), ["A.md", "A.txt"])

    def test_編集の権限が無ければ_POSTでも整理できない(self):
        self.rules([("A", "R", "admin,bob"), ("A", "W", "admin")])
        status, _html = self.call("A", uid="bob", form=self.post_form(".md"))
        self.assertEqual(status, 403)
        self.assertEqual(self.files(), ["A.md", "A.txt"])

    def test_プレビューの本文の入力欄は止める(self):
        self.put("A.md", "<form action=\"/x\"><input name=\"a\"><button>送る</button></form>\n")
        _s, html = self.call("A")
        self.assertNotRegex(html.split('class="dup-preview"')[2], r"<form[^>]*action=\"/x\"")


# ---- 同じ名前のファイルとフォルダ（X.md と X/） -------------------------------

class FolderBase(SolveBase):

    def tree(self):
        """wiki の下のファイルを、相対パスの並びで返す。"""
        found = []
        for dirpath, _dirs, names in os.walk(self.wiki_dir):
            for name in names:
                found.append(os.path.relpath(os.path.join(dirpath, name), self.wiki_dir))
        return sorted(found)

    def read(self, name):
        with open(os.path.join(self.wiki_dir, name), encoding="utf-8") as f:
            return f.read()

    def folder_hashes(self, entry="X/index"):
        plan = solvedup.inspect_folder(self.wiki_dir, entry)
        return {f["key"]: f["hash"] for f in plan["files"]}

    def solve_folder(self, keep, uid="admin", entry="X/index", hashes=None):
        return solvedup.solve_folder(self.wiki_dir, self.config, entry, keep,
                                     self.folder_hashes(entry) if hashes is None else hashes, uid)

    def adopt(self, *subpaths):
        from wikilib.pagesync import adopt_page
        for subpath in subpaths:
            adopt_page(self.wiki_dir, subpath, self.config)


class TestFolderStage(FolderBase):

    def test_ファイルとフォルダの入口が並べば_フォルダの段(self):
        from wikilib.pagenotice import duplicate_stage
        self.put("X.md")
        self.put("X/index.txt")
        self.assertEqual(duplicate_stage(self.wiki_dir, "X/index"), ("folder", "X"))
        plan = solvedup.inspect_folder(self.wiki_dir, "X/index")
        self.assertEqual([(f["key"], f["name"]) for f in plan["files"]],
                         [("folder", "X/index.txt"), ("file", "X.md")])
        self.assertEqual((plan["pagepath"], plan["twin"], plan["bak_subpath"]), ("X", "X", "X_bak"))

    def test_入口が無くても_フォルダの段_bak_は作らない(self):
        self.put("X.md")
        self.put("X/kid.md")
        plan = solvedup.inspect_folder(self.wiki_dir, "X/index")
        self.assertEqual([f["key"] for f in plan["files"]], ["file"])
        self.assertIsNone(plan["bak_subpath"])

    def test_重なっていれば_1段ずつ(self):
        from wikilib.pagenotice import duplicate_stage
        self.put("X.txt")
        self.put("X.md")
        self.put("X/index.txt")
        self.put("X/index.md")
        self.assertEqual(duplicate_stage(self.wiki_dir, "X/index"), ("ext", "X/index"))
        os.remove(os.path.join(self.wiki_dir, "X", "index.md"))
        self.assertEqual(duplicate_stage(self.wiki_dir, "X/index"), ("ext", "X"))
        self.assertIsNone(solvedup.inspect_folder(self.wiki_dir, "X/index"))
        os.remove(os.path.join(self.wiki_dir, "X.md"))
        self.assertEqual(duplicate_stage(self.wiki_dir, "X/index"), ("folder", "X"))

    def test_フォルダが無ければ重複ではない(self):
        from wikilib.pagenotice import duplicate_stage
        self.put("X.md")
        self.put("Y/index.md")
        self.assertIsNone(duplicate_stage(self.wiki_dir, "Y/index"))
        self.assertIsNone(duplicate_stage(self.wiki_dir, "index"))
        self.assertIsNone(solvedup.inspect_folder(self.wiki_dir, "Y/index"))


class TestFolderSolve(FolderBase):

    def setUp(self):
        super().setUp()
        self.put("X.md", "# ファイル版\n")
        self.adopt("X")
        self.put("X/index.txt", "* フォルダ版\n")
        self.put("X/kid.md", "# 下位\n")
        self.adopt("X/index", "X/kid")
        self.attach("X", "file.png")
        self.attach("X/index", "entry.png")
        self.attach("X/kid", "kid.png")

    def test_フォルダを採用_ファイルは_bak_へ_添付と記録も付いていく(self):
        ok, message, result = self.solve_folder("folder")
        self.assertTrue(ok, message)
        self.assertEqual(self.tree(), ["X/index.txt", "X/kid.md", "X_bak.md"])
        self.assertEqual((result["bak_pagepath"], result["bak_name"], result["moved_to"]),
                         ("X_bak", "X_bak.md", None))
        self.assertEqual(self.attached("X_bak"), ["file.png"])
        self.assertEqual(self.attached("X"), [])
        self.assertEqual(self.attached("X/index"), ["entry.png"])
        self.assertEqual(self.attached("X/kid"), ["kid.png"])  # 下位ページの添付は動かさない
        self.assertEqual(pagedb.load_page(self.wiki_dir, "X_bak")["body"], "# ファイル版\n")
        self.assertIsNone(pagedb.load_page(self.wiki_dir, "X"))
        self.assertIsNotNone(pagedb.first_backup_stamp(self.wiki_dir, "X_bak"))
        self.assertIsNone(pagedb.first_backup_stamp(self.wiki_dir, "X"))
        self.assertEqual(pagedb.load_page(self.wiki_dir, "X/index")["body"], "* フォルダ版\n")
        from wikilib.pagenotice import duplicate_stage
        self.assertIsNone(duplicate_stage(self.wiki_dir, "X/index"))

    def test_ファイルを採用_入口は_bak_へ_ファイルが入口へ(self):
        ok, message, result = self.solve_folder("file")
        self.assertTrue(ok, message)
        self.assertEqual(self.tree(), ["X/index.md", "X/kid.md", "X_bak.txt"])
        self.assertEqual((result["kept_name"], result["moved_to"], result["bak_name"]),
                         ("X.md", "X/index.md", "X_bak.txt"))
        self.assertEqual(self.attached("X/index"), ["file.png"])
        self.assertEqual(self.attached("X_bak"), ["entry.png"])
        self.assertEqual(self.attached("X/kid"), ["kid.png"])
        row = pagedb.load_page(self.wiki_dir, "X/index")
        self.assertEqual((row["path"], row["body"]), ("X/index.md", "# ファイル版\n"))
        row = pagedb.load_page(self.wiki_dir, "X_bak")
        self.assertEqual((row["path"], row["body"]), ("X_bak.txt", "* フォルダ版\n"))
        self.assertIsNone(pagedb.load_page(self.wiki_dir, "X"))
        self.assertEqual(pagedb.stale_pages(self.wiki_dir), [])

    def test_入口が無ければ_ファイルを入口へ移すだけ(self):
        os.remove(os.path.join(self.wiki_dir, "X", "index.txt"))
        shutil.rmtree(os.path.join(self.attach_root, "X", "index"))
        ok, message, result = self.solve_folder("file")
        self.assertTrue(ok, message)
        self.assertEqual(self.tree(), ["X/index.md", "X/kid.md"])
        self.assertIsNone(result["bak_pagepath"])
        self.assertEqual(self.attached("X/index"), ["file.png"])
        self.assertEqual(pagedb.load_page(self.wiki_dir, "X/index")["body"], "# ファイル版\n")

    def test_取り込まれていなかったファイルも_取り込む(self):
        os.remove(os.path.join(self.wiki_dir, "X.md"))
        self.put("X.txt", "* 手で置いた\n")
        pagedb.remove_page(self.wiki_dir, "X")
        ok, _m, _r = self.solve_folder("file")
        self.assertTrue(ok)
        self.assertEqual(pagedb.load_page(self.wiki_dir, "X/index")["body"], "* 手で置いた\n")

    def test_開いたあとに書き換えられていたら断る(self):
        hashes = self.folder_hashes()
        self.put("X.md", "# 書き換えた\n")
        ok, message, _r = self.solve_folder("file", hashes=hashes)
        self.assertFalse(ok)
        self.assertIn("書き換えられました", message)
        self.assertEqual(self.tree(), ["X.md", "X/index.txt", "X/kid.md"])

    def test_2つめの移動で失敗したら_1つめも戻す(self):
        real = os.replace

        def replace(src, dst, *a, **k):
            if dst.endswith(os.path.join("X", "index.md")):
                raise OSError("simulated")
            return real(src, dst, *a, **k)
        with mock.patch("os.replace", side_effect=replace):
            ok, _m, _r = self.solve_folder("file")
        self.assertFalse(ok)
        self.assertEqual(self.tree(), ["X.md", "X/index.txt", "X/kid.md"])
        self.assertEqual(self.attached("X"), ["file.png"])
        self.assertEqual(self.attached("X/index"), ["entry.png"])
        self.assertFalse(os.path.exists(os.path.join(self.attach_root, "X_bak")))
        self.assertEqual(pagedb.load_page(self.wiki_dir, "X/index")["body"], "* フォルダ版\n")

    def test_bak_を編集できなければ断る(self):
        self.rules([("*_bak", "W", "admin")])
        ok, message, _r = self.solve_folder("folder", uid="bob")
        self.assertFalse(ok)
        self.assertIn("編集する権限", message)
        self.assertEqual(self.tree(), ["X.md", "X/index.txt", "X/kid.md"])


class TestShadowedExtStage(FolderBase):
    """`X.txt` と `X.md` に加えて `X/` がある。1段めで `.txt` と `.md` を整理する。"""

    def setUp(self):
        super().setUp()
        self.put("X/index.md", "# 入口\n")
        self.adopt("X/index")
        self.dup("X", txt="* txt版\n", md="# md版\n")

    def test_X_は取り込まない_入口の記録はそのまま(self):
        ok, message, result = self.solve(".md", stem="X")
        self.assertTrue(ok, message)
        self.assertEqual(self.tree(), ["X.md", "X/index.md", "X_bak.txt"])
        self.assertTrue(result["synced"])
        self.assertIsNone(pagedb.load_page(self.wiki_dir, "X"))
        self.assertEqual(pagedb.load_page(self.wiki_dir, "X/index")["body"], "# 入口\n")
        from wikilib.pagenotice import duplicate_stage
        self.assertEqual(duplicate_stage(self.wiki_dir, "X/index"), ("folder", "X"))


class TestFolderScreen(FolderBase, ScreenBase):

    def setUp(self):
        super().setUp()
        self.put("X.md", "# ファイル版\n")
        self.put("X/index.txt", "* フォルダ版\n")

    def form(self, keep):
        form = {"keep": keep, "stage": "folder:X/index"}
        form.update({"hash" + k: h for k, h in self.folder_hashes().items()})
        return form

    def test_ページ名で開くと_フォルダの重複の画面(self):
        status, html = self.call("X")
        self.assertEqual(status, 200)
        self.assertIn("同じ名前のファイル <code>X.md</code> とフォルダ <code>X/</code>", html)
        self.assertIn("X/index.txt を採用する", html)
        self.assertIn("X.md を採用する", html)
        self.assertIn('name="stage" value="folder:X/index"', html)
        self.assertNotIn('name="dest:', html)  # 添付の移動先は選ばせない

    def test_採用すると整理されて_結果の画面が出る(self):
        status, html = self.call("X", form=self.form("file"))
        self.assertEqual(status, 200)
        self.assertIn("X.md</strong> を採用しました", html)
        self.assertIn("X/index.md</strong> へ移しました", html)
        self.assertEqual(self.tree(), ["X/index.md", "X_bak.txt"])
        self.assertNotIn("続けて整理する", html)

    def test_入口が無ければ_移すボタンだけ(self):
        os.remove(os.path.join(self.wiki_dir, "X", "index.txt"))
        _s, html = self.call("X")
        self.assertIn("X.md をフォルダの入口へ移す", html)
        self.assertNotIn("<h2>アクセス制限</h2>", html)
        status, html = self.call("X", form=self.form("file"))
        self.assertEqual(status, 200)
        self.assertIn("X/index.md</strong> へ移しました", html)
        self.assertEqual(self.tree(), ["X/index.md"])

    def test_段が替わっていたら断る(self):
        form = self.form("file")
        form["stage"] = "ext:X"
        status, html = self.call("X", form=form)
        self.assertEqual(status, 409)
        self.assertIn("重複の状態が変わりました", html)
        self.assertEqual(self.tree(), ["X.md", "X/index.txt"])

    def test_1段めのあとは_続けて整理するリンク(self):
        self.put("X.txt", "* txt版\n")
        _s, html = self.call("X")
        self.assertIn("どれも読まれていません", html)
        self.assertIn('name="stage" value="ext:X"', html)
        form = {"keep": ".md", "stage": "ext:X"}
        form.update({"hash" + ext: h for ext, h in self.hashes("X").items()})
        status, html = self.call("X", form=form)
        self.assertEqual(status, 200)
        self.assertIn("続けて整理する", html)
        _s, html = self.call("X")
        self.assertIn('name="stage" value="folder:X/index"', html)

    def test_編集の権限が無ければ_説明だけ(self):
        self.rules([("X", "W", "admin")])
        status, html = self.call("X", uid="bob")
        self.assertEqual(status, 403)
        self.assertIn("編集の権限が必要です", html)
        self.assertNotIn('name="keep"', html)


if __name__ == "__main__":
    unittest.main()
