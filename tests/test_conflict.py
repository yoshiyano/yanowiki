#!/usr/bin/env python3
"""編集の競合を統合する画面（wikilib.conflict）のテスト。

サーバーを立てずに確かめられるのは、**統合結果を書き戻してよいかの判断**
（save_merged の断り）だけである。画面そのもの（diffmergeの表示・取り込み
操作）はブラウザ側にあり、突き合わせの組み立ては保存時のリクエストの中で
起きる。

節の切り出し・貼り戻し（セクション編集からの保存が使う）は
tests/test_section.py にある。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_conflict.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import conflict  # noqa: E402
from wikilib.draft import load_draft, save_draft  # noqa: E402
from wikilib.paths import resolve_page_ref  # noqa: E402


class TestSaveMerged(unittest.TestCase):
    """統合結果を書き戻してよいかの判断。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="wikitest-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def write_page(self, subpath, text, ext=".md"):
        path = os.path.join(self.wiki_dir, subpath + ext)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def ref_of(self, subpath):
        return resolve_page_ref(self.wiki_dir, subpath)

    def test_空にする統合は断る(self):
        self.write_page("page", "中身\n")
        ok, notice = conflict.save_merged(
            self.wiki_dir, {}, self.ref_of("page"), "   \n", "")
        self.assertFalse(ok)
        self.assertIn("空になります", notice)

    def test_いまと同じなら書き込まずに競合を解く(self):
        # 相手の更新をそのまま受け入れた（自分の変更を捨てた）場合。
        # 書き込むものは無いが競合は解けているので、**成功として返し、
        # 預かっている書きかけを消す**。ここを失敗にすると、書きかけが
        # 残ったまま競合の画面へ戻され、何度保存を押しても出られなくなる
        # （Wiki設計者の報告、2026-09-03）
        self.write_page("page", "中身\n")
        save_draft(self.wiki_dir, "page", "書きかけ\n", "origin-hash")
        self.assertIsNotNone(load_draft(self.wiki_dir, "page"))

        ok, notice = conflict.save_merged(
            self.wiki_dir, {}, self.ref_of("page"), "中身\n", "")

        self.assertTrue(ok)
        self.assertEqual(notice, "")
        self.assertIsNone(load_draft(self.wiki_dir, "page"),
                          "書きかけが残ると競合の画面から出られなくなる")

    def test_いまと同じでもページの中身は変えない(self):
        self.write_page("page", "中身\n")
        conflict.save_merged(self.wiki_dir, {}, self.ref_of("page"), "中身\n", "")
        with open(os.path.join(self.wiki_dir, "page.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "中身\n")


if __name__ == "__main__":
    unittest.main()
