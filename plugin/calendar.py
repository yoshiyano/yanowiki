"""calendar — 1か月のカレンダーを表示し、日ごとのページ（`ページ名/YYYY/MM/YYYY-MM-DD`）へ案内する。

    #calendar                   今月。日ごとのページはこのページの下
    #calendar(日記)              日ごとのページを「日記」の下に置く
    #calendar(202609)            2026年9月
    #calendar(日記, 202609)      年月とページ名は、どちらの順で書いてもよい

 1. date … 表示する年月（6桁の `yyyymm`） (default: 今月)
 2. page … 日ごとのページを置く場所のページ名 (default: このページ)

日付の数字は、その日のページ（`日記/2026/09/2026-09-25` のように、年・月のフォルダの中）が
あるときだけリンクになります。ページを作りながら使うときは
[calendar_edit](/Syntax/Plugin/calendar_edit) を使います。

以前の形（`日記/20260925` のように、区切りの無い8桁を直下に置く）のページがあれば、
編集の権限がある人が表示したときに、新しい形へまとめて移します（移している間は
「ファイル構成を更新中」と進み具合が出ます）。
"""

""" 技術資料
本家 `calendar.inc.php`（PukiWiki 1.5系）の移植。`calendar_edit`・`calendar_read`
は本家と同じく、このファイルの `render` をモード（`edit`/`read`）を変えて呼ぶ
（本家は `global $command` を書き換えてから `plugin_calendar_convert` を呼んでいた）。

## 引数（本家の位置の自由を、宣言で表す）

本家は引数が1つなら「6桁の数字なら年月、そうでなければページ名」、2つなら
「6桁の数字のほうが年月、もう一方がページ名」と読んだ。`date` を自由順序の
項目にして `candidate` を6桁の数字にし、残りを `page`（`num_order: -1`）が
受け取る形で同じことになる（`page=…`・`date=…` の名前付きでも書ける）。
本家は2つとも年月でない場合は両方を黙って捨てたが、ここではエラーにする
（書き間違いを黙って流さない。受け皿の `page` には `,` で連結されて届くので
それで見分ける）。

## 表題の `(read)`

本家は表題に `2026.9 (read)` のように、そのときのコマンドを添えた。通常の
閲覧では `read`、`calendar_edit` では `edit` になる。そのまま残した。

## 日付のリンク

- `read`（既定）: その日のページが**閲覧できるときだけ**リンクにする。本家は
  「在るとき」だったが、閲覧できないページは無いページと同じ扱いにする
  （`calendar_.readable_pages`。`#ls` と同じく、見えないページの存在を知らせない）
- `edit`: すべての日を押せるようにする。本家は `?cmd=edit` へのリンクだったが、
  wikiSystemの編集画面はPOSTでしか開けない。**まだ無い日は、編集の権限があれば
  `cmd=edit` をPOSTするボタン**（`calendar_.new_page_button`。2026-09-27、Wiki設計者の
  指示）で新規編集の画面を直接開く。ある日と、編集の権限が無い人のまだ無い日は、
  ページのURLへのリンク（本家どおり全部の日を押せる形を残す）

## 日ごとのページの名前（Wiki設計者の指示、2026-10-27）

本家は `基準/20260925`（区切り無し）だった。いまは `calendar2` と同じ
`基準/2026/09/2026-09-25` にそろえ、古い形は組み替える（`calendar_.py`
「日ごとのページは `年/月/` のフォルダに置く」）。

## 出力

表の組み立ては本家どおり（日曜始まり、前後の空きは `style_td_blank`）。
`width="200"` などの属性はやめて `calendar.css` に移した。
"""
import datetime
import importlib.util
import os
from html import escape

from bottle import HTTPResponse

from wikilib.paths import full_pagepath, is_valid_pagepath
from wikilib.plugins import PluginArgumentError

PLUGIN_INFO = {
    "help": "#calendar(date,page)",
    "args": [
        {"name": "date", "candidate": [(r"\d{6}", "re")], "default": "", "label": "年月（6桁の yyyymm）"},
        {"name": "page", "num_order": -1, "link": True},
    ],
}


def _load_common():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendar_.py")
    spec = importlib.util.spec_from_file_location("wikiplugin_calendar_", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(resolved, context, cmd):
    """`calendar`・`calendar_edit`・`calendar_read` の本体。`cmd` は `read` か `edit`。"""
    cal = _load_common()
    cal.use_css(context)
    here = (context.page or "").strip("/")
    name = cal.strip_bracket(resolved.get("page") or "")
    if "," in name:
        # 年月でない引数が2つ以上（受け皿の page に連結されて届く）。技術資料「引数」
        raise PluginArgumentError(f"年月（6桁）とページ名を1つずつ書いてください: {name}")
    page = full_pagepath(here, name).strip("/") if name else here
    if name and not is_valid_pagepath(page):
        raise PluginArgumentError(f"ページ名が正しくありません: {name}")

    now = cal.today()
    if resolved.get("date"):
        year, month = cal.parse_yyyymm(resolved["date"])
    else:
        year, month = now.year, now.month
    other_month = (year, month) != (now.year, now.month)

    migrating = cal.migration_html(context, "calendar", page)
    if migrating is not None:
        return migrating
    prefix = page + "/" if page else ""
    days = cal.day_pages(context, page)

    out = [
        '<table class="calendar style_calendar">',
        ' <thead>',
        '  <tr><th class="style_td_caltop" colspan="7">',
        f'   <strong>{year}.{month} ({escape(cmd)})</strong><br>',
        f'   [<a href="{escape(cal.page_url(context, page))}">{escape(page)}</a>]',
        '  </th></tr>',
        '  <tr>' + "".join(f'<th class="style_td_week">{w}</th>' for w in cal.WEEK_LABELS)
        + '</tr>',
        ' </thead>',
        ' <tbody>',
    ]
    for row in cal.weeks(year, month):
        cells = []
        for wday, day in enumerate(row):
            if day is None:
                cells.append('<td class="style_td_blank"></td>')
                continue
            day_page = days.get(datetime.date(year, month, day))
            exists = day_page is not None
            if not exists:
                day_page = cal.day_page_name(prefix, year, month, day)
            label = f"<strong>{day}</strong>"
            if cmd == "edit" and not exists and cal.can_write(context, day_page):
                # まだ無い日は、新規編集の画面を直接開く（calendar_.py「まだ無い日は」）
                label = cal.new_page_button(context, day_page, label)
            elif cmd == "edit" or exists:
                label = (f'<a href="{escape(cal.page_url(context, day_page))}"'
                         f' title="{escape(day_page)}">{label}</a>')
            klass = cal.day_class(year, month, day, wday, now, other_month)
            cells.append(f'<td class="{klass}">{label}</td>')
        out.append("  <tr>" + "".join(cells) + "</tr>")
    out += [" </tbody>", "</table>"]
    return "\n".join(out) + "\n"


def _convert(resolved, body, context):
    return render(resolved, context, "read")


def _action(context):
    """ファイル構成の組み替えの開始と進み具合（`calendar_.migration_action`）。"""
    handled = _load_common().migration_action(context)
    if handled is None:
        return HTTPResponse(status=404)
    return handled
