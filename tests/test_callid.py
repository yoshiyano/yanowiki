#!/usr/bin/env python3
"""`comment`・`vote` の書き込み先を、呼び出しごとの ID で見分けること（2026-09-30、
`plugin/_polling.py`。2026-10-23 までは `_callid.py`）。polling の試験は `tests/test_polling.py`。

- 描いたときに、ID の無い呼び出しへ `id="cmt…"` を書き足す（描かれない所は触らない）。
  本体が描き直す（`pagesave.watch_writes`）ので、表示に出るフォームには ID がある
- 投稿は ID で探す。同じ ID が重なっていれば最初のもの。無ければ「該当フォームがなくなりました」
- 別のページ（include など）と ID が重なっても振り直さない（2026-10-10）。同じページの
  中の重なりは、後のほうに新しい ID を振る（`oldid` は残さない。2026-10-22）
- 投稿は fetch（`X-Requested-With: fetch`）からだけ受け付け、成功は 204
- 保存済みの本文と対応の取れない呼び出しは、投稿できないフォームにする
- メニューページは、メニューページ自身を `page` にした context で描く（2026-10-05、
  `themes.render_menu`）ので、メニューの中の呼び出しにも ID が付き、投稿できる

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_callid.py     （このファイルだけ）
"""
import importlib.util
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib.pagesave import save_page, watch_writes  # noqa: E402
from wikilib.paths import farm_plugin_dir  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import render_source  # noqa: E402
from wikilib.themes import render_menu  # noqa: E402


def load_plugin(name):
    spec = importlib.util.spec_from_file_location(
        "plugin_under_test_" + name, os.path.join(ROOT, "plugin", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ID = r"cmt[0-9A-Za-z]{5}"
VID = r"vot[0-9A-Za-z]{5}"


class CallIdTestBase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="callid-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "t", "wiki")
        os.makedirs(self.wiki_dir)
        bottle.request.bind({})

    def tearDown(self):
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def write(self, page, text, ext=".md"):
        save_page(self.wiki_dir, {}, page, ext, text)

    def read(self, page, ext=".md"):
        with open(os.path.join(self.wiki_dir, page + ext), encoding="utf-8") as f:
            return f.read()

    def render_once(self, page, ext=".md", partial=False, text=None):
        """`page` を1回だけ描く。`text` を渡すと、`page` の context でその本文を描く（本体が
        メニューを描くときと同じ形）。(HTML, context)"""
        context = PluginContext(config={}, farm="t", wiki_dir=self.wiki_dir, page=page,
                                base_url="", ext=ext, partial=partial)
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        body = self.read(page, ext) if text is None else text
        html, _, _ = render_source(md, body, ext, True, context)
        return html, context

    def render(self, page, ext=".md", partial=False, text=None):
        """本体の表示（`views.render_page`）と同じく、描画の中で本文が書き換わったら描き直す。
        `text` を渡したときは、描き直しても同じ `text` を描く。"""
        for _ in range(5):
            with watch_writes() as written:
                html, _ = self.render_once(page, ext, partial, text)
            if not written:
                break
        return html

    def post(self, name, _headers=None, **fields):
        data = urlencode(fields).encode("utf-8")
        headers = {"HTTP_X_REQUESTED_WITH": "fetch"} if _headers is None else _headers
        bottle.request.bind({
            **headers,
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(data)),
            "wsgi.input": io.BytesIO(data),
        })
        context = PluginContext(config={}, farm="t", wiki_dir=self.wiki_dir, page="",
                                base_url="")
        try:
            return load_plugin(name)._action(context)
        finally:
            bottle.request.bind({})

    @staticmethod
    def form_ids(html, field="comment_id"):
        return re.findall(r'name="%s" value="([^"]*)"' % field, html)


class TestAssign(CallIdTestBase):
    def test_描かれない所は数えず書き換えない(self):
        # todo にあった例: #code の本体の #comment() が、後ろの本物の投稿先を奪っていた
        self.write("Top", "#code(){{\n#comment()\n}}\n\n#table(){{\n|a|\n#comment()\n|\\\\\n}}\n\n#comment()\n")
        html = self.render("Top")
        text = self.read("Top")
        self.assertIn("#code(){{\n#comment()\n}}", text)
        self.assertRegex(text, r'\|a\|\n#comment\(id="' + ID + r'"\)\n\|')
        m = re.search(r'\n\n#comment\(id="(' + ID + r')"\)\n', text)
        self.assertIsNotNone(m, text)
        # #table のセルの中には ID を書き足し、投稿できる（2026-10-23。TestTableCell）
        self.assertEqual(len(self.form_ids(html)), 2)
        self.assertEqual(self.form_ids(html)[1], m.group(1))

        r = self.post("comment", page="Top", msg="こんにちは", comment_id=m.group(1), newtop="1")
        self.assertEqual(r.status_code, 204)
        text = self.read("Top")
        self.assertIn("#code(){{\n#comment()\n}}", text)
        self.assertRegex(text, r'#comment\(id="' + ID + r'"\)\{\{\n- こんにちは -- 名無しさん ')

    def test_書き足した描画は捨てられ_描き直しで使える(self):
        # 1回目の描画で ID を書き足して保存する。そのフォームは投稿できない形だが、
        # 本体が描き直すので表示には出ない（2026-10-23）
        self.write("Top", "#comment()\n")
        with watch_writes() as written:
            first, _ = self.render_once("Top")
        self.assertTrue(written)
        self.assertIn('name="comment_id" value=""', first)
        html = self.render("Top")
        (cid,) = re.findall(ID, self.read("Top"))
        self.assertEqual(self.form_ids(html), [cid])
        self.assertIn("data-needs-js", html)

    def test_既にあるIDは上書きしない_無いものだけ書き足す(self):
        self.write("Top", '#comment(見出し, noname)\n\n#comment(id="cmt0abcd")\n')
        self.render("Top")
        text = self.read("Top")
        self.assertRegex(text, r'^#comment\(見出し, noname, id="' + ID + r'"\)\n')
        self.assertIn('#comment(id="cmt0abcd")', text)
        # 2回目は何も変えない
        self.render("Top")
        self.assertEqual(self.read("Top"), text)

    def test_展開する本体の中は数える(self):
        self.write("Top", "#note(){{\n#comment()\n}}\n")
        html = self.render("Top")
        self.assertRegex(self.read("Top"), r'#note\(\)\{\{\n#comment\(id="' + ID + r'"\)\n\}\}')
        self.assertEqual(len(self.form_ids(html)), 1)

    def test_PukiWiki記法の丸括弧なし(self):
        self.write("Top", "#comment\n#comment{{\n- 前\n}}\n", ".txt")
        html = self.render("Top", ".txt")
        text = self.read("Top", ".txt")
        self.assertRegex(text, r'^#comment\(id="' + ID + r'"\)\n#comment\(id="' + ID + r'"\)\{\{\n')
        ids = self.form_ids(html)
        self.assertEqual(len(ids), 2)
        r = self.post("comment", page="Top", msg="後", comment_id=ids[1], newtop="1")
        self.assertEqual(r.status_code, 204)
        self.assertRegex(self.read("Top", ".txt"), r'\{\{\n- 後 -- 名無しさん .*\n- 前\n\}\}')

    def test_部分プレビューでは書き換えない(self):
        self.write("Top", "#comment()\n")
        html = self.render("Top", partial=True)
        self.assertEqual(self.read("Top"), "#comment()\n")
        self.assertNotIn("poll-box", html)

    def test_トップページ_ページ名が空でも振る(self):
        # `/=Wiki名/` はページ名 "" のまま index を描く（2026-10-02、sandbox で投稿できなかった）
        self.write("index", "#vote(a,b)\n\n#comment()\n")
        # ページ名が空のときは index の本文を渡して描く。描き直しは読み直した本文で行う
        self.render_once("", text=self.read("index"))
        html = self.render("", text=self.read("index"))
        text = self.read("index")
        m = re.search(r'#comment\(id="(' + ID + r')"\)', text)
        self.assertIsNotNone(m, text)
        self.assertRegex(text, r'#vote\(a,b, id="' + VID + r'"\)')
        self.assertEqual(self.form_ids(html), [m.group(1)])
        self.assertNotIn(" disabled>", html)
        r = self.post("comment", page="", msg="トップから", comment_id=m.group(1), newtop="1")
        self.assertEqual(r.status_code, 204)
        self.assertIn("- トップから", self.read("index"))

    def test_1行の本体の中にも振る(self):
        self.write("Top", "#note(){#comment()}\n")
        html = self.render("Top")
        m = re.search(r'^#note\(\)\{#comment\(id="(' + ID + r')"\)\}$', self.read("Top"))
        self.assertIsNotNone(m, self.read("Top"))
        self.assertEqual(self.form_ids(html), [m.group(1)])

    def test_保存済みの本文と対応が取れなければ投稿できないフォーム(self):
        # 描いている本文が、保存済みの本文と食い違うとき（ファイルを直接直して、まだ
        # 取り込んでいないときなど）
        self.write("Top", "本文\n")
        html = self.render("Top", text="#comment()\n")
        self.assertIn('name="comment_id" value=""', html)
        self.assertIn("<button type=\"submit\" disabled>", html)
        self.assertNotIn("poll-box", html)
        self.assertNotIn("plugin-error", html)
        self.assertEqual(self.read("Top"), "本文\n")

    def test_引数の誤りがあっても他のフォームに影響しない(self):
        self.write("Top", "#comment(bad=1)\n\n#comment()\n")
        html = self.render("Top")
        m = re.search(r'\n#comment\(id="(' + ID + r')"\)\n', self.read("Top"))
        self.assertEqual(self.form_ids(html), [m.group(1)])


class TestDuplicate(CallIdTestBase):
    def test_同じページの中の重なりは後のほうを振り直す(self):
        self.write("Top", '#comment(id="cmt0abcd")\n\n#comment(id="cmt0abcd")\n')
        html = self.render("Top")
        text = self.read("Top")
        m = re.search(r'\n#comment\(id="(' + ID + r')"\)\n$', text)
        self.assertIsNotNone(m, text)
        self.assertTrue(text.startswith('#comment(id="cmt0abcd")\n'))
        self.assertNotIn("oldid", text)
        self.assertEqual(self.form_ids(html), ["cmt0abcd", m.group(1)])
        self.assertNotIn("plugin-error", html)

    def test_includeで別のページと重なっても振り直さない(self):
        # 表示しただけで、差し込み先のページの本文を書き換えない
        self.write("Sub", '#comment(id="cmt0abcd")\n')
        self.write("Top", '#comment(id="cmt0abcd")\n\n#include(Sub)\n')
        html = self.render("Top")
        self.assertEqual(self.form_ids(html), ["cmt0abcd", "cmt0abcd"])
        self.assertEqual(self.form_ids(html, "page"), ["Top", "Sub"])
        self.assertEqual(re.findall(r'data-poll-page="([^"]*)"', html), ["Top", "Sub"])
        self.assertEqual(self.read("Top"), '#comment(id="cmt0abcd")\n\n#include(Sub)\n')
        self.assertEqual(self.read("Sub"), '#comment(id="cmt0abcd")\n')

    def test_別のページと同じIDでも_投稿はpageで決まる(self):
        self.write("Sub", '#comment(id="cmt0abcd"){{\n}}\n')
        self.write("Top", '#comment(id="cmt0abcd"){{\n}}\n\n#include(Sub)\n')
        self.render("Top")
        r = self.post("comment", page="Sub", msg="差し込まれた側へ", comment_id="cmt0abcd", newtop="1")
        self.assertEqual(r.status_code, 204)
        self.assertIn("- 差し込まれた側へ", self.read("Sub"))
        self.assertNotIn("差し込まれた側へ", self.read("Top"))
        r = self.post("comment", page="Top", msg="取り込み元へ", comment_id="cmt0abcd", newtop="1")
        self.assertEqual(r.status_code, 204)
        self.assertIn("- 取り込み元へ", self.read("Top"))
        self.assertNotIn("取り込み元へ", self.read("Sub"))

    def test_includeした先のcommentへの投稿は_その先のページに入る(self):
        self.write("Sub", '#comment(id="cmt0wxyz")\n')
        self.write("Top", '本文\n\n#include(Sub)\n')
        html = self.render("Top")
        self.assertIn('name="page" value="Sub"', html)
        r = self.post("comment", page="Sub", msg="取り込み先から", comment_id="cmt0wxyz", newtop="1")
        self.assertEqual(r.status_code, 204)
        self.assertIn("- 取り込み先から", self.read("Sub"))
        self.assertEqual(self.read("Top"), '本文\n\n#include(Sub)\n')

    def test_同じページを2回差し込んでも振り直さない(self):
        self.write("Sub", '#comment(id="cmt0abcd")\n')
        self.write("Top", '#pagediv(Sub, Sub)\n')
        self.render("Top")
        self.assertEqual(self.read("Sub"), '#comment(id="cmt0abcd")\n')


class TestPost(CallIdTestBase):
    def test_保存されただけの重なりは最初に一致したものへ書く(self):
        # まだ描かれていない（振り直されていない）本文（2026-10-22）
        self.write("Top", '#comment(見出しA, id="cmt0abcd")\n\n#comment(見出しB, id="cmt0abcd")\n')
        r = self.post("comment", page="Top", msg="やあ", comment_id="cmt0abcd", newtop="1")
        self.assertEqual(r.status_code, 204)
        self.assertRegex(self.read("Top"), r'見出しA, id="cmt0abcd"\)\{\{\n- やあ ')

    def test_本文が変わっていても_IDで書き込む(self):
        # digest で断るのはやめた（ID で書き込み先を取り違えないため）
        self.write("Top", '#comment(id="cmt0abcd")\n')
        r = self.post("comment", page="Top", msg="やあ", comment_id="cmt0abcd",
                      digest="古いハッシュ", newtop="1")
        self.assertEqual(r.status_code, 204)

    def test_なくなったIDは断る(self):
        self.write("Top", '#comment(id="cmt0abcd")\n')
        r = self.post("comment", page="Top", msg="やあ", comment_id="cmt0zzzz", newtop="1")
        self.assertEqual(r.status_code, 409)
        self.assertIn("該当フォームがなくなりました", r.body)
        r = self.post("comment", page="Top", msg="やあ", comment_id="", newtop="1")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.read("Top"), '#comment(id="cmt0abcd")\n')

    def test_JSからでない投稿は断る(self):
        # JS が使えない環境では投稿を受け付けない（2026-10-20）
        self.write("Top", '#comment(id="cmt0abcd")\n')
        for name, fields in (("comment", {"msg": "やあ", "comment_id": "cmt0abcd"}),
                             ("vote", {"vote_id": "cmt0abcd", "index": "0"})):
            with self.subTest(name=name):
                r = self.post(name, _headers={}, page="Top", **fields)
                self.assertEqual(r.status_code, 400)
                self.assertIn("この環境では投稿ができません", r.body)
        self.assertEqual(self.read("Top"), '#comment(id="cmt0abcd")\n')

    def test_リストの中の呼び出しには字下げをそろえて書き足す(self):
        self.write("Top", '- 項目\n  #comment(id="cmt0abcd")\n')
        r = self.post("comment", page="Top", msg="やあ", comment_id="cmt0abcd", newtop="1")
        self.assertEqual(r.status_code, 204)
        self.assertRegex(self.read("Top"),
                         r'  #comment\(id="cmt0abcd"\)\{\{\n  - やあ .*\n  \}\}\n')


class TestMenu(CallIdTestBase):
    def render_with_menu(self, page, menu="mainmenu"):
        """`page` を描いたあと、同じ context でメニューを描く（本体の `render_theme` と同じ順）。
        描画の中で本文が書き換わったら描き直す。(本文のHTML, メニューのHTML, context)"""
        for _ in range(5):
            with watch_writes() as written:
                context = PluginContext(config={}, farm="t", wiki_dir=self.wiki_dir, page=page,
                                        base_url="", ext=".md")
                md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
                body, _, _ = render_source(md, self.read(page), ".md", True, context)
                menu_html = render_menu(md, self.wiki_dir, "", menu, context)
            if not written:
                break
        return body, menu_html, context

    def test_メニューの中のcommentにIDが付き_投稿できる(self):
        self.write("Top", "本文\n")
        self.write("mainmenu", "#comment()\n")
        _body, menu, context = self.render_with_menu("Top")
        m = re.search(r'^#comment\(id="(' + ID + r')"\)\n$', self.read("mainmenu"))
        self.assertIsNotNone(m, self.read("mainmenu"))
        self.assertEqual(self.form_ids(menu), [m.group(1)])
        self.assertIn('name="page" value="mainmenu"', menu)
        self.assertNotIn(" disabled>", menu)
        self.assertEqual(self.read("Top"), "本文\n")
        # 本文の context は変わらない
        self.assertEqual(context.page, "Top")
        # 投稿はメニューページに入る
        r = self.post("comment", page="mainmenu", msg="メニューから", comment_id=m.group(1),
                      newtop="1")
        self.assertEqual(r.status_code, 204)
        self.assertIn("- メニューから", self.read("mainmenu"))

    def test_メニューの中のvoteにもIDが付く(self):
        self.write("Top", "本文\n")
        self.write("mainmenu", "#vote(はい, いいえ)\n")
        _body, menu, _context = self.render_with_menu("Top")
        m = re.search(r'id="(' + VID + r')"', self.read("mainmenu"))
        self.assertIsNotNone(m, self.read("mainmenu"))
        self.assertEqual(self.form_ids(menu, "vote_id"), [m.group(1)])
        self.assertNotIn(" disabled>", menu)

    def test_メニューページ自身を開いても同じIDになる(self):
        self.write("mainmenu", "#comment()\n")
        body, menu, _context = self.render_with_menu("mainmenu")
        ids = re.findall(ID, self.read("mainmenu"))
        self.assertEqual(len(ids), 1)
        self.assertEqual(self.form_ids(body), ids)
        self.assertEqual(self.form_ids(menu), ids)
        self.assertNotIn(" disabled>", body + menu)

    def test_本文とメニューのそれぞれにあっても取り違えない(self):
        self.write("Top", "#comment()\n")
        self.write("mainmenu", "#comment()\n")
        body, menu, _context = self.render_with_menu("Top")
        (top_id,) = re.findall(ID, self.read("Top"))
        (menu_id,) = re.findall(ID, self.read("mainmenu"))
        self.assertEqual(self.form_ids(body), [top_id])
        self.assertEqual(self.form_ids(menu), [menu_id])
        self.assertIn('name="page" value="Top"', body)
        self.assertIn('name="page" value="mainmenu"', menu)
        # フォームの部品の id（label の for の対応）も、本文とメニューで重ならない
        ids = re.findall(r'\bid="(comment-[a-z]+-[^"]+)"', body + menu)
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 4, ids)


class TestVote(CallIdTestBase):
    def test_IDを書き足し_投票で残す(self):
        self.write("Top", "#code(){{\n#vote(x,y)\n}}\n\n#vote(カレー,ラーメン)\n")
        html = self.render("Top")
        text = self.read("Top")
        self.assertIn("#code(){{\n#vote(x,y)\n}}", text)
        m = re.search(r'#vote\(カレー,ラーメン, id="(' + VID + r')"\)', text)
        self.assertIsNotNone(m, text)
        self.assertEqual(self.form_ids(html, "vote_id"), [m.group(1)])
        r = self.post("vote", page="Top", vote_id=m.group(1), index="1")
        self.assertEqual(r.status_code, 204)
        self.assertIn(f'#vote(カレー[0],ラーメン[1], id="{m.group(1)}")', self.read("Top"))
        self.assertIn("#code(){{\n#vote(x,y)\n}}", self.read("Top"))

    def test_commentとvoteが同じページでも保存は1回(self):
        self.write("Top", "#vote(a,b)\n\n#comment()\n")
        with watch_writes() as written:
            self.render_once("Top")
        self.assertEqual(len(written), 1)
        html = self.render("Top")
        text = self.read("Top")
        self.assertRegex(text, r'#vote\(a,b, id="' + VID + r'"\)\n\n#comment\(id="' + ID + r'"\)')
        self.assertEqual(len(self.form_ids(html, "vote_id")), 1)
        self.assertEqual(len(self.form_ids(html)), 1)

    def test_投票できない注意書きも描画範囲に入る(self):
        self.write("Top", "本文\n")
        html = self.render("Top", text="#vote(a,b)\n")
        self.assertIn("ここからは投票できません", html)
        self.assertNotIn("poll-box", html)


class TestTableCell(CallIdTestBase):
    """`#table` のセルの中の呼び出し（2026-10-23。セルがブロック要素を描くようになり、
    走査もセルの中まで見るようになった）。"""

    def cell_ids(self, page, ext=".md"):
        return re.findall(ID, self.read(page, ext))

    def test_セルのcommentにもIDが付き_投稿できる(self):
        for ext in (".md", ".txt"):
            with self.subTest(ext=ext):
                self.write("Top", "#table(){{\n|~欄|h\\\\\n|#comment()|\\\\\n}}\n\n#comment()\n", ext)
                html = self.render("Top", ext)
                text = self.read("Top", ext)
                cell_id, tail_id = self.cell_ids("Top", ext)
                self.assertIn(f'|#comment(id="{cell_id}")|\\\\', text)
                self.assertEqual(self.form_ids(html), [cell_id, tail_id])
                self.assertNotIn("ここからは投稿できません", html)
                r = self.post("comment", page="Top", msg="セルへ", comment_id=cell_id, newtop="1")
                self.assertEqual(r.status_code, 204)
                text = self.read("Top", ext)
                # 閉じ括弧の行にセルの残りを続ける（閉じ括弧だけの行にしない）
                self.assertRegex(text, r'\|#comment\(id="' + cell_id + r'"\)\{\{\n- セルへ .*\n\}\}\|\\\\\n\}\}\n')
                # 2回目は既存の本体に足す（newbottom でも）
                r = self.post("comment", page="Top", msg="2つ目", comment_id=cell_id, newtop="0")
                self.assertEqual(r.status_code, 204)
                text = self.read("Top", ext)
                self.assertRegex(text, r'- セルへ .*\n- 2つ目 .*\n\}\}\|\\\\\n\}\}\n')
                html = self.render("Top", ext)
                # 表は壊れず、後ろの #comment も描かれる
                self.assertEqual(html.count("<table"), 1)
                self.assertIn("セルへ", html)
                self.assertEqual(self.form_ids(html), [cell_id, tail_id])
                self.assertNotIn("plugin-error", html)

    def test_同じ行の複数のセルと_目印付きのセル(self):
        self.write("Top", "#table(){{\n|CENTER:#comment(左)|~#comment(右)|\\\\\n}}\n")
        html = self.render("Top")
        left, right = self.cell_ids("Top")
        self.assertIn(f'|CENTER:#comment(左, id="{left}")|~#comment(右, id="{right}")|\\\\', self.read("Top"))
        self.assertEqual(self.form_ids(html), [left, right])
        r = self.post("comment", page="Top", msg="右へ", comment_id=right, newtop="1")
        self.assertEqual(r.status_code, 204)
        text = self.read("Top")
        self.assertIn(f'#comment(右, id="{right}"){{{{\n- 右へ', text)
        self.assertRegex(text, r'\n\}\}\|\\\\\n\}\}\n$')
        self.assertNotIn("右へ", self.render("Top").split("左")[1].split("右")[0])

    def test_セルのvoteに投票でき_問い合わせにも答える(self):
        self.write("Top", "#table(){{\n|#vote(a,b)|\\\\\n}}\n")
        html = self.render("Top")
        (vid,) = re.findall(VID, self.read("Top"))
        self.assertEqual(self.form_ids(html, "vote_id"), [vid])
        r = self.post("vote", page="Top", vote_id=vid, index="1")
        self.assertEqual(r.status_code, 204)
        self.assertIn(f'|#vote(a[0],b[1], id="{vid}")|\\\\', self.read("Top"))

    def test_tsvの表の中は見ない(self):
        self.write("Top", "#table(tsv){{\n#comment()\tx\n}}\n")
        self.render("Top")
        self.assertEqual(self.read("Top"), "#table(tsv){{\n#comment()\tx\n}}\n")

    def test_セルにincludeした見出しはidを持たない(self):
        self.write("Sub", "## 差し込んだ見出し\n本文\n")
        self.write("Top", "## 本文の見出し\n\n#table(){{\n|#include(Sub)|\\\\\n}}\n")
        html = self.render("Top")
        self.assertIn('id="本文の見出し"', html)
        self.assertIn("差し込んだ見出し", html)
        self.assertNotIn('id="差し込んだ見出し"', html)

if __name__ == "__main__":
    unittest.main()
