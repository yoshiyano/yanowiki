#!/usr/bin/env python3
"""comment プラグインが投稿日時を `&new{日時};` で囲んで書き足すこと、丸括弧の無い
`#comment` にも書き足せること（2026-09-26）。

Markdownのページでは丸括弧の無い `&new{…};` がプラグインにならないので、
`&new(){日時};` と書く。書き足した行がそれぞれの書きかたで new として描かれることも見る。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_commentdate.py     （このファイルだけ）
"""
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib.paths import farm_plugin_dir  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import parse_source  # noqa: E402


def load_comment():
    spec = importlib.util.spec_from_file_location(
        "plugin_under_test_comment", os.path.join(ROOT, "plugin", "comment.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAMP = r"\d{4}-\d{2}-\d{2} \(.\) \d{2}:\d{2}:\d{2}"


class TestCommentDate(unittest.TestCase):
    def setUp(self):
        self.comment = load_comment()
        self.work = tempfile.mkdtemp(prefix="commentdate-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "t", "wiki")
        os.makedirs(self.wiki_dir)
        bottle.request.bind({})

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def render(self, text, ext):
        context = PluginContext(config={}, farm="t", wiki_dir=self.wiki_dir, page="Top",
                                base_url="", ext=ext, partial=True)
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        return md.renderer.render(parse_source(md, text, ext, env), md.options, env)

    def test_PukiWiki記法は丸括弧なし(self):
        line = self.comment._format_comment("質問です", "", "山田", False, False, ".txt")
        self.assertRegex(line, r"^- 質問です -- 山田 &new\{" + STAMP + r"\};$")
        self.assertIn('class="__plugin_new new1"', self.render(line, ".txt"))

    def test_Markdownは丸括弧を付ける(self):
        line = self.comment._format_comment("質問です", "", "山田", False, False, ".md")
        self.assertRegex(line, r"^- 質問です -- 山田 &new\(\)\{" + STAMP + r"\};$")
        self.assertIn('class="__plugin_new new1"', self.render(line, ".md"))

    def test_nodateなら日時もnewも付けない(self):
        line = self.comment._format_comment("質問です", "", "山田", False, True, ".txt")
        self.assertEqual(line, "- 質問です -- 山田")

    def test_nonameでも日時はnewで囲む(self):
        line = self.comment._format_comment("質問です", "", "", True, False, ".txt")
        self.assertRegex(line, r"^- 質問です &new\{" + STAMP + r"\};$")


class TestBareComment(unittest.TestCase):
    """丸括弧の無い `#comment` にも投稿を書き足せる（PukiWiki記法のみ。2026-09-26）。
    書き込み先は 2026-09-30 から ID で探す（`tests/test_callid.py`）。ここでは本体への
    差し込みだけを見る。"""

    def setUp(self):
        self.comment = load_comment()

    def insert(self, source, name="comment"):
        # _polling.find_call が返す形の呼び出し（1行目）
        callid = self.comment._load_polling()
        line = source.split("\n")[0]
        call = {"line": 0, "loc": callid.locate(line, name)}
        return self.comment._insert_comment(source, call, "- 新しい投稿", True)

    def test_PukiWiki記法の丸括弧なし(self):
        self.assertEqual(self.insert("#comment\n"),
                         ("#comment{{\n- 新しい投稿\n}}\n", True))
        self.assertEqual(self.insert("#comment{{\n- 前の投稿\n}}"),
                         ("#comment{{\n- 新しい投稿\n- 前の投稿\n}}", True))

    def test_1行の本体には差し込めない(self):
        self.assertEqual(self.insert("#comment(){x}\n"), ("#comment(){x}\n", False))


if __name__ == "__main__":
    unittest.main()
