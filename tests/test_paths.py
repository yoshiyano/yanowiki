#!/usr/bin/env python3
"""ページの置き場所の決まり（wikilib.paths）のテスト。

**書かれたリンク先が、どのページ・どの添付ファイルを指すか**は、書きかた
（Markdown / PukiWiki）に関わらず `full_pagepath` と `resolve_link` の
2つだけで決まる。表示（`render.rewrite_content_links`）・記録
（`links.page_links`）・リネーム時の書き換え（`pagelinks`）が同じ答えを
使う土台なので、ここがずれると「画面のリンク先」と「記録した参照先」が
食い違う。サーバーを立てずに書けるところなので、決まりを固定しておく。

`safe_join` は、外部由来の文字列（設定値・URLの断片等）をディレクトリ
結合に使う箇所が通す関門。境界の外へ出る結合はNoneを返す（chroot相当）。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_paths.py     （このファイルだけ）
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.paths import (  # noqa: E402
    DEFAULT_ATTACH_LINK_EXTS, as_attach_link, entry_subpath_of, full_pagepath,
    is_attach_name, is_folder_entry, is_valid_pagepath, pagepath_of_subpath,
    parse_link_exts, resolve_link, safe_join,
)


class TestSafeJoin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        os.makedirs(os.path.join(self.base, "sub"))
        with open(os.path.join(self.base, "sub", "file.txt"), "w") as f:
            f.write("ok")

    def tearDown(self):
        self.tmp.cleanup()

    def test_境界の内側はそのまま結合される(self):
        self.assertEqual(
            safe_join(self.base, "sub", "file.txt"),
            os.path.join(self.base, "sub", "file.txt"),
        )

    def test_base自身も結合結果として認める(self):
        self.assertEqual(safe_join(self.base), self.base)
        self.assertEqual(safe_join(self.base, ""), self.base)

    def test_親ディレクトリへ抜けようとするとNone(self):
        self.assertIsNone(safe_join(self.base, "..", "etc", "passwd"))
        self.assertIsNone(safe_join(self.base, "sub", "..", "..", "etc"))

    def test_絶対パスを混ぜても境界の外ならNone(self):
        self.assertIsNone(safe_join(self.base, "/etc/passwd"))

    def test_同じ接頭辞を持つだけの兄弟ディレクトリはNone(self):
        # base="/tmp/xxx" に対し "/tmp/xxx_evil" のような、prefix一致だけの
        # 取り違えを起こさないことの確認（os.sepを挟んだ比較になっているか）
        sibling = self.base + "_evil"
        self.assertIsNone(safe_join(self.base, "..", os.path.basename(sibling)))

    def test_区切り文字を含む一見無害な値も境界内なら通る(self):
        # "a/b" のような複数階層の指定自体は禁止しない（境界の外に
        # 出るかどうかだけを見る）。安全な単純名だけに絞りたい呼び出し側は
        # 別途正規表現等で検証する
        os.makedirs(os.path.join(self.base, "a", "b"))
        self.assertEqual(
            safe_join(self.base, "a/b"),
            os.path.join(self.base, "a", "b"),
        )


class TestFullPagepath(unittest.TestCase):
    """`full_pagepath`: 書かれた名前を、いま開いているページから見て解決する
    （本家PukiWikiの get_fullname と同じ決まり）。"""

    BASE = "p1/p2/page"   # いま開いているページ

    def test_裸の名前はルートからの絶対(self):
        # ここが要。となりではなくルートを指す（[[FrontPage]] がどのページから
        # 書かれても同じページを指すようにするため）
        self.assertEqual(full_pagepath(self.BASE, "abc"), "abc")
        self.assertEqual(full_pagepath(self.BASE, "abc/def"), "abc/def")

    def test_ドットスラッシュはそのページの下(self):
        self.assertEqual(full_pagepath(self.BASE, "./abc"), "p1/p2/page/abc")

    def test_親をたどる(self):
        self.assertEqual(full_pagepath(self.BASE, "../abc"), "p1/p2/abc")
        self.assertEqual(full_pagepath(self.BASE, "../bbb/abc"), "p1/p2/bbb/abc")
        self.assertEqual(full_pagepath(self.BASE, "../../abc"), "p1/abc")

    def test_ルートを越える親はルートで止まる(self):
        self.assertEqual(full_pagepath(self.BASE, "../../../../../abc"), "abc")

    def test_空や自分自身はそのページ(self):
        for name in ("", ".", "./"):
            self.assertEqual(full_pagepath(self.BASE, name), self.BASE)

    def test_トップページから書いた場合(self):
        # ページパスが空（そのWikiのトップ）でも壊れない
        self.assertEqual(full_pagepath("", "abc"), "abc")
        self.assertEqual(full_pagepath("", "./abc"), "abc")
        self.assertEqual(full_pagepath("", "../abc"), "abc")


class TestResolveLink(unittest.TestCase):
    """`resolve_link`: 書かれたリンク先を (種類, 値) にする。
    種類は "page" / "attach" / "keep"（触らないもの）。"""

    SUBPATH = "p1/p2/page"   # いま開いているページの実体（拡張子抜き）

    def test_ページは絶対と相対を書き分けられる(self):
        self.assertEqual(resolve_link(self.SUBPATH, "abc"), ("page", "abc"))
        self.assertEqual(resolve_link(self.SUBPATH, "./abc"), ("page", "p1/p2/page/abc"))
        self.assertEqual(resolve_link(self.SUBPATH, "../abc"), ("page", "p1/p2/abc"))

    def test_スラッシュ始まりはWiki内の絶対(self):
        self.assertEqual(resolve_link(self.SUBPATH, "/abc"), ("page", "abc"))

    def test_アンカーは行き先の末尾に残る(self):
        self.assertEqual(resolve_link(self.SUBPATH, "abc#見出し"),
                         ("page", "abc#見出し"))
        self.assertEqual(resolve_link(self.SUBPATH, "./abc#見出し"),
                         ("page", "p1/p2/page/abc#見出し"))

    def test_拡張子に見えるものは添付ファイル(self):
        # 名前の形だけで決める（実在するかは見ない）
        self.assertEqual(resolve_link(self.SUBPATH, "logo.png"),
                         ("attach", "p1/p2/page/logo.png"))
        self.assertEqual(resolve_link(self.SUBPATH, "./logo.png"),
                         ("attach", "p1/p2/page/logo.png"))

    def test_添付はディレクトリ部分だけを同じ決まりで読む(self):
        self.assertEqual(resolve_link(self.SUBPATH, "../logo.png"),
                         ("attach", "p1/p2/logo.png"))
        self.assertEqual(resolve_link(self.SUBPATH, "bbb/logo.png"),
                         ("attach", "bbb/logo.png"))

    def test_スラッシュ始まりの添付はルートからの絶対(self):
        # ディレクトリ部分はページと同じ決まり。`/` だけならトップページ（実体は index）
        self.assertEqual(resolve_link(self.SUBPATH, "/bbb/logo.png"),
                         ("attach", "bbb/logo.png"))
        self.assertEqual(resolve_link(self.SUBPATH, "/bbb/logo.png#x"),
                         ("attach", "bbb/logo.png#x"))
        self.assertEqual(resolve_link(self.SUBPATH, "/logo.png"),
                         ("attach", "index/logo.png"))

    def test_触らないもの(self):
        # 外部URL・ページ内アンカー・mailto:・tel:・別Wiki・システムのURL
        for href in ("https://example.com/", "#見出し", "mailto:a@example.com",
                     "tel:0120", "/=other/Page", "/.attach/p1/logo.png"):
            self.assertEqual(resolve_link(self.SUBPATH, href), ("keep", None), href)

    def test_空のリンク先も触らない(self):
        self.assertEqual(resolve_link(self.SUBPATH, ""), ("keep", None))

    def test_まだ無いページもページとして扱う(self):
        # 実在を見ないのが決まり（リンクをたどって作りにいける）
        self.assertEqual(resolve_link(self.SUBPATH, "NoSuchPage"),
                         ("page", "NoSuchPage"))


class TestAttachLinkRule(unittest.TestCase):
    """ページか添付ファイルかの決まり（2026-10-02）。上から順に見る。

        ::名前        添付ファイル（拡張子が何でも、無くても）
        名前/         ページ
        名前.拡張子   拡張子が添付の一覧（attach.link_exts）にあれば添付ファイル
        それ以外      ページ
    """

    SUBPATH = "p1/p2/page"

    def test_一覧に無い拡張子の形はページ(self):
        # 不具合のもとになった版番号。`.2` は拡張子の一覧に無い
        self.assertEqual(resolve_link(self.SUBPATH, "ver1.2"), ("page", "ver1.2"))
        self.assertEqual(resolve_link(self.SUBPATH, "./v2.0.1"),
                         ("page", "p1/p2/page/v2.0.1"))
        self.assertEqual(resolve_link(self.SUBPATH, "/ver1.2"), ("page", "ver1.2"))

    def test_拡張子は大文字小文字を区別しない(self):
        self.assertEqual(resolve_link(self.SUBPATH, "LOGO.PNG"),
                         ("attach", "p1/p2/page/LOGO.PNG"))

    def test_印を付ければどんな名前も添付ファイル(self):
        self.assertEqual(resolve_link(self.SUBPATH, "::model.blend"),
                         ("attach", "p1/p2/page/model.blend"))
        self.assertEqual(resolve_link(self.SUBPATH, "::README"),
                         ("attach", "p1/p2/page/README"))
        self.assertEqual(resolve_link(self.SUBPATH, "::ver1.2#x"),
                         ("attach", "p1/p2/page/ver1.2#x"))

    def test_印のあとは添付の指しかたをそのまま書ける(self):
        self.assertEqual(resolve_link(self.SUBPATH, "::../x.bin"),
                         ("attach", "p1/p2/x.bin"))
        self.assertEqual(resolve_link(self.SUBPATH, "::bbb/x.bin"),
                         ("attach", "bbb/x.bin"))
        self.assertEqual(resolve_link(self.SUBPATH, "::/bbb/x.bin"),
                         ("attach", "bbb/x.bin"))
        self.assertEqual(resolve_link(self.SUBPATH, "::/x.bin"),
                         ("attach", "index/x.bin"))

    def test_ファイル名の無い印は触らない(self):
        for href in ("::", "::foo/", "::#x", "::/.attach/p/x.png", "::/=other/x.png"):
            self.assertEqual(resolve_link(self.SUBPATH, href), ("keep", None), href)

    def test_末尾のスラッシュはページ(self):
        self.assertEqual(resolve_link(self.SUBPATH, "memo.txt/"), ("page", "memo.txt"))
        self.assertEqual(resolve_link(self.SUBPATH, "./Node.js/"),
                         ("page", "p1/p2/page/Node.js"))
        self.assertEqual(resolve_link(self.SUBPATH, "/memo.txt/"), ("page", "memo.txt"))

    def test_Wikiの設定の一覧で決まる(self):
        with tempfile.TemporaryDirectory() as root:
            wiki_dir = os.path.join(root, "w", "wiki")
            os.makedirs(wiki_dir)
            os.makedirs(os.path.join(root, "w", "config"))
            with open(os.path.join(root, "w", "config", "default.yaml"), "w",
                      encoding="utf-8") as f:
                f.write("attach:\n  link_exts: zip blend\n")
            self.assertEqual(resolve_link("page", "m.blend", wiki_dir),
                             ("attach", "page/m.blend"))
            self.assertEqual(resolve_link("page", "memo.txt", wiki_dir),
                             ("page", "memo.txt"))
            # 画像の拡張子は書かなくても添付（PukiWiki記法が画像として埋め込むため）
            self.assertEqual(resolve_link("page", "a.png", wiki_dir),
                             ("attach", "page/a.png"))


class TestAttachLinkExts(unittest.TestCase):

    def test_空白区切りでもリストでも読む(self):
        self.assertIn("zip", parse_link_exts("zip  .PDF,txt"))
        self.assertIn("pdf", parse_link_exts(["zip", ".PDF"]))

    def test_書かれていなければ既定の一覧(self):
        self.assertEqual(parse_link_exts(None), DEFAULT_ATTACH_LINK_EXTS)

    def test_画像の拡張子は常に含む(self):
        self.assertTrue({"png", "jpg", "svg"} <= parse_link_exts(""))

    def test_既定の一覧は設定の雛形と同じ(self):
        # 雛形（config/default.example.yaml）は設定画面に既定値として出る。
        # paths の既定値（設定が読めない場面で使う）とずれないようにする
        from wikilib.wikiconfig import load_config
        self.assertEqual(parse_link_exts(load_config()["attach"]["link_exts"]),
                         DEFAULT_ATTACH_LINK_EXTS)

    def test_既定の一覧に画像の拡張子が入っている(self):
        self.assertEqual(parse_link_exts(sorted(DEFAULT_ATTACH_LINK_EXTS)),
                         DEFAULT_ATTACH_LINK_EXTS)

    def test_名前の判定(self):
        self.assertTrue(is_attach_name("memo.TXT", DEFAULT_ATTACH_LINK_EXTS))
        self.assertFalse(is_attach_name("ver1.2", DEFAULT_ATTACH_LINK_EXTS))
        self.assertFalse(is_attach_name("README", DEFAULT_ATTACH_LINK_EXTS))


class TestAsAttachLink(unittest.TestCase):

    def test_添付の書きかたにする(self):
        self.assertEqual(as_attach_link("x.blend"), "::x.blend")
        self.assertEqual(as_attach_link("../p/x.png"), "::../p/x.png")

    def test_すでに印があるものやURLはそのまま(self):
        for src in ("::x.zip", "https://example.com/a.png", "#x", "mailto:a@b",
                    "/.attach/p/x.png", "/=other/x.png", ""):
            self.assertEqual(as_attach_link(src), src, src)


class TestFolderEntry(unittest.TestCase):
    """フォルダの入口（`X/index`）とページパス（`X`）の行き来。

    `X.txt` と フォルダ `X/` は同居できないので、フォルダを持つページの実体は
    必ず `X/index` になる。この読み替えを各所が独自に書くと、片方だけ
    `index` を落とし忘れて取りこぼす。**判定と変換はここに集めてある。**"""

    def test_入口かどうか(self):
        self.assertTrue(is_folder_entry("index"))          # トップページ
        self.assertTrue(is_folder_entry("Tech/index"))
        self.assertFalse(is_folder_entry("Tech"))

    def test_名前の一部がindexでも入口ではない(self):
        self.assertFalse(is_folder_entry("Tech/indexes"))
        self.assertFalse(is_folder_entry("myindex"))

    def test_フォルダから入口の実体を組み立てる(self):
        self.assertEqual(entry_subpath_of("Tech"), "Tech/index")
        self.assertEqual(entry_subpath_of("a/b"), "a/b/index")

    def test_いちばん上の入口はトップページ(self):
        self.assertEqual(entry_subpath_of(""), "index")

    def test_区切りが付いていても揃える(self):
        self.assertEqual(entry_subpath_of("/Tech/"), "Tech/index")

    def test_行きと帰りで元に戻る(self):
        for folder in ("", "Tech", "a/b/c"):
            self.assertEqual(pagepath_of_subpath(entry_subpath_of(folder)), folder)


class TestPagepathOfSubpath(unittest.TestCase):
    """`pagepath_of_subpath`: 実体のパスからURLのページパスへ（indexを畳む）。"""

    def test_indexはフォルダそのものを指す(self):
        self.assertEqual(pagepath_of_subpath("index"), "")
        self.assertEqual(pagepath_of_subpath("Tech/index"), "Tech")

    def test_ふつうのページはそのまま(self):
        self.assertEqual(pagepath_of_subpath("Tech/Reference"), "Tech/Reference")

    def test_名前の一部がindexでも畳まない(self):
        self.assertEqual(pagepath_of_subpath("Tech/indexing"), "Tech/indexing")


class TestIsValidPagepath(unittest.TestCase):
    """`is_valid_pagepath`: "=" はWiki指定、"." はシステム資材の予約接頭辞。"""

    def test_ふつうのページ名は通る(self):
        for path in ("", "UsageGuide", "Tech/Reference", "日本語のページ"):
            self.assertTrue(is_valid_pagepath(path), path)

    def test_予約された接頭辞で始まる段は弾く(self):
        for path in ("=other", "=other/Page", ".theme", "Tech/.hidden",
                     "..", "../etc", "Tech/../etc"):
            self.assertFalse(is_valid_pagepath(path), path)


if __name__ == "__main__":
    unittest.main()
