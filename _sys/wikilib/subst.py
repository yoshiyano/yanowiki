"""プラグインではない、単純な置換系コマンド（本家PukiWikiの「置換文字」）。

`plugin/*.py` を用意しなくても最初から使える、日付・時刻・タブ・ページ名の
置き換え。本家と同じく2種類ある。

保存時に置換されるもの（`&date;` `&time;` `&now;` `&t;` `&page;` `&fpage;`）
    保存した瞬間の値がそのまま本文に書き込まれ、そのページを開くたびに
    変わることはない（書いた `&date;` という文字はそこで消える）。
    `save_time_replace` が担当し、編集画面の保存本体（`wikilib.editor`）から
    呼ばれる。一時保存（下書き）には適用しない。まだ書きかけの内容が、
    保存していないのに日付を確定させてしまわないようにするため。

表示時に置換されるもの（`&_date;` `&_time;` `&_now;` `&lastmod;` `&lastmod(ページ名);`）
    開くたびに評価し直される。プラグイン（`&name();`）と同じトークン化・
    描画規則の仕組みに乗せて実現している（`wikilib.pukiwiki.inline_match`・
    `wikilib.plugins` の描画規則登録を参照）。`lastmod` はDBの `updated`
    （最終更新日時）を読む。
"""
import datetime
import re
from html import escape

WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]  # datetime.weekday() は月曜=0

# レジストリ（テーブル）の中身だけを見て振る舞いが決まる名前の一覧。
# pukiwiki.inline_match はこれを見て、プラグイン記法ではなくここで処理する。
SAVE_TIME_NAMES = frozenset({"date", "time", "now", "t", "page", "fpage"})
DISPLAY_TIME_NAMES = frozenset({"_date", "_time", "_now", "lastmod"})
SAVE_TIME_RE = re.compile(r"&(" + "|".join(SAVE_TIME_NAMES) + r");")


def _date_str(when):
    return when.strftime("%Y-%m-%d")


def _time_str(when):
    return when.strftime("%H:%M:%S")


def _now_str(when):
    return "{} ({}) {}".format(_date_str(when), WEEKDAY_JA[when.weekday()], _time_str(when))


def save_time_replace(text, pagepath, now=None):
    """`&date;` `&time;` `&now;` `&t;` `&page;` `&fpage;` を、その場の値へ
    書き換える。以降このページを開いても再評価されない＝本文からは消える。

    pagepath はページのURLパス（`""` はそのWikiのトップ）。`&fpage;` は
    そのまま、`&page;` は最後の階層だけを使う（`"hoge/fuga"` なら
    `"fuga"`）。階層が無ければ両方同じになる。"""
    now = now or datetime.datetime.now()
    values = {
        "date": _date_str(now),
        "time": _time_str(now),
        "now": _now_str(now),
        "t": "\t",
        "page": pagepath.rsplit("/", 1)[-1] if pagepath else pagepath,
        "fpage": pagepath,
    }

    def replace(m):
        return values[m.group(1)]

    return SAVE_TIME_RE.sub(replace, text)


def render_display_time(context, name, arg):
    """`&_date;` `&_time;` `&_now;` `&lastmod;` `&lastmod(ページ名);` を、
    表示のたびに文字列へ変える。`context` が無い（部分プレビューなど）場合や、
    `lastmod` の対象ページが見つからない場合は空文字を返す
    （プラグインの断り書きのような大きな表示にはしない。単なる日付の穴埋めが
    崩れて目立つほうが煩わしいため）。"""
    now = datetime.datetime.now()
    if name == "_date":
        return escape(_date_str(now))
    if name == "_time":
        return escape(_time_str(now))
    if name == "_now":
        return escape(_now_str(now))
    if name == "lastmod":
        return escape(_lastmod_str(context, arg))
    return ""


def _lastmod_str(context, arg):
    if context is None or context.wiki_dir is None:
        return ""
    from wikilib.pagedb import load_page
    from wikilib.paths import resolve_link, resolve_page_ref

    current = resolve_page_ref(context.wiki_dir, context.page)
    if arg:
        kind, value = resolve_link(current.subpath if current else "", arg,
                                   context.wiki_dir)
        if kind != "page":
            return ""
        target = resolve_page_ref(context.wiki_dir, value.split("#", 1)[0])
    else:
        target = current
    if target is None:
        return ""

    row = load_page(context.wiki_dir, target.subpath)
    if row is None or not row.get("updated"):
        return ""
    try:
        when = datetime.datetime.strptime(row["updated"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    return _now_str(when)
