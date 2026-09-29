#!/usr/bin/env python3
"""日本語の中の `**強調**` をゆるめた件（wikilib.cjkemphasis）のテスト。

CommonMark は、`*` の並びが開き側・閉じ側になれるかを前後の文字の種類で
決める。**空白で単語を切る言語を前提にした決めかた**なので、日本語では
本来効いてほしい書きかたが落ちる（Wiki設計者の指摘、2026-09-06）。

このテストが見ているのは2つ。

  落ちていたものが効くようになったか      TestNowWorks
  **効いていたものが変わっていないか**    TestUnchanged

後者のほうが大事である。ゆるめる変更は、**ゆるめるつもりの無かったところ**
まで動かしていないことを示せて初めて安心して入れられる。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_cjkemphasis.py     （このファイルだけ）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import cjkemphasis  # noqa: E402
from wikilib.plugins import build_markdown_renderer  # noqa: E402


class MarkdownTestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = build_markdown_renderer({}, None)

    def html(self, source):
        return self.engine.render(source).strip()

    def strong(self, source, inner):
        self.assertIn(f"<strong>{inner}</strong>", self.html(source),
                      f"強調にならなかった: {source!r}")

    def plain(self, source):
        got = self.html(source)
        self.assertNotIn("<strong>", got, f"強調になってしまった: {source!r}")
        self.assertNotIn("<em>", got, f"強調になってしまった: {source!r}")


class TestNowWorks(MarkdownTestBase):
    """落ちていた書きかた。`**` の外側が全角の文字・約物のとき。

    後半の3つは、別プロジェクトが書いた実際のページ（`=303WifiLC01`）から
    採ったもの（Wiki設計者の提示、2026-09-06）。**思いつきで並べた例ではなく、
    現に落ちていた行**である。"""

    def test_かぎかっこ(self):
        self.strong("文言に**「ロックまで残りn回」**を添えます",
                    "「ロックまで残りn回」")

    def test_丸かっこ(self):
        self.strong("これは**（かっこ）**です", "（かっこ）")

    def test_二重かぎかっこ(self):
        self.strong("この**『二重かぎ』**も", "『二重かぎ』")

    def test_閉じ側の直前が約物(self):
        self.strong("テキスト**「かぎかっこ」**つづき", "「かぎかっこ」")

    def test_中黒や波線(self):
        self.strong("説明**〜ここまで〜**でした", "〜ここまで〜")

    def test_閉じ側の直前が句点で直後が半角英字(self):
        # 実例1: 箇条書きの見出しを太字にして、そのまま英語の語で説明が続く
        self.strong("- **前提としているハードウェアの癖。**WDT のタイムアウト",
                    "前提としているハードウェアの癖。")

    def test_番号付きでも同じ(self):
        # 実例2
        self.strong("1. **文鎮化させない。**Web 経由で更新できる以上",
                    "文鎮化させない。")

    def test_かっこの直後で終わる(self):
        # 2026-08-14に「書きかたで避ける」と決めた形。いまは書けるようにした
        self.strong("**見出し一覧（目次）**を差し込む", "見出し一覧（目次）")

    def test_斜体と取り消し線も同じ(self):
        self.assertIn("<em>斜体（かっこ）</em>", self.html("*斜体（かっこ）*を書く"))
        self.assertIn("<s>取り消し（かっこ）</s>",
                      self.html("~~取り消し（かっこ）~~を書く"))


class TestUnchanged(MarkdownTestBase):
    """**もともと効いていたもの**と、**効いてはいけないもの**。

    ここが動くと、ゆるめたつもりが別のものまで壊している。"""

    def test_日本語の地の文(self):
        self.strong("これは**強調**です", "強調")

    def test_文末(self):
        self.strong("**強調**。", "強調")

    def test_英語(self):
        self.strong("英語 **bold** です", "bold")

    def test_行頭と行末(self):
        self.strong("**強調**", "強調")

    def test_掛け算は強調にしない(self):
        # 空白で挟んだ星は、これまでどおりただの文字
        self.plain("2 * 3 * 4")

    def test_下線付きの語はそのまま(self):
        # `_` は単語の中では効かない決まり（変数名がそのまま書ける）
        self.plain("snake_case_word はそのまま")

    def test_閉じが無ければ強調にしない(self):
        self.plain("**閉じていない")

    def test_空白だけを挟んでも強調にしない(self):
        self.plain("** **")

    def test_コード内はそのまま(self):
        self.assertIn("<code>**強調**</code>", self.html("`**強調**`"))


class TestIsCjk(unittest.TestCase):
    """約物と同じ扱いにする文字の範囲。"""

    def test_仮名と漢字(self):
        for char in "あアｱ漢字ヶ":
            self.assertTrue(cjkemphasis.is_cjk(char), char)

    def test_全角の約物(self):
        # 「。」「」「（）」——**ここが入っていないと今回の件が直らない**
        for char in "。、「」『』（）〜・":
            self.assertTrue(cjkemphasis.is_cjk(char), char)

    def test_ラテン文字と数字は違う(self):
        for char in "aZ0_-":
            self.assertFalse(cjkemphasis.is_cjk(char), char)

    def test_全角の空白は入れない(self):
        # あれは空白として判定されるべきもの。約物扱いにすると話が変わる
        self.assertFalse(cjkemphasis.is_cjk("　"))

    def test_全角の英数は入れる(self):
        self.assertTrue(cjkemphasis.is_cjk("Ａ"))

    def test_空文字でも落ちない(self):
        self.assertFalse(cjkemphasis.is_cjk(""))


class TestInstall(unittest.TestCase):

    def test_2度目は何もしない(self):
        # 組み立てるたびに呼ばれるので、重ねて差し替えないこと
        cjkemphasis.install()
        self.assertFalse(cjkemphasis.install())


if __name__ == "__main__":
    unittest.main()
