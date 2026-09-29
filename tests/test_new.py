#!/usr/bin/env python3
"""new プラグイン（日付・ページの更新の新しさに「New!」の印を付ける）のテスト。

本家の書きかた（`&new{日付};`・`&new(nodate){日付};`・`&new(ページ名[,nolink]);`・
`&new(フォルダ/);`）が通ること、印の段階（1日以内 New!・5日以内 New）、閲覧できない
ページを無いページと同じに扱うことを見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_new.py     （このファイルだけ）
"""
import datetime
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import auth, pagedb, paths, privilege_records, userdb  # noqa: E402
from wikilib.auth import act_as  # noqa: E402
from wikilib.pagesync import sync_wiki  # noqa: E402
from wikilib.paths import farm_plugin_dir  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import parse_source  # noqa: E402

FARM = "testwiki"


def load_new():
    spec = importlib.util.spec_from_file_location(
        "plugin_under_test_new", os.path.join(ROOT, "plugin", "new.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local(*args):
    return datetime.datetime(*args).astimezone()


class TestParseAndMark(unittest.TestCase):
    """日付の読みかたと、印の段階。"""

    def setUp(self):
        self.new = load_new()

    def test_日付の読みかた(self):
        parse = self.new.parse_date
        self.assertEqual(parse("2026-09-25 (金) 18:15:23"), local(2026, 9, 25, 18, 15, 23))
        self.assertEqual(parse("2026/9/25 18:15"), local(2026, 9, 25, 18, 15))
        self.assertEqual(parse("2026-09-25"), local(2026, 9, 25))
        self.assertEqual(parse("2026-09-25T18:15:23+00:00"),
                         datetime.datetime(2026, 9, 25, 18, 15, 23, tzinfo=datetime.timezone.utc))
        self.assertIsNone(parse("きのう"))
        self.assertIsNone(parse("2026-13-40"))

    def test_印の段階(self):
        now = local(2026, 9, 26, 12, 0, 0)
        mark = self.new.mark_html
        self.assertIn('class="__plugin_new new1"', mark(local(2026, 9, 26, 9, 0, 0), now))
        self.assertIn("> New!</span>", mark(local(2026, 9, 26, 9, 0, 0), now))
        self.assertIn('title="(3h)"', mark(local(2026, 9, 26, 9, 0, 0), now))
        self.assertIn('class="__plugin_new new5"', mark(local(2026, 9, 23, 12, 0, 0), now))
        self.assertIn("> New</span>", mark(local(2026, 9, 23, 12, 0, 0), now))
        old = mark(local(2026, 9, 20, 12, 0, 0), now)
        self.assertEqual(old, '<span class="__plugin_new" data-mtime="'
                              + local(2026, 9, 20, 12, 0, 0).isoformat(timespec="seconds")
                              + '"></span>')

    def test_経過時間の書きかた(self):
        now = local(2026, 9, 26, 12, 0, 0)
        self.assertEqual(self.new.passage(local(2026, 9, 26, 11, 30, 0), now), "(30m)")
        self.assertEqual(self.new.passage(local(2026, 9, 24, 12, 0, 0), now), "(2d)")


class TestRender(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="new-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(os.path.join(self.wiki_dir, "日記"))
        userdb.create_db(self.wiki_dir, "adminpw")
        userdb.add_user(self.wiki_dir, "alice",
                        userdb.hash_password(self.wiki_dir, "alice", "p"), "alice")
        self.kept = (paths.WIKIDATA_DIR, auth.SECRET_PATH)
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        for name in ("Top", "メモ", "日記/2026-09-20", "日記/2026-09-25"):
            with open(os.path.join(self.wiki_dir, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(name)
        sync_wiki(self.wiki_dir, {})
        self.set_updated("日記/2026-09-20", "2026-09-20 10:00:00")
        self.set_updated("日記/2026-09-25", "2026-09-25 10:00:00")
        bottle.request.bind({})

    def tearDown(self):
        paths.WIKIDATA_DIR, auth.SECRET_PATH = self.kept
        shutil.rmtree(self.work, ignore_errors=True)

    def set_updated(self, subpath, stamp):
        with pagedb.connect(self.wiki_dir) as con:
            con.execute("UPDATE pages SET updated = ? WHERE subpath = ?", (stamp, subpath))

    def render(self, text, uid=None, ext=".txt"):
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page="Top",
                                base_url="", ext=ext)
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        with (act_as(uid) if uid else mock.MagicMock()):
            return md.renderer.render(parse_source(md, text, ext, env), md.options, env)

    def test_日付を書く形(self):
        html = self.render("&new{2022-12-23 (金) 18:33:02};")
        self.assertIn('<span class="comment_date">2022-12-23 (金) 18:33:02'
                      '<span class="__plugin_new" data-mtime="2022-12-23T18:33:02', html)

    def test_nodateは日付の文字を出さない(self):
        html = self.render("&new(nodate){2022-12-23 (金) 18:33:02};")
        self.assertIn('<span class="comment_date"><span class="__plugin_new"', html)
        self.assertNotIn("18:33:02</", html)

    def test_Markdownでは丸括弧を付ける(self):
        html = self.render("&new(){2022-12-23 18:33:02};", ext=".md")
        self.assertIn('class="comment_date"', html)

    def test_ページを指定する形(self):
        html = self.render("&new(メモ);")
        self.assertIn('<a href="/メモ">メモ</a><span class="__plugin_new new1"', html)
        self.assertNotIn("<a ", self.render("&new(メモ,nolink);"))

    def test_フォルダは一番新しいページ(self):
        html = self.render("&new(日記/);")
        self.assertIn('<a href="/日記/2026-09-25">日記/2026-09-25</a>', html)
        self.assertIn('data-mtime="2026-09-25T10:00:00', html)

    def test_閲覧できないページは無いページと同じ(self):
        ok, message, _ = privilege_records.put(self.wiki_dir, "日記/2026-09-25", "R", "alice")
        self.assertTrue(ok, message)
        self.assertIn('<a href="/日記/2026-09-20">', self.render("&new(日記/);"))
        self.assertIn('<a href="/日記/2026-09-25">', self.render("&new(日記/);", uid="alice"))
        ok, message, _ = privilege_records.put(self.wiki_dir, "メモ", "R", "alice")
        self.assertTrue(ok, message)
        self.assertIn("plugin-error", self.render("&new(メモ);"))

    def test_エラー(self):
        for text in ("&new(なし);", "&new(無い/);", "&new{きのう};", "&new(メモ){2026-09-25};"):
            with self.subTest(text=text):
                self.assertIn("plugin-error", self.render(text))


class TestDropOldCalls(TestRender):
    """5日を過ぎた日付の `&new` は、描いたときに本文から外す（Wiki設計者の指示、2026-09-26）。"""

    def page_text(self, name, ext=".txt"):
        with open(os.path.join(self.wiki_dir, name + ext), encoding="utf-8") as f:
            return f.read()

    def put_page(self, name, text, ext=".txt"):
        with open(os.path.join(self.wiki_dir, name + ext), "w", encoding="utf-8") as f:
            f.write(text)
        sync_wiki(self.wiki_dir, {})

    def view(self, name, ext=".txt", partial=False):
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page=name,
                                base_url="", ext=ext, partial=partial)
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        text = self.page_text(name, ext)
        return md.renderer.render(parse_source(md, text, ext, env), md.options, env)

    def test_古いものは外れ_新しいものとページ指定は残る(self):
        soon = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.put_page("メモ", "- 古い -- &new{2022-12-23 (金) 18:33:02};\n"
                              "- 印だけ -- &new(nodate){2022-12-23 (金) 18:33:02};です\n"
                              f"- 新しい -- &new{{{soon}}};\n"
                              "- ページ -- &new(Top);\n")
        html = self.view("メモ")
        self.assertIn("comment_date", html)   # 描いた回は、これまでどおり出る
        self.assertEqual(self.page_text("メモ"),
                         "- 古い -- 2022-12-23 (金) 18:33:02\n"
                         "- 印だけ -- です\n"
                         f"- 新しい -- &new{{{soon}}};\n"
                         "- ページ -- &new(Top);\n")

    def test_部分プレビューでは書き換えない(self):
        # 取り込み（sync_wiki）はページを1回描くので、そこで書き換わってしまう。
        # ファイルを置くだけにして、プレビューの描画だけを見る
        with open(os.path.join(self.wiki_dir, "メモ.txt"), "w", encoding="utf-8") as f:
            f.write("&new{2022-12-23 (金) 18:33:02};\n")
        self.view("メモ", partial=True)
        self.assertEqual(self.page_text("メモ"), "&new{2022-12-23 (金) 18:33:02};\n")

    def test_書きかたの例は書き換えない(self):
        text = ("```\n&new(){2022-12-23};\n```\n"
                "`&new(){2022-12-23};`\n"
                "#code(){{\n&new(){2022-12-23};\n}}\n"
                "&new{2022-12-23};\n"           # Markdownではプラグインにならない
                "&new(){2022-12-23};\n")
        self.put_page("例", text, ext=".md")
        self.view("例", ext=".md")
        self.assertEqual(self.page_text("例", ".md"), (
            "```\n&new(){2022-12-23};\n```\n"
            "`&new(){2022-12-23};`\n"
            "#code(){{\n&new(){2022-12-23};\n}}\n"
            "&new{2022-12-23};\n"
            "2022-12-23\n"))

    def test_PukiWiki記法の整形済みテキストと本体は書き換えない(self):
        text = (" &new{2022-12-23};\n"
                "#code{{\n&new{2022-12-23};\n}}\n"
                "&new{2022-12-23};\n")
        self.put_page("例", text)
        self.view("例")
        self.assertEqual(self.page_text("例"), (" &new{2022-12-23};\n"
                                               "#code{{\n&new{2022-12-23};\n}}\n"
                                               "2022-12-23\n"))


if __name__ == "__main__":
    unittest.main()
