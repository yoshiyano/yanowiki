"""時間のかかるページの操作を、作業の手順のファイルに沿って行う（2026-10-01）。

名前の変更（`pagerename.rename_page`。移動も同じ）は、ページを動かしたあと、指していた
ページを1枚ずつ保存し直す。大きなWikiでは時間がかかり、途中で止まると、どこまで済んだか
分からない中途半端な状態が残る。Wiki設計者の指示:

- 「作業手順をファイル化し、作業がどこまで済んだかを記録して打ち切りタイムアウト処理。
  また続きができる状態にすること」
- 再開は、ファイル一覧（画面）と管理の画面から頼む。サーバーの起動時に自動では続けない
- 中断している操作と範囲が重なる名前の変更・移動・削除は断る。ページの編集は止めない
  （以上2つはクロコの案を設計者が了承、2026-10-01）

## 作業の手順のファイル

`pageinfo/operations/<ID>.json`（Wikiごと）。操作を始めるときに作り、手順が1つ進むたびに
書き直し、最後まで済んだら消す。中身:

    id, kind          操作の番号と種類（いまは "rename" だけ）
    actor             始めた人（ログインID。未ログインなら None）
    state             "running"（行っている／途中でサーバーが止まった）・"paused"（止めた）
    args, plan        頼まれた中身と、準備で決めたこと（動かすページの組など）
    done              済んだ手順の名前
    fixed             動いたページ自身のリンクを直した結果（本文のハッシュ。pagerename）
    fixed_count       リンクを直したページの数（何回に分けても数える）
    message           止めたときの知らせ

**手順はやり直してよい形にしてある**（再開すると、途中だった手順をもう一度行う）。
ファイル（`state` が "running" のまま残ったもの）は、サーバーが途中で止まったしるし。
そのときは DB の書き込み（まとめて最後に確定する。`bulkscope`）が失われているので、
ファイルの上の手順（ファイル・添付を動かす、アクセス制限の記録）だけを済みとして扱い、
ほかはやり直す（`resumable_done`）。

## 止める

止めるのは手順と手順の間、リンクを直すページとページの間だけ（手順の途中では止めない）。
止めるきっかけは、画面の［中止］（`Progress.cancelled`）と、1回で続ける時間の上限
（`TIME_LIMIT`。クロコの判断で 120 秒）。止めたら DB を確定し、ファイルを "paused" にして
知らせる。

## 進み具合

`Progress` を渡すと、手順・ページを数えて知らせる（`add_total`・`begin`・`advance`）。
ファイル一覧（`wikilib.filesui`）は、これを webFileDir のジョブの進み具合と［中止］につなぐ。
"""
import contextlib
import json
import os
import re
import threading
import time
import uuid

from wikilib.paths import farm_pageinfo_dir

OPS_DIR = "operations"
TIME_LIMIT = 120.0   # 1回で続ける時間の上限（秒）。超えたら止めて続きを残す（クロコの判断）
KIND_RENAME = "rename"
ID_RE = re.compile(r"^[0-9a-f]{32}$")

_locks = {}                 # Wikiごとの、操作を1つずつ行うための鍵
_locks_guard = threading.Lock()
_active = set()             # いま行っている操作の番号


class Progress:
    """進み具合と中止の受け渡し。既定は何も数えず、中止もしない。

    止めたときは、呼ばれた側が `paused` に手順のファイルの中身を入れる。"""

    paused = None

    def add_total(self, n):
        pass

    def begin(self, item):
        pass

    def advance(self):
        pass

    def cancelled(self):
        return False


class Stopped(Exception):
    """手順の境目で止めた（中止・時間切れ）。`reason` は "cancel" か "timeout"。"""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class Stopper:
    """止めるかどうかを確かめる。手順・ページの境目で `check()` を呼ぶ。"""

    def __init__(self, progress, limit=None):
        self.progress = progress
        self.deadline = time.monotonic() + (TIME_LIMIT if limit is None else limit)

    def check(self):
        if self.progress.cancelled():
            raise Stopped("cancel")
        if time.monotonic() > self.deadline:
            raise Stopped("timeout")


# ---- 手順のファイル -----------------------------------------------------------

def ops_dir(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, OPS_DIR)


def _path(wiki_dir, op_id):
    if not ID_RE.match(op_id or ""):
        return None
    return os.path.join(ops_dir(wiki_dir), op_id + ".json")


def new_op(wiki_dir, kind, actor, args, plan):
    """手順のファイルを作り、その中身を返す。"""
    now = time.time()
    op = {"id": uuid.uuid4().hex, "kind": kind, "actor": actor, "state": "running",
          "created": now, "updated": now, "args": args, "plan": plan,
          "done": [], "fixed": {}, "fixed_count": 0, "message": ""}
    save(wiki_dir, op)
    return op


def save(wiki_dir, op):
    """書き直す（途中で止まっても壊れたファイルを残さないよう、書いてから入れ替える）。"""
    op["updated"] = time.time()
    path = _path(wiki_dir, op["id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(op, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load(wiki_dir, op_id):
    path = _path(wiki_dir, op_id)
    if path is None or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def remove(wiki_dir, op_id):
    path = _path(wiki_dir, op_id)
    if path is not None and os.path.exists(path):
        os.remove(path)


def unfinished(wiki_dir):
    """済んでいない操作（行っているものも含む）。古いものから。"""
    directory = ops_dir(wiki_dir)
    if not os.path.isdir(directory):
        return []
    ops = []
    for name in os.listdir(directory):
        if name.endswith(".json"):
            op = load(wiki_dir, name[:-5])
            if op is not None:
                ops.append(op)
    return sorted(ops, key=lambda op: op.get("created", 0))


def is_active(op):
    return op["id"] in _active


def resumable_done(op):
    """再開するとき、済みとして飛ばしてよい手順。止めて（"paused"）残したものは記録どおり。
    サーバーが途中で止まったもの（"running" のまま）は、DB の書き込みが失われているので、
    ファイルの上の手順だけを済みとする（モジュール冒頭）。"""
    if op.get("state") == "paused":
        return set(op["done"])
    return set(op["done"]) & FILE_STEPS


# ファイルの上の手順（DB を使わないので、記録が残っていれば済んでいる）
FILE_STEPS = frozenset({"privileges_copy", "move", "attach"})


def _overlaps(a, b):
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def overlapping(wiki_dir, roots):
    """中断している（行っているものも含む）操作のうち、ページパスの範囲 roots と重なるもの。
    無ければ None。名前の変更・移動・削除を始める前に確かめる（設計者が了承した決まり）。"""
    for op in unfinished(wiki_dir):
        plan = op.get("plan") or {}
        mine = [r for r in (plan.get("old_root"), plan.get("new_root")) if r]
        if any(_overlaps(r, m) for r in roots for m in mine):
            return op
    return None


@contextlib.contextmanager
def running(wiki_dir, op):
    """op を行っているあいだ。同じWikiの操作は1つずつ行う（再開が重ならないように）。"""
    with _locks_guard:
        lock = _locks.setdefault(os.path.abspath(wiki_dir), threading.Lock())
    with lock:
        _active.add(op["id"])
        try:
            yield
        finally:
            _active.discard(op["id"])


def describe(op):
    """一覧に出す説明（「/A → /B」）。"""
    plan = op.get("plan") or {}
    return "/{} → /{}".format(plan.get("old_root", "?"), plan.get("new_root", "?"))


BUSY_MESSAGE = ("中断している名前の変更（{}）と範囲が重なるため、できません。"
                "先にその続きを済ませてください（ファイル一覧の「中断した操作を続ける」か、"
                "管理の画面の「中断した操作」）。")


def busy_message(op):
    return BUSY_MESSAGE.format(describe(op))
