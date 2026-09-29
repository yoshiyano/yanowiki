#!/usr/bin/env python3
"""`./wiki.py --help` のサブコマンド一覧（wiki.SUBCOMMANDS）のテスト。

以前は `-h`/`--help` を打っても起動オプション（--host/--port/--debug）しか
出ず、`updatepage`・`convwiki` などのサブコマンドがあること自体が
分からなかった（Wiki設計者の指摘、2026-09-18）。

`SUBCOMMANDS` は main() の振り分けと `--help` の一覧表示の両方が見る
唯一の一覧（wiki.py冒頭のコメント参照）。ここでは、**その一覧が実際に
振り分け先の関数と一致していること**と、**一覧表示にサブコマンド名が
漏れなく出ること**を確かめる。個々のサブコマンドの引数そのものの検証は
`test_resetpw.py`・`test_convwiki.py` など、各機能のテストに任せる。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_cli_help.py     （このファイルだけ）
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))


def load_wiki_py():
    """`wiki.py` を読み込む。**コマンドとしてではなく、関数を借りるため。**
    （test_resetpw.py の同名関数と同じやりかた）"""
    spec = importlib.util.spec_from_file_location("wiki_main",
                                                  os.path.join(ROOT, "wiki.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSubcommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wiki = load_wiki_py()

    def test_run_で始まる関数が一覧に全部載っている(self):
        # SUBCOMMANDSに載せ忘れた run_* 関数が無いか（増やしたときの直し忘れ対策）。
        # 一覧に載せない特別な関数を足す場合は、ここの除外にも追記すること
        defined = {name[len("run_"):] for name in dir(self.wiki)
                  if name.startswith("run_") and callable(getattr(self.wiki, name))}
        listed = {name for name, _, _ in self.wiki.SUBCOMMANDS}
        self.assertEqual(defined, listed)

    def test_一覧の関数がrun_名と対応している(self):
        for name, runner, _ in self.wiki.SUBCOMMANDS:
            self.assertIs(runner, getattr(self.wiki, f"run_{name}"))

    def test_一行説明が全項目に付いている(self):
        for name, _, desc in self.wiki.SUBCOMMANDS:
            self.assertTrue(desc, f"{name} の説明が空")

    def test_名前が重複していない(self):
        names = [name for name, _, _ in self.wiki.SUBCOMMANDS]
        self.assertEqual(len(names), len(set(names)))


class TestEpilog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wiki = load_wiki_py()

    def test_全サブコマンド名と説明が一覧に出る(self):
        text = self.wiki.subcommands_epilog()
        for name, _, desc in self.wiki.SUBCOMMANDS:
            self.assertIn(name, text)
            self.assertIn(desc, text)

    def test_個別helpの案内が出る(self):
        self.assertIn("--help", self.wiki.subcommands_epilog())


class TestTopLevelHelp(unittest.TestCase):
    """`./wiki.py --help` の実際の出力に、サブコマンド一覧が乗っていること。"""

    def test_helpにサブコマンド名が出る(self):
        import argparse
        import io
        import contextlib

        wiki = load_wiki_py()
        server_conf = {}
        parser = argparse.ArgumentParser(
            description="Python + bottle 製 Wiki Farm システム",
            epilog=wiki.subcommands_epilog(),
            formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--host", default=server_conf.get("host", "127.0.0.1"))
        parser.add_argument("--port", type=int, default=server_conf.get("port", 8619))
        parser.add_argument("--debug", action="store_true")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--help"])
        printed = out.getvalue()
        for name, _, _ in wiki.SUBCOMMANDS:
            self.assertIn(name, printed)


if __name__ == "__main__":
    unittest.main()
