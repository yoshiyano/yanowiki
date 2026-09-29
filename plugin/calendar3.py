"""calendar3 — 予定表のページに書いた予定を、月のカレンダーに並べて表示する。

    #calendar3                        「予定表」のページの予定を、今月で
    #calendar3(schedule2026)          「schedule2026」のページの予定を
    #calendar3(schedule2026, 202611)  2026年11月で

 1. page … 予定を書いたページ (default: 予定表)
 2. date … 表示する年月（6桁の `yyyymm`） (default: 今月)

`<<`・`>>` で前後の月へ移れます（ページ全体は読み込み直さず、カレンダーだけが
入れ替わります）。

## 予定の書きかた（予定表のページ）

次の3つの書きかたを、同じページの中で混ぜて使えます。行の頭の `- ` と `-- ` は
半角で、そのあとに空白（スペースかタブ）を1つ以上入れます。

    - 5/22 原稿締め切り            1日だけの予定
    - 7/11-12 オープンキャンパス    同じ月の中の期間（11日から12日）
    - 4                            月だけの行。このあとの `--` の行はこの月の予定
    -- 13 prog1-1                  その月の13日
    -- 20-21 合宿                   その月の20日から21日

- **年は、予定表のページ名の末尾の4桁の数字**です（`schedule2026` なら2026年）。
  末尾が数字でなければ今年です
- 月に13以上を書くと翌年です（`- 14/25 模擬講義` は翌年の2月25日）
- 期間は、月末を越えて翌月へ続けられます（`- 1/30-33` は1月30日〜2月2日。60日目まで）
- 予定の文字には、その予定表のページと同じ記法（太字・色・リンクなど）が使えます
- `::` のあとに書いた文字は、マウスを重ねたときに出る説明（ツールチップ）になります。
  説明の中の `\\n` は改行です

      - 6/6 学科別懇談会::3年次担当\\n竹内・矢野

予定表のページを閲覧できない人には、予定は表示されません。
"""

""" 技術資料
Wiki設計者の手元にあった独自プラグイン `calendar3.inc.php`（`~/pukiwiki/.wkcommon/plugin/`、
`$Id: calendar3.inc.php,v 1.34 2026/05/13 全形式共存修正版`）の移植。同じ名前で
中身の違う版がほかに2つある（`AdvCal/plugin/` のものは `calendar2` の複製、
`mypkwk/obs/` のものは古い版）。いちばん新しい `.wkcommon` の版を正とした。
本家PukiWiki公式のプラグインではない。

## 予定の読みかた（本家のまま）

予定表のページの**生テキストを1行ずつ**、次の順で見る（本家の正規表現そのまま）。

    ^- (\\d{1,2})/(\\d{1,2})(?:-(\\d{1,2}))?\\s*(.*)   1行形式
    ^- (\\d{1,2})                                   ツリーの月の行（以降の -- の月・年を決める）
    ^-- (\\d{1,2})(?:-(\\d{1,2}))?\\s*(.*)             ツリーの日の行

- 年: ページ名の末尾4桁（`(\\d{4})$`）。無ければ今年
- 月: `m` が13以上なら `年 + (m-1)//12`・`(m-1)%12+1`
- 期間: 開始日から `min(終了日, 60)` までを1日ずつ、`mktime` と同じく月末を越えて
  数える。表示中の月に入る日にだけ置く
- 内容が空の行は置かない
- `::` で「表示」と「ツールチップ」に分け、ツールチップの `\\n`（2文字）を改行にする。
  ツールチップは `title` 属性へエスケープして入れる

表示の部分は、本家が `convert_html()` で描いてから外側の `<p>` を外していた。
ここでは**予定表のページと同じ記法**で描き（`render_source`。予定表のページを
描いているのと同じ `PluginContext` なので、リンクや添付の裸の名前は予定表の
ページを基準に解ける）、外側の `<p>` を1つだけ外す。使われたプラグインの資材は
呼び出し元へ合流させる（`_embedpage.render` と同じ）。

## 閲覧の権限

予定表のページを閲覧できない人には、予定を1つも出さず、その旨を表題に添える
（本家には権限の概念が無かった）。本文は `published_ref`（公開されたもの）から読む。

## 前後の月（本家は Ajax）

本家は `load_calendar3(id, page, date)` で `?plugin=calendar3&action=load&…` を
`XMLHttpRequest` で取りに行き、カレンダーの枠の中身だけを差し替えた。ここでは
`plugin/calendar3.js` が同じことをする（`/.plugin/calendar3?file=…&date=…&page=…`
を取りに行く。`_action` がカレンダーの表だけを返す）。

リンクの `href` は、他のカレンダーと同じく**このページを問い合わせ付きで開き直す
URL**にしてある（`_calendar.nav_url`）。JavaScriptが動かない環境でも前後の月へ
移れる。`page` は `href` を組み立て直すための、カレンダーを置いたページ名。

## 出力

本家の `height="80" width="100"`・`style="font-size:80%"` は `calendar.css`
（`.calendar3`）へ移した。表題のクラスは本家の `style_td_caltop2` のまま。
"""
import importlib.util
import os
import re
from html import escape

from bottle import request

from wikilib.auth import PAGE_NONE
from wikilib.pagedb import published_ref
from wikilib.paths import PLUGIN_URLPATH, farm_plugin_dir, full_pagepath, is_valid_pagepath
from wikilib.plugins import FREE_TEXT, PluginArgumentError, PluginContext, build_markdown_renderer
from wikilib.render import render_source, rewrite_content_links

PLUGIN_INFO = {
    "help": "#calendar3(page,date)",
    "args": [
        {"name": "page", "candidate": [FREE_TEXT], "default": "予定表", "link": True},
        {"name": "date", "candidate": [(r"\d{6}", "re")], "default": "", "label": "年月（6桁の yyyymm）"},
    ],
}

DEFAULT_PAGE = "予定表"
MAX_DAY = 60   # 期間の終わりとして数える日の上限（本家の min($day_to, 60)）

_ONE_LINE_RE = re.compile(r"^- (\d{1,2})/(\d{1,2})(?:-(\d{1,2}))?\s*(.*)")
_TREE_MONTH_RE = re.compile(r"^- (\d{1,2})")
_TREE_DAY_RE = re.compile(r"^-- (\d{1,2})(?:-(\d{1,2}))?\s*(.*)")
_YEAR_RE = re.compile(r"(\d{4})$")
_OUTER_P_RE = re.compile(r"^\s*<p>(.*)</p>\s*$", re.S)


def _load_common():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_calendar.py")
    spec = importlib.util.spec_from_file_location("wikiplugin__calendar", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_schedule(source, base_year):
    """予定表の生テキストを [(年, 月, 開始日, 終了日, 内容), …] にする（本家の読みかた）。"""
    cal = _load_common()
    items = []
    tree_year, tree_month = base_year, 0
    for line in source.splitlines():
        line = line.rstrip("\r")
        m = _ONE_LINE_RE.match(line)
        if m:
            year, month = cal.shift_month(base_year, 1, int(m.group(1)) - 1)
            start = int(m.group(2))
            end = int(m.group(3)) if m.group(3) else start
            content = m.group(4)
        else:
            m = _TREE_MONTH_RE.match(line)
            if m:
                tree_year, tree_month = cal.shift_month(base_year, 1, int(m.group(1)) - 1)
                continue
            m = _TREE_DAY_RE.match(line)
            if not m:
                continue
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else start
            content = m.group(3)
            year, month = tree_year, tree_month
        if start > 0 and month > 0 and content != "":
            items.append((year, month, start, end, content))
    return items


def _item_html(engine, sub, ref, content, base_url, wiki_dir):
    display, tooltip = content, ""
    if "::" in content:
        display, tooltip = content.split("::", 1)
        tooltip = tooltip.replace("\\n", "\n")
    html, _, _ = render_source(engine, display, ref.ext, False, sub)
    html = rewrite_content_links(html, base_url, ref.subpath, wiki_dir).strip()
    m = _OUTER_P_RE.match(html)
    if m and "<p>" not in m.group(1):
        html = m.group(1)
    if tooltip:
        html = f'<span title="{escape(tooltip, quote=True)}">{html}</span>'
    return html


def _schedules(context, data_page, ref, year, month):
    """表示する月の {日: [HTML, …]}。"""
    import datetime

    m = _YEAR_RE.search(data_page)
    base_year = int(m.group(1)) if m else datetime.date.today().year
    sub = PluginContext(config=context.config, farm=context.farm, wiki_dir=context.wiki_dir,
                        page=data_page, base_url=context.base_url, ext=ref.ext)
    engine = build_markdown_renderer(context.config, farm_plugin_dir(context.wiki_dir), sub)
    days = {}
    for item_year, item_month, start, end, content in parse_schedule(ref.body or "", base_year):
        first = datetime.date(item_year, item_month, 1)
        html = None
        for d in range(start, min(end, MAX_DAY) + 1):
            target = first + datetime.timedelta(days=d - 1)
            if (target.year, target.month) != (year, month):
                continue
            if html is None:
                html = _item_html(engine, sub, ref, content, context.base_url, context.wiki_dir)
            days.setdefault(target.day, []).append(html)
    context.used_plugins |= sub.used_plugins
    return days


def render_table(context, data_page, year, month):
    """カレンダーの表（`<table>`）。`_convert` と `_action` の両方が使う。"""
    cal = _load_common()
    now = cal.today()
    ref = published_ref(context.wiki_dir, data_page)
    notice = ""
    days = {}
    if ref is not None and ref.privilege == PAGE_NONE:
        notice = "<br>（予定表を閲覧する権限がありません）"
    elif ref is not None and ref.exists:
        days = _schedules(context, data_page, ref, year, month)

    def nav(y, m):
        date = f"{y:04d}{m:02d}"
        href = cal.nav_url(context, plugin="calendar3", file=data_page, date=date)
        return (f'<a href="{escape(href)}" data-calendar3-file="{escape(data_page)}"'
                f' data-calendar3-date="{date}">')

    prev_y, prev_m = cal.shift_month(year, month, -1)
    next_y, next_m = cal.shift_month(year, month, 1)
    top = (f'{nav(prev_y, prev_m)}&lt;&lt;</a> <strong>{year}.{month}</strong>'
           f' {nav(next_y, next_m)}&gt;&gt;</a>'
           f'<br>[<a href="{escape(cal.page_url(context, data_page))}">{escape(data_page)}</a>]'
           f'{notice}')
    out = [
        '<table class="calendar calendar3 style_calendar">',
        ' <thead>',
        f'  <tr><th class="style_td_caltop2" colspan="7">{top}</th></tr>',
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
            klass = cal.day_class(year, month, day, wday, now)
            items = "".join(f"・{html}<br>" for html in days.get(day, []))
            cells.append(f'<td class="{klass}"><strong>{day}</strong>'
                         f'<div class="calendar3-items">{items}</div></td>')
        out.append("  <tr>" + "".join(cells) + "</tr>")
    out += [" </tbody>", "</table>"]
    return "\n".join(out) + "\n"


def _data_page(context, name):
    here = (context.page or "").strip("/")
    name = _load_common().strip_bracket(name)
    if not name or name == "off":
        # 本家: 1つ目が off なら既定の予定表
        name = DEFAULT_PAGE
    page = full_pagepath(here, name).strip("/")
    if not is_valid_pagepath(page):
        raise PluginArgumentError(f"ページ名が正しくありません: {name}")
    return page


def _year_month(cal, date):
    if date and len(date) == 6 and date.isdigit():
        return cal.parse_yyyymm(date)
    now = cal.today()
    return now.year, now.month


def _convert(resolved, body, context):
    cal = _load_common()
    cal.use_css(context)
    data_page = _data_page(context, resolved.get("page") or "")
    date = resolved.get("date") or ""
    query = cal.nav_query(context, "calendar3", data_page)
    if query is not None:
        date = query.getunicode("date", "") or date
    year, month = _year_month(cal, date)
    host = escape(context.page or "", quote=True)
    api = escape(f"{context.base_url}/{PLUGIN_URLPATH}/calendar3", quote=True)
    return (f'<div class="calendar3-frame" data-calendar3-page="{host}"'
            f' data-calendar3-api="{api}">\n'
            f'{render_table(context, data_page, year, month)}</div>\n')


def _action(context):
    """`/.plugin/calendar3?file=<予定表>&date=<yyyymm>&page=<置いたページ>` で、表だけを返す。"""
    cal = _load_common()
    try:
        data_page = _data_page(context, request.query.getunicode("file", "") or "")
    except PluginArgumentError as exc:
        return f'<p class="calendar3-error">{escape(str(exc))}</p>'
    page = (request.query.getunicode("page", "") or "").strip("/")
    if page and is_valid_pagepath(page):
        context.page = page   # 前後の月のリンク（href）を、置いたページのURLで組むため
    year, month = _year_month(cal, request.query.getunicode("date", "") or "")
    return render_table(context, data_page, year, month)
