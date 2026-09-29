"""note — 中身を囲んで目立たせる、ブロック／インライン両対応のプラグイン。

    #note(){{
    複数行の**中身**が書けます。
    }}
    #note(type=warn, label=見出し){1行で書く場合}
    &note(type=tip){ちょっとした補足};

 1. type  … 枠の種類 (default: info)
       info: お知らせ / tip: ヒント / warn: 注意
       指定外の値を書いても既定（info）として扱われます
 2. label … 左上に出す見出しの文字 (default: 種類ごとの既定ラベル)

インラインの場合は1行本文のみ対応です。中身にはMarkdown記法や他のプラグインも
そのまま使えます。
"""

""" 技術資料
expand_block / expand_inline / expand_plugin を宣言している（入れ子を
受け入れる例）。`body`は`_convert`/`_inline`が呼ばれる前にフレームワーク側
（`wikilib.plugins.expand_body()`）で展開済みのHTMLとして渡ってくるため、
ここでは検査もエスケープもせずそのまま埋め込むだけでよい。返り値
（このプラグイン自身が返す`<div>`/`<span>`）は展開後に再パースされない
（`html`ポリシーの影響を受けない）。
"""

from html import escape

PLUGIN_INFO = {
    "help": "#note(type,label){中身} / &note(type,label){中身};",
    "expand_block": True,
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "type", "default": "info"},
        {"name": "label", "default": None},
    ],
}

TYPES = {"info": "お知らせ", "tip": "ヒント", "warn": "注意"}


def _note_type(resolved):
    """選べる種類（TYPES）に無い値は、エラーにせず黙って既定（info）にする。"""
    value = resolved["type"]
    return value if value in TYPES else "info"


def _convert(resolved, body, context):
    kind = _note_type(resolved)
    label = resolved["label"] or TYPES[kind]
    return f'''<div class="note note-{escape(kind)}">
<div class="note-label">{escape(label)}</div>
{body or ""}
</div>
'''

def _inline(resolved, body, context):
    kind = _note_type(resolved)
    return f'<span class="note-inline note-{escape(kind)}">{body or ""}</span>'
