"""`#readauth`・`#writeauth` の記録（`config/privileges.plugin`）のうち、もう
機能していない行を消す（`/.updatePageAuth`。Wiki設計者の指示、2026-09-25）。

プラグインは描画のときにしか記録を書かないので、**プラグインの行を本文から
消したページ・削除したページの記録は残り続ける**（制限が外れない）。ここで
記録を1行ずつ見て、そのページにもうプラグインの記述が無いものを消す。

    /.updatePageAuth            誰でも実行できる（結果は件数だけ）
    pagesync.start_watcher      1時間ごとの取り込みのあとにも、全Wikiで行う

## 「記述が残っていない」の判定

**本文の字面ではなく、そのページを実際に描いて決める。** 字面で探すと、囲み
コード・`<!-- -->`・他のプラグインの `{{ }}` の中をどう読むかを、プラグインとは
別にここで作り直すことになり、読み違えは必ず「消す」（＝制限を緩める）側に
働くため。描いて、`R` の行なら `readauth`、`W` の行なら `writeauth` が呼ばれた
か（`context.used_plugins`）を見る。

- 描くのは**編集中のプレビューと同じ扱い**（`partial=True`）。プラグインが
  記録を書き直したり、本文を先頭へ寄せ直したりしない（ここは消すだけ）
- **システム（`$sys`）として描く。** 実行した人が読めない `#include` 先の
  中身で結果が変わらないようにするため（読めないと呼ばれず、消してしまう）
- 描画で例外が出たページは**消さない**（判断がつかない。残るのは厳しい側）
- ページそのものが無ければ消す（削除・改名の残り物）

## 保存と同時に走ったとき

描いてから消すまでの間にページが保存され、プラグインの行が書き足されて
いると、消してはいけない行を消してしまう（記録が同じ内容ならプラグインは
ファイルに触らないので、あとから書き直されることもない）。そこで、**消す
直前に、記録のロックの中で本文が描いたときのままか確かめ**、変わっていれば
その行は残す。保存は本文を書いてから描く（＝記録を書く）ので、ロックの中で
本文が変わっていなければ、その後の保存の描画は必ずロックの後に来て、記録を
書き直す。

## 実行の回数

誰でも実行できるが、描き直しは重いので、**同じ人が1時間に10回まで**（超えたら
429）。ログインしていればWiki名とID、していなければWiki名とIPアドレスで数える。
**管理者と助手は数えない**（`auth.is_staff`）。数えた記録は一時フォルダの
`wikisystem-updatepageauth-<設置場所の要約>.json`（直近1時間ぶんだけ残す）。
`plugin/updateDB.py` の `force=1` と同じ作り。

結果に**ページ名は出さない**。誰でも実行できるので、出すと制限の付いたページの
名前が漏れる。
"""
import hashlib
import json
import os
import tempfile
import time

from bottle import request

from wikilib import auth, privilege_records
from wikilib.paths import farm_plugin_dir, resolve_page_ref
from wikilib.web import plain

try:
    import fcntl
except ImportError:  # Windowsなど。ロック無しで数える
    fcntl = None

# 記録の種類と、それを書くプラグイン
PLUGIN_OF_KIND = {privilege_records.READ: "readauth", privilege_records.WRITE: "writeauth"}

RUN_WINDOW = 60 * 60   # 数える幅（秒）
RUN_MAX = 10           # その幅の中で実行できる回数（管理者と助手は除く）
RUN_LOG = os.path.join(
    tempfile.gettempdir(),
    "wikisystem-updatepageauth-{}.json".format(
        hashlib.sha1(os.path.abspath(__file__).encode("utf-8")).hexdigest()[:12]))


def _used_plugins(wiki_dir, config, farm, ref):
    """そのページを描いて、呼ばれたプラグインの名前の集合を返す。描けなければNone。"""
    from wikilib.plugins import build_markdown_renderer
    from wikilib.render import render_source
    from wikilib.themes import make_plugin_context

    first_h1 = (config.get("markdown") or {}).get("first_h1_as_title", True)
    context = make_plugin_context(config, farm, wiki_dir, ref.pagepath,
                                  partial=True, ext=ref.ext)
    try:
        with auth.act_as(auth.SYSTEM_UID):
            engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
            render_source(engine, ref.body or "", ref.ext, first_h1, context)
    except Exception:
        return None
    return set(context.used_plugins)


def _body_of(wiki_dir, page):
    """いまの本文。ページが無ければNone。"""
    ref = resolve_page_ref(wiki_dir, page)
    return ref.body if ref is not None and ref.exists else None


def sweep(wiki_dir, config, farm):
    """機能していない記録を消す。`{"checked": 見た行数, "removed": 消した行数}`。"""
    entries = privilege_records.load_plugin(wiki_dir)
    stale = {}  # (ページ名, 種類) → 判定したときの本文（ページが無ければNone）
    used_by_page = {}
    for e in entries:
        page, kind = e["page"], e["kind"]
        ref = resolve_page_ref(wiki_dir, page)
        if ref is None:
            continue  # Wikiの外を指すような名前。判断しない
        if not ref.exists:
            stale[(page, kind)] = None
            continue
        if page not in used_by_page:
            used_by_page[page] = (ref.body, _used_plugins(wiki_dir, config, farm, ref))
        body, used = used_by_page[page]
        if used is not None and PLUGIN_OF_KIND.get(kind) not in used:
            stale[(page, kind)] = body

    removed = []

    def change(current):
        left = []
        for e in current:
            key = (e["page"], e["kind"])
            # 消す直前に、本文が判定したときのままか確かめる（冒頭「保存と同時に」）
            if key in stale and _body_of(wiki_dir, e["page"]) == stale[key]:
                removed.append(key)
                continue
            left.append(e)
        return left

    if stale and not privilege_records.rewrite_plugin_records(wiki_dir, change):
        removed = []
    return {"checked": len(entries), "removed": len(removed)}


def sweep_all(log=None):
    """全Wikiで `sweep` を行う（1時間ごとの取り込みのあと。pagesync.start_watcher）。"""
    from wikilib.pagesync import wiki_names
    from wikilib.paths import farm_wiki_dir
    from wikilib.wikiconfig import load_wiki_config

    for name in wiki_names():
        wiki_dir = farm_wiki_dir(name)
        if wiki_dir is None:
            continue
        try:
            result = sweep(wiki_dir, load_wiki_config(wiki_dir), name)
        except Exception:  # 1つのWikiの失敗で、ほかのWikiを止めない
            continue
        if log is not None and result["removed"]:
            log("機能していないページの権限の記録: [{}] {}件を消しました".format(
                name, result["removed"]))


def _count_run(key, now):
    """key の直近1時間の実行を数え、使えるなら記録してNone、だめなら断りの応答。"""
    fd = os.open(RUN_LOG, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as f:
        if fcntl is not None:
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            log = json.loads(f.read() or "{}")
        except ValueError:
            log = {}
        # 1時間より前の分は捨てる
        log = {k: [t for t in v if now - t < RUN_WINDOW] for k, v in log.items()}
        log = {k: v for k, v in log.items() if v}
        runs = log.get(key, [])
        if len(runs) >= RUN_MAX:
            wait = int(RUN_WINDOW - (now - runs[0]) + 59) // 60
            return plain("1時間に{}回までです。あと{}分ほどで使えます。".format(
                RUN_MAX, wait), status=429)
        log[key] = runs + [now]
        f.seek(0)
        f.truncate()
        json.dump(log, f)
    return None


def serve_update_page_auth(wiki_dir, config, farm, explicit_farm):
    """`/.updatePageAuth`。回数を数えてから `sweep` を行い、件数を返す。"""
    user = auth.current_user(wiki_dir, farm)
    if not auth.is_staff(wiki_dir, user):
        who = user["uid"] if user is not None else "ip:" + (request.remote_addr or "")
        refused = _count_run("{}\t{}".format(farm or "", who), time.time())
        if refused is not None:
            return refused
    result = sweep(wiki_dir, config, farm)
    return plain("ページの権限の記録: {}件を調べ、機能していない{}件を消しました。".format(
        result["checked"], result["removed"]))
