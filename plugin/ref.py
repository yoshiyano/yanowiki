"""ref — 添付ファイル（か外部URL）を参照する、ブロック／インライン両対応のプラグイン。

    #ref(src)                              ブロック（画像なら大きく、それ以外はファイルへのリンク）
    #ref(src, right)                       右寄せ
    #ref(src, right, around)               右寄せ＋回り込み
    #ref(src, 300x200)                     サイズを指定
    &ref(src);                             文中に差し込む
    &ref(src, nolink);                     画像を画像そのものへのリンクにしない
    &ref(src, 資料);                        表示する文字を変える

PukiWikiの `ref` と同じ値が指定できます。`src`だけは常に1番目で、
`title`はどの引数にも当てはまらなかった残り（複数あればカンマ区切りで
まとめて受け取ります）。それ以外（`size`/`align`/`around`/`wrap`/
`noicon`/`nolink`/`noimg`/`zoom`）は`src`より後ろなら好きな順に書けます。

 1. **src** … 添付ファイル名かURL（省略不可、常に1番目）
 2. size … 大きさ (default: 元の大きさ)
       `300x200` / `300x` / `x200` / `300w` / `200h` / `50%`
 3. align … 寄せ方（**ブロックのみ**） (default: LEFT)
       `LEFT` / `CENTER` / `RIGHT`
 4. around … 単語を書くと回り込みにする（**ブロックのみ**、無ければ寄せは
       `text-align`だけ） (default: 回り込まない)
 5. wrap … 単語を書くと枠（背景つきの箱）で囲む（**ブロックのみ**） (default: 囲まない)
 6. noicon … 単語を書くと、画像以外のファイルのアイコンを出さない (default: 出す)
 7. nolink … 単語を書くと、画像を画像そのものへのリンクにしない (default: リンクにする)
 8. noimg … 単語を書くと、拡張子が画像でも展開せずファイル扱いにする (default: 展開する)
 9. zoom … 本家互換の値。単語を書くと縦横比を保つ意図になる
       （このシステムでは元画像の実寸を調べるしくみが無いため、指定しても
       出力には影響しません。詳しくは技術資料参照） (default: 書いても書かなくても出力は同じ)
 10. title … 表示する文字。どれにも当てはまらなかった残り (default: ファイル名をそのまま使う)

画像かどうかは拡張子で自動判定します（`noimg`で強制的にファイル扱いにできます）。
"""

""" 技術資料
本家PukiWikiのref.inc.phpの機能に完全互換を目指しつつ、引数は
`PLUGIN_INFO["args"]` の宣言だけで検証できる、意味の分かる名前付きの
項目にした。

本家は`ref_check_arg()`で「小文字化して先頭一致する最初のフラグ名」を
順不同に受け付け、いったんフラグに当てはまらない値が出るとそれ以降は
残り全部をサイズ/タイトル候補として扱う、というかなり複雑な位置非依存の
スキャン方式だった。ここでは`size`/`align`/`around`/`wrap`/`noicon`/
`nolink`/`noimg`/`zoom`/`title`をそれぞれ専用の引数にした。**書ける値・
組み合わせ（機能）は本家と同じ**。

## num_orderによる自由順序化（2026-08-23）

`src`は`num_order: 1`で1番目に固定し、`title`は`num_order: -1`で
「どの引数にも当てはまらなかった残り」を受け取る（本家の`join(',',
$_title)`と同じくカンマ連結）。それ以外（`size`/`align`/`around`/
`wrap`/`noicon`/`nolink`/`noimg`/`zoom`）は`num_order`を宣言しない
自由順序にした。これにより、名前付き引数を使わなくても**`src`より
後ろなら本家と同じ組み合わせを好きな順で書ける**ようになった
（旧来は宣言順＝呼び出し順が固定だったため、`title`だけ変えたくても
間の引数をすべて空カンマで埋める必要があった）。

`around`/`wrap`/`noicon`/`nolink`/`noimg`/`zoom`は`"flag": True`
（単語を書くだけで有効になる糖衣構文）にした。本家の「先頭一致する
フラグ名」ほど柔軟ではないが（完全一致のみ）、単語を書くだけで有効に
なる点は同じ。**位置を選ばず・かつ先頭一致の省略形まで許す**という
本家特有の融通そのものは、意図的に互換対象から外している
（プロジェクトの方針。引数名・呼び出し方の自由度は互換対象外）。

`size`はもともと独立した`"re": SIZE_PATTERN`（`args`の項目直下のキー）で
検証していたが、2026-08-24に`"candidate": [(SIZE_PATTERN, "re")]`
（`candidate`一覧に混ぜる`(パターン, "re")`タプル）へ移行した。
`CANDIDATE_CASE_SENSITIVE`マーカーとあわせて古い`re`単独キーはやがて
`_sys/wikilib/plugins.py`から削除される予定（`candidate`のタプル形が
両方の役割を代替するため。詳しくは`Tech/PluginCandidateReCleanup.md`）
だが、`_check_re`/`_check_candidate`の検証結果自体は同一のため、
挙動は変わっていない。

## 本家との違い（技術的な理由による簡略化）

- **`zoom`は実在の画像サイズを見た自動計算をしない。** 本家は
  `getimagesize()`で元の画像の実ピクセルサイズを取得し、指定サイズとの
  比率から縦横比を保つ値を計算する。このシステムには画像を読んで
  サイズを取るしくみ（Pillow等）が無く、追加するのはプラグイン1つの
  移植の範囲を超えるため、`zoom`は引数として受け付けるが出力には
  反映しない（指定サイズをそのままmax-width/max-heightとして使う。
  zoom無しと同じ）
- **`wrap`の枠は`<table>`ではなくCSSで組む。** 本家がtableで囲むのは、
  古いブラウザで`margin:auto`が効かない問題への回避策（コメントに
  Mozilla 1.x・Netscape 6・IE6の相性表がある）。現行ブラウザにこの
  問題は無いため、`<div>`＋CSSで同じ見た目にした

## 添付ファイルの実在確認・種別判定

画像かどうか・種別（PDF/文書/圧縮等）・ファイルサイズ・更新日時は
`wikilib.attach`（`attach_kind`・`ATTACH_IMAGE_EXTS`・`format_bytes`）を
使う。編集画面の「添付ファイル」タブと同じ分類になる。パス解決には
`wikilib.paths.resolve_link`（本文のリンクと共通）を使う。

添付ファイルが実在しない場合は本家に合わせてエラーにする
（`PluginArgumentError`。本家の「File not found」に相当）。

`src`には`"link": True`を宣言している。値がリンク元データベースに
記録される（`wikilib.links.plugin_arg_links`）。

実際に埋め込む`src`/`href`の値そのものは、`img`と同じく自分で
`/.attach/...`を組み立てず、`wikilib.render.rewrite_content_links`に
書き換えを任せる。

## 閲覧の権限（2026-09-25、Wiki設計者の指示）

添付ファイルは、**持ち主のページを閲覧できない閲覧者には、書かれた名前（か
`title`）に「閲覧できないファイル」の札を添えるだけにする**（リンク・大きさ・
更新日時・画像は出さない）。以前は権限を見ておらず、
読めないページの添付でも、ファイル名・大きさ・更新日時の札を出していた（開こうと
しても配信側で止まるが、札の情報は漏れていた。`attachls` の確認で見つかった）。

- 持ち主のページは、添付の配信 `attach.attach_viewable` と同じく、置き場所の
  subpath から `pagepath_of_subpath` で求める（`Tech/index/a.pdf` の持ち主は
  `Tech`）。判定は `context.privilege.check(持ち主)` が `-` かどうか
  （`attachls`・`include` と同じ判定器）。表示の可否と、リンクを開けるかどうかが一致する
- **実在の確認より先に見る。** 先に「見つかりません」を出すと、読めないページに
  そのファイルがあるかどうかが分かってしまうため。出す名前は、ページ本文に書かれた
  名前（`src` の最後の部分か `title`）だけ（閲覧者はそのページを読めているので、
  新しく漏れる情報は無い）。大きさ・更新日時・実在の有無は出さない
- `PluginArgumentError`（赤いエラー枠）にはしない。書き手の誤りではなく、見る人に
  よって結果が変わるだけなので、ふだんのファイルの札（`plugin-ref-file`）と同じ形で
  種別の札の代わりに「閲覧できないファイル」を出す
- 最初は中身を「閲覧する権限がありません: 名前」という案内に差し替える形で作ったが、
  設計者の指示（「閲覧権がない場合のアクセスでは『閲覧できないファイル』と併記すれば
  十分」）で、名前に札を添える形にした。どのファイルへの参照かが本文の流れのまま
  分かり、見た目も自然なので賛成。ただし併記する場合も、大きさ・更新日時は読めない
  ページから取り出す情報なので出さない（画像も展開しない）ことにした
- 外部URL（`keep`）は対象外。ページを指した場合（`page`）は従来どおり「見つかりません」
"""

import datetime
import os
from html import escape

from wikilib.attach import ATTACH_IMAGE_EXTS, attach_dir_for, attach_kind, format_bytes
from wikilib.auth import PAGE_NONE
from wikilib.paths import pagepath_of_subpath, resolve_link, resolve_page_ref
from wikilib.plugins import PluginArgumentError

SIZE_PATTERN = (
    r"[0-9]+x[0-9]+"          # WxH
    r"|[0-9]+x"                # Wx
    r"|x[0-9]+"                # xH
    r"|[0-9]+w"                # Ww
    r"|[0-9]+h"                # Wh
    r"|[0-9]+(?:\.[0-9]+)?%"   # N%
)


def _size_style(size):
    if not size:
        return ""
    if "x" in size and size[0].isdigit() and size[-1].isdigit():
        w, h = size.split("x", 1)
        return f"max-width:{w}px;max-height:{h}px;"
    if size.endswith("x"):
        return f"max-width:{size[:-1]}px;height:auto;"
    if size.startswith("x"):
        return f"width:auto;max-height:{size[1:]}px;"
    if size.endswith("w"):
        return f"max-width:{size[:-1]}px;height:auto;"
    if size.endswith("h"):
        return f"width:auto;max-height:{size[:-1]}px;"
    if size.endswith("%"):
        return f"max-width:{size};max-height:{size};"
    return ""


PLUGIN_INFO = {
    "help": "#ref(src,size,align,around,wrap,noicon,nolink,noimg,zoom,title)",
    "args": [
        {"name": "src", "num_order": 1, "link": True},
        {"name": "size", "default": None, "candidate": [(SIZE_PATTERN, "re")], "label": "大きさ"},
        {"name": "align", "default": "LEFT", "candidate": ["LEFT", "CENTER", "RIGHT"], "label": "寄せ"},
        {"name": "around", "flag": True, "default": False, "label": "回り込み"},
        {"name": "wrap", "flag": True, "default": False, "label": "枠"},
        {"name": "noicon", "flag": True, "default": False, "label": "アイコンなし"},
        {"name": "nolink", "flag": True, "default": False, "label": "リンクなし"},
        {"name": "noimg", "flag": True, "default": False, "label": "画像展開なし"},
        {"name": "zoom", "flag": True, "default": False, "label": "縦横比保持"},
        {"name": "title", "num_order": -1, "default": None},
    ],
}


DENIED = "denied"  # _resolve の1つ目: 持ち主のページを閲覧する権限が無い


def _resolve(src, context):
    """(実在するか, ファイル名, サイズ・更新日時の説明かNone) を返す。
    持ち主のページを閲覧できない添付なら1つ目が `DENIED`（技術資料「閲覧の権限」）。"""
    ref = resolve_page_ref(context.wiki_dir, context.page or "")
    kind, target = resolve_link(ref.subpath, src, context.wiki_dir)

    if kind == "keep":
        name = src.rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0] or src
        return True, name, None

    if kind == "attach":
        owner_subpath, _, name = target.rpartition("/")
        # 実在を確かめるより先に見る（読めないページの添付の有無を漏らさない）
        if context.privilege.check(pagepath_of_subpath(owner_subpath)) == PAGE_NONE:
            return DENIED, name, None
        directory = attach_dir_for(context.wiki_dir, owner_subpath)
        path = os.path.join(directory, name) if directory else None
        found = bool(path) and os.path.isfile(path)
        info = None
        if found:
            stat = os.stat(path)
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
            info = f"{format_bytes(stat.st_size)}・{mtime:%Y-%m-%d %H:%M} 更新"
        return found, name, info

    return False, src, None


def _build(resolved, context, is_block):
    src = resolved["src"]
    if not src:
        raise PluginArgumentError("ファイルを指定してください: #ref(src) / &ref(src);")
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")

    found, name, info = _resolve(src, context)
    if found == DENIED:
        # 書かれた名前（か title）に「閲覧できないファイル」の札を添えるだけ。大きさ・
        # 更新日時・画像は出さない（技術資料「閲覧の権限」）
        body = (
            f'<span class="plugin-ref-file plugin-ref-denied">'
            f'<span class="ref-name">{escape(resolved["title"] or name)}</span>'
            '<span class="ref-kind ref-kind-denied">閲覧できないファイル</span>'
            '</span>'
        )
        return f'<div class="plugin-ref">{body}</div>' if is_block else body
    if not found:
        raise PluginArgumentError(f"見つかりません: {src}")

    is_image = not resolved["noimg"] and os.path.splitext(name)[1].lower() in ATTACH_IMAGE_EXTS
    label = resolved["title"] or name
    h_src = escape(src, quote=True)
    style = _size_style(resolved["size"])

    if is_image:
        h_alt = escape(label, quote=True)
        style_attr = f' style="{escape(style, quote=True)}"' if style else ""
        css = "plugin-ref-image" + (" plugin-ref-block" if is_block else "")
        img = f'<img class="{css}" src="{h_src}" alt="{h_alt}"{style_attr}>'
        body = img if resolved["nolink"] else f'<a href="{h_src}" class="image-link">{img}</a>'
    else:
        kind, kind_label = attach_kind(name)
        icon = "" if resolved["noicon"] else (
            f'<span class="ref-kind ref-kind-{escape(kind, quote=True)}">{escape(kind_label)}</span>'
        )
        title_attr = f' title="{escape(info, quote=True)}"' if info else ""
        info_html = f'<span class="ref-info">{escape(info)}</span>' if info else ""
        css = "plugin-ref-file" + (" plugin-ref-block" if is_block else "")
        body = (
            f'<a href="{h_src}" class="{css}"{title_attr}>'
            f'<span class="ref-name">{escape(label)}</span>'
            f'{icon}'
            f'{info_html}'
            '</a>'
        )

    if not is_block:
        return body

    align = resolved["align"].lower()
    if resolved["around"]:
        pos_style = f"float:{'right' if align == 'right' else 'left'};"
    else:
        pos_style = f"text-align:{align};"

    if resolved["wrap"]:
        box_margin = "margin:0;" if resolved["around"] else (
            "margin:0 auto;" if align == "center" else f"margin-{align}:0;"
        )
        body = f'<div class="plugin-ref-box" style="{box_margin}">{body}</div>'

    return f'<div class="plugin-ref" style="{pos_style}">{body}</div>'


def _inline(resolved, body, context):
    return _build(resolved, context, is_block=False)


def _convert(resolved, body, context):
    return _build(resolved, context, is_block=True)
