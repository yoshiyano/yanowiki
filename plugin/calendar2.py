"""calendar2 — 前後の月へ移れるカレンダーと、今日のページの中身を並べて表示する。

    #calendar2                   今月。日ごとのページはこのページの下（`このページ/2026-09-25`）
    #calendar2(日記)              日ごとのページを「日記」の下に置く
    #calendar2(*)                 日ごとのページを、ページ名の頭に何も付けずに置く（`2026-09-25`）
    #calendar2(日記, 202609, off)  2026年9月。今日のページの中身は出さない

 1. page … 日ごとのページを置く場所のページ名。`*` なら頭に何も付けない (default: このページ)
 2. date … 表示する年月（6桁の `yyyymm`） (default: 今月)
 3. off  … これを書くと、カレンダーの右に今日のページの中身を出さない
       (default: 出す)

引数はどの順で書いてもかまいません。

- 日ごとのページの名前は `日記/2026-09-25` の形です
- ページがある日は、日付がそのページへのリンクになります。まだ無い日は、
  そのページを作る画面へのリンクになります（編集の権限がある人だけ）
- `<<`・`>>` で前後の月へ移れます
- 今日のページがあれば、カレンダーの右にその中身を出します。無ければ
  「〜は空です。」と、そのページへのリンクを出します。別の月を表示しているときは、
  その月の1日のページが対象です（本家と同じ）
"""

""" 技術資料
本家 `calendar2.inc.php`（PukiWiki 1.5系）の移植。

## 前後の月へのリンク（Ajax。Wiki設計者の指示、2026-09-27）

本家は `?plugin=calendar2&file=<基準>&date=<yyyymm>` で、カレンダーだけを載せた
プラグインの画面を開いた。ここでは `calendar3` と同じく、**ページを読み込み直さず
枠（`.calendar2-frame`）の中身だけを差し替える**。`plugin/calendar2.js` が
`<<`・`>>` の `data-calendar2-date` を読み、`_action`（`/.plugin/calendar2?file=…&date=…
&page=…&off=…`）に枠の中身（カレンダーと今日のページの中身）を問い合わせる。
`page` は置いたページ（前後のリンクの `href` と、今日のページが置いたページ自身か
の判定に使う）、`off` は今日のページを出すか。

リンクの `href` は、はじめは**このページを問い合わせ付きで開き直すURL**だった
（`_calendar.nav_url`・`nav_query`）。JavaScriptが動かない環境のために、それを
そのまま残している。`file` は基準のページ名で、`*` のときは `*`（本家は空文字列
だった。本家のURLとの行き来は無いので、読みやすさを取った）。

差し替えた中身に、そのページがまだ読み込んでいないプラグインの資材（今日のページの
中の `#katex` など）が要る場合は、その資材は読み込まれない（`calendar3` と同じ制約）。

## まだ無い日のリンク

本家は `?cmd=edit&page=…&refer=…` へのリンクで、`PKWK_READONLY` なら素の数字に
した。wikiSystemの編集画面はPOSTでしか開けないので、**`cmd=edit` をPOSTするボタン**
（`_calendar.new_page_button`。2026-09-27、Wiki設計者の指示。それまではページのURLへの
リンクで、「このページを作る」を1回経由していた）にして、新規編集の画面を直接開く。
素の数字にするのは、閲覧者にそのページの編集の権限が無いとき（本家の
`PKWK_READONLY` にあたる）。

閲覧できない日のページは**無いページと同じ扱い**（`_calendar.readable_pages`。
`#ls` と同じく、見えないページの存在を知らせない）。

## 今日のページの中身

`include` と同じ `_embedpage` で差し込む（閲覧の権限・表示を止めたページ・
差し込み済みのページの記録を共有する。カレンダーを置いたページ自身が今日の
ページのときの無限ループもここで止まる）。本家は差し込んだ本文の後ろに
`[この日記を編集]`（`?cmd=edit` へのリンク）を付けた。ここでは編集の権限が
ある人にだけ、`cmd=edit` をPOSTするボタンで出す。

### 今日のページが無いとき（Wiki設計者の指示、2026-09-27）

本家は「〜は空です。」の「〜」を `make_pagelink`（無いページなら編集へのリンク）に
した。ここでは、編集の権限（`W`）があれば、そのページへ
`cmd=edit` をPOSTするボタン（リンクの見た目。`calendar.css` の `.calendar2-new`）にして、
**新規編集の画面を直接開く**。編集画面はPOSTでしか開けないので、GETのリンクでは
「このページはまだありません → このページを作る」を1回経由することになるため。
権限が無ければ、ページ名を文字だけで出す（開いても作れないので案内しない）。
フォームは段落（`<p>`）の中に置けないので、全体を `<div class="calendar2-empty">` にした。

本家は、今月以外を表示しているときは「今日」を**その月の1日**として計算し、
その日のページを差し込んだ（`$now_day = 1`）。見た目に分かりにくいが、書き手から
見える挙動なのでそのまま残した。

## 出力

本家の外枠の `<table>`（カレンダーと中身を横に並べる）は `div` のflexにした
（`calendar.css` の `.calendar2`。狭い画面では縦に積む）。
"""
import importlib.util
import os
from html import escape

from bottle import request

from wikilib.paths import PLUGIN_URLPATH, full_pagepath, is_valid_pagepath
from wikilib.plugins import PluginArgumentError

PLUGIN_INFO = {
    "help": "#calendar2(page,date,off)",
    "args": [
        {"name": "date", "candidate": [(r"\d{6}", "re")], "default": "", "label": "年月（6桁の yyyymm）"},
        {"name": "off", "flag": True, "default": False},
        {"name": "page", "num_order": -1, "link": True},
    ],
}

EDIT_LABEL = "[この日記を編集]"
EMPTY_MESSAGE = "{}は空です。"


def _load(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
    spec = importlib.util.spec_from_file_location("wikiplugin_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _day_link(cal, context, page, day, readable):
    if page in readable:
        return (f'<a href="{escape(cal.page_url(context, page))}" title="{escape(page)}">'
                f'<strong>{day}</strong></a>')
    if cal.can_write(context, page):
        # まだ無い日は、新規編集の画面を直接開く（_calendar.py「まだ無い日は」）
        return cal.new_page_button(context, page, str(day), "small")
    return f'<span class="small">{day}</span>'


def _today_html(cal, context, page):
    """今日（別の月ならその1日）のページの中身。"""
    embed = _load("_embedpage")
    state = embed.state(context)
    link = f'<a href="{escape(cal.page_url(context, page))}">{escape(page)}</a>'
    if page in state["included"]:
        return f'<div class="include-notice">既に差し込み済みのページです: {link}</div>'
    status, ref = embed.lookup(context, page)
    if status != "ok":
        # 閲覧できないページも「空」と同じに出す（存在を知らせない）。ページ名は、
        # 編集の権限があればそのページの新規編集画面を直接開くボタン（技術資料
        # 「今日のページが無いとき」）、無ければ文字だけ
        if cal.can_write(context, page):
            name = cal.new_page_button(context, page, escape(page), "calendar2-new")
        else:
            name = escape(page)
        return f'<div class="calendar2-empty">{EMPTY_MESSAGE.format(name)}</div>'
    state["included"].add(page)
    html = embed.render(context, page, ref, state)
    if cal.can_write(context, page):
        html += (
            f'<hr><form class="calendar2-edit" method="post"'
            f' action="{escape(cal.page_url(context, page))}">'
            '<input type="hidden" name="cmd" value="edit">'
            f'<button type="submit" class="small">{EDIT_LABEL}</button></form>'
        )
    return html


def _base_of(cal, context, name):
    """書かれたページ名から (基準のページ, 日ごとのページの頭, 問い合わせの file) を決める。"""
    if "," in name:
        # 年月・off でない引数が2つ以上（受け皿の page に連結されて届く）
        raise PluginArgumentError(f"ページ名は1つだけ書いてください: {name}")
    if name == "*":
        return "", "", "*"
    here = (context.page or "").strip("/")
    base = full_pagepath(here, name).strip("/") if name else here
    if name and not is_valid_pagepath(base):
        raise PluginArgumentError(f"ページ名が正しくありません: {name}")
    return base, (base + "/" if base else ""), base


def render_inner(cal, context, base, prefix, file, year, month, off):
    """枠（`.calendar2-frame`）の中身。`_convert` と `_action` の両方が使う。"""
    now = cal.today()
    other_month = (year, month) != (now.year, now.month)
    # 本家: 別の月なら「今日」はその月の1日
    focus_day = 1 if other_month else now.day

    readable = cal.readable_pages(context, base)

    def nav(y, m, text):
        date = f"{y:04d}{m:02d}"
        href = cal.nav_url(context, plugin="calendar2", file=file, date=date)
        return f'<a href="{escape(href)}" data-calendar2-date="{date}">{text}</a>'

    prev_y, prev_m = cal.shift_month(year, month, -1)
    next_y, next_m = cal.shift_month(year, month, 1)
    top = (f'{nav(prev_y, prev_m, "&lt;&lt;")} <strong>{year}.{month}</strong>'
           f' {nav(next_y, next_m, "&gt;&gt;")}')
    if prefix:
        top += f'<br>[<a href="{escape(cal.page_url(context, base))}">{escape(base)}</a>]'
    out = [
        '<table class="calendar style_calendar">',
        ' <thead>',
        f'  <tr><th class="style_td_caltop" colspan="7">{top}</th></tr>',
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
            page = f"{prefix}{year:04d}-{month:02d}-{day:02d}"
            klass = cal.day_class(year, month, day, wday, now, other_month)
            cells.append(f'<td class="{klass}">{_day_link(cal, context, page, day, readable)}</td>')
        out.append("  <tr>" + "".join(cells) + "</tr>")
    out += [" </tbody>", "</table>"]
    table = "\n".join(out)

    if off:
        return table + "\n"
    today_page = f"{prefix}{year:04d}-{month:02d}-{focus_day:02d}"
    return (
        '<div class="calendar2">\n'
        f'<div class="calendar2-month">\n{table}\n</div>\n'
        f'<div class="calendar2-today">\n{_today_html(cal, context, today_page)}\n</div>\n'
        "</div>\n"
    )


def _year_month(cal, date):
    if len(date) == 6 and date.isdigit():
        return cal.parse_yyyymm(date)
    now = cal.today()
    return now.year, now.month


def _convert(resolved, body, context):
    cal = _load("_calendar")
    cal.use_css(context)
    base, prefix, file = _base_of(cal, context, cal.strip_bracket(resolved.get("page") or ""))
    date = resolved.get("date") or ""
    query = cal.nav_query(context, "calendar2", file)
    asked = (query.getunicode("date", "") or "") if query is not None else ""
    if len(asked) == 6 and asked.isdigit():
        date = asked
    year, month = _year_month(cal, date)
    off = bool(resolved.get("off"))
    api = escape(f"{context.base_url}/{PLUGIN_URLPATH}/calendar2", quote=True)
    return (f'<div class="calendar2-frame" data-calendar2-api="{api}"'
            f' data-calendar2-page="{escape(context.page or "", quote=True)}"'
            f' data-calendar2-file="{escape(file, quote=True)}"'
            f' data-calendar2-off="{"1" if off else "0"}">\n'
            f'{render_inner(cal, context, base, prefix, file, year, month, off)}</div>\n')


def _action(context):
    """`/.plugin/calendar2?file=<基準のページ|*>&date=<yyyymm>&page=<置いたページ>&off=<0|1>`
    で、枠の中身（カレンダーと今日のページの中身）だけを返す（`calendar2.js`）。"""
    cal = _load("_calendar")
    file = (request.query.getunicode("file", "") or "").strip("/")
    page = (request.query.getunicode("page", "") or "").strip("/")
    if page and is_valid_pagepath(page):
        context.page = page   # 前後のリンク（href）と、今日のページの差し込み済みの判定のため
    if file == "*":
        base, prefix = "", ""
    elif file and is_valid_pagepath(file):
        base, prefix = file, file + "/"
    else:
        return '<p class="calendar2-error">基準のページが正しくありません。</p>'
    year, month = _year_month(cal, request.query.getunicode("date", "") or "")
    off = request.query.get("off", "") == "1"
    return render_inner(cal, context, base, prefix, file, year, month, off)
