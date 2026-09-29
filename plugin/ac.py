"""ac — 押すと開いたり閉じたりする、折りたたみの枠を作る。

    #ac(使いかた){{                見出し「使いかた」を押すと中身が開く
    中身
    }}

    *Windows 関連
    #ac(h){{                      すぐ上の見出しを押して開く（見出しの下だけを畳む）
    中身
    }}

    #ac(all)                       ここから後の折りたたみを「全て開く／全て閉じる」ボタン
    #ac(end)                       「全て開く」が効く範囲の終わり
    &ac(補足){ちょっとした説明};    文の途中に置く折りたたみ

 1. title … 押すところに出す見出し (default: 「…」)
 2. h     … 見出しを書かず、すぐ上にある見出し（段落など）を押すところにする
 3. open  … 最初から開いておく
 4. alt   … 閉じているあいだ「▴ クリック or タップで詳細を表示」と添える
 5. all   … 中身を書かず、「全て開く／全て閉じる」ボタンを置く
 6. end   … 中身を書かず、`all` のボタンが効く範囲をここで終える

書く順は自由です（`#ac(alt,h)` も `#ac(h,alt)` も同じ）。中身にはふつうの記法や
ほかのプラグインを書けます。インライン（`&ac`）で使えるのは title・open・alt だけです。

`all` のボタンは、それより後にある同じ階層の折りたたみ（次の `#ac(all)` か
`#ac(end)` まで）をまとめて開け閉めします。
"""

""" 技術資料
kanateko氏の `ac.inc.php`（v1.6、`~/pukiwiki/.wkcommon/plugin/`）の移植。本家
PukiWiki公式のプラグインではない。書きかた（見出し・`h`・`open`・`alt`・`all`・`end`、
インライン）は本家のまま受け、**見た目と作りは新しくした**（Wiki設計者の指示
「見た目や実装などモダンなものを採用してください」）。

## ブロックは `<details>` / `<summary>`

本家は jQuery で「`.plugin-ac` の直前の要素」にクリックを付け、`slideToggle` で
開閉した（ページごとに `<script>` を差し込む）。ここではHTML標準の
`<details>`/`<summary>` にした。

- JavaScriptが無くても開閉でき、キーボード・読み上げにもそのまま対応する
- ページ内検索（Ctrl+F）で、閉じた中身の文字も見つかる（見つかると開く。対応する
  ブラウザで）
- 開閉の動きは CSS（`::details-content` の `block-size` を `interpolate-size` で
  0 ⇔ auto へ）。対応していないブラウザでは動き無しで開閉する。
  `prefers-reduced-motion` なら動かさない

見出しを書かないときは、本家と同じく「…」を押すところにする。

## `h`: すぐ上の見出しを押すところにする

本家の `h` は「見出しの `<div>` を出さない」だけで、結果として直前の要素（多くは
`*見出し`）がクリックの対象になった。`<details>` では押すところは `<summary>` の
中にしか置けないが、**見出しを `<details>` の中へ動かすと、節編集（見出しで区切る
`theme/common.js`）や目次・アンカーが壊れる**。そこで見出しはその場に残し、
`plugin/ac.js` が直前の要素に `role="button"`・`tabindex="0"`・`aria-expanded`・
`aria-controls` を付けて、押す・Enter・Space で `<details>` の `open` を切り替える
（`<details>` 自身の `<summary>` は隠す）。見出しの中のリンク（`#` のアンカーなど）を
押したときは開閉しない。JavaScriptが無ければ `<summary>`（「…」）がそのまま残り、
それで開ける。

押すところにした見出し（h1〜h6）は、**上の余白をテーマの値の1/4に、下の余白を0に**
する（Wiki設計者の指示、2026-09-27）。見出しの余白はテーマごとに違う（`base` 2rem、
`bloom` 3rem、`pkwk` 1.4em など）ので、CSSに決まった値は書かず、`ac.js` がいま効いて
いる上の余白を測って1/4にし、見出しの文字の大きさに対する比（`em`）で入れる
（サイトの拡大・縮小に追随する）。

## `all` / `end`

本家と同じく、ボタンより後ろの**同じ階層の**折りたたみを、次の `all`／`end` の
印まで対象にする（本家の `nextUntil`）。ボタンは JavaScript が無いと働かないので
`hidden` で出し、`ac.js` が見せる。ボタンの文字は、対象が全部開いていれば
「全て閉じる」、そうでなければ「全て開く」。一つずつ開閉したときも合わせて変える
（本家はボタンを押したときだけ切り替えた）。

## インライン

`<details>` は段落（`<p>`）の中に置けない（HTMLの決まりで、置くと段落が途中で
閉じられてしまう）。インラインは**チェックボックスとラベル**で組み、CSSの
`:checked` だけで開閉する（JavaScript不要）。チェックボックスは見えなくするが
フォーカスは受けるので、キーボード（Tab・Space）でも開閉できる。

## `alt`

本家は `alt` の案内を開いたあとも出したままだった。ここでは**閉じているあいだだけ**
出す（ブロックは `<details>` の次の要素として置き、`details[open] + …` で隠す。
`h` のときは JavaScript が開閉に合わせて隠す）。

## 見出しの文字

本家は `convert_html()` で描いて `<p>` を外していた。ここでは見出しをインラインの
記法として展開する（`expand_body` に `expand_inline`・`expand_plugin` を渡す。
`&color` などが使える）。中身は `expand_block`・`expand_inline`・`expand_plugin` で
展開済みのHTMLが届く。

## id

`aria-controls`・`<label for>` のために、呼び出しごとに重ならない id（乱数）を振る。
連番にすると、`#include` などで別のページを差し込んだときに重なるため。
"""
import secrets

from wikilib.plugins import PluginArgumentError, expand_body

PLUGIN_INFO = {
    "help": "#ac(title,h,open,alt){{中身}} / #ac(all) / #ac(end) / &ac(title,open,alt){中身};",
    "expand_block": True,
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "h", "flag": True, "default": False},
        {"name": "open", "flag": True, "default": False},
        {"name": "alt", "flag": True, "default": False},
        {"name": "all", "flag": True, "default": False},
        {"name": "end", "flag": True, "default": False},
        {"name": "title", "num_order": -1},
    ],
}

ALT_MESSAGE = "▴ クリック or タップで詳細を表示"
PLACEHOLDER = "…"
_TITLE_EXPAND = {"expand_inline": True, "expand_plugin": True}


def _new_id():
    return "ac-" + secrets.token_hex(4)


def _title_html(title, context):
    """見出しの文字をインラインの記法として描く。"""
    html = expand_body(title, _TITLE_EXPAND, context, 0, is_inline=True) or ""
    return html.strip()


def _convert(resolved, body, context):
    context.used_plugins.add("ac")
    title = (resolved.get("title") or "").strip()
    if resolved.get("end"):
        return '<div class="plugin-ac-ctrl plugin-ac-end" hidden></div>\n'
    if resolved.get("all"):
        return ('<div class="plugin-ac-ctrl" hidden>'
                '<button type="button" class="plugin-ac-all">全て開く</button></div>\n')
    if body is None or not body.strip():
        raise PluginArgumentError("折りたたむ中身を {{ }} の中に書いてください。")
    if title and resolved.get("h"):
        raise PluginArgumentError("h（すぐ上の見出しを使う）と見出しの文字は一緒に書けません。")

    ac_id = _new_id()
    attrs = f' id="{ac_id}"'
    if resolved.get("open"):
        attrs += " open"
    if resolved.get("h"):
        attrs += ' data-ac-head="prev"'
    shown = _title_html(title, context) if title else PLACEHOLDER
    out = (
        f'<details class="plugin-ac"{attrs}>'
        '<summary class="plugin-ac-summary">'
        '<span class="plugin-ac-icon" aria-hidden="true"></span>'
        f'<span class="plugin-ac-title">{shown}</span></summary>\n'
        f'<div class="plugin-ac-body">\n{body}\n</div>\n'
        "</details>\n"
    )
    if resolved.get("alt"):
        out += f'<p class="plugin-ac-alt">{ALT_MESSAGE}</p>\n'
    return out


def _inline(resolved, body, context):
    context.used_plugins.add("ac")
    for name in ("h", "all", "end"):
        if resolved.get(name):
            raise PluginArgumentError(f"{name} はインライン（&ac）では使えません。")
    if body is None or not body.strip():
        raise PluginArgumentError("折りたたむ中身を { } の中に書いてください。")
    title = (resolved.get("title") or "").strip()
    shown = _title_html(title, context) if title else PLACEHOLDER
    ac_id = _new_id()
    checked = " checked" if resolved.get("open") else ""
    alt = f'<span class="plugin-ac-alt">{ALT_MESSAGE}</span>' if resolved.get("alt") else ""
    return (
        '<span class="plugin-ac-inline">'
        f'<input type="checkbox" class="plugin-ac-check" id="{ac_id}"{checked}>'
        f'<label class="plugin-ac-label" for="{ac_id}">'
        f'<span class="plugin-ac-icon" aria-hidden="true"></span>{shown}</label>'
        f'{alt}<span class="plugin-ac-inline-body">{body}</span></span>'
    )
