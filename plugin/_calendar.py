"""カレンダー系プラグイン（`calendar`・`calendar_edit`・`calendar_read`・`calendar2`・
`calendar3`・`calendar_viewer`）が共有する処理。

`_` で始まるのでプラグインとしては読み込まれない。使う側は自分の `__file__` の
隣を `importlib.util.spec_from_file_location` で呼び出しのたびに読み込む
（`_embedpage.py` と同じ。`sys.modules` に置かないのは、置くとこのファイルを
直してもサーバーを再起動するまで反映されないため）。

    today()                        今日（サーバーの時計）
    parse_yyyymm(text)             "202609" → (2026, 9)。月のはみ出しは年へ繰り上げる
    shift_month(y, m, n)           n か月ずらした (年, 月)
    weeks(y, m)                    月の表。[[日 or None ×7], …]（日曜始まり）
    day_class(y, m, d, wday, today, other_month)   本家と同じセルのクラス名
    readable_pages(context, under) 閲覧できるページのページパスの集合
    page_url(context, page)        ページのURL
    nav_url(context, **query)      いま描いているページに問い合わせを付けたURL
    nav_query(context, name, file) `?plugin=<name>&file=<file>` で開かれていれば、その問い合わせ
    use_css(context)               `calendar.css` を読み込ませる
    can_write(context, page)       そのページを編集できるか（編集の入口を出す設定も見る）
    new_page_button(context, page, label)   まだ無いページの新規編集を直接開くボタン

## 見た目は `calendar.css` に1つ

表のクラス名は本家のまま（`style_calendar`・`style_td_caltop`・`style_td_week`・
`style_td_day`・`style_td_sat`・`style_td_sun`・`style_td_today`・`style_td_blank`）。
PukiWikiのスキンに合わせて書かれたCSSを持ち込んでも効く。見た目は
`plugin/calendar.css` の1か所に置き、`calendar` 以外のプラグインも
`use_css` で `calendar` を「使ったプラグイン」に足して読み込ませる
（プラグインの資材は、そのページで使われたプラグインの名前で選ばれるため）。

## まだ無い日は、新規編集の画面を直接開く（Wiki設計者の指示、2026-09-27）

編集画面はPOSTでしか開けないので、ページのURLへのGETのリンクだと「このページは
まだありません → このページを作る」を1回経由する。編集の権限（`W`）が
ある人には、そのページへ `cmd=edit` をPOSTするボタン（リンクの見た目。
`calendar.css` の `.calendar-new`）を出して、1回で新規編集の画面を開く
（`new_page_button`）。`calendar2` の升目と「〜は空です。」、`calendar_edit` の
まだ無い日が使う。

## 年月の移動は、同じページを問い合わせ付きで開き直す

本家の `calendar2`・`calendar_viewer` は `?plugin=calendar2&file=…&date=…` で
**別のページ（プラグインの画面）**を開いて前後の月を見せた。wikiSystemの
プラグインの `_action` はテーマ付きの画面を返さないので、**カレンダーを置いた
ページ自身を、同じ問い合わせを付けて開き直す**（`nav_url`）。描くときに
`nav_query` が問い合わせを読み、`file` が自分の基準のページと同じなら、その年月で
描く。JavaScriptが要らず、ブラウザの「戻る」も効く。同じページに同じ基準の
カレンダーが2つあれば、両方が動く（区別する手段が本家にも無い）。
"""
import calendar as _pycal
import datetime
from urllib.parse import quote as urlquote
from urllib.parse import urlencode

from html import escape

from wikilib import pagelist
from wikilib.auth import PAGE_READ, PAGE_WRITE

WEEK_LABELS = ("日", "月", "火", "水", "木", "金", "土")


def today():
    return datetime.date.today()


def parse_yyyymm(text):
    """6桁の `yyyymm` を (年, 月) にする。月が0や13以上なら年へ繰り上げる
    （本家は `mktime` に任せていた。`202613` は 2027年1月）。"""
    year, month = int(text[:4]), int(text[4:6])
    return shift_month(year, 1, month - 1)


def shift_month(year, month, n):
    index = year * 12 + (month - 1) + n
    return index // 12, index % 12 + 1


def weeks(year, month):
    """日曜始まりの月の表。月の外は None。"""
    rows = _pycal.Calendar(firstweekday=6).monthdayscalendar(year, month)
    return [[d or None for d in row] for row in rows]


def wday_of(year, month, day):
    """曜日（日曜が0。本家の `date('w')` と同じ数えかた）。"""
    return (datetime.date(year, month, day).weekday() + 1) % 7


def day_class(year, month, day, wday, today_date, other_month=False):
    """本家と同じセルのクラス名。今日 → 日曜 → 土曜 → 平日の順に決める。"""
    if not other_month and datetime.date(year, month, day) == today_date:
        return "style_td_today"
    if wday == 0:
        return "style_td_sun"
    if wday == 6:
        return "style_td_sat"
    return "style_td_day"


def readable_pages(context, under=""):
    """`under`（ページパス。空ならWiki全体）の下にある、いまの閲覧者が読める
    ページのページパスの集合。閲覧できないページは**無いページと同じ扱い**に
    する（`#ls`・`#recent` と同じく、見えないページの存在を知らせない）。"""
    cache = getattr(context, "_calendar_pages", None)
    if cache is None:
        cache = context._calendar_pages = {}
    if under not in cache:
        items = pagelist.walk(context.wiki_dir, under=under, need=PAGE_READ,
                              privilege=context.privilege)
        cache[under] = {item.pagepath for item in items}
    return cache[under]


def page_url(context, page):
    return f"{context.base_url}/{urlquote(page)}"


def nav_url(context, **query):
    """いま描いているページのURLに、問い合わせを付けたもの。"""
    return page_url(context, context.page or "") + "?" + urlencode(query)


def nav_query(context, name, file):
    """いまのページが `?plugin=<name>&file=<file>` で開かれていれば、その問い合わせ
    （bottleの `FormsDict`）。そうでなければ None。

    リクエストの無い描画（取り込みのときの描き直し・テスト）では None。"""
    try:
        from bottle import request
        query = request.query
        if query.getunicode("plugin", "") != name:
            return None
        if (query.getunicode("file", "") or "") != file:
            return None
        return query
    except (RuntimeError, KeyError, AttributeError):
        return None


def can_write(context, page):
    """そのページを編集できるか（閲覧者にそのページの編集の権限 `W` があるか）。"""
    return context.privilege.check(page) == PAGE_WRITE


def new_page_button(context, page, label_html, extra_class=""):
    """まだ無いページ `page` の新規編集を直接開くボタン（docstring「まだ無い日は」）。
    `label_html` はボタンの中身（エスケープ済みのHTML）。"""
    klass = "calendar-new" + (" " + extra_class if extra_class else "")
    return (f'<form class="{klass}" method="post" action="{escape(page_url(context, page))}">'
            '<input type="hidden" name="cmd" value="edit">'
            f'<button type="submit" title="{escape(page)}">{label_html}</button></form>')


def use_css(context):
    context.used_plugins.add("calendar")


def strip_bracket(name):
    """本家の strip_bracket: `[[名前]]` と書かれていたら角括弧を外す。"""
    name = (name or "").strip()
    if name.startswith("[[") and name.endswith("]]"):
        name = name[2:-2].strip()
    return name
