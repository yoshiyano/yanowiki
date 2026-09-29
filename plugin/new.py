"""new — 日付やページの更新が新しければ「New!」の印を付ける。

    &new{2026-09-25 (金) 18:15:23};   日付を出し、1日以内なら New!、5日以内なら New を添える
    &new(nodate){2026-09-25 (金) 18:15:23};   日付は出さず、印だけ
    &new(ページ名);                    ページへのリンクと、そのページの更新の新しさの印
    &new(ページ名, nolink);            印だけ（リンクを出さない）
    &new(フォルダ/);                   その下で一番新しく更新されたページへのリンクと印

 1. page   … 更新の新しさを見るページ。末尾が `/` なら、その下のページのうち
       一番新しいもの (default: このページ)
 2. nolink … これを書くと、ページへのリンクを出さない (default: 出す)
 3. nodate … `{日付}` を書いたとき、日付の文字を出さない (default: 出す)

`{日付}` を書いたときは、その日時で判断します。`#comment` などが書き込む
`2026-09-25 (金) 18:15:23` の形や、`2026-09-25 18:15`・`2026/9/25` のような形が
読めます。

- 1日以内 … ` New!`（クラス `new1`）
- 5日以内 … ` New`（クラス `new5`）
- それより前 … 何も付けない

印にマウスを重ねると、どれくらい前か（`(3h)` など）が出ます。
閲覧できないページは、無いページと同じ扱いになります。

**日付を書いた `&new` は、5日を過ぎて印が付かなくなると、ページを開いたときに
プラグインが外れます。** `&new{2026-09-25 (金) 18:15:23};` は日付の文字
`2026-09-25 (金) 18:15:23` だけに、`&new(nodate){…};` は何も無しに書き換わります
（見た目は変わりません）。ページを指定した `&new(ページ名);` はそのままです。
"""

""" 技術資料
本家 `new.inc.php`（PukiWiki 1.5系）の移植。

## 印はサーバーで付ける

本家1.5系は `<span class="__plugin_new" data-mtime="…">` を出し、スキンの
`main.js` が閲覧時に経過時間を計って ` New!`/` New` と `new1`/`new5` を付けた
（ページの出力がキャッシュされても、見た時点の新しさで出すため）。wikiSystemは
**見るたびに描き直す**のでキャッシュの心配が無く、サーバーで計って出す
（JavaScriptが無くても出る）。目印のクラス `__plugin_new` と `data-mtime` は
本家と同じく残し、`new1`/`new5`・文字・`title`（経過時間）も本家のJSと同じにした。

## ページを指定したときにも印を付ける

本家1.5系のソースは、日付を書いたときだけ `__plugin_new` を出し、ページを
指定したときはページへのリンクしか返さない（`if($date !== '')` の分岐）。1.4系
まではどちらにも印を付けていたので、1.5系で印を出す処理を JavaScript へ移した
ときに、ページの側だけ落ちたものと見て、**1.4系と同じく印を付ける**ことにした。

## 日付の読みかた

本家は `^\\D*(\\d{4})\\D+(\\d{1,2})\\D+(\\d{1,2})\\D+(\\d{1,2}:\\d{2}:\\d{2})\\D*$`（`#comment`
の `2026-09-25 (金) 18:15:23` の形）を先に試し、だめなら PHP の `strtotime` に
任せた。`strtotime` と同じものは標準ライブラリに無いので、次の形を読む。

- 上の本家の正規表現（曜日などの間の文字は問わない）
- 時刻が `時:分` だけのもの、時刻の無いもの（その日の0時）
- `datetime.fromisoformat` が読めるもの（`2026-09-25T18:15:23+09:00` など）

時差の無い日時はサーバーの地方時とみなす（本家の `ZONETIME` と同じ扱い）。

## 古くなった日付の `&new` を外す（Wiki設計者の指示、2026-09-26）

日付を書いた形は、5日（`ELAPSES` の最後）を過ぎると二度と印が付かないので、
**描いたときに、保存済みの本文からプラグインを外す**（`&new{D};`・`&new(){D};` → `D`、
`&new(nodate){D};` → 空）。ページを指定した形は、ページが更新されればまた新しく
なるので外さない。

- 書き換えるのは、古い `&new` を描いたときだけ（`_inline` から `_drop_old_calls`）。
  1回の描画につき1ページ1度。部分プレビュー（`context.partial`）では書き換えない
  （編集中の本文とずれるため。`_authcommon._normalize_saved_page` と同じ作法）
- 書き換えは `pagesave.save_page`（差分は履歴に残る）。閲覧者が誰でも行う
  （プラグインによる書き換えは、ユーザの編集とは別に数える決まり）
- **本文の字面を1行ずつ見て置き換える**が、描いてもプラグインにならない所
  （書きかたの例）は触らない。この説明ページ自身（`Syntax/Plugin/new`）の例が
  書き換わらないようにするため。記法ごとに、実際の描画と同じ区切りにしてある
    - Markdown: 囲みコード（```・~~~）、インデントのコード（4つの空白・タブ）、
      コードスパン（`` `…` ``）、他のプラグインの複数行の本体（`#code(){{ … }}`）。
      丸括弧の無い `&new{…};` はMarkdownではプラグインにならないので触らない
    - PukiWiki記法: 整形済みテキスト（行頭が空白）、他のプラグインの複数行の本体
      （丸括弧の無い `#code{{` も本体になる）。``` や `` ` `` はPukiWiki記法では
      コードにならず、中の `&new` も描かれるので書き換える
  - プラグインの行（`#name(...)`）自体も触らない（引数に `&new` を書くことは無い）
  - この見分けは共有の `_srcscan.py` に切り出した（2026-09-28）
- 日付として読めないもの・まだ5日経っていないものは残す

## ページの更新日時

`pagelist.walk`（閲覧の権限を通したページの一覧。DBの `updated`）から取る。
末尾が `/` のときは、その文字列で始まるページのうち一番新しいもの（本家と同じく
名前の前方一致なので、`日記/` なら `日記/…` 全部）。
"""
import datetime
import re
from html import escape

from wikilib import pagelist
from wikilib.auth import PAGE_READ
from wikilib.pagedb import resolve_page_ref
from wikilib.pagesave import save_page
from wikilib.paths import full_pagepath, is_valid_pagepath
from wikilib.plugins import PluginArgumentError
from wikilib.render import is_pukiwiki

PLUGIN_INFO = {
    "help": "&new(page,nolink){date}; / &new(nodate){date};",
    "args": [
        {"name": "nolink", "flag": True, "default": False},
        {"name": "nodate", "flag": True, "default": False},
        {"name": "page", "num_order": -1, "link": True},
    ],
}

# 経過時間の段階（本家の $_plugin_new_elapses、main.js と同じ）
ELAPSES = ((1, "new1", "New!"), (5, "new5", "New"))

_PUKIWIKI_DATE_RE = re.compile(r"^\D*(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2}):(\d{2}):(\d{2})\D*$")
_MINUTE_DATE_RE = re.compile(r"^\D*(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2}):(\d{2})\D*$")
_DAY_DATE_RE = re.compile(r"^\D*(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*$")


def parse_date(text):
    """日付の文字列を、時差つきの datetime にする。読めなければ None。"""
    text = (text or "").strip()
    for regex in (_PUKIWIKI_DATE_RE, _MINUTE_DATE_RE, _DAY_DATE_RE):
        m = regex.match(text)
        if m:
            try:
                when = datetime.datetime(*(int(g) for g in m.groups()))
            except ValueError:
                return None
            return when.astimezone()
    try:
        when = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.astimezone()


def passage(when, now):
    """経過時間の短い書きかた（本家 main.js の getPassage。`(3h)` など）。"""
    minutes = (now - when).total_seconds() / 60
    value, unit = minutes, "m"
    for next_unit, size in (("h", 60), ("d", 24)):
        if value < size:
            break
        value, unit = value / size, next_unit
    return f"({int(value)}{unit})"


def mark_html(when, now=None):
    """印の `<span>`。古ければ中身の無い目印だけ（本家と同じく、目印は常に出す）。"""
    now = now or datetime.datetime.now().astimezone()
    stamp = escape(when.isoformat(timespec="seconds"), quote=True)
    days = (now - when).total_seconds() / 86400
    for limit, klass, text in ELAPSES:
        if days < limit:
            return (f'<span class="__plugin_new {klass}" data-mtime="{stamp}"'
                    f' title="{escape(passage(when, now), quote=True)}"> {text}</span>')
    return f'<span class="__plugin_new" data-mtime="{stamp}"></span>'


_CALL_RE = re.compile(r"&new(?:\(\s*(nodate)?\s*\))?\{([^{}]*)\};")
# Markdownでは丸括弧の無い `&new{…};` はプラグインにならない（文字のまま出る）
_MD_CALL_RE = re.compile(r"&new\(\s*(nodate)?\s*\)\{([^{}]*)\};")


def _is_old(when, now):
    return (now - when).total_seconds() / 86400 >= ELAPSES[-1][0]


def _drop_in_line(line, now, markdown):
    """1行の中の、古い日付の `&new` を外す。Markdownではコードスパンの中は触らない。"""
    def repl(m):
        when = parse_date(m.group(2))
        if when is None or not _is_old(when, now):
            return m.group(0)
        return "" if m.group(1) else m.group(2)

    if not markdown:
        return _CALL_RE.sub(repl, line)
    parts = re.split(r"(`+[^`]*`+)", line)   # 奇数番目がコードスパン
    return "".join(p if i % 2 else _MD_CALL_RE.sub(repl, p) for i, p in enumerate(parts))


def drop_old_calls(text, ext, now=None):
    """本文から、5日を過ぎた日付の `&new` を外した本文を返す（技術資料「古くなった」）。
    描いてもプラグインにならない行は触らない（行の見分けは `_srcscan.classify_lines`）。"""
    now = now or datetime.datetime.now().astimezone()
    markdown = not is_pukiwiki(ext)
    out = []
    for line, kind in _load_srcscan().classify_lines(text, ext):
        if kind == "text" and "&new" in line:
            line = _drop_in_line(line, now, markdown)
        out.append(line)
    return "\n".join(out)


def _load_srcscan():
    """兄弟の`_srcscan.py`（共有モジュール）を読み込む（呼び出しごと）。"""
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_srcscan.py")
    spec = importlib.util.spec_from_file_location("wikiplugin__srcscan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _drop_old_calls(context):
    """描いたページの保存済みの本文から、古い日付の `&new` を外して保存し直す。"""
    if context.partial or not context.wiki_dir or not context.page:
        return
    done = getattr(context, "_new_dropped", None)
    if done is None:
        done = context._new_dropped = set()
    if context.page in done:
        return
    done.add(context.page)
    ref = resolve_page_ref(context.wiki_dir, context.page)
    if ref is None or not ref.exists:
        return
    source = ref.body or ""
    new_source = drop_old_calls(source, ref.ext)
    if new_source != source:
        save_page(context.wiki_dir, context.config, ref.subpath, ref.ext, new_source,
                  path=ref.path)


def _strip_bracket(name):
    name = (name or "").strip()
    if name.startswith("[[") and name.endswith("]]"):
        name = name[2:-2].strip()
    return name


def _page_link(page, label):
    return f'<a href="/{escape(page)}">{escape(label)}</a>'


def _latest(context, page):
    """ページ（末尾が `/` なら、その下で一番新しいもの）の (ページ名, 更新日時)。無ければ None。"""
    if page.endswith("/"):
        under = page.rstrip("/")
        items = [i for i in pagelist.walk(context.wiki_dir, under=under, need=PAGE_READ,
                                          privilege=context.privilege)
                 if i.pagepath.startswith(page) and i.updated]
        if not items:
            return None
        item = max(items, key=lambda i: i.updated)
    else:
        head = page.rsplit("/", 1)[0] if "/" in page else ""
        items = [i for i in pagelist.walk(context.wiki_dir, under=head, need=PAGE_READ,
                                          privilege=context.privilege)
                 if i.pagepath == page and i.updated]
        if not items:
            return None
        item = items[0]
    when = datetime.datetime.strptime(item.updated, "%Y-%m-%d %H:%M:%S").astimezone()
    return item.pagepath, when


def _inline(resolved, body, context):
    context.used_plugins.add("new")
    raw_page = resolved.get("page") or ""
    if body is not None and body.strip():
        if raw_page:
            raise PluginArgumentError("日付を書くときは、ページ名は書けません（&new(nodate){日付};）。")
        when = parse_date(body)
        if when is None:
            raise PluginArgumentError(f"日付として読めません: {body}")
        shown = "" if resolved.get("nodate") else escape(body)
        if _is_old(when, datetime.datetime.now().astimezone()):
            _drop_old_calls(context)   # 技術資料「古くなった日付の &new を外す」
        return f'<span class="comment_date">{shown}{mark_html(when)}</span>'

    name = _strip_bracket(raw_page)
    if "," in name:
        raise PluginArgumentError(f"ページ名は1つだけ書いてください: {name}")
    here = (context.page or "").strip("/")
    page = full_pagepath(here, name) if name else here
    if name.endswith("/") and not page.endswith("/"):
        page += "/"   # full_pagepath は末尾の / を落とす
    if not is_valid_pagepath(page.rstrip("/")):
        raise PluginArgumentError(f"ページ名が正しくありません: {name}")
    found = _latest(context, page)
    if found is None:
        if page.endswith("/"):
            raise PluginArgumentError(f"その下にページがありません: {page}")
        raise PluginArgumentError(f"そのページはありません: {page}")
    latest, when = found
    link = "" if resolved.get("nolink") else _page_link(
        latest, latest if page.endswith("/") else (name or latest))
    return link + mark_html(when)
