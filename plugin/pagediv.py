"""pagediv — いくつかのページの本文を、枠に入れて縦横に並べて差し込むブロック専用のプラグイン。

    #pagediv(ページA, ページB;30%, ページC)     1行に横並び

    #pagediv{{
    |>|日記TOP|暫定メモ;40%|
    |日記VIEW;30%|大学業務ページ;30%|メモ|
    |^|OS情報|工作|
    }}

    #pagediv(notitle){{                     ページ名の見出しを付けない
    |ページA|ページB|
    }}
    #pagediv(cols){{                        行の高さを揃えず、列ごとに上から詰める
    |日記TOP;40%|暫定メモ|
    |日記VIEW|大学業務ページ|
    }}
    #pagediv(cols=3){{                      ページを3列へ順に振り分けて、上から詰める
    |A|B|C|D|E|F|G|
    }}

 1. ページの並び … 1行で並べるなら引数に、縦横に並べるなら `{{ }}` の中に書く
       `{{ }}` の中は、表と同じく1行を `|` で始めて `|` で終え、セルを `|` で区切る
       `>` … そのセルを右のセルとつなぐ（横に2つ分の大きさになる。続けて書けば3つ分…）
       `^` … そのセルを上のセルとつなぐ（縦に2つ分の大きさになる）
       何も書かないセル（`||`）は空いたままになる
 2. notitle     … 単語を書くと、各セルの上のページ名（見出し）を付けない (default: 付ける)
 3. nostack     … 単語を書くと、狭い画面でも縦1列に積み直さない (default: 積み直す)
 4. cols        … 単語を書くと、行の高さを揃えず、表の列ごとにページを上から詰めて
       並べる（短いページの下に空きを作らない） (default: 表のとおり行を揃える)
       `>` でつないだセルは始まりの列に置き、`^` は無視します
 5. cols=N      … ページを N 列へ、書いた順に左から1つずつ振り分けて、上から詰める
       （A→1列目、B→2列目、…、N+1番目→1列目）。列の幅は等分で、`;40%` などの
       幅の指定は使いません。`cols` と両方書いたら `cols=N` が効きます

各ページ名の後ろには `;` で区切って見た目を足せます（`メモ;40%;bgcol:#cdf`）。

    30% / 200px（width:30% とも） … その列の幅
    col:色    … 見出しの文字色        bgcol:色 … 見出しの背景色
    tdcol:色  … セル全体の背景色
    sz:大きさ … セル全体の文字の大きさ   tdsz:大きさ … 見出しの文字の大きさ

ページ名は本文のリンク `[[ページ名]]` と同じ決まりです（裸の名前はWikiの先頭から、
`./` はこのページの下）。見出しはそのページへのリンクで、そのページを編集できる
閲覧者には編集画面を開くボタンになります。

次のセルには、ページの中身の代わりに案内を出します。

- ページが無い・閲覧する権限が無い
- 自分自身や、自分を差し込んでいるページ（無限ループになるため）
- `#pagediv` の入れ子が3段を超えた

エラーになる書きかた:

- `{{ }}` の中に `|` で始まって `|` で終わらない行がある
- ページの並びを引数と `{{ }}` の両方に書いた
- `;` の後ろに知らない指定・使えない文字を書いた
"""

""" 技術資料
本家は手元の `~/pukiwiki/.wkcommon/plugin/pagediv.inc.php`（自作。`<table>` で
並べ、各セルで `convert_html(get_source(ページ))` する）。2026-09-25に
`~/pukiwiki/*/wiki/*.txt` を調べた範囲では、実際の使用は `{{ }}` 形だけで5つ
（`2023g3_havrec`・`m4w`・`parts`×2・`mypkwk`）。`>`/`^` と `;40%` の幅指定は
`mypkwk` の FrontPage が使っている。予定表（ChangeLog）の方針「pagediv は
モダン実装に」に沿って、書きかたは本家のまま、出力を作り直した。

## `cols`・`cols=N`（Wiki設計者の指示、2026-09-27）

表の形のグリッドは行の高さを揃えるので、同じ行に短いページと長いページがあると
短いほうの下が空く。`cols` はこの揃えを外し、**列ごとに上から詰める**
（`.pagediv-cols`。各列を `<div class="pagediv-col">` にまとめ、その中を縦に積む。
列どうしの幅はこれまでと同じ `--pd-cols`）。検討した方法と選んだ理由:

- **列はサーバーが決める。** CSSのマルチカラム（`column-count`）はどのページが
  どの列に入るかをブラウザが決めてしまい、書き手が表に書いた列の意味が消える。
  グリッドの masonry はまだ主要ブラウザで使えない。高さを測って詰めるJSは
  JavaScript必須で画像の読み込みで崩れる。サーバーで列に振り分ければ、JS無しで
  どのブラウザでも同じに見え、書いたとおりの列になる
- `cols`: 列＝表の列（`_layout` の `col`）。`>` でつないだセルは始まりの列に置く
  （幅は1列分）。`^` は縦の結合で、列ごとに積む形では意味が無いので無視する
  （Wiki設計者の選択、案a。書いたページを消さないため）。空のセルは飛ばす
  （列の中に空きを作らない）。列の幅は表のとき（`_columns`）と同じ
- `cols=N`: セルを書いた順（上の行から左→右）に並べ、左の列から1つずつ振り分ける。
  高さを見て詰めるには測るJSが要るので、順番どおりにした。幅の指定は、どのセルの
  指定をどの列に使うか決めようが無いので使わず、N列を等分する
- `cols=N` は名前付きでしか書けない（`kw_only`）。単語の `cols` と同じ引数にすると、
  自由順序の位置引数としての候補に数字が入り、`2026` のような名前のページを列の数と
  取り違えるため。単語の `cols` は、ページの並びの受け皿（`pages`）から拾う
- 狭い画面では、列を順に縦1列に積み直す（1列目を全部、次に2列目…）。`nostack`
  で止められるのはこれまでと同じ

## 本家から変えたこと・残したこと

- **`<table>` をやめて CSS グリッドにした。** 各セルの位置は `_layout` が
  HTMLの表と同じ規則（`>` は右のセルへ、`^` は上のセルへ結合）でサーバー側で
  決め、`--pd-area`（`grid-area` の値）としてセルに持たせる。自動配置に任せない
  のは、行ごとのセル数が違うと、グリッドは次の行の先頭を前の行の空きへ
  詰めてしまい、表と並びが変わるため。列の幅は `--pd-cols`
  （`grid-template-columns`）。`%` は比率（`fr`）に直し、指定の無い列は残りの
  百分率を等分する（本家の `table-layout: fixed; width: 100%` の割り振りと
  同じ比になる）。`minmax(0, …)` にして、長い中身で列が広がらないようにした
  （これも `table-layout: fixed` と同じ）。
- **狭い画面では縦1列に積み直す**（`pagediv.css` の `@media`）。グリッドの
  値をインラインの `style` に直接書かず CSS変数で渡しているのは、この上書きに
  `!important` を使わずに済ませるため。`nostack` で止められる。
- **`>`/`^` を連ねたら、その分だけつなぐ。** 本家は `colspan=2`/`rowspan=2` を
  決め打ちしており、3つ以上つなげなかった（本家どおりの2つ分は同じ結果）。
- **本家の不具合を2つ直した。** (1) セルの `style` を `,` でつないでいた
  （`width:30%,background-color:red` という壊れたCSSになり、指定を2つ以上
  書くと効かなかった）→ `;` でつなぐ。(2) 同じページの二重差し込みを止める
  `$included` が関数の中で `static`/`global` 宣言されておらず、毎回空だった
  （実際には何も止めていなかった）。
- (2) のため、本家では**同じページを2つのセルに置いても両方表示されていた**。
  その挙動は残し、止めるのは無限ループになるもの（自分自身と、自分を差し込んで
  いる先祖のページ）だけにした。先祖は `_pagediv_chain`（`sub` へ引き継ぐ）で
  たどる。`#include` との間のループも止まるよう、`include` と共有の差し込み
  記録（`_include_state["included"]`）に載っているページも差し込まない。
  セルに差し込んだページはその記録に**足さない**（足すと、同じページ上の後の
  `#include` が「差し込み済み」になり、本家に無い制限になる）。
- 入れ子の上限3段は本家どおり（`_pagediv_depth`、`sub` へ引き継ぐ）。
- 件数の上限は無い（本家どおり）。`include` の12件の上限はかからない。このため
  `include` を `call_plugin` で呼ぶのではなく、差し込みの中核を兄弟の
  `_embedpage.py`（`include` と共有）に切り出して使っている。
- 見出しは本家どおりページ名。本家の編集アイコン（`?cmd=edit` へのGETリンク）は、
  このシステムの決まり（編集画面は `cmd=edit` のPOSTで開く）に合わせて、
  見出し自体を編集ボタン（編集できない閲覧者には閲覧のリンク）にした
  （`_embedpage.title_html`）。
- セルごとの指定（`30%`・`col:`・`bgcol:`・`tdcol:`・`sz:`・`tdsz:`）は本家の
  名前と割り当てのまま（`sz:` がセル全体、`tdsz:` が見出し、という一見逆の
  名付けも本家どおり）。本家は知らない指定を黙って捨てていたが、`blockdiv` と
  同じくエラーにした（実ページで使われていたのは `%` だけ）。
- 引数と `{{ }}` の両方にページを並べるのは本家でもエラー（"No opt for
  multiline"）。本家に無い `notitle`/`nostack` は `{{ }}` と一緒に書ける。
- 空のセル（`||`）は本家では「No such page: []」だったが、空いたままにした。
- ページ名の引数は `link: True` にできない（位置引数の並びを1つの受け皿で
  受け取り、`{{ }}` の中にも書くため、フレームワークが1つのページ参照として
  読めない）。リンク元データベースには載らない。
"""

import importlib.util
import os
import re
from html import escape

from wikilib.paths import full_pagepath, is_valid_pagepath
from wikilib.plugins import PluginArgumentError

MAX_NEST = 3  # 本家の MAX_NEST

# 見た目の指定の値として style に入れてよい文字（`;` `"` `<` などで抜け出させない）
VALUE_RE = re.compile(r"[A-Za-z0-9%#.\-_ (),/+]+")
WIDTH_RE = re.compile(r"(?:width:)?\s*(\d+(?:\.\d+)?)(%|px)", re.IGNORECASE)
# 本家の指定名 → (どこに付けるか, CSSプロパティ)
STYLE_OPTS = {
    "col": ("title", "color"),
    "bgcol": ("title", "background-color"),
    "tdcol": ("cell", "background-color"),
    "sz": ("cell", "font-size"),
    "tdsz": ("title", "font-size"),
}

PLUGIN_INFO = {
    "help": "#pagediv(page;style,page;style,...) / #pagediv(notitle,nostack,cols,cols=N){{ |page;style|page| }}",
    "args": [
        {"name": "notitle", "flag": True, "default": False},
        {"name": "nostack", "flag": True, "default": False},
        {"name": "cols", "kw_only": True, "candidate": [(r"[1-9]\d*", "re")], "default": "",
         "label": "列の数（cols=N）"},
        {"name": "pages", "num_order": -1, "default": ""},
    ],
}


def _load_embed():
    """兄弟の`_embedpage.py`（`include`と共有）を読み込む（呼び出しごと）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_embedpage.py")
    spec = importlib.util.spec_from_file_location("wikiplugin__embedpage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_cell(text):
    """`ページ名;指定;指定` を {"page", "width", "cell", "title"} にする。"""
    parts = [p.strip() for p in text.split(";")]
    cell = {"page": parts[0], "width": None, "cell": [], "title": []}
    for opt in parts[1:]:
        if not opt:
            continue
        m = WIDTH_RE.fullmatch(opt)
        if m:
            cell["width"] = (float(m.group(1)), m.group(2).lower())
            continue
        name, sep, value = opt.partition(":")
        name, value = name.strip().lower(), value.strip()
        if not sep or name not in STYLE_OPTS:
            raise PluginArgumentError(f"知らない指定です: {opt}（{parts[0]}）")
        if not VALUE_RE.fullmatch(value):
            raise PluginArgumentError(f"{name}の値に使えない文字が含まれています: {value}（{parts[0]}）")
        where, prop = STYLE_OPTS[name]
        cell[where].append(f"{prop}:{value};")
    return cell


def _rows_from_body(body):
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) < 2 or not (line.startswith("|") and line.endswith("|")):
            raise PluginArgumentError(f"{{{{ }}}} の中の行は | で始めて | で終えてください: {line}")
        rows.append([c.strip() for c in line[1:-1].split("|")])
    return rows


def _layout(rows):
    """表の各行（セルの文字列の並び）から、各セルの位置と大きさを決める。

    文字列の何番目か＝列の番号（`>`・`^` もその位置を1つ取る）。`>` は直後の
    実セルを左へ広げ、`^` は真上の位置を持つセルを下へ広げる（HTMLの表の
    colspan/rowspan と同じ結果）。返すのは (セルの一覧, 列の数)。"""
    cells, owner = [], {}
    ncols = 0
    for r, row in enumerate(rows, start=1):
        ncols = max(ncols, len(row))
        pending = 0
        for c, text in enumerate(row, start=1):
            if text == ">":
                pending += 1
                continue
            if text == "^":
                pending = 0
                above = owner.get((r - 1, c))
                if above is not None:
                    above["rowspan"] = r - above["row"] + 1
                    owner[(r, c)] = above
                continue
            cell = _parse_cell(text) if text else {"page": "", "width": None, "cell": [], "title": []}
            cell.update(row=r, col=c - pending, colspan=pending + 1, rowspan=1)
            for cc in range(cell["col"], c + 1):
                owner[(r, cc)] = cell
            cells.append(cell)
            pending = 0
    return cells, ncols


def _columns(cells, ncols):
    """`grid-template-columns` の値。%は比率（fr）に、指定の無い列は残りを等分。"""
    widths = {}
    for cell in cells:
        if cell["width"] and cell["colspan"] == 1 and cell["col"] not in widths:
            widths[cell["col"]] = cell["width"]
    if not widths:
        return f"repeat({ncols}, minmax(0, 1fr))" if ncols > 1 else "minmax(0, 1fr)"
    percents = [v for v, unit in widths.values() if unit == "%"]
    rest_cols = ncols - len(widths)
    rest = 100 - sum(percents)
    if rest_cols:
        share = rest / rest_cols if rest > 0 else (sum(percents) / len(percents) if percents else 1)
    out = []
    for col in range(1, ncols + 1):
        if col in widths:
            value, unit = widths[col]
            out.append(f"{value:g}px" if unit == "px" else f"minmax(0, {value:g}fr)")
        else:
            out.append(f"minmax(0, {share:g}fr)")
    return " ".join(out)


def _notice(message):
    return f'<div class="pagediv-notice">{message}</div>'


def _cell_html(cell, context, embed, st, chain, depth, with_title, place=True):
    """セル1つ。`place` が偽なら位置（`--pd-area`）を付けない（`cols` の列の中）。"""
    style = "".join(cell["cell"])
    if place:
        area = f'{cell["row"]} / {cell["col"]} / span {cell["rowspan"]} / span {cell["colspan"]}'
        style = f"--pd-area: {area};" + style
    style_attr = f' style="{escape(style)}"' if style else ""
    open_tag = f'<section class="pagediv-cell"{style_attr}>'
    if not cell["page"]:
        return open_tag + "</section>"

    page = full_pagepath(context.page or "", cell["page"])
    title = ""
    if not is_valid_pagepath(page):
        body = _notice(f"ページ名が正しくありません: {escape(cell['page'])}")
    elif page in chain or page in st["included"]:
        body = _notice(f"自分自身や、自分を差し込んでいるページは差し込めません: {embed.read_link(page)}")
    else:
        status, ref = embed.lookup(context, page)
        if status == "forbidden":
            body = _notice(f"このページを閲覧する権限がありません: {escape(page)}")
        elif status == "missing":
            body = _notice(f"このページはまだありません: {escape(page)}")
        else:
            if with_title:
                tstyle = "".join(cell["title"])
                tattr = f' style="{escape(tstyle)}"' if tstyle else ""
                title = (f'<div class="pagediv-title"{tattr}>'
                         f'{embed.title_html(context, page, ref)}</div>')
            html = embed.render(context, page, ref, st, {
                "_pagediv_chain": chain | {page},
                "_pagediv_depth": depth + 1,
            })
            body = f'<div class="pagediv-body">\n{html}\n</div>'
    return f"{open_tag}{title}\n{body}\n</section>"


def _convert(resolved, body, context):
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")
    depth = getattr(context, "_pagediv_depth", 0)
    if depth >= MAX_NEST:
        return _notice(f"#pagediv の入れ子が{MAX_NEST}段を超えました。") + "\n"

    # 単語の cols は、ページの並びの受け皿に入って届く（技術資料「cols」）
    tokens = [p.strip() for p in (resolved["pages"] or "").split(",")] if resolved["pages"] else []
    by_table = "cols" in tokens
    tokens = [t for t in tokens if t != "cols"]
    pages = ",".join(tokens)
    ncols_wanted = int(resolved["cols"]) if resolved["cols"] else 0
    if body is not None and pages:
        raise PluginArgumentError("ページの並びは、引数と {{ }} のどちらか一方に書いてください。")
    if body is not None:
        rows = _rows_from_body(body)
    else:
        rows = [[p.strip() for p in pages.split(",")]] if pages else []
    if not rows:
        raise PluginArgumentError("差し込むページを指定してください。")

    cells, ncols = _layout(rows)
    embed = _load_embed()
    st = embed.state(context)
    chain = getattr(context, "_pagediv_chain", None) or {context.page or ""}
    with_title = not resolved["notitle"]
    nostack = " pagediv-nostack" if resolved["nostack"] else ""

    if ncols_wanted or by_table:
        return _cols_html(cells, ncols, ncols_wanted, context, embed, st, chain, depth,
                          with_title, nostack)

    classes = "pagediv" + nostack
    style = f"--pd-cols: {_columns(cells, ncols)};"
    inner = "\n".join(_cell_html(cell, context, embed, st, chain, depth, with_title)
                      for cell in cells)
    return f'<div class="{classes}" style="{escape(style)}">\n{inner}\n</div>\n'


def _cols_html(cells, ncols, ncols_wanted, context, embed, st, chain, depth, with_title, nostack):
    """`cols`・`cols=N`: 列ごとにセルを上から詰める（技術資料「cols」）。"""
    filled = [c for c in cells if c["page"]]   # 空のセルは飛ばす（列の中に空きを作らない）
    if ncols_wanted:
        count = ncols_wanted
        columns = [filled[i::count] for i in range(count)]
        widths = f"repeat({count}, minmax(0, 1fr))" if count > 1 else "minmax(0, 1fr)"
    else:
        count = ncols
        columns = [[c for c in filled if c["col"] == i] for i in range(1, count + 1)]
        widths = _columns(cells, ncols)
    style = f"--pd-cols: {widths};"
    parts = []
    for column in columns:
        inner = "\n".join(_cell_html(cell, context, embed, st, chain, depth, with_title,
                                     place=False) for cell in column)
        parts.append(f'<div class="pagediv-col">\n{inner}\n</div>')
    body = "\n".join(parts)
    return (f'<div class="pagediv pagediv-cols{nostack}" style="{escape(style)}">\n'
            f'{body}\n</div>\n')
