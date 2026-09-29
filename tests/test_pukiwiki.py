#!/usr/bin/env python3
"""PukiWiki記法のブロック解析（wikilib.pukiwiki）のテスト。

いまのところ**「`~` で中身を段落にする」記法**に絞ってある。リスト・引用・
定義リストで同じ目印を使い回しており、どれか1つを直すと他が釣られやすい
ためである（[PukiWiki記法](/Syntax/PukiWiki) 参照）。

見ているのはトークンの並びで、HTMLではない。段落かどうかは
`paragraph_open` が `hidden` かどうかで決まり（hidden なら `<p>` は出ず、
文字がそのまま並ぶ）、そこが記法の違いそのものだからである。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_pukiwiki.py     （このファイルだけ）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import pukiwiki  # noqa: E402
from wikilib.paths import FOOTNOTE_TIP_MAX  # noqa: E402


def shape(text):
    """トークンの並びを (種類, 中身) の列にして、見比べやすくする。

    段落は `<p>` として出るものだけを "paragraph" とし、hidden なもの
    （文字がそのまま並ぶ、詰まった段落）は数えない。"""
    out = []
    for token in pukiwiki.parse(text):
        if token.type == "inline":
            out.append(("text", token.content))
        elif token.type == "paragraph_open" and not token.hidden:
            out.append(("paragraph", ""))
        elif token.type.endswith("_open") and token.type != "paragraph_open":
            out.append((token.tag, ""))
    return out


class TestDefinitionList(unittest.TestCase):
    """`:用語|説明` の定義リスト。"""

    def test_ふつうの説明文は段落にしない(self):
        self.assertEqual(shape(":用語|説明"), [
            ("dl", ""), ("dt", ""), ("text", "用語"), ("dd", ""), ("text", "説明")])

    def test_説明文の頭のチルダで段落になる(self):
        self.assertEqual(shape(":用語|~説明"), [
            ("dl", ""), ("dt", ""), ("text", "用語"),
            ("dd", ""), ("paragraph", ""), ("text", "説明")])

    def test_チルダのあとが空なら次の行が中身になる(self):
        self.assertEqual(shape(":用語|~\n次の行"), [
            ("dl", ""), ("dt", ""), ("text", "用語"),
            ("dd", ""), ("paragraph", ""), ("text", "次の行")])

    def test_続きの行は同じ段落にまとまる(self):
        self.assertEqual(shape(":用語|~1行目\n2行目"), [
            ("dl", ""), ("dt", ""), ("text", "用語"),
            ("dd", ""), ("paragraph", ""), ("text", "1行目\n2行目")])

    def test_項目名を省いた行でも段落にできる(self):
        # `:|説明` は直前の項目と <dt> を共有したまま <dd> を足す書きかた
        self.assertEqual(shape(":用語|説明\n:|~もう1つ"), [
            ("dl", ""), ("dt", ""), ("text", "用語"), ("dd", ""), ("text", "説明"),
            ("dd", ""), ("paragraph", ""), ("text", "もう1つ")])

    def test_段落にするものとしないものを並べられる(self):
        self.assertEqual(shape(":あ|~段落\n:い|ふつう"), [
            ("dl", ""), ("dt", ""), ("text", "あ"),
            ("dd", ""), ("paragraph", ""), ("text", "段落"),
            ("dt", ""), ("text", "い"), ("dd", ""), ("text", "ふつう")])


class TestOtherTildeBlocks(unittest.TestCase):
    """同じ `~` の目印を使う、リストと引用。定義リストと足並みを揃える。"""

    def test_リストの項目を段落にできる(self):
        self.assertEqual(shape("-~段落の項目"), [
            ("ul", ""), ("li", ""), ("paragraph", ""), ("text", "段落の項目")])

    def test_リストのふつうの項目は段落にしない(self):
        self.assertEqual(shape("-ふつうの項目"), [
            ("ul", ""), ("li", ""), ("text", "ふつうの項目")])

    def test_番号つきリストでも同じ(self):
        self.assertEqual(shape("+~段落の項目"), [
            ("ol", ""), ("li", ""), ("paragraph", ""), ("text", "段落の項目")])

    def test_引用の中も段落にできる(self):
        self.assertEqual(shape(">~引用の段落"), [
            ("blockquote", ""), ("paragraph", ""), ("text", "引用の段落")])

    def test_地の文の頭のチルダは段落の明示(self):
        self.assertEqual(shape("~- これは箇条書きではない"), [
            ("paragraph", ""), ("text", "- これは箇条書きではない")])


class TestAnnotationTip(unittest.TestCase):
    """注釈（`((…))`）にマウスを乗せたときに出す中身。

    注釈はページ末尾にまとまるので、読んでいる位置から中身を確かめられる
    ようにするための添え物（Wiki設計者の指示、2026-09-03）。"""

    def tips(self, text):
        """本文を解釈して、注釈の参照が持っている tip を出てきた順に返す。"""
        found = []
        for token in pukiwiki.parse(text):
            if token.type != "inline":
                continue
            for child in token.children or ():
                if child.type == "footnote_ref":
                    found.append((child.meta or {}).get("tip"))
        return found

    def test_中身がそのまま入る(self):
        self.assertEqual(self.tips("本文((注釈の中身))です"), ["注釈の中身"])

    def test_飾りの記号は落とす(self):
        # 吹き出しに出るのは素の文字だけ。記法の記号は見せない
        self.assertEqual(self.tips("本文((''強調''と[[リンク>Page]]))です"),
                         ["強調とリンク"])

    def test_長ければ途中で切る(self):
        text = "あ" * (FOOTNOTE_TIP_MAX + 20)
        tip = self.tips(f"本文(({text}))です")[0]
        self.assertEqual(len(tip), FOOTNOTE_TIP_MAX + 1)   # 打ち切りの記号のぶん
        self.assertTrue(tip.endswith("…"))

    def test_ちょうど上限なら切らない(self):
        text = "あ" * FOOTNOTE_TIP_MAX
        self.assertEqual(self.tips(f"本文(({text}))です"), [text])

    def test_入れ子の注釈はそれぞれ自分の中身を持つ(self):
        # 外側の tip に内側の中身は混ぜない（内側は自分の吹き出しを持つ）
        self.assertEqual(self.tips("本文((外側((内側))続き))です"),
                         ["外側続き", "内側"])

    def test_注釈が無ければ何も出ない(self):
        self.assertEqual(self.tips("ふつうの本文です"), [])


def link_hrefs(text):
    """本文から、リンクの飛び先（href属性）を書かれた順に取り出す。

    `resolve_link` に渡る前の**書かれたままの値**を見る（そこから先の
    解決は wikilib.paths の受け持ちで、tests/test_paths.py が見ている）。"""
    out = []
    for token in pukiwiki.parse(text):
        for child in token.children or []:
            if child.type == "link_open":
                out.append(child.attrGet("href"))
    return out


class TestRelativeLink(unittest.TestCase):
    """`{[…]}`（リンクの相対版）。`[[…]]` と書式は同じで、**裸の名前を
    書いたときだけ**「いま開いているページの下」を指す（`./` を補う）。
    Wiki設計者の指示、2026-09-04。"""

    def test_裸の名前には_ドットスラッシュ_を補う(self):
        self.assertEqual(link_hrefs("{[あいう]}"), ["./あいう"])

    def test_角かっこ版はルートからの絶対のまま(self):
        # 既存の書きかたを変えていないことの確認
        self.assertEqual(link_hrefs("[[あいう]]"), ["あいう"])

    def test_表示名を分けて書ける(self):
        self.assertEqual(link_hrefs("{[aiu>あいう]}"), ["./あいう"])
        self.assertEqual(link_hrefs("[[aiu>あいう]]"), ["あいう"])

    def test_表示名は画面に出る文字のまま(self):
        tokens = pukiwiki.parse("{[aiu>あいう]}")
        labels = [c.content for t in tokens for c in (t.children or [])
                  if c.type == "text" and c.content]
        self.assertIn("aiu", labels)

    def test_すでに書かれた指しかたは変えない(self):
        # 書き手が明示した意味（絶対・相対・親）を {[…]} が上書きしない
        self.assertEqual(link_hrefs("{[/あいう]}"), ["/あいう"])
        self.assertEqual(link_hrefs("{[./あいう]}"), ["./あいう"])
        self.assertEqual(link_hrefs("{[../あいう]}"), ["../あいう"])

    def test_アンカーの前だけを相対にする(self):
        self.assertEqual(link_hrefs("{[あいう#見出し]}"), ["./あいう#見出し"])

    def test_アンカー単体は触らない(self):
        # "./#見出し" にしてしまうとページ内リンクとして解決できなくなる
        self.assertEqual(link_hrefs("{[#見出し]}"), ["#見出し"])

    def test_外部URLは触らない(self):
        self.assertEqual(link_hrefs("{[本家:https://example.com/]}"),
                         ["https://example.com/"])


def rendered(text, ext=".txt"):
    """本文をHTMLにして、段落の中身だけを返す（改行の入りかたを見るため）。"""
    from wikilib.plugins import build_markdown_renderer
    from wikilib.render import render_source
    engine = build_markdown_renderer({}, None, None)
    html, _title, _toc = render_source(engine, text, ext, False)
    return html.strip().replace("<p>", "").replace("</p>", "")


class TestSoftbreakSpacing(unittest.TestCase):
    """段落の途中の改行（softbreak）。

    HTMLの改行文字はブラウザが空白1つとして描く。英文では単語の区切りとして
    要るが、日本語では書いた覚えのない空白が文中に出る。**改行の前後の
    どちらかが「ホワイトスペース以外の半角文字」なら空白を残し、それ以外は
    詰める**（Wiki設計者の指示、2026-09-04）。ここで見ているのは、詰めたか
    （改行文字が消えたか）どうか。"""

    def test_日本語どうしは詰める(self):
        self.assertEqual(rendered("あいうえお\nかきくけこ"), "あいうえおかきくけこ")

    def test_英文は空白を残す(self):
        self.assertEqual(rendered("This is\na pen"), "This is\na pen")

    def test_片側が半角なら空白を残す(self):
        self.assertEqual(rendered("これは\nEnglish です"), "これは\nEnglish です")
        self.assertEqual(rendered("English\nですね"), "English\nですね")

    def test_全角の記号どうしも詰める(self):
        self.assertEqual(rendered("これは。\n「次」です"), "これは。「次」です")

    def test_飾りをまたいでも前後の文字を見る(self):
        # 強調・リンクの開始終了タグは文字を持たないので読み飛ばす
        self.assertEqual(rendered("''強調''\nの続き"), "<strong>強調</strong>の続き")
        self.assertEqual(rendered("[[リンク]]\nの続き"),
                         '<a href="リンク">リンク</a>の続き')

    def test_明示の改行は詰めない(self):
        # 行末の "~" は hardbreak。表示上の改行なので触らない
        self.assertIn("<br", rendered("あいう~\nえお"))

    def test_Markdown記法でも同じに効く(self):
        self.assertEqual(rendered("あいうえお\nかきくけこ", ".md"), "あいうえおかきくけこ")
        self.assertEqual(rendered("This is\na pen", ".md"), "This is\na pen")


class TestCharRefInPluginBody(unittest.TestCase):
    """プラグインの中身に書いた文字参照（`&amp;`・`&#38;`）。

    中身を描き直す engine に `char_ref` の描きかたが無く、`A< />B` と
    タグ名の無い空タグになっていた（`plugins.install_token_renderers`）。"""

    def render(self, text):
        from wikilib.plugins import PluginContext, build_markdown_renderer
        from wikilib.render import render_source
        ctx = PluginContext(config={}, farm="t", wiki_dir=None, page="P")
        ctx.ext = ".txt"
        engine = build_markdown_renderer({}, None, ctx)
        html, _title, _toc = render_source(engine, text, ".txt", False, context=ctx)
        return html

    def test_実体参照が中身でも文字参照のまま出る(self):
        html = self.render("&size(150%){X&amp;Y};")
        self.assertIn("X&amp;Y", html)
        self.assertNotIn("< />", html)

    def test_数値文字参照が中身でも文字参照のまま出る(self):
        html = self.render("&color(red){A&#38;B};")
        self.assertIn("A&#38;B", html)
        self.assertNotIn("< />", html)


if __name__ == "__main__":
    unittest.main()
