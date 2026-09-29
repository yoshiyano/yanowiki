#!/usr/bin/env python3
"""PukiWikiのデータを写す仕組み（wikilib.convwiki）のテスト。

見ているのは、**書き込む前に決まること**——どのファイルを写し、どのページ名が
どの実体パスになり、添付ファイルがどこへ行くか。ここを間違えると数百枚を
一度に取り違えるので、サーバーもwikidataも要らない形で固定しておく。

とくに次の3つは、実データ（`~/syncthing/pukiwiki/1ev-c`）で実際に起きたことを
そのまま写している。

  子を持つページ   `A` と `A/B` が並ぶと、`A` は `A/index` でなければ読めない
  名前の衝突       「演習」と「演習.」が並んでいた。末尾の "." を落とすと
                   同じ名前になってしまうので、そのときは整えずに写す
  添付の旧版       `…_ファイル名.1` はPukiWikiが残した世代。写さない
  付属のページ     FormattingRules・SandBox など、PukiWikiに最初から入っている
                   15枚と、説明書 `PukiWiki` 本体・配下は写さない
                   （Wiki設計者の指示、2026-09-18）

非標準プラグイン（attachref/ls2）の書き換え、ブロックプラグインの誤った
セミコロンの除去、#navi の絶対パスから ../.. への書き換えも、同じ
「実データで実際に起きたことをそのまま固定する」考えかたで見ている。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_convwiki.py     （このファイルだけ）
"""
import binascii
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib.convwiki import (  # noqa: E402
    collect_attachments, collect_pages, config_text, decode_hex, is_stock_page,
    plan_subpaths, read_ini, rewrite_navi_home, rewrite_plugin_aliases,
    settings_from_ini, source_dir, strip_block_semicolons, strip_pukiwiki_header,
    top_page_name,
)


def hexname(name):
    """PukiWikiのファイル名（ページ名をhexで書いたもの）を作る。"""
    return binascii.hexlify(name.encode("utf-8")).decode("ascii").upper()


class TestDecode(unittest.TestCase):
    def test_hexのファイル名がページ名に戻る(self):
        self.assertEqual(decode_hex(hexname("C言語/入門")), "C言語/入門")

    def test_hexでない名前はNone(self):
        # syncthingの競合ファイルなど、hexでないものが混ざる
        self.assertIsNone(decode_hex("MenuBar.sync-conflict-20251203"))
        self.assertIsNone(decode_hex("414"))  # 奇数桁


class TestHeader(unittest.TestCase):
    def test_authorとfreezeを落として時刻を返す(self):
        text, stamp = strip_pukiwiki_header(
            '#author("2026-04-10T10:11:18+09:00","","")\n#freeze\n* 見出し\n本文\n')
        self.assertEqual(text, "* 見出し\n本文\n")
        self.assertEqual(stamp, "2026-04-10T10:11:18+09:00")

    def test_先頭に無ければ触らない(self):
        # 本文の途中に同じ書きかたがあれば、書いた人が置いたもの
        body = "* 見出し\n#freeze\n"
        text, stamp = strip_pukiwiki_header(body)
        self.assertEqual(text, body)
        self.assertIsNone(stamp)


class TestSemicolons(unittest.TestCase):
    """ブロックプラグイン呼び出しの誤ったセミコロンを消すところ。"""

    def test_単純な呼び出しから消す(self):
        text, count = strip_block_semicolons("#navi(データ型);\n#img(a.png,left,130w);\n")
        self.assertEqual(text, "#navi(データ型)\n#img(a.png,left,130w)\n")
        self.assertEqual(count, 2)

    def test_括弧無しの呼び出しからも消す(self):
        # #contents; も pukiwiki.PLUGIN_BLOCK_RE にマッチしなくなる同じ不具合
        text, count = strip_block_semicolons("#contents;\n")
        self.assertEqual(text, "#contents\n")
        self.assertEqual(count, 1)

    def test_body付きは対象にしない(self):
        # 実データに例が無い形（本体つき・複数行）は、貪欲マッチで誤爆させない
        text = "#code(){中身};\n"
        result, count = strip_block_semicolons(text)
        self.assertEqual(result, text)
        self.assertEqual(count, 0)

    def test_セミコロンが無ければ触らない(self):
        text = "#navi(データ型)\n"
        result, count = strip_block_semicolons(text)
        self.assertEqual(result, text)
        self.assertEqual(count, 0)

    def test_インラインのセミコロンは対象にしない(self):
        # &name(args); はもともと正しい記法（消すのはブロックだけ）
        text = "文中に &ref(a.png); を書く\n"
        result, count = strip_block_semicolons(text)
        self.assertEqual(result, text)
        self.assertEqual(count, 0)


class TestPluginAliases(unittest.TestCase):
    """attachref→ref、ls2→ls への機械的な書き換え。"""

    def test_ブロックとインラインの両方を書き換える(self):
        text = "&attachref(a.png);\n#ls2(A/)\n#attachref()\n&ls2(B,recursive);\n"
        result, found = rewrite_plugin_aliases(text)
        self.assertEqual(result, "&ref(a.png);\n#ls(A/)\n#ref()\n&ls(B,recursive);\n")
        self.assertEqual(found, {"attachref": 2, "ls2": 2})

    def test_空引数や未知のオプションも置き換える(self):
        # Wiki設計者の指示（2026-09-18）: 置き換えずにエラーになるより、
        # 置き換えてエラーになる件数のほうが圧倒的に多いので機械的に置き換える
        text = "&attachref();\n#ls2(,title)\n"
        result, found = rewrite_plugin_aliases(text)
        self.assertEqual(result, "&ref();\n#ls(,title)\n")
        self.assertEqual(found, {"attachref": 1, "ls2": 1})

    def test_地の文の中の名前は巻き込まない(self):
        # マニュアルページの説明文などにある「#ls2を使う」のような書きかた
        text = "#ls2を使うと一覧になります\n"
        result, found = rewrite_plugin_aliases(text)
        self.assertEqual(result, text)
        self.assertEqual(found, {})

    def test_対象外のプラグイン名は変わらない(self):
        text = "#ls(A/)\n&ref(a.png);\n"
        result, found = rewrite_plugin_aliases(text)
        self.assertEqual(result, text)
        self.assertEqual(found, {})


class TestNaviHome(unittest.TestCase):
    """#navi(引数) を #navi(..) に直すところ。"""

    def test_親フォルダと一致すれば直す(self):
        text = "#navi(演習/第03回)\n本文\n#navi(演習/第03回, reverse)\n"
        result, count = rewrite_navi_home(text, "演習/第03回/p3-1")
        self.assertEqual(result, "#navi(..)\n本文\n#navi(.., reverse)\n")
        self.assertEqual(count, 2)

    def test_すでに相対なら触らない(self):
        for home in ("#navi(..)\n", "#navi(../)\n", "#navi(.)\n"):
            with self.subTest(home=home):
                result, count = rewrite_navi_home(home, "演習/第03回/p3-1")
                self.assertEqual(result, home)
                self.assertEqual(count, 0)

    def test_親と違う場所は触らない(self):
        text = "#navi(講義)\n"
        result, count = rewrite_navi_home(text, "演習/第03回/p3-1")
        self.assertEqual(result, text)
        self.assertEqual(count, 0)

    def test_最上位のページには親が無いので触らない(self):
        result, count = rewrite_navi_home("#navi(演習)\n", "演習")
        self.assertEqual(result, "#navi(演習)\n")
        self.assertEqual(count, 0)

    def test_子を持つページの入口(self):
        # `演習/第01回`は子（p1-1.cなど）を持つので、実体パスは
        # `演習/第01回/index`になる（plan_subpaths参照）。この1つ上
        # （`演習/第01回`）は同じページの入口フォルダであって親ページではない。
        # 親ページは`演習`（`演習/第01回/index`のページパス`演習/第01回`から
        # さらに1つ上）
        text = "#navi(演習)\n"
        result, count = rewrite_navi_home(text, "演習/第01回/index")
        self.assertEqual(result, "#navi(..)\n")
        self.assertEqual(count, 1)

    def test_入口フォルダ名と一致しても親でなければ触らない(self):
        # 上のケースと対比: 実体パスの1つ上の階層（入口フォルダ名）と
        # 一致するだけでは駄目で、ページパスとしての親と一致する必要がある
        text = "#navi(演習/第01回)\n"
        result, count = rewrite_navi_home(text, "演習/第01回/index")
        self.assertEqual(result, text)
        self.assertEqual(count, 0)

    def test_引数無しの呼び出しは触らない(self):
        text = "#navi()\n"
        result, count = rewrite_navi_home(text, "演習/第03回/p3-1")
        self.assertEqual(result, text)
        self.assertEqual(count, 0)


class TestPlan(unittest.TestCase):
    def test_子を持つページは入口になる(self):
        plan, _, _ = plan_subpaths(["演習", "演習/第01回", "演習/第01回/p1-1.c"])
        self.assertEqual(plan["演習"], "演習/index")
        self.assertEqual(plan["演習/第01回"], "演習/第01回/index")
        self.assertEqual(plan["演習/第01回/p1-1.c"], "演習/第01回/p1-1.c")

    def test_トップページだけをindexにする(self):
        # $defaultpage のページが index になる。メニューのページは名前を変えず、
        # 設定（theme.menu1_page）のほうを合わせる
        plan, renamed, _ = plan_subpaths(["TopPage", "MenuBar", "その他"], "TopPage")
        self.assertEqual(plan["TopPage"], "index")
        self.assertEqual(plan["MenuBar"], "MenuBar")
        self.assertIn(("TopPage", "index", "トップページ"), renamed)

    def test_indexが埋まっていれば元の名前のまま(self):
        # 付け替えで既存のページを消してしまわないこと
        plan, _, _ = plan_subpaths(["TopPage", "index"], "TopPage")
        self.assertEqual(plan["TopPage"], "TopPage")
        self.assertEqual(plan["index"], "index")

    def test_トップページを指定しなければ付け替えない(self):
        plan, _, _ = plan_subpaths(["TopPage", "MenuBar"], "")
        self.assertEqual(plan["TopPage"], "TopPage")
        self.assertEqual(plan["MenuBar"], "MenuBar")

    def test_末尾のドットを落とすとぶつかる場合は落とさない(self):
        # 実データに「演習」と「演習.」が並んでいた。整える都合で1枚失わない
        plan, _, conflicts = plan_subpaths(["演習", "演習."])
        self.assertEqual(plan["演習"], "演習")
        self.assertEqual(plan["演習."], "演習.")
        self.assertEqual(conflicts, [])

    def test_使えない先頭文字は直す(self):
        # "=" はWiki指定、"." はシステム資材のURLに使う（paths.is_valid_pagepath）
        plan, _, _ = plan_subpaths(["=abc", ".hidden/page"])
        self.assertEqual(plan["=abc"], "_=abc")
        self.assertEqual(plan[".hidden/page"], "_.hidden/page")

    def test_入口と同じ名前のページがあれば写さない(self):
        # `A` と `A/index` が両方あると、どちらを入口にするか決められない
        plan, _, conflicts = plan_subpaths(["A", "A/index"])
        self.assertEqual(plan["A/index"], "A/index")
        self.assertNotIn("A", plan)
        self.assertEqual(len(conflicts), 1)


class TestIni(unittest.TestCase):
    """PukiWikiの設定ファイルから引き継ぐところ。"""

    INI = """<?php
$page_title = 'PukiWiki';
$defaultpage  = 'TopPage';       // Top / Default page
$menubar      = 'MenuBar';       // Menu
$rightbar_name = 'RightBar';     // RightBar
$nowikiname = 1;
$read_auth = 1;
$adminpass = 'secret-not-migrated';
$auth_users = array(
	'foo' => 'bar',
);
"""
    DEFAULT_INI = "<?php\n$usefacemark = 0;\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = self.tmp.name
        with open(os.path.join(self.src, "pukiwiki.ini.php"), "w", encoding="utf-8") as f:
            f.write(self.INI)
        with open(os.path.join(self.src, "default.ini.php"), "w", encoding="utf-8") as f:
            f.write(self.DEFAULT_INI)
        self.ini = read_ini(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def test_挙げた変数だけを読む(self):
        # $adminpass（平文のパスワード）のようなものは読まない
        self.assertEqual(self.ini["defaultpage"], "TopPage")
        self.assertEqual(self.ini["menubar"], "MenuBar")
        self.assertEqual(self.ini["usefacemark"], 0)
        self.assertNotIn("adminpass", self.ini)
        self.assertNotIn("auth_users", self.ini)

    def test_トップページはdefaultpageから決まる(self):
        self.assertEqual(top_page_name(self.ini), "TopPage")
        self.assertEqual(top_page_name({}), "FrontPage")  # 本家の既定値
        self.assertEqual(top_page_name(self.ini, "べつのページ"), "べつのページ")

    def test_メニューのページ名が設定に移る(self):
        items, notes = settings_from_ini(self.ini, "Prog1")
        values = {(section, key): value for section, key, value, _ in items}
        self.assertEqual(values[("theme", "menu1_page")], "MenuBar")
        self.assertEqual(values[("theme", "menu2_page")], "RightBar")
        # $nowikiname は真偽が逆、$usefacemark はそのまま
        self.assertIs(values[("pukiwiki", "wikiname")], False)
        self.assertIs(values[("pukiwiki", "facemark")], False)
        # $page_title が配布時のままなら、Wikiの名前を入れる
        self.assertEqual(values[("theme", "site_title")], "Prog1")
        # 当てはめずに報告へ回すもの
        self.assertTrue(any("read_auth" in note for note in notes))

    def test_名前を付けていればその名前を使う(self):
        items, _ = settings_from_ini(dict(self.ini, page_title="Cプログラミング"), "Prog1")
        values = {(section, key): value for section, key, value, _ in items}
        self.assertEqual(values[("theme", "site_title")], "Cプログラミング")

    def test_書き出す文面はYAMLとして読める(self):
        import yaml

        items, notes = settings_from_ini(self.ini, "Prog1")
        loaded = yaml.safe_load(config_text(items, notes, "1ev-c"))
        self.assertEqual(loaded["theme"]["menu1_page"], "MenuBar")
        self.assertEqual(loaded["pukiwiki"]["wikiname"], False)
        self.assertEqual(loaded["edit"]["defaultwiki"], "pukiwiki")


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = self.tmp.name
        for folder in ("wiki", "attach"):
            os.makedirs(os.path.join(self.src, folder))
        self.write("wiki", hexname("ページ") + ".txt", "本文")
        self.write("wiki", hexname(":config/plugin") + ".txt", "設定")
        self.write("wiki", hexname("FormattingRules") + ".txt", "PukiWiki付属")
        self.write("wiki", hexname("PukiWiki") + ".txt", "説明書トップ")
        self.write("wiki", hexname("PukiWiki/1.4/Manual") + ".txt", "説明書配下")
        self.write("wiki", hexname("古い版") + ".240415_093438.bk", "旧版")
        self.write("wiki", "4D656E75426172.sync-conflict-20251203-225933.txt", "競合")
        self.write("attach", f"{hexname('ページ')}_{hexname('図.png')}", "PNG")
        self.write("attach", f"{hexname('ページ')}_{hexname('図.png')}.1", "旧版")
        self.write("attach", f"{hexname('ページ')}_{hexname('図.png')}.log", "3")
        self.write("attach", f"{hexname('無いページ')}_{hexname('迷子.png')}", "PNG")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, folder, name, text):
        with open(os.path.join(self.src, folder, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_写すページだけを集める(self):
        pages, skipped = collect_pages(self.src)
        self.assertEqual(list(pages), ["ページ"])
        reasons = sorted(reason for _, reason in skipped)
        self.assertEqual(reasons, ["PukiWikiの設定ページ", "PukiWiki付属のページ",
                                   "PukiWiki付属のページ", "PukiWiki付属のページ",
                                   "syncthingの競合ファイル"])

    def test_include_systemで設定ページも写す(self):
        pages, _ = collect_pages(self.src, include_system=True)
        self.assertEqual(sorted(pages), [":config/plugin", "ページ"])

    def test_include_stockで付属のページも写す(self):
        # どのWikiにも同じものが入っている15枚（記法の説明・練習場・自動の一覧）と、
        # 説明書 PukiWiki 本体・配下
        pages, _ = collect_pages(self.src, include_stock=True)
        self.assertEqual(sorted(pages),
                         ["FormattingRules", "PukiWiki", "PukiWiki/1.4/Manual", "ページ"])

    def test_PukiWiki配下は前方一致で除外する(self):
        # フォルダ丸ごとが配布物のため、STOCK_PAGESと違って前方一致で判定する
        self.assertTrue(is_stock_page("PukiWiki"))
        self.assertTrue(is_stock_page("PukiWiki/1.4/Manual/Plugin/A-D"))
        # "PukiWiki" を含むだけの別名は誤って除外しない（実データにあった形）
        self.assertFalse(is_stock_page("geminilog/PukiWiki RemoEdit リファクタリング"))

    def test_添付は現行の版だけを写す(self):
        pages, _ = collect_pages(self.src)
        subpaths, _, _ = plan_subpaths(pages)
        plans, skipped = collect_attachments(self.src, subpaths)
        self.assertEqual([relative for _, relative, _ in plans],
                         [os.path.join("ページ", "図.png")])
        # 旧版（.1）と記録（.log）は黙って飛ばし、持ち主が居ないものは報告する
        self.assertEqual([reason for _, reason in skipped],
                         ["持ち主のページを写していない"])

    def test_wikiを持たないディレクトリは変換元にならない(self):
        self.assertEqual(source_dir(self.src), self.src)
        self.assertIsNone(source_dir(os.path.join(self.src, "attach")))


if __name__ == "__main__":
    unittest.main()
