"""contents — そのページの見出し一覧（目次）を差し込むプラグイン。

    #contents()          既定の深さ（3）まで
    #contents(depth=2)   深さを指定

 1. depth … 目次に出す見出しの深さ (default: 3)

ページ全体の見出しが必要なため、セクション単位の部分プレビューでは処理されず、
断り書きが表示されます。
"""

""" 技術資料
need_outer_info を宣言し、context.page_headings(max_depth) でページ全体の
見出しを取っている。部分プレビュー（partial）ではページ全体の情報が無い
ため、need_outer_info 宣言によりフレームワーク側が処理せず断り書きに
置き換える（2026-08-24にwhole_pageから改名。挙動は変わっていない。
詳しくはTech/PluginContextFlags.md参照）。
"""

from html import escape

PLUGIN_INFO = {
    "help": "#contents(depth)",
    # ページ全体の見出しが必要。部分プレビューでは処理しない
    "need_outer_info": True,
    "args": [
        {"name": "depth", "type": "int", "default": 3, "label": "深さ"},
    ],
}


def _convert(resolved, body, context):
    entries = context.page_headings(max_depth=resolved["depth"])
    if not entries:
        return '<div class="contents contents-empty">（見出しがありません）</div>'

    html = ['<nav class="contents"><ul>']
    for item in entries:
        html.append(
            f'<li class="contents-l{item["level"]}">'
            f'<a href="#{escape(item["id"])}">{escape(item["title"])}</a></li>'
        )
    html.append("</ul></nav>")
    return "".join(html)
