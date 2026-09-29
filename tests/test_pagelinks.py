#!/usr/bin/env python3
"""本文のリンクの抽出と、リネーム時の書き換え（wikilib.pagelinks /
wikilib.links）のテスト。

ここが受け持つのは**保存されている本文そのもの**である。表示のときの
書き換え（`render.rewrite_content_links`）と違って結果がファイルに残るので、
間違えると書き手の原稿を壊す。壊しかたは2通りある。

- **拾いすぎ**: 記法の説明として書いたサンプルや整形済みテキストの中まで
  書き換えてしまう（`excluded_ranges`）
- **書き戻しかたを誤る**: 行き先は合っているのに、辿らないと分からない
  書きかたに変えてしまう（`rewritten_href` の絶対・相対の選び分け）

どちらもサーバーもDBも要らずに確かめられる。`rewrite_links` は解決結果を
`cache` で渡せるので、ここでは本文の文字列だけを相手にする。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pagelinks.py     （このファイルだけ）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.interwiki import Interwiki  # noqa: E402
from wikilib.links import page_links, plugin_arg_links  # noqa: E402
from wikilib import pukiwiki  # noqa: E402
from wikilib.pagelinks import (  # noqa: E402
    link_spans, move_amount, relative_href, rewrite_links, rewritten_href,
)


def hrefs(text, ext, **kw):
    """拾ったリンク先だけを、本文に出てくる順で返す。"""
    return [href for _s, _e, href, _rel in link_spans(text, ext, **kw)]


class TestLinkSpansMarkdown(unittest.TestCase):
    """Markdownの `[表示](先)` と、行頭の参照定義 `[名前]: 先`。"""

    def test_ふつうのリンクと画像を拾う(self):
        self.assertEqual(hrefs("[表示](Tech/Reference) と ![図](./img.png)", ".md"),
                         ["Tech/Reference", "./img.png"])

    def test_山かっこで囲った書きかたも拾う(self):
        self.assertEqual(hrefs("[表示](<空白 入り>)", ".md"), ["空白 入り"])

    def test_題名は行き先に含めない(self):
        self.assertEqual(hrefs('[表示](Foo "題名")', ".md"), ["Foo"])

    def test_参照定義も拾う(self):
        self.assertEqual(hrefs("本文[名前]\n\n[名前]: /Foo/Bar\n", ".md"), ["/Foo/Bar"])

    def test_位置は行き先の部分だけを指す(self):
        text = "[表示](Tech/Reference)"
        start, end, href, _rel = link_spans(text, ".md")[0]
        self.assertEqual(text[start:end], href)   # 表示名は範囲に入らない


class TestLinkSpansPukiWiki(unittest.TestCase):
    """PukiWikiの `[[…]]` と、その相対版 `{[…]}`。"""

    def test_表示名と行き先を切り分ける(self):
        self.assertEqual(hrefs("[[表示>Tech/Reference]] [[Foo]]", ".txt"),
                         ["Tech/Reference", "Foo"])

    def test_外部URLの書きかたは拾わない(self):
        self.assertEqual(hrefs("[[本家:https://example.com/]]", ".txt"), [])

    def test_相対版はドットスラッシュを補った形で返す(self):
        # 位置の指す文字列（"Sub2"）と、指す先（"./Sub2"）は別。resolve_link に
        # 渡す値をここでそろえておかないと、[[…]] と同じ意味に読まれてしまう
        start, end, href, relative = link_spans("{[Sub2]}", ".txt")[0]
        self.assertEqual("{[Sub2]}"[start:end], "Sub2")
        self.assertEqual(href, "./Sub2")
        self.assertTrue(relative)

    def test_すでにドットスラッシュがあればそのまま(self):
        self.assertEqual(hrefs("{[表示>./Sub3]}", ".txt"), ["./Sub3"])

    def test_角かっこ版は相対の印を立てない(self):
        self.assertFalse(link_spans("[[Foo]]", ".txt")[0][3])

    def test_InterWikiの登録名は相対化しない(self):
        iw = Interwiki({"Wikipedia": {"url": "https://ja.wikipedia.org/wiki/$1"}})
        self.assertEqual(hrefs("{[Wikipedia:PukiWiki]}", ".txt", interwiki=iw),
                         ["Wikipedia:PukiWiki"])

    def test_登録表を渡さないと相対として読んでしまう(self):
        # 登録名かどうかは登録表を見ないと分からない。呼び出し側が渡す
        # （links.page_links / rewrite_links はどちらも渡している）
        self.assertEqual(hrefs("{[Wikipedia:PukiWiki]}", ".txt"),
                         ["./Wikipedia:PukiWiki"])


class TestExcludedRanges(unittest.TestCase):
    """地の文でないところ（コード・整形済みテキスト）は拾わない。

    記法の説明ページには、リンクの書きかたそのものがサンプルとして並ぶ。
    そこを書き換えると説明が壊れる。"""

    def test_Markdownのフェンスとインラインコードは拾わない(self):
        self.assertEqual(
            hrefs("`[表示](Foo)`\n\n```\n[表示](Bar)\n```\n\n[表示](Baz)\n", ".md"),
            ["Baz"])

    def test_PukiWikiの整形済みテキストは拾わない(self):
        # 行頭の半角空白で始まる行
        self.assertEqual(hrefs("ふつう [[A]]\n\n [[B]] 整形済み\n", ".txt"), ["A"])

    def test_HTMLブロックの中は拾わない(self):
        self.assertEqual(hrefs("<div>\n[表示](Foo)\n</div>\n\n[表示](Bar)\n", ".md"),
                         ["Bar"])


class TestMoveAmount(unittest.TestCase):
    """相対の書きかたの「移動量」。上下の向きではなく辿る段数で数える。"""

    def test_となりは0(self):
        self.assertEqual(move_amount("./target"), 0)

    def test_上へも下へも同じ1(self):
        self.assertEqual(move_amount("../target"), 1)
        self.assertEqual(move_amount("./age/ten"), 1)

    def test_段数ぶん増える(self):
        self.assertEqual(move_amount("../../target"), 2)

    def test_先頭のドットスラッシュは数えない(self):
        # 「ここから下」を表すのに必ず要る書きかたで、距離ではない
        self.assertEqual(move_amount("./a/b"), move_amount("a/b"))


class TestRelativeHref(unittest.TestCase):
    def test_同じ階層のとなり(self):
        self.assertEqual(relative_href("p1/p2", "p1/p3"), "../p3")

    def test_下へ辿るときはドットスラッシュを付ける(self):
        # 付けないと「ルートからの絶対」の意味になってしまう
        self.assertEqual(relative_href("p1", "p1/sub"), "./sub")

    def test_同じ場所なら空(self):
        self.assertEqual(relative_href("p1", "p1"), "")


class TestRewrittenHref(unittest.TestCase):
    """指し先の差し替え。**絶対と相対のどちらで書くか**の決まりを固定する。"""

    def test_絶対で書かれていたら絶対のまま(self):
        self.assertEqual(
            rewritten_href("/p1/old", "q1/page", "p1/new", old_owner="/p1/old"),
            "/p1/new")

    def test_裸の名前も絶対として扱う(self):
        # `[[Glossary]]` はルートからの絶対（paths.full_pagepath）。"/" 始まり
        # だけを絶対とみなしていたころは、深い階層のページで
        # `[[../../../../Words]]` のような形に書き換えられていた
        self.assertEqual(
            rewritten_href("Glossary", "Tech/dev_plugin/spec/errors", "Words",
                           old_owner="/Glossary"),
            "Words")

    def test_裸で書かれていたら裸のまま戻す(self):
        # 裸も "/" 付きも意味は同じ。1枚の改名で、指している全ページの
        # 見た目が変わってしまわないよう、書きかたはそのままにする
        self.assertEqual(
            rewritten_href("Tech/Old", "q/page", "Tech/New", old_owner="/Tech/Old"),
            "Tech/New")
        self.assertEqual(
            rewritten_href("/Tech/Old", "q/page", "Tech/New", old_owner="/Tech/Old"),
            "/Tech/New")

    def test_区切りの無い添付は相対のまま扱う(self):
        # `logo.png` は「いま開いているページ」の添付（resolve_link）。
        # 裸でもページとは意味が違うので、絶対の判定には入れない
        self.assertEqual(
            rewritten_href("logo.png", "p1/p2/page", "p1/p2/owner",
                           filename="logo.png", old_owner="/p1/p2/page",
                           old_subpath="p1/page"),
            "../owner/logo.png")

    def test_動いたページの本文でとなりになったら相対にする(self):
        # フォルダごと動かすたびに書き換えが要らないよう、近さが分かる形にする
        self.assertEqual(
            rewritten_href("/p1/old", "p1/page", "p1/new", old_owner="/p1/old",
                           old_subpath="q1/page"),
            "../new")

    def test_相対で書かれていたら相対のまま(self):
        self.assertEqual(
            rewritten_href("./sub", "p1/page", "p1/page/sub2",
                           old_owner="/p1/page/sub"),
            "./sub2")

    def test_前より遠くなるなら絶対にする(self):
        # ../../p3/page/age/ten のような、辿らないと分からない形を残さない
        self.assertEqual(
            rewritten_href("../t", "p1/p2/p3/page", "z1/z2/t", old_owner="/p1/p2/t",
                           old_subpath="p1/page"),
            "/z1/z2/t")

    def test_添付ファイルは遠くなっても相対のまま(self):
        # 添付には farm をまたいでも安全な絶対の書きかたが無い
        self.assertEqual(
            rewritten_href("../logo.png", "p1/p2/p3/page", "z1/z2/owner",
                           filename="logo.png", old_owner="/p1/p2/owner",
                           old_subpath="p1/page"),
            "../../../../z1/z2/owner/logo.png")

    def test_アンカーは末尾に残す(self):
        self.assertEqual(
            rewritten_href("/p1/old#見出し", "q/page", "p1/new", old_owner="/p1/old"),
            "/p1/new#見出し")

    def test_符号化されていたら符号化したまま書き戻す(self):
        self.assertEqual(
            rewritten_href("/%E3%83%86%E3%82%B9%E3%83%88", "q/page", "新テスト",
                           old_owner="/テスト"),
            "/%E6%96%B0%E3%83%86%E3%82%B9%E3%83%88")


class TestRewriteLinks(unittest.TestCase):
    """本文まるごとの書き換え。**書き換えた数**と、触っていない部分が
    そのまま残ることを見る。"""

    def test_指し先の名前が変わったものだけ書き換える(self):
        text, count = rewrite_links(
            "[あ](/Old) と [い](/Other)\n", "q/page", ".md", {"Old": "New"},
            cache={"/Old": ("page", "/Old", None),
                   "/Other": ("page", "/Other", None)})
        self.assertEqual(text, "[あ](/New) と [い](/Other)\n")
        self.assertEqual(count, 1)

    def test_何も変わらなければ本文をそのまま返す(self):
        original = "[い](/Other)\n"
        text, count = rewrite_links(original, "q/page", ".md", {"Old": "New"},
                                    cache={"/Other": ("page", "/Other", None)})
        self.assertIs(text, original)
        self.assertEqual(count, 0)

    def test_コードの中は書き換えない(self):
        text, count = rewrite_links(
            "[あ](/Old) と `[い](/Old)`\n", "q/page", ".md", {"Old": "New"},
            cache={"/Old": ("page", "/Old", None)})
        self.assertEqual(text, "[あ](/New) と `[い](/Old)`\n")
        self.assertEqual(count, 1)

    def test_自分が動いたら指し先が変わらなくても見直す(self):
        # 同じ "../target" でも、動いた先からは別のページを指してしまう
        text, count = rewrite_links(
            "[[../target]]\n", "q1/q2/page", ".txt", {},
            old_subpath="p1/page",
            cache={"../target": ("page", "/target", None)})
        self.assertEqual(text, "[[/target]]\n")
        self.assertEqual(count, 1)

    def test_相対版に書き戻すときは冗長なドットスラッシュを外す(self):
        # {[X]} と {[./X]} は常に同じ意味。裸のほうが書き手の書きかたに近い
        text, count = rewrite_links(
            "{[Old]}\n", "q/page", ".txt", {"q/page/Old": "q/page/New"},
            cache={"./Old": ("page", "/q/page/Old", None)})
        self.assertEqual(text, "{[New]}\n")
        self.assertEqual(count, 1)

    def test_相対版でも親をたどる書きかたはそのまま残す(self):
        # 外すのは冗長な "./" だけ。"../" は {[…}] でも意味を持つので残す
        text, _count = rewrite_links(
            "{[../Sib]}\n", "q/page", ".txt", {"q/Sib": "q/Sib2"},
            cache={"../Sib": ("page", "/q/Sib", None)})
        self.assertEqual(text, "{[../Sib2]}\n")

    def test_相対版でも遠くなれば絶対になる(self):
        # 移動量が増える（となり → 1つ上）ので絶対にする。"/" 始まりは
        # {[…]} でも絶対の意味なので、"./" 外しの対象にもならない
        text, _count = rewrite_links(
            "{[Old]}\n", "q/page", ".txt", {"q/page/Old": "q/New"},
            cache={"./Old": ("page", "/q/page/Old", None)})
        self.assertEqual(text, "{[/q/New]}\n")

    def test_キャッシュに無い文字列は触らない(self):
        # wiki_dir も interwiki も渡していない＝解決する手立てが無い場合
        original = "[あ](/Old)\n"
        text, count = rewrite_links(original, "q/page", ".md", {"Old": "New"}, cache={})
        self.assertIs(text, original)
        self.assertEqual(count, 0)

    def test_動いてもいない書き換えも無ければ何もしない(self):
        original = "[あ](/Old)\n"
        text, count = rewrite_links(original, "q/page", ".md", {})
        self.assertIs(text, original)
        self.assertEqual(count, 0)


class TestPageLinks(unittest.TestCase):
    """保存のたびに記録する参照先（wikilib.links.page_links）。"""

    def test_書かれたままの文字列をキーに集める(self):
        self.assertEqual(
            page_links("[[Zebra]] [[Apple]]\n", ".txt", "p1/page"),
            [("Apple", "page", "/Apple", None), ("Zebra", "page", "/Zebra", None)])

    def test_同じ文字列は1つにまとめる(self):
        self.assertEqual(len(page_links("[[Apple]] [[Apple]]\n", ".txt", "p1/page")), 1)

    def test_ページの外を指すものは記録しない(self):
        self.assertEqual(
            page_links("[[外部>https://example.com/]] [[#見出し]]\n", ".txt", "p1/page"),
            [])

    def test_添付ファイルは持ち主とファイル名で持つ(self):
        self.assertEqual(page_links("[[logo.png]]\n", ".txt", "p1/page"),
                         [("logo.png", "attach", "/p1/page", "logo.png")])

    def test_相対版は指す先まで解いて記録する(self):
        self.assertEqual(page_links("{[Sub]}\n", ".txt", "p1/page"),
                         [("./Sub", "page", "/p1/page/Sub", None)])

    def test_InterWikiは記録しない(self):
        iw = Interwiki({"W": {"url": "https://example.com/$1"}})
        self.assertEqual(page_links("[[W:Foo]] [[Bar]]\n", ".txt", "p1/page", interwiki=iw),
                         [("Bar", "page", "/Bar", None)])


class TestPluginArgLinks(unittest.TestCase):
    """プラグインの引数のうち、`"link": True` と宣言されたものだけを拾う。

    プラグイン本体は実行しない（引数の宣言だけを見る）。"""

    registry = {
        "myref": {"info": {"args": [{"name": "src", "num_order": 1, "link": True}]}},
        "plain": {"info": {"args": [{"name": "x", "num_order": 1}]}},
        "broken": {"error": "読み込みに失敗"},
    }

    def links(self, text):
        return plugin_arg_links(pukiwiki.parse(text), self.registry, "p1/page")

    def test_宣言された引数を拾う(self):
        self.assertEqual(self.links("#myref(./logo.png)\n"),
                         [("./logo.png", "attach", "/p1/page", "logo.png")])

    def test_インラインの呼び出しも拾う(self):
        self.assertEqual(self.links("本文に &myref(Tech/Reference); と続く\n"),
                         [("Tech/Reference", "page", "/Tech/Reference", None)])

    def test_宣言の無い引数は拾わない(self):
        self.assertEqual(self.links("#plain(Zebra)\n"), [])

    def test_読み込みに失敗したプラグインは読み飛ばす(self):
        self.assertEqual(self.links("#broken(Zebra)\n"), [])

    def test_知らないプラグインは読み飛ばす(self):
        self.assertEqual(self.links("#unknown(Zebra)\n"), [])


if __name__ == "__main__":
    unittest.main()
