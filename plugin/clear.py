"""clear — 画像などの回り込み（float）を止める、ブロック専用のプラグイン。

    #clear()

引数はありません。`#img(src, right)`のように回り込ませた画像の後ろに
置くと、それ以降の内容が回り込まなくなります。
"""

""" 技術資料
本家PukiWikiの`clear.inc.php`を移植した。本家はインライン版
（`plugin_clear_inline()`）を持たないブロック専用プラグインで、そのまま
`_inline`を定義せずに移植した（`&clear();`と書くと「このプラグインは
インライン記法に対応していません」になる。本家で対応する書きかたが
無かったのと同じ結果）。

本家は`<div class="clear"></div>`を返すだけで、実際に`clear:both`を
効かせるCSSはスキン側が用意する前提だった（本家コード中のコメント
「inserts a CSS class 'clear', to set 'clear:both'」のとおり）。この
システムはプラグインが自分のCSSを持てるため、`plugin/clear.css`に
`.clear { clear: both; }`を持たせ、単体で機能するようにした（本家の
出力・class名はそのまま、効かせかたの手段だけを補った）。

`plugin/img.py`の`#img(,clear)`（インラインstyleで`clear:both`を直接
書く内部実装、`CLEAR_DIV`）とは独立した別の仕組み。`img`はその場限りの
回り込み解除のために自前で完結させているのに対し、こちらは本家同様
「画像に限らず、どんな回り込みの後ろにでも置ける」汎用のブロック
プラグインとして単独で動く。
"""

PLUGIN_INFO = {
    "help": "#clear()",
}


def _convert(resolved, body, context):
    return '<div class="clear"></div>'
