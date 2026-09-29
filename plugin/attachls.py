"""attachls — ページに添付されたファイルの一覧を出す、ブロック専用のプラグイン。

    #attachls()                     このページの添付ファイルの一覧
    #attachls(資料)                  資料 のページの添付ファイルの一覧
    #attachls(./配布物, MTIME_REV)   新しい順に
    #attachls(, showimg)            画像はその場に表示して並べる
    #attachls(, showimg, 120x90)    画像を小さく表示して並べる

 1. page   … 添付ファイルを並べるページ（1番目に固定） (default: このページ)
       書きかたは本文のリンク [[ページ名]] と同じ決まりです
       （裸の名前はWikiの先頭から、./ はこのページの下、../ は1つ上から）
 2. sort   … 並び順 (default: FNAME)
       FNAME(_REV): ファイル名 / MTIME(_REV): 更新日時 / SIZE(_REV): 大きさ
       _REV がつくと逆順になります
 3. showimg … 単語を書くと、画像をその場に表示する
       (default: 表示せず、ほかのファイルと同じくファイル名のリンクにする)
 4. noimg  … 書いても何も変わりません（既定と同じ。`&ref` と同じ書きかたができるように残してあります）
 5. noicon … 単語を書くと、種別の札を出さない (default: 出す)
 6. nolink … 単語を書くと、画像を画像そのものへのリンクにしない（`showimg` のときだけ効く） (default: リンクにする)
 7. size   … 画像の大きさ（`showimg` のときだけ効く） (default: 元の大きさ)
       `120x90` / `120x` / `x90` / `120w` / `90h` / `50%`

1つ1つのファイルの見せかたは、本文に `&ref(ファイル名, noimg);` と書いたときと
同じです（画像も含めて、種別の札と、大きさ・更新日時つきのリンク）。`showimg` を
書くと `&ref(ファイル名);` と同じになり、画像はその場に表示されます。
`noicon`・`nolink`・`size` も `&ref` と同じ意味です。

添付ファイルが無いときは「添付ファイルはありません」と出します。
閲覧する権限の無いページを指定したときは、一覧の代わりに案内を出します。

エラーになる書きかた:

- 作れない名前（`=` や `.` で始まる部分を含む名前）のページを指定した
- `sort`・`size` に選べない値を書いた
"""

""" 技術資料
本家PukiWikiには無い新規プラグイン（予定表「attachls プラグイン。該当ページに
添付されたファイルの一覧を表示。ページ名を指定して別ページを指定することも
できるように。添付ファイルの表示は &ref に準拠。」、2026-09-25に実装）。本家で
近いのは `#attach`（一覧＋アップロード欄）だが、アップロードは編集画面の
添付タブが担うので、一覧だけにした。

## 表示は `ref` に任せる

各ファイルは `wikilib.plugins.call_plugin(context, "ref", 引数, None, "_inline", "&")`
で、**本文に `&ref(ページ/ファイル名);` と書いたときと同じ経路**で作る
（`newpage` の `showlist` が `#ls` を呼ぶのと同じ形）。画像の判定・種別の札・
大きさと更新日時・`noimg` 等の意味、`ref.css` の読み込み（`context.used_plugins`）
まで `&ref` と揃い、`ref` の見た目が変われば一覧も追随する。`src` は
`ページのsubpath/ファイル名`（先頭の `/` を付けない。裸の名前はWikiの先頭から）。
自分のページならファイル名だけ。`href`/`src` を `/.attach/...` に直すのは、
`ref` と同じく `wikilib.render.rewrite_content_links`。

`size` の検証パターンは `ref.py` の `SIZE_PATTERN` と同じもの（`PLUGIN_INFO` は
読み込み時に確定するので、`ref` のモジュールから借りられない）。先に宣言で
弾いておくと、ファイルの数だけ同じエラーが並ぶのを避けられる。

## 一覧の取りかた・権限

ファイルの一覧は `wikilib.attach.list_attachments`（編集画面の添付タブと同じ。
名前・大きさ・更新日時）。添付の置き場所はページの subpath（フォルダの入口
ページなら `Tech/index`）で決まるので、ページ名は `resolve_page_ref` で
subpath に直してから引く。ページ自体が無くても置き場所にファイルがあれば並べる
（添付の配信 `serve_attach` もページの有無ではなく置き場所で配る）。

閲覧の権限は `context.privilege.check(持ち主のページ)` で見て、`-` なら一覧を出さない
（ファイル名そのものが漏れないように）。**持ち主のページは、添付の配信
`attach.attach_viewable` と同じく、置き場所の subpath から `pagepath_of_subpath` で
求める**（書かれた名前のままだと、`#attachls(Tech/index)` が `Tech/index` で判定され、
配信側の `Tech` とずれうる）。一覧に出す・出さないと、そのリンクを開けるかどうかが
常に一致する。一覧は読むだけの機能なので、**編集の権限は見ない**（閲覧だけできる
閲覧者・未ログインの閲覧者にも、読めるページの一覧は出す）。2026-09-25、設計者の
指示で、閲覧できる人・閲覧だけの人・閲覧できない人・未ログインの人と、フォルダの
入口ページ（`Folder` / `Folder/index`）の組み合わせで、一覧と配信の可否が一致する
ことを確かめた。

`ref` プラグインも同じ日に閲覧の権限を見るようになった（読めないページの添付は
「閲覧できないファイル」の札だけ）。`attachls` は一覧を作る前に自分で止めるので、
ファイル名も出さない（一覧は「そのページに何があるか」自体を見せる機能なので、
`ref` より一段厳しくしている）。

## 既定は `noimg`（2026-09-25、設計者の指示）

最初は `&ref` と同じく画像をその場に展開する既定で作ったが、同じ日に設計者の指示で
「画像も展開しない（`noimg`）」を既定にした。一覧としては、画像が元の大きさで並ぶより
ファイル名・大きさ・更新日時が揃って並ぶほうが見渡しやすく、画像の多いページで
読み込みが重くならない。私もこの既定に賛成。画像を並べたいときのために逆の単語
`showimg` を足し、`noimg` は既定と同じ意味のまま受け付ける（`&ref` の書きかたに慣れた
編集者が書いてもエラーにならないように）。`ref` へは `showimg` が無ければ常に
`noimg` を付けて渡す。

`page` の後ろ（`sort`・`showimg`・`noimg`・`noicon`・`nolink`・`size`）は、`ref` と同じく
好きな順に位置で書ける（`num_order` の自由順序。`sort` と `size` の候補は重ならない）。

`page` には `link: True` を付けている（ページへの参照。リンク元データベースに
記録され、リネームにも追従する）。
"""

from html import escape

from wikilib.attach import list_attachments
from wikilib.auth import PAGE_NONE
from wikilib.paths import full_pagepath, is_valid_pagepath, pagepath_of_subpath, resolve_page_ref
from wikilib.plugins import FREE_TEXT, PluginArgumentError, call_plugin

# ref.py の SIZE_PATTERN と同じ（技術資料参照）
SIZE_PATTERN = (
    r"[0-9]+x[0-9]+"
    r"|[0-9]+x"
    r"|x[0-9]+"
    r"|[0-9]+w"
    r"|[0-9]+h"
    r"|[0-9]+(?:\.[0-9]+)?%"
)
SORTS = ["FNAME", "FNAME_REV", "MTIME", "MTIME_REV", "SIZE", "SIZE_REV"]
SORT_KEYS = {
    "FNAME": lambda item: item["name"].lower(),
    "MTIME": lambda item: item["mtime"],
    "SIZE": lambda item: item["size"],
}

PLUGIN_INFO = {
    "help": "#attachls(page,sort,showimg,noimg,noicon,nolink,size)",
    "args": [
        {"name": "page", "num_order": 1, "candidate": [FREE_TEXT], "default": None, "link": True},
        {"name": "sort", "candidate": SORTS, "default": "FNAME", "label": "並び順"},
        {"name": "showimg", "flag": True, "default": False},
        {"name": "noimg", "flag": True, "default": False},
        {"name": "noicon", "flag": True, "default": False},
        {"name": "nolink", "flag": True, "default": False},
        {"name": "size", "default": None,
         "candidate": [(SIZE_PATTERN, "re")], "label": "大きさ"},
    ],
}


def _strip_bracket(name):
    name = (name or "").strip()
    if name.startswith("[[") and name.endswith("]]"):
        name = name[2:-2].strip()
    return name


def _quote(value):
    """`call_plugin` に渡す引数の1つ分。ファイル名に `,` や `=` があっても崩れないよう
    引用符で囲む（ファイル名には `"` を使えない＝`attach.safe_attach_name`）。"""
    return f'"{value}"'


def _convert(resolved, body, context):
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")
    current = (context.page or "").strip("/")
    raw = _strip_bracket(resolved["page"])
    pagepath = full_pagepath(current, raw).strip("/") if raw else current
    if not is_valid_pagepath(pagepath):
        raise PluginArgumentError(f"ページの指定が正しくありません: {raw}")

    ref = resolve_page_ref(context.wiki_dir, pagepath)
    if ref is None:
        raise PluginArgumentError(f"ページの指定が正しくありません: {raw}")
    # 権限は、添付の配信（attach.attach_viewable）と同じく、置き場所から求めた
    # 持ち主のページで見る（`Tech/index` と書いても `Tech` で判定。技術資料参照）
    owner = pagepath_of_subpath(ref.subpath)
    shown = escape("/" + owner)
    if context.privilege.check(owner) == PAGE_NONE:
        return f'<div class="attachls attachls-empty">このページを閲覧する権限がありません: {shown}</div>\n'

    items = list_attachments(context.wiki_dir, ref.subpath, context.base_url)
    if not items:
        return f'<div class="attachls attachls-empty">添付ファイルはありません: {shown}</div>\n'

    sort = resolved["sort"]
    items.sort(key=SORT_KEYS[sort.replace("_REV", "")], reverse=sort.endswith("_REV"))

    own = ref.subpath == resolve_page_ref(context.wiki_dir, current).subpath
    # 既定は noimg（技術資料「既定は noimg」）。showimg のときだけ ref に画像を展開させる
    options = [] if resolved["showimg"] else ["noimg"]
    options += [name for name in ("noicon", "nolink") if resolved[name]]
    if resolved["size"]:
        options.append(resolved["size"])

    lines = []
    for item in items:
        src = item["name"] if own else f'{ref.subpath}/{item["name"]}'
        argstr = ",".join([_quote(src)] + options)
        lines.append(f'<li class="attachls-item">{call_plugin(context, "ref", argstr, None, "_inline", "&")}</li>')
    return '<ul class="attachls">\n' + "\n".join(lines) + "\n</ul>\n"
