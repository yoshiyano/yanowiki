#!/usr/bin/env python3
"""取り込んだページを描き直す仕組み（`wikilib.pagesync.review_page`）のテスト。

**ファイルを直接置いて取り込んだページは、誰かが開くまで一度も描かれない。**
描いたときにしか作られない記録（プラグインが書き出すアクセス制限など。
[ページごとの権限](/Tech/PagePermissions)）が、その間ずっと欠けたままになる
ので、取り込みのときに1回描く（Wiki設計者の指示、2026-09-13）。

**描くと本文が書き換わるプラグインは、これから出てくる**（Wiki設計者、
2026-09-13。いまはまだ無い）。書き換わったら**描く前と描いたあとが一致する
まで**描き直し、`MAX_REVIEW`（既定5回）で打ち切る。

ここではそのためのプラグインを試験用に置いて、次の3つを見る。

    描かれること           描いた印がページに残るか
    落ち着くまで描くこと   1回だけ書き換えるプラグインで2回描かれるか
    打ち切ること           毎回書き換えるプラグインで MAX_REVIEW 回で止まるか

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pagereview.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.pagesync import MAX_REVIEW, review_page, sync_wiki  # noqa: E402

# 描くたびに本文の末尾へ1行足すプラグイン。**いつまでも落ち着かない**
GROW_PLUGIN = '''
"""試験用。描くたびに本文を書き換える。"""
from wikilib.pagesave import save_page
from wikilib.paths import resolve_page_ref

PLUGIN_INFO = {"help": "#grow()"}


def _convert(resolved, body, context):
    ref = resolve_page_ref(context.wiki_dir, context.page)
    if ref is not None and ref.exists:
        save_page(context.wiki_dir, context.config, ref.subpath, ref.ext,
                  ref.body + "x\\n", path=ref.path)
    return ""
'''

# 1回だけ本文を書き換えるプラグイン。**2回目には落ち着く**
ONCE_PLUGIN = '''
"""試験用。まだ印が無いときだけ本文を書き換える。"""
from wikilib.pagesave import save_page
from wikilib.paths import resolve_page_ref

MARK = "済"

PLUGIN_INFO = {"help": "#once()"}


def _convert(resolved, body, context):
    ref = resolve_page_ref(context.wiki_dir, context.page)
    if ref is not None and ref.exists and MARK not in ref.body:
        save_page(context.wiki_dir, context.config, ref.subpath, ref.ext,
                  ref.body + MARK + "\\n", path=ref.path)
    return ""
'''

# 本文は書き換えず、描かれたことだけを別のファイルに残すプラグイン。
# **記録を作るプラグイン**（アクセス制限の書き出し）に相当する
NOTE_PLUGIN = '''
"""試験用。描かれたら、その回数をファイルに残す。"""
import os

PLUGIN_INFO = {"help": "#note_render()"}


def _convert(resolved, body, context):
    path = os.path.join(os.path.dirname(context.wiki_dir), "rendered.txt")
    with open(path, "a", encoding="utf-8") as f:
        f.write((context.page or "(top)") + "\\n")
    return ""
'''


class ReviewTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pagereview-")
        self.farm_dir = os.path.join(self.work, "wikidata", "testwiki")
        self.wiki_dir = os.path.join(self.farm_dir, "wiki")
        self.plugin_dir = os.path.join(self.farm_dir, "plugin")
        os.makedirs(self.wiki_dir)
        os.makedirs(self.plugin_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put_plugin(self, name, source):
        with open(os.path.join(self.plugin_dir, name + ".py"), "w", encoding="utf-8") as f:
            f.write(source)

    def put(self, subpath, text):
        path = os.path.join(self.wiki_dir, subpath + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def body_of(self, subpath):
        with open(os.path.join(self.wiki_dir, subpath + ".md"), encoding="utf-8") as f:
            return f.read()

    def review(self, subpath):
        return review_page(self.wiki_dir, {}, "testwiki", subpath)


class TestReviewPage(ReviewTestBase):
    """1ページを描き直すところ。"""

    def test_描かれる(self):
        self.put_plugin("note_render", NOTE_PLUGIN)
        self.put("index", "本文\n\n#note_render()\n")
        done, settled = self.review("index")
        self.assertEqual(done, 1)   # 本文が変わらないので1回で済む
        self.assertTrue(settled)
        with open(os.path.join(self.farm_dir, "rendered.txt"), encoding="utf-8") as f:
            # **トップページ（index）の pagepath は空文字列。** 描かれたことは
            # この印で分かる
            self.assertEqual(f.read().strip(), "(top)")

    def test_本文が変わらなければ1回で終わる(self):
        self.put("index", "ただの本文\n")
        done, settled = self.review("index")
        self.assertEqual(done, 1)
        self.assertTrue(settled)

    def test_1回だけ書き換えるプラグインなら2回で落ち着く(self):
        self.put_plugin("once", ONCE_PLUGIN)
        self.put("index", "本文\n\n#once()\n")
        done, settled = self.review("index")
        self.assertEqual(done, 2)   # 1回目で書き換え、2回目で一致
        self.assertTrue(settled)
        self.assertIn("済", self.body_of("index"))

    def test_毎回書き換えるプラグインはMAX_REVIEWで打ち切る(self):
        self.put_plugin("grow", GROW_PLUGIN)
        self.put("index", "本文\n\n#grow()\n")
        done, settled = self.review("index")
        self.assertEqual(done, MAX_REVIEW)
        self.assertFalse(settled)   # 落ち着かなかったことを伝える

    def test_打ち切っても本文は残る(self):
        # 打ち切りは「記録が1回ぶん古い」だけで、ページが壊れるわけではない
        self.put_plugin("grow", GROW_PLUGIN)
        self.put("index", "本文\n\n#grow()\n")
        self.review("index")
        self.assertIn("#grow()", self.body_of("index"))

    def test_描画で例外が出ても落ち着いた扱いにする(self):
        # 描けないページがあることと、取り込みが失敗することは別
        self.put_plugin("boom", 'PLUGIN_INFO = {"help": "#boom()"}\n'
                                'def _convert(resolved, body, context):\n'
                                '    raise RuntimeError("こわれた")\n')
        self.put("index", "本文\n\n#boom()\n")
        done, settled = self.review("index")
        self.assertTrue(settled)
        self.assertGreaterEqual(done, 1)

    def test_無いページは描かない(self):
        done, settled = self.review("missing")
        self.assertEqual(done, 0)
        self.assertTrue(settled)


class TestSyncReviews(ReviewTestBase):
    """取り込み（`sync_wiki`）から呼ばれるところ。"""

    def test_取り込んだページは描かれる(self):
        self.put_plugin("note_render", NOTE_PLUGIN)
        self.put("index", "本文\n\n#note_render()\n")
        self.put("Guide", "本文\n\n#note_render()\n")
        result = sync_wiki(self.wiki_dir, config={}, farm="testwiki")
        self.assertEqual(result["reviewed"], 2)
        self.assertEqual(result["unsettled"], [])
        with open(os.path.join(self.farm_dir, "rendered.txt"), encoding="utf-8") as f:
            self.assertEqual(sorted(f.read().split()), ["(top)", "Guide"])

    def test_同じページを2度描かない(self):
        # 取り込みと「埋める」の両方に載ることがある
        self.put_plugin("note_render", NOTE_PLUGIN)
        self.put("index", "本文\n\n#note_render()\n")
        result = sync_wiki(self.wiki_dir, config={}, farm="testwiki")
        self.assertEqual(result["reviewed"], 1)

    def test_落ち着かなかったページを知らせる(self):
        self.put_plugin("grow", GROW_PLUGIN)
        self.put("index", "本文\n\n#grow()\n")
        result = sync_wiki(self.wiki_dir, config={}, farm="testwiki")
        self.assertEqual(result["unsettled"], ["index"])

    def test_消えたページは描かない(self):
        self.put("index", "本文\n")
        sync_wiki(self.wiki_dir, config={}, farm="testwiki")
        os.remove(os.path.join(self.wiki_dir, "index.md"))
        result = sync_wiki(self.wiki_dir, config={}, farm="testwiki")
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["reviewed"], 0)


if __name__ == "__main__":
    unittest.main()
