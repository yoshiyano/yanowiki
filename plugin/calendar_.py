"""カレンダー系プラグイン（`calendar`・`calendar_edit`・`calendar_read`・`calendar2`・
`calendar3`・`calendar_viewer`）が共有する処理。

`PLUGIN_INFO` を持たないので、プラグインとしては登録されない（`#calendar_` とは書けない）。
名前は使う側の塊（`calendar*`）に揃えて `calendar_.py` にしてある（Wiki設計者の指示、2026-10-02。
`_calendar.py` のような名前の違う共有モジュールは「あまり認めたくない」。`calendar_.py` の形なら可）。
使う側は自分の `__file__` の
隣を `importlib.util.spec_from_file_location` で呼び出しのたびに読み込む
（`include_.py` と同じ。`sys.modules` に置かないのは、置くとこのファイルを
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
    day_page_name(prefix, y, m, d) 日ごとのページの名前（`基準/2026/10/2026-10-27`）
    day_pages(context, base, seps) 閲覧できる日ごとのページ。{date: ページパス}
    migration_html(context, plugin, base, seps)  古い置きかたが残っていれば、組み替えの枠
    migration_action(context, seps) 組み替えの開始と、進み具合の問い合わせ（`_action` から）

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

## 日ごとのページは `年/月/` のフォルダに置く（Wiki設計者の指示、2026-10-27）

日ごとのページは `基準/2026/10/2026-10-27` の形で置く（`day_page_name`）。一覧にする
ファイルの数を減らすため。`calendar` の区切りの無い日付（`20261027`）も、この形の名前に
そろえる。拡張子は元のページのまま。

**古い置きかた**（基準の直下に `2026-10-27`・`20261027`、`calendar_viewer` の `date_sep`
の区切り）は残さず、新しい形へ強制的に組み替える。

- 組み替えるのは、編集の権限がある人がカレンダーを表示したとき。対象は、カレンダーの
  プラグインが基準にしているページ（フォルダ）の直下だけ（`ChangeLog` のような、
  カレンダーを置いていない日付のページは動かさない）
- **時間がかかっても1回で最後まで行い、途中の状態を見せない。** 組み替えの間は、
  カレンダーの代わりに「ファイル構成を更新中」と進み具合（プログレスバーと、作業中の
  `YYYY/MM`）を出す
- 改名は本体の `pagerename.rename_page` で1ページずつ行い、Wiki の中のリンクも
  追従させる（添付・バックアップ・権限の記録も一緒に動く）。Wiki の外からの古い URL は
  手当てしない
- `rename_page` はまだ無いフォルダへは移せない（`check_folder`）ので、先に
  `基準/YYYY/index.md`・`基準/YYYY/MM/index.md` を `#ls(./)` の本文で作って
  フォルダを用意する

### 組み替えの流れ（クロコの実装例。設計者は未確認）

- 描くとき（`migration_html`）は、改名を始めない。古い形のページがあるか・組み替えの
  最中かを見て、枠を出すだけ。改名の中で Wiki 全体の取り込みがあり、カレンダーの
  あるページが描き直されるため、描画から始めると入れ子になる
- 枠の `calendar.js` が `_action` へ開始を頼み（POST、`X-Requested-With: fetch`）、
  1秒ごとに進み具合を問い合わせ、終わったらページを読み込み直す
- 開始の要求を受けると、閲覧者が古い形のページすべてに編集の権限を持つかを
  確かめてから、別のスレッドで最後まで動かす（要求の時間切れに左右されないため）。
  1つでも編集できないページがあれば始めない（途中の状態を作らないため）
- 進み具合は `pageinfo/calendar_/<基準のハッシュ>.json` に書く（gunicorn の別の
  ワーカーからも読めるように、ファイルにする）。始めるときは `.lock` を排他で作る。
  5分更新が無ければ、止まったとみなして始め直せる
- 編集の権限が無い人には、組み替えの最中でなければ、古い形のままのカレンダーを出す
  （`day_pages` は新旧の両方を読む）
- 年は4桁だけを日付と読む（`calendar_viewer` の本家は2桁の年も読んだが、組み替えの
  名前が作れないため）

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
import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import quote as urlquote
from urllib.parse import urlencode

from html import escape

from wikilib import pagelist
from wikilib.auth import PAGE_READ, PAGE_WRITE
from wikilib.paths import PLUGIN_URLPATH, pagepath_of_subpath

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


# ---------------------------------------------------------------------------
# 日ごとのページの置き場所（docstring「日ごとのページは `年/月/` のフォルダに置く」）

DEFAULT_SEPS = ("-", "")    # calendar2 の `2026-10-27` と calendar の `20261027`
NEW_DAY_RE = re.compile(r"(\d{4})/(\d{2})/(\d{4})-(\d{2})-(\d{2})")
INDEX_EXT = ".md"
INDEX_TEXT = "#ls(./)\n"
STALE_SECONDS = 300         # 進み具合がこれだけ更新されなければ、止まったとみなす
MIGRATE_TITLE = "ファイル構成を更新中です（日ごとのページを年・月のフォルダへまとめています）。"
MIGRATE_NOJS = "この環境ではファイル構成を更新できません（JavaScript が必要です）。"


def day_page_name(prefix, year, month, day):
    """日ごとのページの名前。`prefix` は基準のページ名＋`/`（基準が無ければ空）。"""
    return f"{prefix}{year:04d}/{month:02d}/{year:04d}-{month:02d}-{day:02d}"


def _prefix(base):
    return base + "/" if base else ""


def _date(year, month, day):
    try:
        return datetime.date(int(year), int(month), int(day))
    except ValueError:
        return None


def old_date(name, seps):
    """基準の直下の名前が古い形の日付（区切りは `seps` のどれか）なら date、でなければ None。"""
    for sep in seps:
        if sep == "":
            m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", name)
        else:
            s = re.escape(sep)
            m = re.fullmatch(r"(\d{4})" + s + r"(\d{1,2})" + s + r"(\d{1,2})", name)
        if m:
            found = _date(*m.groups())
            if found is not None:
                return found
    return None


def new_date(rest):
    """基準から見た `2026/10/2026-10-27` が新しい形の日付なら date、でなければ None。"""
    m = NEW_DAY_RE.fullmatch(rest)
    if not m or m.group(1) != m.group(3) or m.group(2) != m.group(4):
        return None
    return _date(m.group(3), m.group(4), m.group(5))


def day_pages(context, base, seps=DEFAULT_SEPS):
    """`base` の下の、閲覧できる日ごとのページ。{date: ページパス}。

    新しい形（`基準/2026/10/2026-10-27`）と、組み替える前の古い形（基準の直下）の
    両方を読む。同じ日が両方にあれば新しい形を取る。"""
    prefix = _prefix(base)
    new, old = {}, {}
    for page in readable_pages(context, base):
        if not page.startswith(prefix):
            continue
        rest = page[len(prefix):]
        found = new_date(rest)
        if found is not None:
            new[found] = page
        elif "/" not in rest:
            found = old_date(rest, seps)
            if found is not None:
                old.setdefault(found, page)
    old.update(new)
    return old


def old_pages(wiki_dir, base, seps):
    """組み替える古い形のページ。閲覧者によらず全部。[(実体パス, ページパス, date), …] を日付順に。"""
    from wikilib import pagedb
    prefix = _prefix(base)
    out = []
    for subpath in pagedb.all_subpaths(wiki_dir):
        page = pagepath_of_subpath(subpath)
        if not page.startswith(prefix):
            continue
        rest = page[len(prefix):]
        if not rest or "/" in rest:
            continue
        found = old_date(rest, seps)
        if found is not None:
            out.append((subpath, page, found))
    out.sort(key=lambda item: (item[2], item[1]))
    return out


def _status_path(wiki_dir, base):
    key = hashlib.sha1(("/" + base).encode("utf-8")).hexdigest()[:16]
    return os.path.join(os.path.dirname(wiki_dir), "pageinfo", "calendar_", key + ".json")


def _read_status(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_status(path, status):
    status["updated"] = time.time()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)
    os.replace(tmp, path)


def _is_running(status):
    return bool(status) and status.get("state") == "running" and \
        time.time() - status.get("updated", 0) < STALE_SECONDS


def _all_writable(context, pages):
    return all(context.privilege.check(page) == PAGE_WRITE for _, page, _ in pages)


def migration_html(context, plugin, base, seps=DEFAULT_SEPS, extra_sep=None):
    """古い形のページが残っている・組み替えの最中なら、カレンダーの代わりに出す枠。
    そうでなければ None（ふつうにカレンダーを描く）。改名はここでは始めない（docstring）。

    編集の権限が無い人には、組み替えの最中でなければ None を返す（古い形のまま描く）。"""
    if not context.wiki_dir or getattr(context, "partial", False):
        return None
    status = _read_status(_status_path(context.wiki_dir, base))
    running = _is_running(status)
    if running:
        total, done, current = status.get("total", 0), status.get("done", 0), status.get("current", "")
        start = False
    else:
        pages = old_pages(context.wiki_dir, base, seps)
        if not pages or not _all_writable(context, pages):
            return None
        total, done, current = len(pages), 0, ""
        start = True
    use_css(context)
    api = f"{context.base_url}/{PLUGIN_URLPATH}/{plugin}"
    return (
        f'<div class="calendar-migrate" data-calendar-migrate-api="{escape(api, quote=True)}"'
        f' data-calendar-migrate-base="{escape(base, quote=True)}"'
        f' data-calendar-migrate-sep="{escape(extra_sep or "", quote=True)}"'
        f' data-calendar-migrate-start="{"1" if start else "0"}">\n'
        f'<p class="calendar-migrate-title">{MIGRATE_TITLE}</p>\n'
        f'<progress class="calendar-migrate-bar" max="{max(total, 1)}" value="{done}"></progress>\n'
        f'<span class="calendar-migrate-count">{done} / {total}</span>'
        f' <span class="calendar-migrate-current">{escape(current)}</span>\n'
        '<div class="calendar-migrate-message"></div>\n'
        f'<noscript><p>{MIGRATE_NOJS}</p></noscript>\n'
        '</div>\n'
    )


def _json(data, status=200):
    from bottle import HTTPResponse
    return HTTPResponse(body=json.dumps(data, ensure_ascii=False), status=status,
                        content_type="application/json; charset=utf-8",
                        headers={"Cache-Control": "no-store"})


def _status_json(context, base, seps, status):
    data = {"state": "running" if _is_running(status) else "idle",
            "total": 0, "done": 0, "current": "", "errors": []}
    if status:
        for key in ("total", "done", "current", "errors"):
            data[key] = status.get(key, data[key])
    if data["state"] != "running":
        data["remaining"] = len(old_pages(context.wiki_dir, base, seps))
    return data


def migration_action(context, seps=DEFAULT_SEPS):
    """`_action` から呼ぶ。`migrate=status`（GET）なら進み具合、`migrate=start`（POST）なら
    組み替えを始める。どちらでもない要求なら None（呼び出し元の処理を続ける）。"""
    from bottle import request
    from wikilib.paths import is_valid_pagepath

    what = request.query.get("migrate", "") or request.forms.get("migrate", "")
    if what not in ("status", "start"):
        return None
    params = request.forms if request.method == "POST" else request.query
    base = (params.getunicode("base", "") or "").strip("/")
    if base and not is_valid_pagepath(base):
        return _json({"error": "基準のページが正しくありません。"}, 400)
    extra = params.getunicode("sep", "") or ""
    if extra:
        if "/" in extra or len(extra) > 5:
            return _json({"error": "日付の区切りが正しくありません。"}, 400)
        seps = tuple(seps) + (extra,)
    if base and context.privilege.check(base) not in (PAGE_READ, PAGE_WRITE):
        return _json({"error": "このページを閲覧する権限がありません。"}, 403)

    path = _status_path(context.wiki_dir, base)
    if what == "status":
        return _json(_status_json(context, base, seps, _read_status(path)))

    if request.method != "POST" or request.headers.get("X-Requested-With") != "fetch":
        return _json({"error": MIGRATE_NOJS}, 400)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = path + ".lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            status = _read_status(path)
            if _is_running(status):
                return _json(_status_json(context, base, seps, status))   # 別の人が始めている
            try:
                os.remove(lock)   # 止まったまま残った印
            except OSError:
                pass
    else:
        return _json({"error": "ファイル構成の更新を始められませんでした。"}, 409)

    pages = old_pages(context.wiki_dir, base, seps)
    if not _all_writable(context, pages):
        os.remove(lock)
        return _json({"error": "編集の権限が無い日のページがあるため、ファイル構成を更新できません。"}, 403)
    status = {"state": "running", "total": len(pages), "done": 0, "current": "", "errors": []}
    _write_status(path, status)
    worker = threading.Thread(target=_migrate, name="calendar-migrate", daemon=True,
                              args=(context.wiki_dir, context.config, base, pages, path, lock, status))
    worker.start()
    return _json(_status_json(context, base, seps, status))


def _ensure_folder(wiki_dir, config, folder):
    """`folder` に何も無ければ、`#ls(./)` の入口ページを作ってフォルダにする
    （`rename_page` はまだ無いフォルダへ移せないため。docstring）。"""
    from wikilib import pagerename
    from wikilib.pagesave import save_page
    if pagerename.check_folder(wiki_dir, folder) is None:
        return
    save_page(wiki_dir, config, folder + "/index", INDEX_EXT, INDEX_TEXT)


def _migrate(wiki_dir, config, base, pages, path, lock, status):
    """別のスレッドで、古い形のページを最後まで組み替える。"""
    from wikilib import pagerename
    prefix = _prefix(base)
    errors = status["errors"]
    try:
        for subpath, page, day in pages:
            ym = f"{day.year:04d}/{day.month:02d}"
            status["current"] = ym
            _write_status(path, status)
            _ensure_folder(wiki_dir, config, f"{prefix}{day.year:04d}")
            _ensure_folder(wiki_dir, config, prefix + ym)
            ok, message, _ = pagerename.rename_page(
                wiki_dir, config, subpath, f"{day.year:04d}-{day.month:02d}-{day.day:02d}",
                prefix + ym)
            if not ok:
                errors.append(f"{page}: {message}")
            status["done"] += 1
    except Exception as exc:   # 残りは次に表示したときに始め直せる
        errors.append(f"途中で失敗しました: {exc}")
    finally:
        status["state"] = "done"
        status["current"] = ""
        _write_status(path, status)
        try:
            os.remove(lock)
        except OSError:
            pass
