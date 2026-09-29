#!/usr/bin/env python3
"""`./wiki.py resetpw` の取り違え防止のテスト。

管理者のパスワードを入れ直すのは、**画面からは戻れなくなったときの逃げ道**。
サーバーで実行できる人しかここへ来ないので、防ぎたいのは「なりすまし」では
なく**別のWikiを指してしまうこと**である（Wiki設計者の指示、2026-09-08）。

そこで、そのWikiの**トップページのフッターを貼ってもらう**。あれは画面を
実際に開いた人にしか貼れないので、名前の打ち間違いなら合わない。

見るのは `Last-modified` と `DiskUsage` の**両方**。片方でも合わなければ
通さず、**その場でやり直してもらう**（Wiki設計者の指示、2026-09-08）。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_resetpw.py     （このファイルだけ）
"""
import builtins
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))


def load_wiki_py():
    """`wiki.py` を読み込む。**コマンドとしてではなく、関数を借りるため。**"""
    spec = importlib.util.spec_from_file_location("wiki_main",
                                                  os.path.join(ROOT, "wiki.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FingerprintTestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.wiki = load_wiki_py()

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="resetpw-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        with open(os.path.join(self.wiki_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write("# トップ\n\n本文\n")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def marks(self):
        return self.wiki.wiki_fingerprint(self.wiki_dir)

    def paste(self, *texts):
        """貼り付けを順に流し込んで、確認が通るかを返す。

        1つ渡せば1回ぶん。2つ渡せば「1回目が合わなくてやり直す」形になる。"""
        lines = []
        for text in texts:
            lines += list(text.splitlines()) + [""]
        lines.append("")          # 最後は空行＝やめる
        it = iter(lines)
        kept_input, kept_stdout = builtins.input, sys.stdout
        builtins.input = lambda _prompt="": next(it)
        sys.stdout = io.StringIO()
        try:
            return self.wiki.confirm_by_footer("testwiki", self.wiki_dir)
        finally:
            builtins.input, sys.stdout = kept_input, kept_stdout


class TestFingerprint(FingerprintTestBase):
    """フッターに出ている値を、同じ書きかたで作れているか。"""

    def test_2つ拾う(self):
        marks = self.marks()
        self.assertEqual(len(marks), 2)
        self.assertTrue(marks[0].startswith("Last-modified: "))
        self.assertTrue(marks[1].startswith("DiskUsage: "))

    def test_更新日時は分まで(self):
        # フッターの書きかたと同じ（秒までは出さない）
        self.assertRegex(self.marks()[0],
                         r"^Last-modified: \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_トップページが無ければ大きさだけ(self):
        os.remove(os.path.join(self.wiki_dir, "index.md"))
        marks = self.marks()
        self.assertEqual(len(marks), 1)
        self.assertTrue(marks[0].startswith("DiskUsage: "))


class TestConfirm(FingerprintTestBase):
    """貼り合わせ。**どちらか一方でも合っていれば通す。**"""

    def test_フッターを丸ごと貼れば通る(self):
        footer = "Convert-time: 17.1ms " + " ".join(self.marks())
        self.assertTrue(self.paste(footer))

    def test_更新日時だけでは通らない(self):
        # **両方そろって初めて通す**（Wiki設計者の指示、2026-09-08）
        self.assertFalse(self.paste(self.marks()[0]))

    def test_大きさだけでは通らない(self):
        self.assertFalse(self.paste(self.marks()[1]))

    def test_合わなければやり直せる(self):
        # 貼るあいだに添付が増えて DiskUsage が変わった、のような場合。
        # **その場で貼り直せば通る**
        footer = " ".join(self.marks())
        self.assertTrue(self.paste("Last-modified: 2001-01-01 00:00", footer))

    def test_改行や余分な空白が混ざっても通る(self):
        marks = self.marks()
        self.assertTrue(self.paste(f"Convert-time: 9.9ms\n  {marks[0]}  \n{marks[1]}"))

    def test_別のWikiのフッターでは通らない(self):
        # **これが本題。** 名前を打ち間違えたときに気づけるか
        self.assertFalse(self.paste(
            "Convert-time: 5.0ms Last-modified: 2001-01-01 00:00 "
            "DiskUsage: Page/Attached 1KB/2KB"))

    def test_空なら通らない(self):
        self.assertFalse(self.paste(""))

    def test_それらしい言葉だけでは通らない(self):
        self.assertFalse(self.paste("Last-modified: DiskUsage:"))


if __name__ == "__main__":
    unittest.main()
