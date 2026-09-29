#!/usr/bin/env python3
"""ページの記録（wikilib.pagedb）のうち、**一覧の組み立て**のテスト。

見ているのは `page_children`（`os.listdir` にあたるもの）である。
**OSのフォルダとwikiのフォルダは意味が違う。** OSから見れば `講義/第07回/` は
ただのフォルダだが、そこに入口（`第07回/index`）があれば、wikiの世界では
`/講義/第07回` という1枚のページになる。この読み替えを呼び出し側が自分で
書くと、名前の形（`/` が続くか）だけで判断してしまい、**入口を持つフォルダが
一覧から丸ごと消える**（`#ls()` で実際に起きた。Wiki設計者の指示、2026-09-05）。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pagedb.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.pagedb import page_children, page_entries  # noqa: E402
from wikilib.pagesave import save_page  # noqa: E402


class PageChildrenTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pagedb-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, subpath, text="* 本文\n"):
        path = os.path.join(self.wiki_dir, subpath + ".txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        save_page(self.wiki_dir, {}, subpath, ".txt", text, write=False)

    def shape(self, prefix="", entries=None):
        """(名前, そのページのURL または None, 下にまだあるか) の列。"""
        return [(c["name"], c["page"]["pagepath"] if c["page"] else None, c["has_more"])
                for c in page_children(self.wiki_dir, prefix, entries)]


class TestPageChildren(PageChildrenTestBase):

    def test_入口を持つフォルダは1枚のページとして出る(self):
        # これが出ないのが #ls() の不具合だった
        self.put("講義/第07回/index")
        self.assertEqual(self.shape("講義"), [("第07回", "講義/第07回", False)])

    def test_入口の下にページがあれば下にまだあると分かる(self):
        self.put("講義/第07回/index")
        self.put("講義/第07回/演習課題1")
        self.assertEqual(self.shape("講義"), [("第07回", "講義/第07回", True)])

    def test_入口の無いフォルダは通り道として返す(self):
        # 開けるページが無いので page は None。それでも名前は返す
        # （下に何かあることは分かるので、辿るかどうかは呼び出し側が決める）
        self.put("講義/第07回/演習課題1")
        self.assertEqual(self.shape("講義"), [("第07回", None, True)])

    def test_ふつうのページはそのまま(self):
        self.put("講義/資料")
        self.assertEqual(self.shape("講義"), [("資料", "講義/資料", False)])

    def test_区切りの付けかたは問わない(self):
        self.put("講義/資料")
        self.assertEqual(self.shape("講義"), self.shape("講義/"))

    def test_Wikiの直下も同じように読める(self):
        self.put("index")
        self.put("講義/index")
        self.assertEqual(self.shape(""),
                         [("index", "", False), ("講義", "講義", False)])

    def test_そのフォルダ自身の入口も1つ返る(self):
        # #ls() を入口ページに置いたとき自分を落とすかは、見せかたの都合なので
        # 呼び出し側に決めてもらう
        self.put("講義/index")
        self.put("講義/資料")
        self.assertEqual(self.shape("講義"),
                         [("index", "講義", False), ("資料", "講義/資料", False)])

    def test_2段以上下は1つの名前にまとまる(self):
        self.put("講義/第07回/課題/A")
        self.put("講義/第07回/課題/B")
        self.assertEqual(self.shape("講義"), [("第07回", None, True)])

    def test_中身が無ければ空(self):
        self.put("講義/資料")
        self.assertEqual(self.shape("存在しない"), [])

    def test_一覧を渡せばDBを引き直さない(self):
        # 階層をたどるときに、同じ一覧を階層の数だけ引かないための道
        self.put("講義/第07回/index")
        self.put("講義/第07回/演習課題1")
        entries = page_entries(self.wiki_dir, "講義/")
        self.assertEqual(self.shape("講義", entries), self.shape("講義"))

    def test_渡した一覧の範囲外は混ざらない(self):
        self.put("講義/第07回/index")
        self.put("資料/index")
        everything = page_entries(self.wiki_dir)
        self.assertEqual(self.shape("講義", everything), [("第07回", "講義/第07回", False)])

    def test_一覧を組み立てるのに要るものが揃う(self):
        # page_entries の1行に pagepath を足した形。呼び出し側が実体パスから
        # URLを組み直さなくて済む（入口を畳む読み替えがまさにそこで要るため）
        self.put("講義/第07回/index")
        page = page_children(self.wiki_dir, "講義")[0]["page"]
        # subpath は実体（入口そのもの）、pagepath は開くときのURL
        self.assertEqual(page["subpath"], "講義/第07回/index")
        self.assertEqual(page["pagepath"], "講義/第07回")
        for key in ("title", "created", "updated", "size"):
            self.assertIn(key, page)



class TestUpdatedStamp(PageChildrenTestBase):
    """`updated`（最終更新日時）は、本文か記法が変わったときだけ進む。

    同じ中身を入れ直すたびに進めると、`updatepage --force` の全ページの取り込み直しで
    どのページも取り込んだ時刻になり、「最新の更新」が並んでしまった（2026-09-29）。"""

    def record(self, body, ext=".txt", now=None):
        from wikilib import pagedb
        path = os.path.join(self.wiki_dir, "P" + ext)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        self.assertTrue(pagedb.record_page(self.wiki_dir, "P", ext, body, now=now))
        return pagedb.load_page(self.wiki_dir, "P")["updated"]

    def test_同じ中身の入れ直しでは進まない(self):
        first = self.record("本文\n", now=1_000_000_000)
        self.assertEqual(self.record("本文\n", now=1_000_086_400), first)

    def test_本文が変われば進む(self):
        first = self.record("本文\n", now=1_000_000_000)
        self.assertNotEqual(self.record("直した本文\n", now=1_000_086_400), first)

    def test_進めるときはファイルの更新日時(self):
        # 直接編集したページを取り込んだとき、取り込んだ時刻ではなく編集した時刻になる
        from wikilib import pagedb
        self.record("本文\n", now=1_000_000_000)
        path = os.path.join(self.wiki_dir, "P.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("直した本文\n")
        os.utime(path, (1_500_000_000, 1_500_000_000))
        self.assertTrue(pagedb.record_page(self.wiki_dir, "P", ".txt", "直した本文\n"))
        self.assertEqual(pagedb.load_page(self.wiki_dir, "P")["updated"],
                         pagedb.stamp_of(1_500_000_000))

    def test_記法が変われば進む(self):
        first = self.record("本文\n", now=1_000_000_000)
        os.remove(os.path.join(self.wiki_dir, "P.txt"))
        self.assertNotEqual(self.record("本文\n", ext=".md", now=1_000_086_400), first)


if __name__ == "__main__":
    unittest.main()
