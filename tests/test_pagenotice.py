#!/usr/bin/env python3
"""タイトル右端の info（`page_info`）に出す知らせ（wikilib.pagenotice）。

同じページ名に `.txt` と `.md` の両方があるとき、整理の画面（`/.solveDupPage/<ページ名>`）へ
つなぐ `<a>` を返す。
**無いときは空の Markup**（テーマは空のあいだ幅を取らない）。

実行:
    _venv/bin/python3 tests/test_pagenotice.py
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from bottle import request  # noqa: E402
from markupsafe import Markup  # noqa: E402

from wikilib.pagenotice import (  # noqa: E402
    DUPLICATE_GUIDE_PAGE, duplicate_notice, guide_url, page_info_for, solve_url,
)
from wikilib.paths import SOLVEDUP_URLPATH, page_files  # noqa: E402

CONFIG = {"farm": {"default": "_system"}}


class PageNoticeTest(unittest.TestCase):
    def setUp(self):
        request.bind({})  # X-Forwarded-Prefix なし
        self.wiki_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.wiki_dir)

    def put(self, name, text="x\n"):
        path = os.path.join(self.wiki_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def info(self, subpath, farm="_system", base_url="", shown_ext=None):
        return page_info_for(CONFIG, farm, base_url, self.wiki_dir, subpath, shown_ext)

    def test_page_files_は閲覧で読まれる順に返す(self):
        self.put("A.md")
        self.put("A.txt")
        target = os.path.join(self.wiki_dir, "A")
        self.assertEqual(page_files(target), [target + ".txt", target + ".md"])
        self.assertEqual(page_files(os.path.join(self.wiki_dir, "none")), [])

    def test_片方だけなら空(self):
        self.put("A.txt")
        self.put("B.md")
        for subpath in ("A", "B", "none"):
            html = self.info(subpath)
            self.assertIsInstance(html, Markup)
            self.assertEqual(html, "")
        self.assertIsNone(duplicate_notice(CONFIG, "_system", "", self.wiki_dir, "A"))

    def test_両方あれば整理の画面へつなぐ(self):
        self.put("A.txt")
        self.put("A.md")
        html = self.info("A")
        self.assertIsInstance(html, Markup)
        self.assertIn('class="page-info"', html)
        self.assertIn('href="/' + SOLVEDUP_URLPATH + '/A"', html)
        self.assertIn("整理の画面を開きます", html)
        self.assertIn("<svg", html)
        # 名前の分からない絵だけにしない（読み上げ）
        self.assertIn('aria-label="', html)
        # どのファイルが読まれ、どれが読まれないかを title で伝える
        self.assertIn("A.txt・A.md", html)
        self.assertIn("A.txt が優先され、A.md は読まれません", html)

    def test_画面に出ているのが優先されないほうなら_そう伝える(self):
        # .md を公開したあとで .txt を置いた（取り込み前）。画面は .md のまま
        self.put("A.txt")
        self.put("A.md")
        html = self.info("A", shown_ext=".md")
        self.assertIn("いま画面に出ているのは、取り込み済みの A.md です", html)
        self.assertIn("A.txt の内容に替わります", html)
        self.assertNotIn("A.md は読まれません", html)
        # 画面に出ているのが優先されるほうなら、これまでの文
        html = self.info("A", shown_ext=".txt")
        self.assertIn("A.txt が優先され、A.md は読まれません", html)
        self.assertNotIn("いま画面に出ているのは", html)

    def test_フォルダを兼ねるページは_index_を見る(self):
        self.put("Tech/index.txt")
        self.put("Tech/index.md")
        self.assertIn("index.txt が優先され、index.md は読まれません", self.info("Tech/index"))
        self.assertIn("取り込み済みの index.md です",
                      self.info("Tech/index", shown_ext=".md"))
        # 親の「Tech」には実体が無いので、重複とは言わない
        self.assertEqual(self.info("Tech"), "")

    def test_整理の画面は_いま開いているWikiのもの(self):
        # 案内ページのように `_system` へは飛ばさない（整理するのはそのWikiのページ）
        self.put("A.txt")
        self.put("A.md")
        html = self.info("A", farm="mywiki", base_url="/=mywiki")
        self.assertIn('href="/=mywiki/' + SOLVEDUP_URLPATH + '/A"', html)
        self.assertNotIn("=_system", html)

    def test_整理の画面のURL(self):
        self.assertEqual(solve_url("", "A"), "/" + SOLVEDUP_URLPATH + "/A")
        self.assertEqual(solve_url("/=w", "Tech/Foo"), "/=w/" + SOLVEDUP_URLPATH + "/Tech/Foo")
        # トップページは名前を付けない
        self.assertEqual(solve_url("", ""), "/" + SOLVEDUP_URLPATH)
        self.assertEqual(solve_url("", "日本語"), "/" + SOLVEDUP_URLPATH + "/%E6%97%A5%E6%9C%AC%E8%AA%9E")

    def test_フォルダの入口とトップページのURL(self):
        self.put("Tech/index.txt")
        self.put("Tech/index.md")
        self.assertIn('href="/' + SOLVEDUP_URLPATH + '/Tech"', self.info("Tech/index"))
        self.put("index.txt")
        self.put("index.md")
        self.assertIn('href="/' + SOLVEDUP_URLPATH + '"', self.info("index"))

    def test_別のWikiからの案内ページは_system_を明示して開く(self):
        url = guide_url(CONFIG, "mywiki", "/=mywiki", DUPLICATE_GUIDE_PAGE)
        self.assertEqual(url, "/=_system/" + DUPLICATE_GUIDE_PAGE)

    def test_案内のあるWikiでは入口をそのまま使う(self):
        # `/=_system/…` と明示して見ているときは、その景色を変えない
        url = guide_url(CONFIG, "_system", "/=_system", DUPLICATE_GUIDE_PAGE)
        self.assertEqual(url, "/=_system/" + DUPLICATE_GUIDE_PAGE)

    def test_属性に入る値は_escape_される(self):
        self.put('a"<b>&.txt')
        self.put('a"<b>&.md')
        html = self.info('a"<b>&')
        self.assertNotIn("<b>", html)
        self.assertNotIn('a"<b>', html)
        self.assertIn("a&#34;&lt;b&gt;&amp;.txt", html)

    def test_同じ名前のファイルとフォルダ_入口があるとき(self):
        self.put("X.md")
        self.put("X/index.txt")
        html = self.info("X/index")
        self.assertIn('href="/' + SOLVEDUP_URLPATH + '/X"', html)
        self.assertIn("同じ名前のファイルとフォルダがあります（X.md と X/）", html)
        self.assertIn("X/index.txt が優先され、X.md は読まれません", html)

    def test_同じ名前のファイルとフォルダ_入口が無いとき(self):
        self.put("X.md")
        self.put("X/kid.md")
        html = self.info("X/index")
        self.assertIn("フォルダに入口のページ（index）が無いので", html)

    def test_フォルダに隠れた_txt_と_md(self):
        self.put("X.txt")
        self.put("X.md")
        self.put("X/index.md")
        self.assertIn("どれも、同じ名前のフォルダ X/ があるため読まれません", self.info("X/index"))

    def test_入口の_txt_と_md_を先に知らせる(self):
        self.put("X.md")
        self.put("X/index.txt")
        self.put("X/index.md")
        self.assertIn("index.txt が優先され、index.md は読まれません", self.info("X/index"))

    def test_フォルダだけ_ファイルだけなら空(self):
        self.put("X/index.md")
        self.put("Y.md")
        self.assertEqual(self.info("X/index"), "")
        self.assertEqual(self.info("Y"), "")
        self.assertEqual(self.info("index"), "")


if __name__ == "__main__":
    unittest.main()
