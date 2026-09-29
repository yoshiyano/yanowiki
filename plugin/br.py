"""br — 強制的に1行分の空白（改行）を挿入する、ブロック／インライン両対応のプラグイン。

    #br()
    &br();

引数はありません。段落の区切りだけでは足りない、見た目の上で1行分だけ
空けたい・改行したいときに使います。

**Markdownページでは丸括弧を省略できません。** `#br`／`&br;`のように
丸括弧を省く書きかたは、Markdownページでは展開されず書いた文字がそのまま
表示されます（詳しくは技術資料）。PukiWiki記法のページでは丸括弧を省いて
`#br`／`&br;`と書いても構いません。
"""

""" 技術資料
本家PukiWikiの`br.inc.php`を移植した。

## ブロック側の出力（div.spacer）

本家はブロック側（`plugin_br_convert()`）を、`PLUGIN_BR_ESCAPE_BLOCKQUOTE`
という定数（本家のソース上の既定値は`1`）で分岐させており、有効なときは
`<br />`ではなく`<div class="spacer">&nbsp;</div>`を返す
（`<blockquote>`内での`<br />`の見えかたに関する古い不具合の回避策、
本家のBugTrack/583）。この定数は利用者が呼び出しごとに選べる引数ではなく
ソース側の`define()`であり、本家配布時点の値が`1`のまま変更されずに
使われるのが通常のため、実質的に**常にこちらの挙動**になる（`else`側の
素の`<br />`に本家で到達することはまず無い）。このシステムでは分岐その
ものを持ち込まず、`div.spacer`を返す唯一の挙動として移植した。

インライン側（`&br();`）は常に`<br class="spacer">`を返す（本家の
`<br class="spacer" />`から、自己終了スラッシュだけをHTML5流に省略した。
タグ名・class・見た目は本家と同じ）。

引数・中身は取らない（本家の`plugin_br_convert()`/`plugin_br_inline()`は
どちらも引数を一切参照しない関数）。`#br(...)`のように余分な引数を書くと、
このシステム共通の検証で「引数が多すぎます」エラーになる（本家は黙って
無視するだけだったが、宣言に無い引数を必ずエラーにするのはこの
フレームワーク全体で一貫した挙動であり、`br`固有の差ではない）。

## 丸括弧を省いた書きかたはMarkdownでは通らない（PukiWiki記法限定）

このプラグインの実装ではなく、**フレームワーク側の記法パーサーの仕様**
（`_sys/wikilib/pukiwiki.py`）による制約。実際に`build_markdown_renderer`
で確認した組み合わせを表にする。

| 書きかた | Markdown（`.md`） | PukiWiki記法（`.txt`） |
|---|---|---|
| `#br()` | このプラグイン（`div.spacer`） | このプラグイン（`div.spacer`） |
| `#br`（丸括弧省略） | **展開されない**（ただの文字列） | このプラグイン（`div.spacer`） |
| `&br();` | このプラグイン（`<br class="spacer">`） | このプラグイン（`<br class="spacer">`） |
| `&br;`（丸括弧省略） | **展開されない**（`&amp;br;`と表示） | このプラグイン（`<br class="spacer">`） |

丸括弧を省いた書きかたは、PukiWiki記法側の`PLUGIN_BLOCK_RE`
（ブロック。本家の`#contents`等に合わせて丸括弧を任意にしている、
`br`固有ではない一般仕様）・`wikilib.pukiwiki`の`&name;`糖衣構文
（インライン。同じくPukiWiki記法だけの一般仕様）としてどちらも通る。
Markdown側の`PLUGIN_BLOCK_HEAD_RE`/`PLUGIN_INLINE_HEAD_RE`は丸括弧を
必須にしているため、Markdownページでは`#br`／`&br;`（丸括弧無し）は
ただの文字列として表示されるだけで、プラグインとして展開されない
（全プラグイン共通の一般仕様。詳しくは`../SPECIFICATIONS.md`の
「2. 呼び出し記法」参照）。

**旧仕様の記録:** 2026-08-27にこのプラグインを作った時点では、
PukiWiki記法の`&br;`（丸括弧省略）だけは`wikilib/pukiwiki.py`の
`amp_tokens()`にあった`bare and name == "br"`というハードコードで
markdown-it-pyの標準hardbreakトークンに奪われ、このプラグインへは
一切届いていなかった（結果は`class="spacer"`の付かない素の`<br />`）。
プラグイン導入前の暫定的な組み込み処理だったため、同日中にこの
ハードコードを削除し、`&br;`（丸括弧省略）もこのプラグインへ届くように
した（詳しくは`Tech/ChangeLog/plugin/2026-08-27`参照）。
"""

PLUGIN_INFO = {
    "help": "#br() / &br();",
}


def _convert(resolved, body, context):
    return '<div class="spacer">&nbsp;</div>'


def _inline(resolved, body, context):
    return '<br class="spacer">'
