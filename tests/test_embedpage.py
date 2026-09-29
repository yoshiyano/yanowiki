#!/usr/bin/env python3
"""別のページの本文を差し込むプラグイン（`include`・`pagediv`）が共有する
`plugin/_embedpage.py` のテスト。

見出し（`title_html`）の編集ボタンは `cmd=edit` をPOSTする `<form>` で、その
`action` は描画の後段（`render.rewrite_content_links`）が入口を補わない。既定の
Wiki以外で見出しを押すと、既定のWikiの同じ名前のページへ送られていた
（2026-09-25、`pagediv` で発覚）ので、入口（`/=Wiki名`）が付くことを見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_embedpage.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import auth, paths, userdb  # noqa: E402
from wikilib.pagesync import sync_wiki  # noqa: E402
from wikilib.paths import farm_plugin_dir  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import parse_source, rewrite_content_links  # noqa: E402

FARM = "other"


class TestTitleFormAction(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="embedpage-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(os.path.join(self.wiki_dir, "資料"))
        userdb.create_db(self.wiki_dir, "adminpw")
        self.kept = (paths.WIKIDATA_DIR, auth.SECRET_PATH)
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        for name in ("Top", "資料/メモ"):
            with open(os.path.join(self.wiki_dir, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(f"{name}の本文\n")
        sync_wiki(self.wiki_dir, {})
        bottle.request.bind({})

    def tearDown(self):
        paths.WIKIDATA_DIR, auth.SECRET_PATH = self.kept
        shutil.rmtree(self.work, ignore_errors=True)

    def render(self, text, base_url):
        """ページの表示と同じく、描いたあとに rewrite_content_links を通す。"""
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page="Top",
                                base_url=base_url, ext=".txt")
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        html = md.renderer.render(parse_source(md, text, ".txt", env), md.options, env)
        return rewrite_content_links(html, base_url, "Top", self.wiki_dir)

    def test_見出しの編集ボタンはこのWikiのページへ送る(self):
        want = 'action="/=other/%E8%B3%87%E6%96%99/%E3%83%A1%E3%83%A2"'
        for text in ("#pagediv(資料/メモ)", "#include(資料/メモ)"):
            with self.subTest(text=text):
                html = self.render(text, "/=other")
                self.assertIn(want, html)
                self.assertNotIn('action="/資料', html)

    def test_既定のWikiでは入口が付かない(self):
        html = self.render("#pagediv(資料/メモ)", "")
        self.assertIn('action="/%E8%B3%87%E6%96%99/%E3%83%A1%E3%83%A2"', html)


    def test_見出しの編集ボタンは差し込まれるページを編集できる人にだけ出す(self):
        # 入口は権限で出し分ける（theme.show_edit は 2026-09-29 に廃止）。include は
        # ページの情報を渡さないので、差し込まれるページ名で権限を引く
        from wikilib import privilege_records
        for uid in ("alice", "bob"):
            userdb.add_user(self.wiki_dir, uid, userdb.hash_password(self.wiki_dir, uid, "p"), uid)
        ok, message, _ = privilege_records.put(self.wiki_dir, "資料/メモ", "W", "bob")
        self.assertTrue(ok, message)
        for uid, want in (("alice", False), ("bob", True)):
            with self.subTest(uid=uid), auth.act_as(uid):
                html = self.render("#include(資料/メモ)", "/=other")
                self.assertEqual('name="cmd" value="edit"' in html, want, html)


if __name__ == "__main__":
    unittest.main()
