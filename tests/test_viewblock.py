#!/usr/bin/env python3
"""プラグインが「このページは出さない」と決める窓口（`PluginContext.block_view`）
のテスト。

閲覧期間の設定のように、**認証とは別の理由で表示を止めたい**プラグインのための
差込口（Wiki設計者の指示、2026-09-05）。本文の描画から
`wikilib.themes.render_with_theme` まで、同じ `PluginContext` が流れることを
使っている（`theme_override` と同じ仕掛け）。

**止まるのはページを開いたときの本文の描画だけ**で、本文そのものは編集画面・
見出し単位の取り出し・バックアップ・検索の抜粋からは今までどおり読める。
ここで見ているのも「本文の代わりに出るか」だけである。
秘密を守る用途に使えないことは `block_view` のdocstringに書いてある。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_viewblock.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.plugins import PluginContext  # noqa: E402
from wikilib.themes import render_with_theme  # noqa: E402

# 試験用のプラグイン。引数で渡された文言を添えて、本文を出さないよう頼む。
# 本物（viewable_period）は wikiPlugin が作るので、ここでは窓口が働くか
# だけを見られる最小のものを置く。
BLOCK_PLUGIN = '''"""試験用: 本文を出さないよう頼むだけのプラグイン。"""
PLUGIN_INFO = {"help": "#blocktest(status){{代わりに出す文}}",
               "args": [{"name": "status", "num_order": 1, "default": "200"}]}


def _convert(resolved, body, context):
    context.block_view("<p>" + (body or "") + "</p>", by="blocktest",
                       status=int(resolved.get("status") or 200))
    return ""
'''

# 2つ目。先に立てたほうが残ることを見るために使う
SECOND_PLUGIN = BLOCK_PLUGIN.replace("blocktest", "blocktest2")


class TestBlockView(unittest.TestCase):
    """窓口そのもの。**先に立てたものが効く。**"""

    def setUp(self):
        self.context = PluginContext(page="Page")

    def test_はじめは止まっていない(self):
        self.assertIsNone(self.context.view_block)

    def test_立てられる(self):
        self.assertTrue(self.context.block_view("<p>だめ</p>", by="a"))
        self.assertEqual(self.context.view_block["message"], "<p>だめ</p>")
        self.assertEqual(self.context.view_block["by"], "a")
        self.assertEqual(self.context.view_block["status"], 200)

    def test_あとから来たものは受け付けない(self):
        # あとから黙って書き換えると、どちらが効いたのか読み手にも
        # 書き手にも分からなくなる
        self.context.block_view("<p>さきに</p>", by="a")
        self.assertFalse(self.context.block_view("<p>あとから</p>", by="b"))
        self.assertEqual(self.context.view_block["by"], "a")

    def test_ステータスを指定できる(self):
        self.context.block_view("<p>だめ</p>", by="a", status=403)
        self.assertEqual(self.context.view_block["status"], 403)


class ViewBlockRenderTestBase(unittest.TestCase):
    """本文の描画を通したときに、実際に差し替わるか。

    Markdownのページで見ている。**先頭の見出しがページの題名になるのは
    Markdownだけ**（PukiWikiはページ名がそのまま題名。`uses_title_heading`）
    なので、「出さないと決めたページの見出しが題名として漏れないか」を
    見るには、こちらでないと確かめたことにならない。"""

    EXT = ".md"
    BODY = "# 見出しのひみつ\n\n本文のひみつ\n"

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="viewblock-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        self.plugin_dir = os.path.join(self.work, "wikidata", "testwiki", "plugin")
        os.makedirs(self.wiki_dir)
        os.makedirs(self.plugin_dir)
        self.put_plugin("blocktest", BLOCK_PLUGIN)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put_plugin(self, name, source):
        with open(os.path.join(self.plugin_dir, name + ".py"), "w", encoding="utf-8") as f:
            f.write(source)

    def render(self, body):
        res = render_with_theme(self.wiki_dir, {}, "testwiki", "Page", body,
                                False, "Page", ext=self.EXT)
        raw = res.body if hasattr(res, "body") else res
        return res, raw.decode("utf-8") if isinstance(raw, bytes) else raw


class TestBlockedPage(ViewBlockRenderTestBase):

    def blocked(self, message="いまは見せません"):
        return self.render(self.BODY + f"\n#blocktest(){{{{\n{message}\n}}}}\n")

    def test_本文は出ない(self):
        _res, html = self.blocked()
        self.assertNotIn("本文のひみつ", html)

    def test_代わりの文が出る(self):
        _res, html = self.blocked()
        self.assertIn("いまは見せません", html)

    def test_見出しは題名に使わない(self):
        # 出さないと決めたページの中身が、題名として出てしまわないように
        _res, html = self.blocked()
        self.assertNotIn("見出しのひみつ", html.split("</title>")[0])

    def test_編集リンクは消さない(self):
        # **閲覧できないことと編集できないことは別物**（Wiki設計者の指示、
        # 2026-09-05）。消してしまうと、期間を書き間違えたページを画面から
        # 直せなくなる。しかもサーバー側は cmd=edit を通すので、消しても
        # 「表から辿れないだけ」で編集は止まらない
        _res, html = self.blocked()
        self.assertIn("data-editable", html)

    def test_止めなければこれまでどおり(self):
        _res, html = self.render(self.BODY)
        self.assertIn("本文のひみつ", html)
        self.assertIn("見出しのひみつ", html.split("</title>")[0])
        self.assertIn("data-editable", html)

    def test_先に書いたほうの文が出る(self):
        self.put_plugin("blocktest2", SECOND_PLUGIN)
        _res, html = self.render(
            self.BODY + "\n#blocktest(){{\nさきの言い分\n}}\n"
            + "\n#blocktest2(){{\nあとの言い分\n}}\n")
        self.assertIn("さきの言い分", html)
        self.assertNotIn("あとの言い分", html)


class TestPageViewBlock(ViewBlockRenderTestBase):
    """止められているかを、ページを指定して確かめる（`editor.page_view_block`）。

    セクション編集の入口が使う。**描いてみないと分からない**（止めるかどうかを
    決めるのはプラグインの `_convert` で、それが動くのは解析ではなく描画のとき）
    ので、本文を1回描いて確かめている。"""

    def setUp(self):
        super().setUp()
        from wikilib.pagesave import save_page
        self.save = save_page

    def put(self, sub, body):
        self.save(self.wiki_dir, {}, sub, self.EXT, body)

    def block_of(self, sub):
        from wikilib.editor import page_view_block
        return page_view_block(self.wiki_dir, {}, "testwiki", sub)

    def test_止まっていれば中身が返る(self):
        self.put("Hidden", self.BODY + "\n#blocktest(){{\nいまは見せません\n}}\n")
        block = self.block_of("Hidden")
        self.assertIsNotNone(block)
        self.assertIn("いまは見せません", block["message"])
        self.assertEqual(block["by"], "blocktest")

    def test_止まっていなければNone(self):
        self.put("Open", self.BODY)
        self.assertIsNone(self.block_of("Open"))

    def test_無いページはNone(self):
        self.assertIsNone(self.block_of("NoSuchPage"))


if __name__ == "__main__":
    unittest.main()
