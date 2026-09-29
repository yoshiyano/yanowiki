"""calendar_viewer — calendar・calendar2 で作った日ごとのページの中身を、まとめて表示する。

    #calendar_viewer(日記, this)          「日記」の今月のページ（今日まで）を新しい順に
    #calendar_viewer(日記, 2026-09)       2026年9月のページ
    #calendar_viewer(日記, 5)             新しいほうから5件
    #calendar_viewer(日記, 5*5)           新しいほうから数えて6件目から5件
    #calendar_viewer(予定, this, future)  今日以降のページを古い順に

 1. page … 日ごとのページを置いた場所のページ名。空なら、ページ名の頭に何も
       付けない日付のページ（calendar2 の `*`） (default: 頭に何も付けない)
 2. **range** … どのページを出すか
       this     今月
       yyyy-mm  その年月（`2026-09`）
       n        先頭から n 件
       x*n      先頭から数えて x 件目（0が先頭）から n 件
 3. mode … 出す範囲と並べる順 (default: past)
       past     今日と過去を、新しい順に（日記・記録向け）
       future   今日と未来を、古い順に（予定向け）
       view     過去から未来まで全部を、古い順に
 4. date_sep … 日付の区切り文字 (default: `-`。calendar2 のページ `2026-09-25`)
       calendar のページ（`20260925`）を出すときは `none` と書く

- 日ごとのページは `ページ名/2026-09-25` の形の名前のものだけが並びます
- ページごとに日付の見出し（`2026/9/25 (金)`）を付けます。見出しは、編集の権限が
  あればそのページの編集画面を開くボタン、無ければページへのリンクです
- 最後に、前後の月・前後の件へのリンクを出します
- 閲覧できないページは並びません
- 長い記事は7行ほどで畳まれ、「（省略）」を押すと続きが開きます（「（閉じる）」で戻せます）
- 同じページ名を基準にした calendar_viewer は、1つのページに4つまでです
"""

""" 技術資料
本家 `calendar_viewer.inc.php`（PukiWiki 1.5系）の移植。

## 2つ目の引数の読みかた（本家の順）

1. `[0-9]{4}<区切り>[0-9]{2}` を含む → その年月（31件まで）
2. `this` を含む（大文字小文字を問わない）→ 今月（31件まで）
3. 数字だけ → 先頭から n 件
4. `(-?数字)*(数字)` を含む → x 件目から n 件
5. それ以外 → エラー（本家「第2引数が変だよ」）

本家は 1・2 を**区切りの既定値 `-` のまま**判定していた（4つ目の引数を読む前に
判定するため）。区切りを変えると `this` が当たらなくなる不具合なので、ここでは
**指定された区切りで**判定する。

## 区切り文字を「無し」にする書きかた（`none`）

本家は4つ目を空（`#calendar_viewer(日記,this,past,)`）にすると区切り無し
（`calendar` の `20260925`）になった。wikiSystemでは空の引数は省略と同じに
扱われ、既定の `-` になってしまうので、`none` と書く形を足した。

## 並べるページ

`pagelist.walk` で、閲覧の権限を通したページだけを拾う。本家は閲覧できない
ページも並べて「閲覧制限がかかっているため参照はできません」と出したが、
`#ls`・`#recent` と同じく**並べない**（見えないページの存在を知らせない）。
件数・前後のリンクも、見えるページだけで数える。

日付の部分は `^([0-9]{2,4})<区切り>([0-9]{1,2})<区切り>([0-9]{1,2})$`（区切り無しなら
8桁）で、暦の上であり得る日付のものだけ。`past` は今日より後を、`future` は今日より
前を外す（本家と同じく**文字列で**比べる）。

## 本文の差し込み

`include` と同じ `_embedpage` で差し込む（表示を止めたページ・添付へのリンク・
資材の合流を共有する）。

**同じページを2つの calendar_viewer に出してよい**（本家と同じ。`include` のように
「差し込み済み」で止めると、今月の一覧と直近5件の一覧を並べたときに、重なった日が
片方から消える）。止めるのは、置いたページ自身を差し込むときだけ。入れ子の
無限ループ（AのページのviewerがBを出し、BのページのviewerがAを出す）は、本家の
`PLUGIN_CALENDAR_VIEWER_MAX_SHOW_COUNT`（同じページ名を基準にした呼び出しは4回まで）
で止める。本家は `static` 変数で1回の要求全体を数えていたので、ここでも数えを
**差し込みの記録（`_embedpage.state`。入れ子の描画をまたいで共有される）**に置く。
`PluginContext` に置くと、差し込み先を描く新しい `PluginContext` ごとに0から
数え直してしまい、ループが止まらない。

## 見出し

本家は `<h1><a href="?cmd=edit&page=…">2026/9/25 (金)</a></h1>`（`PKWK_READONLY` なら
閲覧のリンク）。ここでは編集の権限（`W`）があれば
`cmd=edit` をPOSTするボタン、無ければ閲覧のリンクにした（`_embedpage.title_html`
と同じ考えかた。文字は日付）。日付として読めないページ名はそのまま出す。

## 長い記事（Wiki設計者の指示、2026-09-27）

長い記事は、途中から「（省略）」に置き換え、押すと続きを開く（目安は7行ほど）。
**本文はサーバーで切らずに全部出し、ブラウザ側で高さを抑える**（`plugin/calendar_viewer.js`・
`calendar.css` の `.calendar_viewer-body.is-clamped`）。

- 行数は見た目のもので、画面の幅・文字の大きさで変わる。本文の生テキストを7行目で
  切ると、表・箇条書き・複数行のプラグインの途中で壊れるので、描いたHTMLは切らない
- 高さは `10lh`（本文の行の高さの10こぶん）。日ごとのページは先頭に見出しを置く
  ことが多く、見出しとその余白で3行ほど使うので、**見える本文が7行ほどになるように**
  足してある（見出しや画像が入ると「行」は目安になる）。先頭の要素の上余白は詰める。
  JavaScriptが中身の高さを測り、それを超えるときだけ抑えて、末尾をぼかし
  「（省略）」のボタンを置く。押すと抑えを外し、ボタンは「（閉じる）」になる。
  もう一度押すと元の高さに戻す（2026-09-27、Wiki設計者の指示）。閉じたときに
  記事の頭が画面の上に隠れていれば、そこまで戻す（縮んだ記事の下に取り残されないため）
- 抑えるための印（`is-clamped`）は JavaScript が付ける。**JavaScriptが無ければ全文**を
  出す（開けない省略にしない）。印刷でも全文
- 画像が後から読み込まれて高さが変わるので、ページの `load` のあとにも測り直す

## 前後のリンク

本家は `?plugin=calendar_viewer&mode=…&file=…&date_sep=…&date=…` で、一覧だけの
プラグインの画面を開いた。ここでは**このページ自身を同じ問い合わせ付きで開き
直す**（`_calendar.nav_url`・`nav_query`。理由は `_calendar.py`）。`past` では
左が新しい月（`<<2026-10`）、右が古い月（`2026-08>>`）。それ以外は逆。件数の
表示では `<<前の5件`・`次の5件>>`。
"""
import datetime
import importlib.util
import os
import re
from html import escape

from wikilib.auth import PAGE_WRITE
from wikilib.paths import full_pagepath, is_valid_pagepath
from wikilib.plugins import FREE_TEXT, PluginArgumentError

PLUGIN_INFO = {
    "help": "#calendar_viewer(page,range,mode,date_sep)",
    "args": [
        {"name": "page", "candidate": [FREE_TEXT], "default": "", "link": True},
        {"name": "range", "candidate": [FREE_TEXT], "label": "表示する範囲（2つ目の引数）"},
        {"name": "mode", "candidate": ["past", "view", "future"], "default": "past", "label": "モード（3つ目の引数）"},
        {"name": "date_sep", "candidate": [FREE_TEXT], "default": "-"},
    ],
}

MAX_SHOW_COUNT = 4      # 同じページ名を基準にした呼び出しの上限（本家と同じ）
MONTH_LIMIT = 31        # 年月を指定したときに読むページ数（本家と同じ）
RIGHT_TEXT = "次の{}件&gt;&gt;"
LEFT_TEXT = "&lt;&lt;前の{}件"


def _load(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
    spec = importlib.util.spec_from_file_location("wikiplugin_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_range(text, sep, today):
    """2つ目の引数を (年月, 読み飛ばす数, 1回に出す数, 読む数) にする。読めなければ None。"""
    ym_re = re.compile(r"\d{4}" + re.escape(sep) + r"\d{2}")
    m = ym_re.search(text)
    if m:
        return m.group(0), 0, 0, MONTH_LIMIT
    if re.search("this", text, re.I):
        return f"{today.year:04d}{sep}{today.month:02d}", 0, 0, MONTH_LIMIT
    if re.fullmatch(r"\d+", text):
        n = int(text)
        return "", 0, n, n
    m = re.search(r"(-?\d+)\*(\d+)", text)
    if m:
        base, pitch = int(m.group(1)), int(m.group(2))
        return "", base, pitch, base + pitch
    return None


def parse_date(text, sep):
    """日付の部分を date にする。日付でなければ None。"""
    if sep == "":
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text)
    else:
        s = re.escape(sep)
        m = re.fullmatch(r"(\d{2,4})" + s + r"(\d{1,2})" + s + r"(\d{1,2})", text)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _title_html(cal, context, page, sep):
    date = parse_date(page.rsplit("/", 1)[-1], sep)
    if date is None:
        label = escape(page)
    else:
        week = cal.WEEK_LABELS[(date.weekday() + 1) % 7]
        label = escape(f"{date.year}/{date.month}/{date.day} ({week})")
    url = escape(cal.page_url(context, page))
    if context.privilege.check(page) == PAGE_WRITE:
        return (f'<form class="calendar_viewer-edit" method="post" action="{url}">'
                '<input type="hidden" name="cmd" value="edit">'
                f'<button type="submit">{label}</button></form>')
    return f'<a href="{url}">{label}</a>'


def _convert(resolved, body, context):
    cal = _load("_calendar")
    cal.use_css(context)
    here = (context.page or "").strip("/")
    name = cal.strip_bracket(resolved.get("page") or "")
    pagename = full_pagepath(here, name).strip("/") if name else ""
    if name and not is_valid_pagepath(pagename):
        raise PluginArgumentError(f"ページ名が正しくありません: {name}")

    spec, mode = resolved["range"], (resolved.get("mode") or "past").lower()
    sep = resolved.get("date_sep")
    sep = "" if sep == "none" else ("-" if sep is None else sep)
    query = cal.nav_query(context, "calendar_viewer", pagename)
    if query is not None:
        spec = query.getunicode("date", "") or spec
        asked = (query.getunicode("mode", "") or "").lower()
        mode = asked if asked in ("past", "view", "future") else mode
        asked = query.getunicode("date_sep", None)
        if asked is not None:
            sep = "" if asked == "none" else asked

    now = cal.today()
    parsed = parse_range(spec, sep, now)
    if parsed is None:
        raise PluginArgumentError(
            f"2つ目の引数が正しくありません: {spec}（this・yyyy{sep}mm・件数・x*件数 のどれか）")
    page_ym, limit_base, limit_pitch, limit_page = parsed

    embed = _load("_embedpage")
    state = embed.state(context)
    # 数えは差し込みの記録（入れ子の描画をまたいで共有される）に置く。技術資料「本文の差し込み」
    counts = state.setdefault("calendar_viewer", {})
    counts[pagename] = counts.get(pagename, 0) + 1
    if counts[pagename] > MAX_SHOW_COUNT:
        raise PluginArgumentError(
            f"同じページ名（{pagename}）の calendar_viewer は{MAX_SHOW_COUNT}つまでです。")

    head = pagename + "/" if pagename else ""
    pattern = head + page_ym
    today_text = f"{now.year:04d}{sep}{now.month:02d}{sep}{now.day:02d}"
    pages = []
    for page in cal.readable_pages(context, pagename):
        if not page.startswith(pattern):
            continue
        date_text = page[len(head):]
        if parse_date(date_text, sep) is None:
            continue
        if (mode == "past" and date_text > today_text) or \
                (mode == "future" and date_text < today_text):
            continue
        pages.append(page)
    pages.sort(reverse=(mode == "past"))

    out = []
    for page in pages[max(limit_base, 0):limit_page]:
        out.append(f'<h1 class="calendar_viewer-title">{_title_html(cal, context, page, sep)}</h1>')
        if page == here:
            out.append(f'<div class="include-notice">このページ自身は差し込めません: {embed.read_link(page)}</div>')
            continue
        status, ref = embed.lookup(context, page)
        if status != "ok":
            continue
        state["included"].add(page)
        # 長い記事は、ブラウザ側で約7行に抑えて「（省略）」を出す（技術資料「長い記事」）
        out.append(f'<div class="calendar_viewer-body">\n{embed.render(context, page, ref, state)}</div>')

    out.append(_nav_html(cal, context, pagename, mode, sep, page_ym,
                         limit_base, limit_pitch, len(pages)))
    return "\n".join(out) + "\n"


def _nav_html(cal, context, pagename, mode, sep, page_ym, limit_base, limit_pitch, total):
    left = right = None   # (問い合わせの date, 文字)
    if page_ym:
        year, month = int(page_ym[:4]), int(page_ym[4 + len(sep):6 + len(sep)])
        ny, nm = cal.shift_month(year, month, 1)
        py, pm = cal.shift_month(year, month, -1)
        next_ym, prev_ym = f"{ny:04d}{sep}{nm:02d}", f"{py:04d}{sep}{pm:02d}"
        if mode == "past":
            left, right = (next_ym, f"&lt;&lt;{escape(next_ym)}"), (prev_ym, f"{escape(prev_ym)}&gt;&gt;")
        else:
            left, right = (prev_ym, f"&lt;&lt;{escape(prev_ym)}"), (next_ym, f"{escape(next_ym)}&gt;&gt;")
    else:
        if limit_base > 0:
            left = (f"{limit_base - limit_pitch}*{limit_pitch}", LEFT_TEXT.format(limit_pitch))
        if limit_base + limit_pitch < total:
            right = (f"{limit_base + limit_pitch}*{limit_pitch}", RIGHT_TEXT.format(limit_pitch))
    if left is None and right is None:
        return ""

    def link(item):
        if item is None:
            return ""
        href = cal.nav_url(context, plugin="calendar_viewer", mode=mode, file=pagename,
                           date_sep=sep if sep else "none", date=item[0])
        return f'<a href="{escape(href)}">{item[1]}</a>'

    return ('<div class="calendar_viewer">'
            f'<span class="calendar_viewer_left">{link(left)}</span>'
            f'<span class="calendar_viewer_right">{link(right)}</span>'
            '</div>')
