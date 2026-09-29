"""glossarytip — ページ内の用語をtooltipで参照できるようにするプラグイン。

    #glossarytip()

このページの中にある[定義リスト](/Syntax/Markdown/Block#定義リスト)（`用語`
`: 説明`の書きかた）を集め、本文中の他の場所に同じ`用語`が出てきたら
マウスホバーで`説明`を読めるようにします。

ページの中に呼ぶだけで、そのページ限定で有効になります（他のページには
影響しません）。**出力するHTMLはありません。** 定義リストが本文の
どこに何個あってもかまいません。
"""

""" 技術資料
Python側（`_convert`）は何もしない（空文字列を返すだけ）。目的は
`call_plugin`が呼び出しを記録すること（`context.used_plugins.add(name)`）
だけで、これにより`plugin_script_urls`/`plugin_style_urls`が
`plugin/glossarytip.js`/`plugin/glossarytip.css`を自動的に読み込み対象に
加える（`ls`/`recent`と同じ、プラグイン専用資材の仕組み。詳しくは
`Tech/PluginGuide#cssは基本的にプラグイン自身が持つ`）。呼ばなければ
資材ごと読み込まれない＝そのページでは一切動かない、という「ページごとに
ON/OFFを選べる」性質はこの仕組みだけで実現できる。

実際に「本文中の`<dl>`から用語を集め、他の場所をtooltip化する」処理は
すべて`glossarytip.js`（ブラウザ側）が担う。Python側は`<dl>`の中身を
一切見ない（`mdit_py_pluginsのdeflist`が生成したHTMLを、あとから
ブラウザがDOMとして読み直すだけなので、Python側でパースし直す必要が
無い）。

`args`を宣言していないので、`#glossarytip(なにか)`のように余分な引数を
書くと「引数が多すぎます（0個までです）」でエラーになる（フレームワークの
既定動作。黙って無視されると書いた側が気づけないため、これは意図した
挙動）。
"""


PLUGIN_INFO = {
    "help": "#glossarytip()",
}


def _convert(resolved, body, context):
    return ""
