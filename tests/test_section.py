#!/usr/bin/env python3
"""セクション（節）の切り出し（wikilib.render）のテスト。

セクション編集からの保存は、**前・その節・後の3つに分けて、繋ぐと元に戻る**
ことの上に乗っている。画面は前後をそのまま持っておき、編集した節と繋いで
ページ全体として送り返す。ここが1文字でもずれると、編集していない場所が
動いて差分に毎回ゴミが出る（[セクション編集](/Tech/SectionEditing) 参照）。

見出し位置（heading_positions）はMarkdownのパーサが出すものなので、
ここではその形だけを手で組み立てて、行の扱いに絞って確かめる。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_section.py     （このファイルだけ）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.render import (  # noqa: E402
    extract_section_text, section_bounds, split_section_text,
)

# 見出し位置は heading_positions が返す形（level/id/start/end）だけを使う。
# 下のページに対応する:
#
#   0: # 題名
#   1:
#   2: 前書き。
#   3:
#   4: ## 一つ目
#   5:
#   6: Aの本文。
#   7:
#   8: ## 二つ目
#   9:
#  10: Bの本文。
PAGE = ("# 題名\n\n前書き。\n\n## 一つ目\n\nAの本文。\n\n"
        "## 二つ目\n\nBの本文。\n")
# 1行目のh1はページのタイトルとして抜かれるので（split_title）、
# 節の区切りには数えない。intro_start はその次の行になる
POSITIONS = [
    {"level": 2, "id": "一つ目", "start": 4, "end": 5},
    {"level": 2, "id": "二つ目", "start": 8, "end": 9},
]
INTRO_START = 1


class TestSectionBounds(unittest.TestCase):
    """どこからどこまでを1つの節とみなすか。"""

    def test_見出しを含む範囲(self):
        self.assertEqual(
            section_bounds(PAGE, POSITIONS, "一つ目", "header"), (4, 8))

    def test_本文だけの範囲(self):
        self.assertEqual(
            section_bounds(PAGE, POSITIONS, "一つ目", "body"), (5, 8))

    def test_最後の節は文書の終わりまで(self):
        self.assertEqual(
            section_bounds(PAGE, POSITIONS, "二つ目", "body"),
            (9, len(PAGE.splitlines())))

    def test_知らない見出しなら範囲が決まらない(self):
        self.assertIsNone(section_bounds(PAGE, POSITIONS, "無い見出し", "body"))


class TestSplit(unittest.TestCase):
    """前・その節・後の3つに分ける。繋ぐと元に戻る。"""

    def joined(self, text, positions, heading_id, scope, intro_start=0):
        parts = split_section_text(text, positions, heading_id, scope, intro_start)
        self.assertIsNotNone(parts)
        return "".join(parts)

    def test_繋ぐと元に戻る(self):
        for heading_id, scope in [("一つ目", "body"), ("一つ目", "header"),
                                  ("二つ目", "body")]:
            with self.subTest(heading=heading_id, scope=scope):
                self.assertEqual(self.joined(PAGE, POSITIONS, heading_id, scope), PAGE)

    def test_末尾に改行が無くても戻る(self):
        text = PAGE.rstrip("\n")
        self.assertEqual(self.joined(text, POSITIONS, "二つ目", "body"), text)

    def test_末尾に空行が続いても減らない(self):
        text = PAGE + "\n\n"
        self.assertEqual(self.joined(text, POSITIONS, "二つ目", "body"), text)

    def test_CRLFのままでも戻る(self):
        text = "# 題名\r\n\r\n前書き。\r\n\r\n## 一つ目\r\n\r\nAの本文。\r\n"
        positions = [{"level": 2, "id": "一つ目", "start": 4, "end": 5}]
        self.assertEqual(self.joined(text, positions, "一つ目", "body"), text)

    def test_最初の見出しより前も分けられる(self):
        self.assertEqual(
            self.joined(PAGE, POSITIONS, None, "body", INTRO_START), PAGE)

    def test_切り出した節が範囲と合っている(self):
        before, section, after = split_section_text(
            PAGE, POSITIONS, "一つ目", "body")
        self.assertTrue(before.endswith("## 一つ目\n"))
        self.assertEqual(section, "\nAの本文。\n\n")
        self.assertTrue(after.startswith("## 二つ目"))

    def test_見出しごと分けられる(self):
        before, section, after = split_section_text(
            PAGE, POSITIONS, "一つ目", "header")
        self.assertTrue(section.startswith("## 一つ目\n"))
        self.assertTrue(before.endswith("前書き。\n\n"))

    def test_知らない見出しなら分けられない(self):
        self.assertIsNone(
            split_section_text(PAGE, POSITIONS, "無い見出し", "body"))


class TestExtract(unittest.TestCase):
    """節だけを取り出す（保存を伴わない、これまでの取り出しかた）。"""

    def test_本文だけを取り出す(self):
        self.assertEqual(
            extract_section_text(PAGE, POSITIONS, "一つ目", "body"),
            "\nAの本文。\n")

    def test_見出しを含めて取り出す(self):
        self.assertEqual(
            extract_section_text(PAGE, POSITIONS, "一つ目", "header"),
            "## 一つ目\n\nAの本文。\n")

    def test_知らない見出しなら取り出せない(self):
        self.assertIsNone(
            extract_section_text(PAGE, POSITIONS, "無い見出し", "body"))


if __name__ == "__main__":
    unittest.main()
