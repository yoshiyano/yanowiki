"""table — セルの中を複数行で書ける表。表計算ソフトから貼った TSV も表にできる。

    #table(){{
    |~品名|~説明|h\\\\
    |a|b
    c
    def|\\\\
    |x| abcde |\\\\
    }}

    #table(tsv){{ 表計算ソフトからコピーした内容 }}
    #table(tsv, header){{ 1行目を見出しにする }}
    #table(cols="120px | 30% || calc(100% - 200px)", width=100%){{ … }}

 1. format … 中身の書きかた (default: pukiwiki)
       pukiwiki  `|セル|セル|` の表。行末の `|\\\\` で表の1行が終わる
       tsv       タブ区切り。表計算ソフトからコピーしたものをそのまま貼る
 2. header … `tsv` のとき、1行目を見出し行にする (default: しない)
 3. cols   … 列の幅と縦線。列ごとの幅を `|` で区切って並べる (default: 内容に合わせる)
       `||` で区切ったところには二重線を引く。先頭・末尾の `||` は外枠
 4. width  … 表全体の幅 (default: 内容に合わせる)

## pukiwiki（既定）の書きかた

表の1行は、行末の `|\\\\` が来るまで続く。途中で改行してよく、セルの中の
改行はそのまま改行として表示される。`|` のすぐ前・すぐ後の改行は無視する
ので、1つのセルを1行ずつ書いてもよい。

    #table(){{
    |a
    |b
    c
    |\\\\
    }}

セルの頭の目印と行の種類は、PukiWiki記法の表と同じ。

    |~字|      見出しセル（th）
    |>|        右のセルとつなぐ
    |~|        上のセルとつなぐ
    |CENTER:字|  LEFT: / CENTER: / RIGHT: / COLOR(色): / BGCOLOR(色): / SIZE(数):
    |h\\\\  |f\\\\  |c\\\\   その行を見出し行 / フッタ行 / 書式指定だけの行にする

セルの中は、ページの書きかた（Markdown / PukiWiki）で、本文と同じように書ける
（強調・リンク・リスト・引用・ブロックのプラグインなど）。1段落だけのセルは、
段落の余白を付けずに表示する。見出しも書けるが、目次・ページ内リンクの飛び先には
ならない飾りの見出しになる（`#include`・`#pagediv` で差し込んだページの見出しも同じ）。
`#comment`・`#vote` もセルの中に置ける（投稿・投票もできる）。
PukiWiki のページでは、セルの中の `//` で始まる行もコメントになる。

セルの中に `|` を書くときは `\\|` と書く。`//` で始まる行は、表の行と行の
あいだに書くとコメントになる。

最後の行の `|\\\\` は省いてもよい（`}}` の前の `|` で終わっていれば1行とみなす）。

## tsv の書きかた

タブでセルを区切り、改行で行を区切る。`"` で囲んだセルの中では改行・タブを
書ける（`""` は `"` 1文字）。表計算ソフトからコピーすると、この形になる。
セルの中の文字はインライン記法だけを展開する（リスト・見出しなどのブロック記法は
読まない）。`~`・`>`・`CENTER:` などの表の目印としても読まない（書いた文字のまま出す）。空の行は飛ばし、セルの
足りない行は右を空のセルで埋める。

## 幅と罫線

`cols` には列の幅を左から `|` で区切って並べる。`120px`・`30%`・`8em` のような
単位付きの数（単位の無い数は px）、`auto`、`calc()`・`min()`・`max()`・`clamp()`
を書ける。空欄はその列を内容に合わせる。`%` と `calc(100% - …)` は表全体の
幅が基準なので、`width` も一緒に書く。`cols` を書くと、列の幅は中身で押し
広げられない（長い語は折り返す）。

`||` で区切ったところには縦の二重線を引く。表の行と行のあいだに `==` だけの
行を書くと、そこに横の二重線を引く（表の最初・最後に書けば外枠）。
`tsv` でも同じ `==` の行を書ける。
"""

""" 技術資料
2026-09-30 に作成。PukiWiki記法の表（`|セル|セル|`）は1行で1行を書くため、
セルの中に改行を入れるには `&br;` を並べるしかない。これを複数行で書ける
ようにしたもの。

## PukiWiki記法（本体）を変えずにプラグインにした理由

最初は書きかたそのもの（`|a|{{` … `}}|`）を変える案だったが、本文を行単位で
読む箇所（見出しの判定 `_starts_block`、`#comment`/`#vote` の数え上げ、
プラグイン引数のリンク抽出、`code.js` の色付け）が多く、影響が本体の
あちこちへ広がる。本家PukiWikiとの互換も崩れる。プラグインなら影響が
呼び出しの中に閉じ、本家では「プラグインが無い」表示1つで済む
（設計者との検討の結果、2026-09-30）。

## 表の解析を `wikilib.pukiwiki` と共有しない理由

設計者の方針（2026-09-30）「表の parse 処理は pukiwiki と独立で作るほうが
良い。pukiwiki でできない部分を検討していくので二重化はやむなし」
「プラグインの表をデザインする部分以外は markdown の知識だけで済むように
すべき」。そのため:

- 目印（`~`・`>`・`CENTER:` など）の読みかたは `pukiwiki.parse_cell` と同じだが、
  このファイルに自前で持つ（`CELL_STYLE_RE` も複製）
- セルの中身は、**ページの書きかた**のブロック記法として展開する（次の節）。展開には
  `build_expand_renderer` を使い、PukiWiki のページだけ
  `expand_pukiwiki_output` を通す（`pre.py` の `_expand_verbatim` と同じ）
- セルの中の改行は、展開用のレンダラーの `breaks` を有効にして `<br />` に
  する（Markdown の softbreak、PukiWiki の行の変わり目のどちらも softbreak
  トークンになるので、これ1つで両方に効く）

`expand_*` は宣言しない（生の本文を受け取り、行とセルを自分で切ってから
セルごとに展開するため）。展開の深さ（`depth`）は `_convert` に渡されない
ので `0` から数える（`pre.py` と同じ既知の制限）。

## セルの中のブロック要素（2026-10-23）

Wiki設計者の要求（2026-10-04）「セルでは見出しを除くブロック要素を受け付ける。目次・
アンカーに入らないデザイン上の見出しなら許容できる」「中身として見出しを出すプラグイン
（`#include`・`#pagediv`）が、セルの中で、目次・アンカーに入る見出しを出さないように
する」による。2026-10-23 まではインライン記法だけを展開していた。

- `expand_block` を立てた展開用のレンダラーで、セルを1つのブロックとして描く。
  `<td>` の中はフローコンテンツなので、`<ul>`・`<div>`・`<details>` も正しい HTML
- **段落1つだけのセルは `<p>` を外す**（普通のセルに段落の余白が付かないように。
  クロコの実装例）
- **セルの出力の見出し（`<h1>`〜`<h6>`）から `id` を外す**（`HEADING_ID_RE`）。
  セルの中に直接書いた見出しも、`#include`・`#pagediv` で差し込んだページの見出しも、
  まとめて飾りの見出しになる。目次（`#contents`）はページ本文のトークンから集める
  （`page_headings`）ので、`#table` の本体の中の見出しはもともと入らない。
  差し込んだページの中に `#contents` があると、そのリンクは飛び先を失う（設計者の
  要求の範囲として受け入れる。クロコの見立て）
- **`tsv` はインライン記法だけを展開する**（2026-10-23 より前と同じ）。表計算ソフトから
  貼ったデータは、`-5`・`>`・`*` で始まる値がリスト・引用・見出しとして読まれると困るため
  （クロコの判断。設計者の要求は書き手がセルに書く表を想定していると読んだ）
- PukiWiki のページでは、セルの中の `//` で始まる行もコメントになる（ブロック記法として
  読むので、本文と同じ扱いになる。2026-10-23 までは文字のまま出していた。`#table` を
  使っている PukiWiki のページは無かった）
- `#comment`・`#vote` もセルの中で投稿・投票できる（Wiki設計者の指示、2026-10-23）。
  ID の書き足しと照合（`_polling.py` の `scan`）が、このファイルと同じ切りかたでセルの中まで
  見る（`_polling._table_cells`。セルの切りかたを変えたら、そちらも合わせる）。コメントの
  書き足しかたは `comment.py` の技術資料「#table のセルの中」

## 幅と罫線の作りかた

`cols`（縦線を `||` で同じ項目に書く、LaTeX の tabular の列指定と同じ考えかた）・
`width`・`==` の行は、クロコの案を設計者が了承したもの（2026-09-30）。

- **表を `<div class="table-plugin">` で包み、横スクロールはそちらで行う。**
  `base` 系のテーマは `.content table` を `display: block` にして表そのものを
  スクロールさせているが、その表示では表の `width` や列の `%` が効かない
  （中の匿名の表が内容に合わせた幅になる）。`table.css` で表を
  `display: table` に戻す
- **幅は `<colgroup>` の `<col style="width:…">` に書き、`cols` があれば
  `table-layout: fixed` にする**（幅が中身で押し広げられないように）
- **二重線はセルに付ける**（`table-dl`/`table-dr`/`table-dt`/`table-db` の
  クラス。左・右・上・下）。`<col>`・`<tr>` の罫線は `border-collapse: collapse`
  でしか効かず、`bloom` は `separate`（縦線を引かないテーマ）なので効かない。
  二重線は 3px 以上ないと見えないため 3px にする。`collapse` の表では太い線が
  勝つので、テーマの 1px の線より優先される
- 縦線は、その境目から始まるセルの左に引く。表の右端で終わるセルだけは
  右に引く（内側の境目で左右両方に引くと、`separate` の表で線が4本に見える）
- 横線は、`==` の次の行のセルの上に引く（最後に書いたときは前の行の下）。
  行に付けるので、`h`/`f` で thead・tfoot へ並べ替えても行と一緒に動く。
  `c` の行（表示しない）の前に書いた `==` は、次に表示する行へ付ける。
  縦に結合したセルは、そのセルが始まる行・終わる行で判定する（境目を
  またぐセルには引かない。LaTeX の `\\hline` と同じ）
- 幅の値は、`style` 属性へほかの指定を紛れ込ませられないよう、単位付きの
  数・`auto`・`calc()` 等の関数（中は数字・単位・演算子・丸括弧・カンマ
  だけ）に絞る（`WIDTH_RE`・`WIDTH_FUNC_RE`）

## 細部の決めかた

クロコが提案し、設計者が了承したもの（2026-09-30）:

- 行の終わりは `|\\\\`（後ろの空白は可）に限る。行末の `\\\\` だけで判定すると、
  KaTeX の数式の改行（`\\\\`）と同じ形になる（既存のページに31行あった）
- 行の種類は `|h\\\\` のように `\\\\` の直前に書く（PukiWiki の `|h` と同じ位置）
- セルの前後の空白・改行は捨てる（`parse_cell` と同じ）。これで1セル1行の
  書きかたも通る
- `\\|` は GFM の表と同じく、セルを区切らない `|` として中身へ渡す
  （Markdown のコード片の中では `&#124;` が効かないため）
- 最後の行の `|\\\\` は省いてよい。`//` の行は、行と行のあいだでだけコメント
  （2026-10-23 からは、PukiWiki のページのセルの中でもコメント。上の節）
- PukiWiki記法の表は列数が変わるとそこで表を切るが、ここでは1つの
  `#table` を1つの表として出す（呼び出しで範囲がはっきりしているため）
- 表の外に出る文字（`|` で始まらない行）があれば、エラーにする
- `header` を `pukiwiki` の書きかたで使うとエラーにする（`|h\\\\` があるため）
- TSV の空の行は飛ばし、セルの足りない行は右を空のセルで埋める

設計者の判断: `|\\\\` の書き忘れの注意は出さない（プレビューで分かるため）。
"""

import re
from html import escape

from wikilib.plugins import PluginArgumentError, build_expand_renderer, expand_pukiwiki_output
from wikilib.render import is_pukiwiki

PLUGIN_INFO = {
    "help": "#table(format,header,cols,width){{中身}}",
    "args": [
        {"name": "format", "candidate": ["pukiwiki", "tsv"], "default": "pukiwiki",
         "label": "書きかた"},
        {"name": "header", "flag": True, "default": False, "label": "見出し行"},
        {"name": "cols", "default": None, "label": "列の幅"},
        {"name": "width", "default": None, "label": "表の幅"},
    ],
}

# 表の1行の終わり。`|` の直後の `\\`（前に行の種類 h/f/c を置ける）
ROW_END_RE = re.compile(r"\|([hHfFcC]?)\\\\[ \t]*$")
# 最後の行の `|\\` を省いたとき、その行が `|` で閉じているか
ROW_TAIL_RE = re.compile(r"\|([hHfFcC]?)\s*$")
# セルを区切る `|`（`\|` は区切らない）
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
# セルの先頭に書ける書式指定（`pukiwiki.CELL_STYLE_RE` と同じ。重ねて書ける）
CELL_STYLE_RE = re.compile(
    r"^(?:(LEFT|CENTER|RIGHT)|(BG)?COLOR\(([#\w]+)\)|SIZE\((\d+)\)):(.*)$", re.S)
COMMENT_PREFIX = "//"
HLINE_MARK = "=="  # 行と行のあいだに書くと、そこに横の二重線を引く

# 幅の値。単位付きの数（単位が無ければ px）か auto
WIDTH_RE = re.compile(r"^(\d+(?:\.\d+)?)(px|%|em|rem|ch|ex|vw|vh)?$")
# calc() 等。中は数字・単位（英小文字）・演算子・丸括弧・カンマ・空白だけ
WIDTH_FUNC_RE = re.compile(r"^(?:calc|min|max|clamp)\([0-9a-z.%+\-*/(), ]*\)$")
# cols の区切り（`|` は通常の線、`||` は二重線）
COLS_SEP_RE = re.compile(r"(\|+)")
# セルの中の見出しの id（技術資料「セルの中のブロック要素」）
HEADING_ID_RE = re.compile(r'(<h[1-6]\b[^>]*?)\s+id="[^"]*"')
# 段落1つだけのセル
SINGLE_PARAGRAPH_RE = re.compile(r"^<p>(.*)</p>$", re.S)


# ---- pukiwiki の書きかた ----------------------------------------------------

def _split_rows(body):
    """本文を表の行に分ける。

    [(行の種類, 行の中身（先頭と末尾の | を除いたもの）, 上に二重線), …] と、
    最後の行の下に二重線を引くかどうかを返す。"""
    rows = []
    buffer = []
    hline = False
    for number, line in enumerate(body.split("\n"), 1):
        if not buffer:
            stripped = line.strip()
            if not stripped or stripped.startswith(COMMENT_PREFIX):
                continue  # 行と行のあいだの空行・コメント
            if stripped == HLINE_MARK:
                hline = True
                continue
            if not stripped.startswith("|"):
                raise PluginArgumentError(
                    f"{number}行目: 表の行は | で始めてください: {stripped}")
            line = stripped
        m = ROW_END_RE.search(line)
        if m:
            buffer.append(line[:m.start()])
            rows.append((m.group(1).lower(), "\n".join(buffer)[1:], hline))
            buffer, hline = [], False
        else:
            buffer.append(line)
    if buffer:
        text = "\n".join(buffer).rstrip()
        m = ROW_TAIL_RE.search(text)
        if not m:
            raise PluginArgumentError("最後の行が | で終わっていません（行の終わりは |\\\\）")
        rows.append((m.group(1).lower(), text[:m.start()][1:], hline))
        hline = False
    return rows, hline


def _parse_cell(text):
    """セル1つの目印・書式を読む（`pukiwiki.parse_cell` と同じ読みかた）。"""
    text = text.replace("\\|", "|").strip()
    if text == ">":
        return {"merge": "right"}
    if text == "~":
        return {"merge": "up"}
    header = text.startswith("~")
    if header:
        text = text[1:].strip()
    style = {}
    while True:
        m = CELL_STYLE_RE.match(text)
        if not m:
            break
        if m.group(1):
            style["text-align"] = m.group(1).lower()
        elif m.group(3):
            style["background-color" if m.group(2) else "color"] = m.group(3)
        else:
            style["font-size"] = m.group(4) + "px"
        text = m.group(5).strip()
    return {"merge": None, "header": header, "style": style, "text": text}


def _pukiwiki_rows(body):
    split, hline_below = _split_rows(body)
    rows = [{"kind": kind, "hline": above,
             "cells": [_parse_cell(c) for c in CELL_SPLIT_RE.split(text)]}
            for kind, text, above in split]
    return rows, hline_below


# ---- tsv の書きかた ---------------------------------------------------------

def _split_tsv(body):
    """TSV を [[セルの文字列, …] または HLINE_MARK, …] にする。`"` で囲んだ
    セルの中では改行・タブを書ける（`""` は `"`）。囲まずに `==` だけを書いた
    行は、横の二重線の目印（HLINE_MARK）になる。"""
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    rows, row, cell = [], [], []
    quoted = False  # この行に `"` で囲んだセルがあったか
    i, n = 0, len(text)
    at_start = True  # セルの先頭か（`"` で囲んだセルかどうかを見る位置）

    def end_row():
        row.append("".join(cell))
        if not quoted and len(row) == 1 and row[0].strip() == HLINE_MARK:
            rows.append(HLINE_MARK)
        else:
            rows.append(list(row))

    while i < n:
        ch = text[i]
        if at_start and ch == '"':
            quoted = True
            i += 1
            while i < n:
                if text[i] == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        cell.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                cell.append(text[i])
                i += 1
            at_start = False
            continue
        if ch == "\t":
            row.append("".join(cell))
            cell, at_start = [], True
        elif ch == "\n":
            end_row()
            row, cell, at_start, quoted = [], [], True, False
        else:
            cell.append(ch)
            at_start = False
        i += 1
    if cell or row:
        end_row()
    # 空の行は飛ばし、足りないセルは右を空のセルで埋める
    rows = [r for r in rows if r == HLINE_MARK or any(c.strip() for c in r)]
    width = max((len(r) for r in rows if r != HLINE_MARK), default=0)
    return [r if r == HLINE_MARK else r + [""] * (width - len(r)) for r in rows]


def _tsv_rows(body, header):
    rows = []
    hline = False
    for cells in _split_tsv(body):
        if cells == HLINE_MARK:
            hline = True
            continue
        is_head = header and not rows
        rows.append({"kind": "h" if is_head else "", "hline": hline,
                     "cells": [{"merge": None, "header": is_head, "style": {},
                                "text": c.strip()} for c in cells]})
        hline = False
    return rows, hline


# ---- 幅と縦線（cols・width） ------------------------------------------------

def _width_value(value, label):
    """幅の値を CSS の値にする。書けない値ならエラー。"""
    value = value.strip()
    if value == "auto":
        return value
    m = WIDTH_RE.match(value)
    if m:
        return m.group(1) + (m.group(2) or "px")
    if WIDTH_FUNC_RE.match(value) and value.count("(") == value.count(")"):
        return value
    raise PluginArgumentError(
        f"{label}には 120px・30%・calc(100% - 200px) のような値を書いてください: {value}")


def _parse_cols(spec):
    """`cols` を ([列の幅または None, …], {境目の位置: "double"}) にする。

    境目の位置は、その左にある列の数（0 は左の外枠、列の数と同じなら右の外枠）。"""
    parts = COLS_SEP_RE.split(spec)
    # parts は [列, 区切り, 列, 区切り, …, 列]。両端の空の列は外枠の区切りのため
    widths = []
    lines = {}
    for index, part in enumerate(parts):
        if index % 2:  # 区切り
            if len(part) > 2:
                raise PluginArgumentError(f"列の幅の区切りは | か || です: {part}")
            if len(part) == 2:
                lines[len(widths)] = "double"
            continue
        at_edge = index == 0 or index == len(parts) - 1
        if at_edge and not part.strip() and len(parts) > 1:
            continue
        widths.append(_width_value(part, "列の幅") if part.strip() else None)
    return widths, lines


# ---- 表の組み立て -----------------------------------------------------------

def _placed_cells(cells):
    """[(セル, colspan), …]。`>` のセルは右のセルに吸収される。"""
    placed = []
    colspan = 1
    for cell in cells:
        if cell["merge"] == "right":
            colspan += 1
            continue
        placed.append([cell, colspan])
        colspan = 1
    if colspan > 1:
        placed.append([_blank_cell(), colspan - 1])
    return placed


def _blank_cell():
    return {"merge": None, "header": False, "style": {}, "text": ""}


def _build_group(rows, column_styles, vlines, render_text):
    """thead / tbody / tfoot の中の <tr> の並びを HTML にする。

    縦の結合（`~`）は、その列に最後に置いたセルの rowspan を足していく。"""
    grid = []  # 行ごとの [セル, colspan, rowspan, 列, 始まりの行]
    owners = {}
    for row_index, row in enumerate(rows):
        placed = []
        column = 0
        for cell, colspan in _placed_cells(row["cells"]):
            if cell["merge"] == "up":
                owner = owners.get(column)
                if owner is not None:
                    owner[2] += 1
                    column += 1
                    continue
                cell = _blank_cell()  # 上にセルが無い。空のセルにする
            entry = [cell, colspan, 1, column, row_index]
            placed.append(entry)
            owners[column] = entry
            column += colspan
        grid.append(placed)

    total = max((e[3] + e[1] for placed in grid for e in placed), default=0)
    out = []
    for placed in grid:
        out.append("<tr>\n")
        for cell, colspan, rowspan, column, start in placed:
            tag = "th" if cell["header"] else "td"
            style = dict(column_styles.get(column, {}))
            style.update(cell["style"])
            end = column + colspan
            classes = []
            if vlines.get(column):
                classes.append("table-dl")
            if vlines.get(end) and end == total:  # 右の外枠だけ（内側は右のセルの左）
                classes.append("table-dr")
            if rows[start]["hline"]:
                classes.append("table-dt")
            if rows[start + rowspan - 1].get("hline_below"):
                classes.append("table-db")
            attrs = ""
            if classes:
                attrs += f' class="{" ".join(classes)}"'
            if colspan > 1:
                attrs += f' colspan="{colspan}"'
            if rowspan > 1:
                attrs += f' rowspan="{rowspan}"'
            if style:
                css = ";".join("%s:%s" % kv for kv in style.items())
                attrs += f' style="{escape(css)}"'
            out.append(f"<{tag}{attrs}>{render_text(cell['text'])}</{tag}>\n")
        out.append("</tr>\n")
    return "".join(out)


def _build_table(rows, hline_below, widths, vlines, table_width, render_text):
    """`h`→thead、`f`→tfoot、残り→tbody。`c` の行は列の既定の書式になる。"""
    column_styles = {}
    for row in rows:
        if row["kind"] == "c":
            for column, cell in enumerate(row["cells"]):
                if not cell["merge"]:
                    column_styles[column] = cell["style"]

    # 横線は表示する行に付ける（`c` の行の前の `==` は、次に表示する行へ）
    shown = [row for row in rows if row["kind"] != "c"]
    carry = False
    for row in rows:
        if row["kind"] == "c":
            carry = carry or row["hline"]
        else:
            row["hline"] = row["hline"] or carry
            carry = False
    if shown and (hline_below or carry):
        shown[-1]["hline_below"] = True

    table_style = []
    if table_width:
        table_style.append(f"width:{table_width}")
    if any(widths):
        table_style.append("table-layout:fixed")
    style_attr = f' style="{escape(";".join(table_style))}"' if table_style else ""

    out = [f'<div class="table-plugin">\n<table{style_attr}>\n']
    if any(widths):
        out.append("<colgroup>\n")
        for width in widths:
            out.append(f'<col style="width:{escape(width)}">\n' if width else "<col>\n")
        out.append("</colgroup>\n")
    for kind, tag in (("h", "thead"), ("", "tbody"), ("f", "tfoot")):
        group = [row for row in shown if row["kind"] == kind]
        if group:
            out.append(f"<{tag}>\n{_build_group(group, column_styles, vlines, render_text)}"
                       f"</{tag}>\n")
    out.append("</table>\n</div>\n")
    return "".join(out)


def _cell_renderer(context, block=True):
    """セルの中身を、ページの書きかたで展開する関数を返す。`block` ならブロック記法
    （技術資料「セルの中のブロック要素」）、そうでなければインライン記法だけ（`tsv`）。"""
    info = {"expand_inline": True, "expand_plugin": True, "expand_block": block}
    engine = build_expand_renderer(context, info, 0)
    engine.options["breaks"] = True  # セルの中の改行を <br /> にする
    env = {"wiki": context}
    pukiwiki = is_pukiwiki(getattr(context, "ext", ".md"))

    def render(text):
        if not text:
            return ""
        if not block:
            if pukiwiki:
                return expand_pukiwiki_output(text, engine, context, False, env)
            return engine.renderInline(text, env)
        if pukiwiki:
            html = expand_pukiwiki_output(text, engine, context, True, env)
        else:
            html = engine.render(text, env)
        html = html.strip()
        m = SINGLE_PARAGRAPH_RE.match(html)
        if m and "<p>" not in m.group(1) and "</p>" not in m.group(1):
            html = m.group(1)
        return HEADING_ID_RE.sub(r"\1", html)
    return render


def _convert(resolved, body, context):
    if not body or not body.strip():
        raise PluginArgumentError("表の中身を書いてください: #table(){{ … }}")
    widths, vlines = _parse_cols(resolved["cols"]) if resolved["cols"] else ([], {})
    table_width = _width_value(resolved["width"], "表の幅") if resolved["width"] else None
    if resolved["format"] == "tsv":
        rows, hline_below = _tsv_rows(body, resolved["header"])
    else:
        if resolved["header"]:
            raise PluginArgumentError(
                "header は tsv のときだけ使えます（pukiwiki の書きかたでは行末を |h\\\\ にします）")
        rows, hline_below = _pukiwiki_rows(body)
    if not any(row["kind"] != "c" for row in rows):
        raise PluginArgumentError("表に出す行がありません")
    # tsv は表計算ソフトから貼ったデータなので、インライン記法だけを展開する（技術資料）
    render_text = _cell_renderer(context, block=resolved["format"] != "tsv")
    return _build_table(rows, hline_below, widths, vlines, table_width, render_text)
