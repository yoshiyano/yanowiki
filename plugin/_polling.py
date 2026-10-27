"""フォームの送信でページ本文を書き換えるプラグイン（`comment`・`vote`）の共有モジュール。
呼び出しごとの ID（個別化）と、ページを開いている間の差し替え（polling）を扱う。

`_` で始まるのでプラグインとしては読み込まれない。使う側は自分の `__file__` の隣を
`importlib.util.spec_from_file_location` で読み込む（`_srcscan.py` と同じ）。

    call_id(context, name, resolved_id) → 描いている呼び出しの ID（使えなければ None）
    find_call(context, text, ext, name, pid) → (呼び出し, None) か (None, 断り文)
    scan(context, text, ext)           → 保存されている本文の呼び出しの一覧
    wrap(html, context, name, pid)     → 描画範囲を印（`.poll-box` と `data-poll-*`）で包む
    handle(context)                    → 問い合わせ（`/.plugin/<name>?poll=1`）に答える
    fetch_only()                       → JS（fetch）からでない投稿を断る応答
    NEEDS_JS                           → 送信ボタンに付ける属性（JS が動くまで押せない）

## 呼び出しごとの ID の決まり（Wiki設計者の指示）

- 書き込み先は「ページの中で何番目の呼び出しか」ではなく、**呼び出しごとの ID で分ける**
  （2026-09-30。描かれない所 —— `#code` の本体・`#table` のセル —— に書いた呼び出しまで
  数えてずれていたため）。ID は呼び出しの名前付き引数 `id="…"` に書く。今後、呼び出しを
  個別に見分ける必要が出たら、この決まりを使う
- **ID は描画時に付ける**（2026-10-11「描画時なのは、余計なテキスト更新のステージを特別に
  用意する必要がないようにするためです。設計時からの思想です」）。ID の無い呼び出しを
  描いたら、本文へ書き足して保存する。本体は、描画の中で本文が書き換わったら新しい本文で
  最初から描き直す（2026-10-23、`views.render_page` と `pagesave.watch_writes`）ので、
  **ID の無いフォームが表示に出ることは無い**
- **ID の無い投稿はエラーにする**（2026-10-11）
- **別のページとの重なりは直さない**（2026-10-10）。書き込み先は `page` と ID の組で探す
- 同じページの中の重なりは、描画時に後から出てきたほうへ新しい ID を振り直す
  （2026-10-22「複雑にならない範囲」として残す）。古い ID の記録（`oldid`）・選択画面・
  通し番号は持たない（2026-10-22 に削除）
- 保存されただけでまだ描かれていない本文に同じ ID が重なっているときは、**最初に
  一致した呼び出し**を使う（2026-10-22。正しく描かれれば振り直されて戻り、整合しない
  場合は閲覧側の理解で解決する）
- ID が見つからない投稿は「該当フォームがなくなりました」で断る（2026-10-22）

## polling の決まり（Wiki設計者の指示、2026-10-22）

- 表示しているフォームの ID が保存されている本文にまだあるかを polling で確かめ、
  新しい投稿があれば取得して、いま表示しているフォームに反映する（ID が別の呼び出しに
  付け直されていれば、投稿する前に分かる）
- polling はプラグインごとではなく、**ページごとに1回**まとめて行う。`#include` で
  差し込んだページは、そのページごとに独立に扱う。知らない ID の情報は無視する。
  該当 ID が無ければ「該当フォームがなくなりました」
- 間隔は 5 分。表示が非アクティブの間は更新しない。アクティブに戻ったとき、十分に
  時間が経っていれば polling する。変化はプラグインの描画範囲だけを差し替え、
  変わっていなければ何もしない
- 受け口は、使うプラグインそれぞれが `_action` に持ち、処理の実体はここに置く。
  ID の扱いも同じモジュールにまとめる（2026-10-23）
- polling が要るプラグインかどうかを、プラグインの分類の基準にする
  （`PLUGIN_INFO["polling"]`。[PLUGIN_INFO](/Tech/dev_plugin/plugin_info)）
- JS が使えない環境では投稿を受け付けない（2026-10-20）
"""

""" 技術資料
## ID

- 形は「接頭語3文字＋ランダム5文字」（`cmtaB3xY`）。接頭語は `PREFIXES`。2026-10-22
  までは「接頭語＋通し番号1文字＋4文字」（`cmt0aB3x`）で、本文に残っている古い形も
  そのまま照合できる（引数の candidate は `[0-9A-Za-z_-]+`）
- 呼び出しの位置は、保存されている本文をページと同じパーサー（`render.parse_source`）で
  トークンにし、`plugin_block` の `map`（行の範囲）から拾う（`scan`）。本体をブロックとして
  展開するプラグイン（`expand_block`。`#note` など）の本体は、同じやりかたで中まで見る。
  展開しないもの（`#code` など）の本体と囲みコードは、パーサーがそもそも呼び出しに
  しないので外れる
- **`#table` のセルの中も見る**（2026-10-23、設計者の指示。セルがブロック要素を描くように
  なったため）。`#table` は `expand_block` を宣言せず、セルを自分で切るので、ここでも
  `table.py` と同じ切りかた（`|` で区切り、前後の空白と頭の目印 `~`・`CENTER:` などを除く）で
  セルに分け、セルの中身を同じやりかたで見る（`_table_cells`）。`tsv` の表はセルを
  インライン記法だけで描くので見ない。行の中の呼び出しは、セルの頭（`|`・`~`・`:`）の
  直後にあってもよい（`locate`。同じ行に `url:#comment` のような文字があると、何番目かの
  数えかたがずれうる。クロコの見立てで、実際には確かめていない）
- `call_id` は、引数の ID が保存されている本文の同じ名前の呼び出しにあるかだけを見る
  （描いた順の対応づけはしない。2026-10-23 まではしていた）。描いている本文が保存済みの
  ものと違う（ファイルを直接直して取り込んでいない、など）・走査が見ない場所に書かれて
  いる（自前で本体を展開するプラグインの中、など）と None になり、使う側は投稿できない
  フォームを出す
- 書き足しは、ページごとに最初の `call_id` で、`PREFIXES` の全部のプラグインの分を1度に
  保存する。保存の直前に本文が変わっていたら、読み直して振り直す（`_RETRY` 回）
- 部分プレビュー（`context.partial`）と、`context._callid_readonly` が立っている描画
  （`handle` の問い合わせ）では書き換えない
- メニュー（`mainmenu` など）の中の呼び出しも、本体がメニューページ自身を `page` にした
  `context` で描くので、普通に ID が付く（2026-10-05）。投稿先はメニューページ

## polling（クロコの実装例。設計者は E1〜E8 として示された案の実装を指示。2026-10-23）

- 対象は `PLUGIN_INFO["polling"]` を宣言したプラグイン（E1）。呼び出しの ID が要るので、
  `PREFIXES` にあるものに限られる
- 差し替える中身は、その呼び出しをプラグインの `_convert` でもう一度描いたもの（E2）。
  ページと同じ `call_plugin` を、問い合わせのページの `context` で呼ぶ。その描画では
  ID を書き足さない（`_callid_readonly`）
- 描画範囲の印は、ここが外から包む `<div class="poll-box">`（E3）。`data-poll-page`
  （書き込み先のページ）・`data-poll-id`・`data-poll-action`（問い合わせ先）・
  `data-poll-version`（描いたときの本文の版）を持つ。プラグインの出力の外にはみ出す
  部分（注意書きなど）も含めて差し替わるように、プラグイン自身ではなくここで包む。
  ID が決まらない呼び出し（投稿できないフォーム）と部分プレビューは包まない
- 版は保存されている本文（平文ファイル）のハッシュ。問い合わせの版が今と同じなら、
  描かずに `{"unchanged": true}` だけ返す（E5）
- 応答は `{"version": 版, "calls": {ID: {"html": …} | {"missing": true}}}`（E6）
- 閲覧の権限が無いページは、すべての ID を `missing` にする（E7）
- 書きかけの入力の引き継ぎ（E4）・投稿後の更新（E8）・間隔は `_polling.js`
- `_polling.js` は、`wrap` が `context.used_plugins` に `_polling` を足すことで
  `/.plugin/_polling.js` として読み込まれる（`calendar_.py` が `calendar` を足すのと同じ）
- JS が無い環境: 送信ボタンを `disabled` で描き（`NEEDS_JS`）、`_polling.js` が外す。
  `<noscript>` で「この環境では投稿ができません」と出す。`_action` 側は
  `X-Requested-With: fetch` の無い投稿を断る（`fetch_only`）
- 2026-10-23 までは ID の扱いを `_callid.py` に分けていた。使う側は必ず両方を読み込み、
  分けて得をする場面が無かったので、ここへまとめた（E9）
"""
import hashlib
import json
import random
import re
import string
import itertools
from html import escape

from bottle import HTTPResponse, request

from wikilib.auth import PAGE_NONE
from wikilib.pagedb import resolve_page_ref
from wikilib.pagesave import save_page
from wikilib.paths import PLUGIN_URLPATH, farm_plugin_dir, is_valid_pagepath
from wikilib.plugins import (PluginContext, build_markdown_renderer, call_plugin,
                             match_plugin_block, parse_plugin_args, parse_plugin_args_spans)
from wikilib.render import parse_source
from wikilib.web import plain

PREFIXES = {"comment": "cmt", "vote": "vot"}
ID_CHARS = string.digits + string.ascii_lowercase + string.ascii_uppercase
ID_LEN = 5
ID_ARG_RE = r"[0-9A-Za-z_-]+"  # 引数 id の candidate（手で書いた ID・古い形も受け取る）
GONE = "該当フォームがなくなりました（ページが編集された可能性があります）。"
NEEDS_JS = " disabled data-needs-js"
NOJS = "この環境では投稿ができません（JavaScript が必要です）。"
_MAX_DEPTH = 8
# `#table` のセルの区切り（`\|` は区切らない）と、セルの頭の目印（`table.py` と同じ）
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_CELL_STYLE_RE = re.compile(
    r"^(?:(LEFT|CENTER|RIGHT)|(BG)?COLOR\(([#\w]+)\)|SIZE\((\d+)\)):(.*)$", re.S)
_RETRY = 3
_MAX_IDS = 200


# ---- 保存されている本文から呼び出しを拾う ----

def _engine(context):
    engine = getattr(context, "_callid_engine", None)
    if engine is None:
        engine = build_markdown_renderer(context.config, farm_plugin_dir(context.wiki_dir))
        context._callid_engine = engine
    return engine


def _strip_counting(text):
    """前後の空白を除いた文字列と、先頭で除いた改行の数。"""
    stripped = text.lstrip()
    return stripped.rstrip(), text[:len(text) - len(stripped)].count("\n")


def _table_cells(body):
    """`#table` の本体（pukiwiki の書きかた）を、[(本体の中の開始行, セルの中身)] に分ける。
    切りかたは `table.py`（`_split_rows`・`_parse_cell`）と同じ。行の終わりの `|\\\\` や、
    行と行のあいだの `//`・`==` はセルの中身として残るが、呼び出しにはならない。"""
    cells = []
    pos = 0
    for m in itertools.chain(_CELL_SPLIT_RE.finditer(body), [None]):
        end = m.start() if m else len(body)
        line = body.count("\n", 0, pos)
        text, skipped = _strip_counting(body[pos:end].replace("\\|", "|"))
        line += skipped
        if text.startswith("~"):
            text, skipped = _strip_counting(text[1:])
            line += skipped
        while True:
            style = _CELL_STYLE_RE.match(text)
            if not style:
                break
            text, skipped = _strip_counting(style.group(5))
            line += skipped
        if text:
            cells.append((line, text))
        if m is None:
            break
        pos = m.end()
    return cells


def _is_tsv_table(args):
    positional, keyword = parse_plugin_args(args or "")
    return keyword.get("format") == "tsv" or "tsv" in (p.strip() for p in positional)


def _walk(text, ext, offset, engine, env, out, depth):
    """`text` の中の、描かれるブロックの呼び出しを `out` に足す（技術資料）。
    `offset` は `text` の1行目がページの何行目か。"""
    registry = getattr(engine, "plugin_registry", {}) or {}
    for tok in parse_source(engine, text, ext, env):
        if tok.type != "plugin_block" or tok.map is None:
            continue
        name = tok.meta.get("name")
        line = offset + tok.map[0]
        info = (registry.get(name) or {}).get("info") or {}
        if name in PREFIXES:
            out.append({"name": name, "line": line, "args": tok.meta.get("args"),
                        "body": tok.meta.get("body"), "body_error": tok.meta.get("body_error")})
        body = tok.meta.get("body")
        if not body or not body.strip() or depth >= _MAX_DEPTH:
            continue
        # 複数行の本体は次の行から、1行の本体（{…}）は同じ行の中
        start = line + 1 if tok.map[1] - tok.map[0] > 1 else line
        if name == "table" and not _is_tsv_table(tok.meta.get("args")):
            for cell_line, cell in _table_cells(body):
                _walk(cell, ext, start + cell_line, engine, env, out, depth + 1)
        elif info.get("expand_block"):
            _walk(body, ext, start, engine, env, out, depth + 1)


def locate(line, name, nth=0):
    """呼び出しの行の中で、`nth` 番目の `#name` の位置と引数を探す。見つからなければ None。

    {"pos": `#` の位置, "paren": 丸括弧があるか, "args": (開始, 終了)（丸括弧の中）,
     "tail": 閉じ括弧の後ろの位置, "id", "id_span"}"""
    # 行頭・空白・`>`（引用）・`{`（1行の本体）の直後。`#table` のセルの頭（`|`・見出しの
    # `~`・`CENTER:` などの `:`）の直後も
    found = list(re.finditer(r"(?<![^\s>{|~:])#" + re.escape(name) + r"(?![\w-])", line))
    if nth >= len(found):
        return None
    m = found[nth]
    pos = m.start()
    loc = {"pos": pos, "paren": False, "args": None, "tail": m.end(), "id": None, "id_span": None}
    if line[m.end():m.end() + 1] != "(":
        return loc
    parsed = match_plugin_block(line[pos:])
    if parsed is None:
        return None
    _name, args, _tail, a0, a1 = parsed
    loc.update(paren=True, args=(pos + a0, pos + a1), tail=pos + a1 + 1)
    _pos_args, kwargs = parse_plugin_args_spans(args)
    if "id" in kwargs:
        value, (s, e) = kwargs["id"]
        loc["id"] = value or None
        loc["id_span"] = (pos + a0 + s, pos + a0 + e)
    return loc


def scan(context, text, ext):
    """保存されている本文から、描かれる呼び出しを本文の順に返す。
    [{"name", "line", "args", "body", "body_error", "loc", "id"}]（行の中に見つからない
    ものは除く）"""
    out = []
    _walk(text, ext, 0, _engine(context), {"wiki": context}, out, 0)
    lines = text.split("\n")
    nth = {}
    calls = []
    for call in out:
        key = (call["line"], call["name"])
        k = nth.get(key, 0)
        nth[key] = k + 1
        loc = locate(lines[call["line"]], call["name"], k) if call["line"] < len(lines) else None
        if loc is None:
            continue
        call["loc"] = loc
        call["id"] = loc["id"]
        calls.append(call)
    return calls


# ---- ID を作る・書く ----

def new_id(prefix, taken):
    """まだ使われていない ID（接頭語＋ランダム5文字）。"""
    while True:
        pid = prefix + "".join(random.choice(ID_CHARS) for _ in range(ID_LEN))
        if pid not in taken:
            return pid


def rewrite_call(line, loc, pid):
    """呼び出しの `id` を `pid` にした行。無ければ書き足す。"""
    if loc["id_span"] is not None:
        s, e = loc["id_span"]
        return line[:s] + pid + line[e:]
    add = f'id="{pid}"'
    if loc["paren"]:
        a0, a1 = loc["args"]
        if line[a0:a1].strip():
            return line[:a1] + ", " + add + line[a1:]
        return line[:a0] + add + line[a1:]
    at = loc["tail"]
    return line[:at] + "(" + add + ")" + line[at:]


def _save(context, text, ref, changes):
    """`changes`（[(呼び出し, 新しい ID)]）を保存する。読んでから本文が変わっていたら
    何もせず False。1行に複数の呼び出しがあるときは右から書き換える。"""
    now = resolve_page_ref(context.wiki_dir, context.page)
    if now is None or not now.exists or (now.body or "") != text:
        return False
    lines = text.split("\n")
    for call, pid in sorted(changes, key=lambda c: (c[0]["line"], -c[0]["loc"]["pos"])):
        lines[call["line"]] = rewrite_call(lines[call["line"]], call["loc"], pid)
    return bool(save_page(context.wiki_dir, context.config, ref.subpath, ref.ext,
                          "\n".join(lines), path=ref.path))


# ---- 描くとき ----

def _load(context):
    """保存されている本文を読み、ID の無いもの・ページ内で重なったものに振って保存する。
    {"ids": {名前: ID の集合}, "saved": 保存できたか（振るものが無かった場合も含む）}"""
    st = {"ids": {}, "saved": True}
    ref = resolve_page_ref(context.wiki_dir, context.page)
    if ref is None or not ref.exists:
        return st
    text = ref.body or ""
    calls = scan(context, text, ref.ext)
    for call in calls:
        if call["id"]:
            st["ids"].setdefault(call["name"], set()).add(call["id"])
    if context.partial or getattr(context, "_callid_readonly", False):
        return st
    taken = {c["id"] for c in calls if c["id"]}
    seen = set()
    changes = []
    for call in calls:
        if call["id"] is not None and call["id"] not in seen:
            seen.add(call["id"])
            continue
        # ID が無い、または同じページの中の重なり（後から出てきたこちらを振り直す）
        pid = new_id(PREFIXES[call["name"]], taken)
        taken.add(pid)
        seen.add(pid)
        changes.append((call, pid))
    if changes:
        st["saved"] = _save(context, text, ref, changes)
    return st


def _page_state(context):
    """このページの呼び出しの ID。ページごとに最初に呼ばれたときに作る（ID を振って保存する）。
    振って保存したら、本体がこの描画を捨てて描き直すので、ここで覚えた ID は古いままでよい。"""
    states = getattr(context, "_callid_pages", None)
    if states is None:
        states = context._callid_pages = {}
    st = states.get(context.page)
    if st is None:
        for _ in range(_RETRY):
            st = _load(context)
            if st["saved"]:
                break
        states[context.page] = st
    return st


def call_id(context, name, resolved_id):
    """いま描いている `#name` の呼び出しの ID を返す（技術資料）。引数の ID が保存されている
    本文の `#name` の呼び出しに無ければ None（使う側は投稿できないフォームを出す）。"""
    resolved_id = resolved_id or None
    # トップ（`/=Wiki名/`）はページ名が空文字のまま index を描くので、None だけを見る
    if context.partial or not context.wiki_dir or context.page is None:
        return resolved_id
    st = _page_state(context)
    if resolved_id is None or resolved_id not in st["ids"].get(name, ()):
        return None
    return resolved_id


def version_of(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def _page_version(context):
    """`context.page` の保存されている本文の版（1回の描画の中ではページごとに1度だけ読む）。"""
    versions = getattr(context, "_polling_versions", None)
    if versions is None:
        versions = context._polling_versions = {}
    if context.page not in versions:
        ref = resolve_page_ref(context.wiki_dir, context.page)
        versions[context.page] = version_of(ref.body if ref is not None and ref.exists else "")
    return versions[context.page]


def wrap(html, context, name, pid):
    """プラグインの描画範囲 `html` を、polling の印で包む（技術資料）。"""
    if pid is None or context.partial or not context.wiki_dir or context.page is None:
        return html
    context.used_plugins.add("_polling")
    action = f"{context.base_url}/{PLUGIN_URLPATH}/{name}"
    attrs = (f'data-poll-page="{escape(context.page, quote=True)}" '
             f'data-poll-id="{escape(pid, quote=True)}" '
             f'data-poll-action="{escape(action, quote=True)}" '
             f'data-poll-version="{_page_version(context)}"')
    return (f'<div class="poll-box" {attrs}>{html}'
            f'<noscript><p class="poll-message">{NOJS}</p></noscript></div>')


# ---- 投稿・問い合わせを受けたとき ----

def find_call(context, text, ext, name, pid):
    """保存されている本文 `text` から、ID が `pid` の `#name` の呼び出しを探す。
    同じ ID が重なっていれば最初のもの。(呼び出し, None) か (None, 断り文) を返す。"""
    if not pid:
        return None, "このフォームからは書き込めません（ページを読み直してください）。"
    for call in scan(context, text, ext):
        if call["name"] == name and call["id"] == pid:
            return call, None
    return None, GONE


def fetch_only():
    """JS（`fetch`）からの投稿でなければ、断る応答を返す（技術資料）。そうでなければ None。"""
    if request.headers.get("X-Requested-With") != "fetch":
        return plain(NOJS, status=400)
    return None


def _json(data):
    return HTTPResponse(body=json.dumps(data, ensure_ascii=False), status=200,
                        content_type="application/json; charset=utf-8",
                        headers={"Cache-Control": "no-store"})


def handle(context):
    """polling の問い合わせに答える（`page`・`ids`（カンマ区切り）・`version`）。"""
    page = (request.query.getunicode("page", "") or "").strip("/")
    if page and not is_valid_pagepath(page):
        return plain("ページの指定が正しくありません。", status=400)
    ids = [i for i in (request.query.getunicode("ids", "") or "").split(",") if i][:_MAX_IDS]
    sent = request.query.getunicode("version", "") or ""

    def all_missing():
        return _json({"version": "", "calls": {i: {"missing": True} for i in ids}})

    if context.privilege.check(page) == PAGE_NONE:
        return all_missing()
    ref = resolve_page_ref(context.wiki_dir, page)
    if ref is None or not ref.exists:
        return all_missing()
    text = ref.body or ""
    version = version_of(text)
    if version == sent:
        return _json({"unchanged": True})

    sub = PluginContext(config=context.config, farm=context.farm, wiki_dir=context.wiki_dir,
                        page=page, base_url=context.base_url, ext=ref.ext)
    sub._callid_readonly = True
    sub._polling_versions = {page: version}
    engine = build_markdown_renderer(context.config, farm_plugin_dir(context.wiki_dir), sub)
    registry = getattr(engine, "plugin_registry", {}) or {}
    calls = [c for c in scan(sub, text, ref.ext)
             if ((registry.get(c["name"]) or {}).get("info") or {}).get("polling")]
    out = {}
    for pid in ids:
        call = next((c for c in calls if c["id"] == pid), None)
        if call is None:
            out[pid] = {"missing": True}
            continue
        out[pid] = {"html": call_plugin(sub, call["name"], call["args"], call["body"],
                                        "_convert", "#", body_error=call["body_error"])}
    return _json({"version": version, "calls": out})
