"""aname — ページ内アンカー（リンクの飛び先）を設置する、ブロック／インライン両対応のプラグイン。

    #aname(anchorID)
    #aname(anchorID){リンク文字列}
    &aname(anchorID){リンク文字列};

 1. **anchorID** … アンカーの名前（省略不可）
       英字で始まり、英数字・アンダースコア・ハイフンだけが使えます
       （40文字まで）
 2. super … アンカーの見た目を変えるCSSクラス（`anchor_super`）を使うか
       (default: 使わない。`anchor`クラスになる)
 3. full … リンク先をこのページ自身の絶対パス込みで書くか
       (default: 書かない。`#anchorID`のみ)
 4. noid … `id`属性を付けないか (default: 付ける)
 5. nouserselect … リンク文字列をドラッグ選択できなくするか
       (default: 選択できる)

`{リンク文字列}`（中身）を省略すると、アンカーを設置するだけで見た目には
何も表示されません（後から`[[見出し>#anchorID]]`のように別の場所から
リンクするための目印になります）。中身を書くと、その場に**自分自身
（`#anchorID`）へのリンク**として表示されます。

`super`/`full`/`noid`は、中身（リンク文字列）を省略すると意味を持たない
ため、その組み合わせで書くとエラーになります。
"""

""" 技術資料
本家PukiWikiの`aname.inc.php`を移植した。

## 「リンク文字列」の扱いをbodyに統一した

本家はブロック側（`#aname(id,...,タイトル)`）では末尾のカンマ引数として
「リンク文字列」を渡し、インライン側（`&aname(id,...){タイトル};`）では
`{…}`の中身として渡す、という**呼びかたごとに違う位置**だった
（`func_get_args()`で受けた生の引数列を`plugin_aname_tag()`という
共通関数に渡す際、末尾の1個を`array_pop`で取り出すことで両対応させて
いた）。このシステムは`args`（丸括弧）と`body`（波括弧）が最初から
分かれているため、**ブロック・インラインどちらも「リンク文字列」は
必ずbody（波括弧の中身）**という、このシステム内で一貫した書きかたに
揃えた（`note`/`img`など他の同梱プラグインと同じ考えかた。引数の
位置・書式は互換対象外という方針に基づく）。

## idの検証

本家の`PLUGIN_ANAME_ID_REGEX`（`/^[A-Za-z][\\w\\-]*$/`）・
`PLUGIN_ANAME_ID_MAX`（40文字）をそのまま`ID_RE`/`ID_MAX`として移植した。
`candidate`の正規表現1つに丸めず、「長すぎる」「形式が違う」を別々の
`PluginArgumentError`メッセージにしている（本家が別メッセージを
返していたのに合わせた）。

本家にある`PLUGIN_ANAME_ID_MUST_UNIQUE`（IDの重複を禁止するか）は既定で
`0`（無効）であり、実質「重複していても黙って許す」が本家の実際の挙動
だったため、重複チェックの仕組みごと持ち込んでいない（無効な機能を
移植しても意味が無いため）。

## full（絶対パス）の扱い

本家は`get_page_uri()`でホスト名込みの完全な絶対URIを組み立てるが、この
システムには「サイトの公開ホスト名」を持つ設定が無い（`context.base_url`
はfarm/server.prefixを含む**パスの接頭辞**であり、スキーム・ホスト名は
含まない）。そのため`full`は、ホスト名込みの絶対URIではなく
**`context.base_url + "/" + context.page`（ルート相対の完全なパス）**
を`href`に含める形にした。本家ほど完全ではないが、目的（このページの
外から見ても迷子にならないリンクにする。特に`include`プラグインで
このページの中身が別ページへ差し込まれた場合に、素の`#anchorID`だと
差し込んだ側のページ内で探してしまう問題を避ける）は同じ形で果たせる。

## body（リンク文字列）の展開

本家はブロック側では`htmlsc()`でエスケープする一方、インライン側では
（呼び出しまでの経路の違いにより）本文側で先に展開済みのインライン記法が
そのまま来る、という**呼びかたによって展開の有無が違う**実装だった。
このシステムでは`expand_inline`/`expand_plugin`を宣言せず、ブロック・
インラインどちらも`html.escape()`でエスケープする一貫した扱いにした
（`&`本文のリンク文字列は短い文字列であることが大半で、太字等の装飾を
必要とする場面は薄いと判断した）。
"""

import re

from html import escape

from wikilib.plugins import PluginArgumentError

ID_RE = re.compile(r"[A-Za-z][\w\-]*")
ID_MAX = 40

PLUGIN_INFO = {
    "help": "#aname(id,super,full,noid,nouserselect){title} / &aname(id,super,full,noid,nouserselect){title};",
    "args": [
        {"name": "id", "num_order": 1, "label": "アンカーID"},
        {"name": "super", "flag": True, "default": False, "label": "super"},
        {"name": "full", "flag": True, "default": False, "label": "full"},
        {"name": "noid", "flag": True, "default": False, "label": "noid"},
        {"name": "nouserselect", "flag": True, "default": False, "label": "nouserselect"},
    ],
}


def _validate_id(raw):
    if len(raw) > ID_MAX:
        raise PluginArgumentError(
            f"アンカーIDが長すぎます（{ID_MAX}文字まで）: {raw}"
        )
    if not ID_RE.fullmatch(raw):
        raise PluginArgumentError(
            "アンカーIDの形式が正しくありません"
            f"（先頭は英字、以降は英数字・アンダースコア・ハイフンのみ）: {raw}"
        )


def _render(resolved, body, context):
    anchor_id = resolved["id"]
    _validate_id(anchor_id)

    f_super = resolved["super"]
    f_full = resolved["full"]
    f_noid = resolved["noid"]
    f_nouserselect = resolved["nouserselect"]

    if not body:
        if f_noid:
            raise PluginArgumentError("リンク文字列が無いと noid は意味を持ちません")
        if f_super:
            raise PluginArgumentError("リンク文字列が無いと super は意味を持ちません")
        if f_full:
            raise PluginArgumentError("リンク文字列が無いと full は意味を持ちません")

    css_class = "anchor_super" if f_super else "anchor"
    attr_id = "" if f_noid else f' id="{escape(anchor_id, quote=True)}"'
    path = context.base_url + "/" + (context.page or "") if f_full else ""

    if body:
        href = f' href="{escape(path, quote=True)}#{escape(anchor_id, quote=True)}"'
        title_attr = f' title="{escape(anchor_id, quote=True)}"'
        astyle = ' style="user-select:none;"' if f_nouserselect else ""
    else:
        href = title_attr = astyle = ""

    return (
        f'<a class="{css_class}"{attr_id}{href}{title_attr}{astyle}>'
        f'{escape(body) if body else ""}</a>'
    )


def _convert(resolved, body, context):
    return _render(resolved, body, context)


def _inline(resolved, body, context):
    return _render(resolved, body, context)
