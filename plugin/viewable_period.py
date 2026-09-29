"""viewable_period — 指定した期間の外では、ページの本文を表示しない。

    #viewable_period(start,end)                       使いかたの例
    #viewable_period(start,end){期間外に出す文}         1行の案内文つき
    #viewable_period(start,end){{
    複数行の案内文
    }}
    #viewable_period(start,end,alice,bob)             編集者を指定する例

 1. start … 表示を始める日時 (default: 制限なし＝最初から表示)
       `YYYY/MM/DD HH:MM:SS` の書式。年は省いて `MM/DD` にでき、その場合は
       ページの最終更新日以降で最初に迎えるその月日が使われる（endが
       指定されているときは、end以前になる年を優先して選ぶ。下記技術資料
       参照）。年は`YY/MM/DD`（2桁、20xx年として解釈）でもよい。時刻を
       省くと`00:00:00`になる（`SS`だけ省いて`HH:MM`と書いてもよい。
       `HH`だけ・`MM`だけは書けない）
 2. end   … 表示を終える日時 (default: 制限なし＝ずっと表示)
       書式はstartと同じ。時刻を省くと`23:59:59`になる。
       **ページの最終更新日より過去の日時は指定できない**
 3. editors … 表示期間外でも本文を見せる編集者のログインID
       (default: 指定なし＝誰も特例扱いしない)。end のうしろに `,` 区切りで
       何人でも並べられる（`login` プラグインでログインするときのID）。
       ログイン中のIDがこの一覧に含まれる相手には、期間内・期間外に
       かかわらず本文をそのまま見せたうえで、本文の先頭へ「ページ表示期間
       設定」という `<fieldset>` を差し込む（現在の公開状態＝閲覧可能/閲覧
       不能、表示可能期間、編集者の一覧を確認できる）。**このパネルは
       一覧に載っている本人にだけ見える**（他の閲覧者には今までどおり
       何も出ない／期間外なら案内文に差し替わる）。
       **パネルは期間内（閲覧可能）でも必ず出す。** このページに
       `#viewable_period` による日付指定があること自体を編集者が忘れない
       ようにするための、設定の存在を知らせるメモを兼ねている（Wiki設計者の指示、
       2026-09-10）。

start・endはどちらか一方、または両方を省略できる（両方省略すると常に
表示される。それ自体はエラーにならない）。startがendより後になる書きかたは
エラーになる。editorsを省けば、このプラグインは従来どおり「期間外は誰にも
見せない（編集者も見られない）」という動作のままになる。

中身（`{}`）には、期間外に表示する案内文をWikiテキストで書ける（省略すると
既定の案内文になる）。他の記法・プラグインもそのまま展開される。

**これは「見せない」であって「読ませない」ではない。** 期間外でも本文は
平文・DBに残ったままで、編集画面（「履歴」タブを含む）・検索の
抜粋・`#ls`/`#recent`に出るタイトルからは今までどおり読める。**秘密を
守る用途には使えない。** 見出し単位の取り出し（`/.section/<ページ名>`、
セクション編集）だけは別で、期間外のページでは取り出し・保存とも403で
断られる（`editor.serve_section`。通常の編集画面は止まらない）。他ページ
からの`#include`も別で、このページ自身が書いた期間外の案内文に差し替わり
読めない（`include.py`の技術資料「差し込み先が表示を止めている場合」参照）。
"""

""" 技術資料
`wikilib.plugins.PluginContext.block_view`（2026-09-05にwikiSystem側へ
追加された窓口。認証とは別の理由でページ表示を止めたいプラグイン向け、
Wiki設計者の指示）を使う。期間外と判定したら`context.block_view(html,
by="viewable_period")`を呼んで`""`を返すだけで、本文の実際の差し替えは
`wikilib.themes.render_with_theme`側が担う。同じページに複数の
`#viewable_period`があった場合、先に呼ばれたものが勝つ（`block_view`の
仕様。あとから呼んでも`False`が返るだけで無視される。このプラグイン側では
特にハンドリングしていない）。

## editors（表示期間外でも本文を見せる編集者）（Wiki設計者の指示、2026-09-10）

Wiki設計者の依頼:「現在閲覧可能日程でない場合ページ編集者も閲覧できない。そこで
オプションを追加。開始・終了の後に 編集者ID を書けるようにする。ログイン
情報のIDが指定されていれば、ページ内容を表示する。ただし、『ページ表示
期間設定』というlegend を持った fieldset を表示し、その中に表示可能期間と
編集者の一覧を表示させる。一番上には現在のステータス『閲覧可能・閲覧不能』
を色を付けて表示させる。」

クロコ（実装者）の評価: 条件付きで賛成。従来この機能は「期間外は誰も
（＝編集者も）本文を見られない」という単純な作りだったが、掲載期間を
管理する当人が公開前・公開終了後に自分のページを確認できないのは不便
なので、明示的に列挙したログインIDにだけ現在の本文を見せるのは妥当。
ただし `block_view`（＝『見せない』であって『読ませない』ではない、
秘密保持には使えない）という前提は変わらないので、editorsは
「編集者向けの下見用の抜け道」であって権限制御ではない、という位置づけを
docstring・説明ページの両方に残した。

実装上の判断:

- **可変個数の編集者IDは `rest_params: True` で受ける**（`readauth.py`（旧`viewaccess.py`）
  の`users`と同じ。`end`のうしろに残った位置引数を`,`連結で受け取り、
  `_convert`側で`,`に割り直す）。`readauth.py`（旧`viewaccess.py`）と違い**空指定は
  エラーにしない**——editorsを省いた`#viewable_period(start,end)`は
  従来どおりの「編集者も見られない」動作でなければ後方互換が崩れるため、
  `editors=""` はそのまま「特例なし」を意味する。
- **ログイン中IDの取得は `wikilib.auth.current_user(context.wiki_dir,
  context.farm)` の `uid`**（`readauth.py`（旧`viewaccess.py`）/`login.py`と同じ呼びかた）。
  未ログインは常に非該当。
- **「ページ表示期間設定」パネルは期間内・期間外どちらでも編集者に出す。**
  当初は「期間外のときだけ出す」案も検討したが、Wiki設計者の確認で「日付指定
  （このプラグイン設定）があること自体を編集者に忘れさせないためのメモ
  として、閲覧可能なときも常に出す」と決まった（Wiki設計者の指示、2026-09-10）。
  「ステータスを『閲覧可能・閲覧不能』の2値で色分けして出す」という指定
  とも整合する（期間内＝閲覧可能・緑の状態も、パネルが出て初めて確認
  できる）。実装上は「editorsに載っているログイン中の相手には、in/outを
  問わずパネルを返す」だけ。期間内の非編集者・未ログインには従来どおり
  `""`（何も出さない）を返す。
- **編集者に見せるときは `block_view` を呼ばない。** 呼ぶと
  `render_with_theme`が本文まるごとをメッセージへ差し替えてしまい、
  肝心の本文・見出し・編集リンクが消える。editorsに一致した時点で
  `_panel_html(...)`だけを返して`block_view`は素通りさせ、パネルは
  プラグインを書いた位置（＝ふつうページ先頭）にそのまま挿入される。
- パネルの見た目は `plugin/viewable_period.css`（`used_plugins`により
  自動読み込み）。ステータスの緑/赤だけはCSS未読込でも意味が伝わるよう
  `<strong>` テキストにも状態語（閲覧可能/閲覧不能）を入れてある。

## 日時の書式・年決定ロジック（Wiki設計者の指示、2026-09-05）

`_parse_date_fields`/`_parse_time_fields`が`/`と`:`で分解するだけの
簡易パーサー（`datetime.strptime`は使っていない。`9/1`のような1桁月日、
`9:5`のような1桁時分もそのまま受け付けるため）。

年省略（`MM/DD`）時にどの日付を基準に年を決めるかは、指定の有無で3通りに
分かれる（すべてWiki設計者の指示）。

1. **endが年省略**: ページの最終更新日（`wikilib.pagedb.page_updated_at`。
   DBにまだ無い新規ページ・プレビュー中は代わりにサーバーの今日を使う）
   **以降**（当日を含む）で最初にそのMM/DDを迎える年。
2. **startが年省略・endが省略されている**: 上と同じ基準（最終更新日）。
3. **startが年省略・endが指定されている**: **今日**（レンダリング時点。
   最終更新日ではない）を基準に、今日より**後**で一番近い年を試し、その
   年のMM/DDがend以前ならその年を採用する。endを超えてしまう場合は、
   今日より**前**の年（＝上で試した年のひとつ前）を使う（Wiki設計者の例:
   今日を起点に`(05/22, 30/3/3)`なら開始は2027年——2026年の05/22は
   今日より前で候補にならず、2027年の05/22は今日より後かつend
   （2030/03/03）以前なので採用）。

MM/DDが該当年に存在しない場合（2/29のうるう年でない年）は、存在する年が
見つかるまで最大8年分探す（`_next_occurrence`/`_prev_occurrence`）。
それでも見つからなければ`PluginArgumentError`にする（理論上は起こらない
はずの安全網）。

## 制約（Wiki設計者の指示、2026-09-05）

- **endはページの最終更新日より過去にできない。** endが確定した時点
  （年ありで明示指定された場合を含む）で`end.date() < 最終更新日`なら
  `PluginArgumentError`。年省略のendは上記1のロジックにより自動的に
  最終更新日以降になるため、実際にこのチェックへ引っかかるのは年を
  明示した場合だけ。
- **startはendより過去でもよい**（下限チェックは無い）。
- **startはendより後にはできない。** 両方確定した時点で`start > end`なら
  `PluginArgumentError`。

## 期間の境界

`start <= now <= end`を閉区間で判定する（時刻省略時の既定値が
`00:00:00`/`23:59:59`になっているのもこれに合わせたもの）。

## 期間外メッセージの展開

`PLUGIN_INFO`では`expand_*`を宣言せず、`_convert`の中で
`wikilib.plugins.expand_body(body, info, context, 0)`を直接呼んでいる
（`SPECIFICATIONS.md`5節の方法2）。期間内かどうかを判定してから初めて
展開するかどうかが決まるため、静的な`expand_*`宣言では対応できない。
"""
import re
from datetime import date, datetime, timedelta
from html import escape

from wikilib.auth import current_user
from wikilib.pagedb import page_updated_at
from wikilib.paths import resolve_page_ref
from wikilib.plugins import PluginArgumentError, expand_body

PLUGIN_INFO = {
    "help": "#viewable_period(start,end,editors){期間外メッセージ}",
    "args": [
        {"name": "start", "default": None},
        {"name": "end", "default": None},
        {"name": "editors", "rest_params": True},
    ],
}

_DATE_RE = re.compile(r"^(?:(\d{2}|\d{4})/)?(\d{1,2})/(\d{1,2})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?$")
_MAX_YEAR_SEARCH = 8  # 2/29探索の上限（理論上は数年以内で必ず見つかる）

_DEFAULT_MESSAGE_HTML = "<p>このページは現在閲覧できません。</p>"
_EXPAND_INFO = {"expand_block": True, "expand_inline": True, "expand_plugin": True}

_STAMP_FMT = "%Y/%m/%d %H:%M:%S"


def _safe_date(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_occurrence(month, day, after):
    """`after`（date）以降（当日を含む）で最初にmonth/dayを迎える日付。"""
    year = after.year
    for _ in range(_MAX_YEAR_SEARCH):
        d = _safe_date(year, month, day)
        if d is not None and d >= after:
            return d
        year += 1
    raise PluginArgumentError("viewable_period: 日付の指定が正しくありません（存在しない日付です）")


def _prev_occurrence(month, day, before):
    """`before`（date）以前（当日を含む）で最後にmonth/dayを迎えた日付。"""
    year = before.year
    for _ in range(_MAX_YEAR_SEARCH):
        d = _safe_date(year, month, day)
        if d is not None and d <= before:
            return d
        year -= 1
    raise PluginArgumentError("viewable_period: 日付の指定が正しくありません（存在しない日付です）")


def _edit_date(context):
    """ページの最終更新日（DB上のupdated）。まだ公開されていなければ今日。"""
    if context is not None and context.wiki_dir:
        ref = resolve_page_ref(context.wiki_dir, context.page or "")
        if ref is not None:
            stamp = page_updated_at(context.wiki_dir, ref.subpath)
            if stamp:
                return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").date()
    return datetime.now().date()


def _parse_date_fields(date_text):
    m = _DATE_RE.match(date_text)
    if not m:
        raise PluginArgumentError(f"viewable_period: 日付の書きかたが正しくありません: {date_text}")
    year_text, month_text, day_text = m.groups()
    month, day = int(month_text), int(day_text)
    if not (1 <= month <= 12):
        raise PluginArgumentError(f"viewable_period: 月の指定が正しくありません: {date_text}")
    if not (1 <= day <= 31):
        raise PluginArgumentError(f"viewable_period: 日の指定が正しくありません: {date_text}")
    if year_text is None:
        return None, month, day
    year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text)
    return year, month, day


def _parse_time_fields(time_text, is_start):
    if time_text is None:
        return (0, 0, 0) if is_start else (23, 59, 59)
    m = _TIME_RE.match(time_text)
    if not m:
        raise PluginArgumentError(f"viewable_period: 時刻の書きかたが正しくありません: {time_text}")
    hour, minute, second = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if not (0 <= hour <= 23):
        raise PluginArgumentError(f"viewable_period: 時の指定が正しくありません: {time_text}")
    if not (0 <= minute <= 59):
        raise PluginArgumentError(f"viewable_period: 分の指定が正しくありません: {time_text}")
    if not (0 <= second <= 59):
        raise PluginArgumentError(f"viewable_period: 秒の指定が正しくありません: {time_text}")
    return hour, minute, second


def _resolve_start_year_with_end(month, day, today, end_date):
    after = _next_occurrence(month, day, today + timedelta(days=1))
    if after <= end_date:
        return after.year
    return _prev_occurrence(month, day, today).year


def _parse_datetime_arg(text, is_start, today, edit_date, end_date=None):
    """開始/終了の日時文字列をdatetimeにする。"""
    date_text, _, time_text = text.partition(" ")
    time_text = time_text.strip() or None
    year, month, day = _parse_date_fields(date_text)
    hour, minute, second = _parse_time_fields(time_text, is_start)

    if year is None:
        if is_start and end_date is not None:
            year = _resolve_start_year_with_end(month, day, today, end_date)
        else:
            year = _next_occurrence(month, day, edit_date).year

    if _safe_date(year, month, day) is None:
        raise PluginArgumentError(f"viewable_period: 日付の指定が正しくありません（存在しない日付です）: {text}")
    return datetime(year, month, day, hour, minute, second)


def _parse_editors(raw):
    """`end` のうしろに `,` 区切りで並んだ編集者IDを一覧にする。
    未指定（`""`）なら空リスト＝「特例扱いする編集者はいない」。"""
    return [e.strip() for e in (raw or "").split(",") if e.strip()]


def _current_uid(context):
    """ログイン中のユーザのuid。未ログイン・context不足ならNone。"""
    if context is None or not context.wiki_dir:
        return None
    user = current_user(context.wiki_dir, context.farm)
    return user["uid"] if user is not None else None


def _period_text(start_dt, end_dt):
    """パネルに出す「表示可能期間」の説明文（プレーンテキスト）。"""
    if start_dt is None and end_dt is None:
        return "制限なし（常に閲覧可能）"
    if start_dt is None:
        return f"{end_dt.strftime(_STAMP_FMT)} まで"
    if end_dt is None:
        return f"{start_dt.strftime(_STAMP_FMT)} から"
    return f"{start_dt.strftime(_STAMP_FMT)} 〜 {end_dt.strftime(_STAMP_FMT)}"


def _panel_html(in_period, start_dt, end_dt, editors):
    """editorsに載っているログイン中の相手にだけ出す「ページ表示期間設定」
    パネル。先頭に現在の公開状態（閲覧可能/閲覧不能）を色付きで示し、
    続けて表示可能期間と編集者の一覧を並べる。"""
    if in_period:
        status_cls, status_label = "viewable-period-status-open", "閲覧可能"
    else:
        status_cls, status_label = "viewable-period-status-closed", "閲覧不能"
    editor_html = "、".join(f"<code>{escape(e)}</code>" for e in editors)
    period_html = escape(_period_text(start_dt, end_dt))
    return f"""<fieldset class="viewable-period">
  <legend>ページ表示期間設定</legend>
  <p class="viewable-period-status {status_cls}">現在のステータス: <strong>{status_label}</strong></p>
  <dl class="viewable-period-detail">
    <dt>表示可能期間</dt><dd>{period_html}</dd>
    <dt>編集者</dt><dd>{editor_html}</dd>
  </dl>
</fieldset>"""


def _convert(resolved, body, context):
    now = datetime.now()
    today = now.date()
    edit_date = _edit_date(context)

    end_text = (resolved["end"] or "").strip()
    end_dt = _parse_datetime_arg(end_text, False, today, edit_date) if end_text else None
    if end_dt is not None and end_dt.date() < edit_date:
        raise PluginArgumentError(
            f"viewable_period: 終了日時はページの最終更新日（{edit_date.isoformat()}）より前にはできません: {end_text}")

    start_text = (resolved["start"] or "").strip()
    start_dt = (
        _parse_datetime_arg(start_text, True, today, edit_date, end_dt.date() if end_dt else None)
        if start_text else None
    )
    if start_dt is not None and end_dt is not None and start_dt > end_dt:
        raise PluginArgumentError(
            f"viewable_period: 開始日時は終了日時より後にはできません: {start_text} > {end_text}")

    in_period = (start_dt is None or now >= start_dt) and (end_dt is None or now <= end_dt)

    # editorsに載っているログイン中の相手には、期間内・期間外にかかわらず
    # 本文をそのまま見せる（block_viewは呼ばない）。そのうえで、現在の公開
    # 状態と設定内容を確認できるパネルを本文へ差し込む。
    editors = _parse_editors(resolved["editors"])
    if editors and _current_uid(context) in editors:
        return _panel_html(in_period, start_dt, end_dt, editors)

    if in_period:
        return ""

    message_html = _DEFAULT_MESSAGE_HTML if body is None else (expand_body(body, _EXPAND_INFO, context, 0) or "")
    context.block_view(message_html, by="viewable_period")
    return ""
