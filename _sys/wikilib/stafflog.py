"""助手（staff）の操作の記録（wikidata/<Wiki名>/log/staff.log.db。Wiki設計者の指示、
2026-09-26）。

助手が何をしたかを管理者が把握し、間違えた操作を**元に戻す**ための材料を残す。
記録するのは**助手だけ**で、管理者の操作は記録しない（Wiki設計者の選択）。
確認と「元に戻す」は `/.admin/stafflog`（管理者だけ。`wikilib.stafflogui`）、
戻しかたは `wikilib.staffundo`。

    stafflog(id, unixtime, actor_uid, actor_uidnum, kind, target, summary,
             before, after, undone_at, undone_by, undo_note)

    kind      何をしたか（`KINDS` の名前。戻しかたもこれで決まる）
    target    何に対して（ページの実体パス・設定ファイル・グループ名など）
    before    操作の前の状態（JSON）。戻すときに書き戻す
    after     操作の後の状態（JSON）。戻す前に「いまもこのままか」を確かめる

## 記録するところ

画面ごとではなく、**実際に書き込む関数の側**で記録する（ページなら
`pagesave.save_page`、添付なら `attach` の各関数）。入口が増えても記録が
漏れないようにするため。記録するのは次がそろったときだけ（`actor`）。

- HTTPの要求の中である（取り込み・1時間ごとの後始末は記録しない）
- システムとして動いていない（`auth.act_as` の中ではない）
- ログインしている人が助手で、管理者ではない

## 入れ子の操作は1件にまとめる

改名はリンクを直すために他のページも保存し、`/.garbagecollect` は trashbox の
ページを作る。これらを別々に記録すると、ひとつの操作が何件にも分かれ、1件
だけ戻すと食い違う。外側の操作を `quiet()` で囲み、中の書き込みは記録しない。

## ファイルの控え

添付の上書き・削除のように、操作の前の中身がほかに残らないものは、ファイルを
`log/staff/<id>/` へ控える（`record(..., blobs=)`）。ページの本文は記録の中に
そのまま持つ。
"""
import contextlib
import contextvars
import hashlib
import json
import os
import shutil
import sqlite3
import time

from wikilib.paths import farm_log_dir

DB_NAME = "staff.log.db"
BLOB_DIR = "staff"
TABLE = "stafflog"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    unixtime     INTEGER NOT NULL,
    actor_uid    TEXT    NOT NULL DEFAULT '',
    actor_uidnum INTEGER,
    kind         TEXT    NOT NULL,
    target       TEXT    NOT NULL DEFAULT '',
    summary      TEXT    NOT NULL DEFAULT '',
    before       TEXT,
    after        TEXT,
    undone_at    INTEGER,
    undone_by    TEXT    NOT NULL DEFAULT '',
    undo_note    TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS {TABLE}_time ON {TABLE}(unixtime);
"""

# 操作の名前と、確認の画面での呼び名
KINDS = {
    "page.save": "ページの保存",
    "page.delete": "ページの削除",
    "page.rename": "ページの改名・移動",
    "attach.put": "添付の追加",
    "attach.delete": "添付の削除",
    "attach.rename": "添付の名前の変更",
    "attach.move": "添付の移動",
    "config.file": "設定の変更",
    "farm.rename": "Wiki名の変更",
    "privileges.page": "アクセス制限",
    "group.members": "グループ",
    "account.approve": "アカウントの承認",
    "account.reject": "アカウントの申請を断る",
    "garbagecollect": "削除したページの添付を集める",
    "wiki.create": "Wikiの作成",
    "wiki.delete": "Wikiの削除",
    "restart": "サービスの再起動",
}

_quiet = contextvars.ContextVar("stafflog_quiet", default=0)


def db_path(wiki_dir):
    return farm_log_dir(wiki_dir, DB_NAME)


def blob_dir(wiki_dir, entry_id):
    return farm_log_dir(wiki_dir, BLOB_DIR, str(int(entry_id)))


@contextlib.contextmanager
def quiet():
    """`with` の中の書き込みは記録しない（外側の操作が1件にまとめて記録する）。"""
    token = _quiet.set(_quiet.get() + 1)
    try:
        yield
    finally:
        _quiet.reset(token)


def _request_user(wiki_dir, farm):
    """いまの要求でログインしている人（成り代わり中・要求の外ならNone）。"""
    from wikilib import auth

    uid = auth.current_uid(wiki_dir, farm)
    if not uid or uid == auth.SYSTEM_UID:
        return None
    user = auth.current_user(wiki_dir, farm)
    if user is None or user["uid"] != uid:
        return None  # 成り代わっている
    return user


def actor(wiki_dir, farm=None):
    """記録すべき要求なら、操作している助手のアカウントを返す。そうでなければNone。

    **要求の外（取り込み・定期の後始末）・成り代わりの中・`quiet()` の中・
    管理者・助手でない人**はNone。判定の失敗は記録しない側に倒す（記録の都合で
    操作を止めない）。"""
    if _quiet.get():
        return None
    try:
        from wikilib import auth, userdb

        if farm is None:
            farm = os.path.basename(os.path.dirname(wiki_dir))
        user = _request_user(wiki_dir, farm)
        if user is None or userdb.is_admin(user) or not auth.is_staff(wiki_dir, user):
            return None
        return user
    except Exception:  # 要求の外（bottle の request が無い）など
        return None


def record(wiki_dir, user, kind, target, summary, before=None, after=None, blobs=None):
    """1件残す。記録の番号を返す（残せなければNone）。

    `blobs` は `{控えの名前: 元のファイルの場所}`。`log/staff/<番号>/` へ写す。
    **記録は積むだけで、戻したときも消さない**（`mark_undone` で印を付ける）。
    残せなかったときは黙って諦める（操作そのものは止めない。`adminlog` と同じ構え）。"""
    path = db_path(wiki_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        con = sqlite3.connect(path)
        with con:
            con.executescript(SCHEMA)
            cur = con.execute(
                f"INSERT INTO {TABLE} (unixtime, actor_uid, actor_uidnum, kind, target,"
                " summary, before, after) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (int(time.time()), user["uid"], user.get("uidnum"), kind, target or "",
                 summary or "", _dump(before), _dump(after)))
            entry_id = cur.lastrowid
        con.close()
    except (sqlite3.Error, OSError, TypeError, ValueError):
        return None
    for name, src in (blobs or {}).items():
        try:
            directory = blob_dir(wiki_dir, entry_id)
            os.makedirs(directory, exist_ok=True)
            shutil.copy2(src, os.path.join(directory, name))
        except OSError:
            pass
    return entry_id


def _dump(value):
    return None if value is None else json.dumps(value, ensure_ascii=False)


def _load(text):
    return None if text is None else json.loads(text)


def _row(row):
    entry = dict(row)
    entry["before"] = _load(entry["before"])
    entry["after"] = _load(entry["after"])
    return entry


def entries(wiki_dir, limit=100, offset=0, actor_uid=None):
    """新しいほうから返す。記録が無ければ空。"""
    path = db_path(wiki_dir)
    if not os.path.isfile(path):
        return []
    where, args = "", []
    if actor_uid:
        where, args = " WHERE actor_uid = ?", [actor_uid]
    try:
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        with con:
            rows = con.execute(
                f"SELECT * FROM {TABLE}{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                args + [int(limit), int(offset)]).fetchall()
        con.close()
    except sqlite3.Error:
        return []
    return [_row(r) for r in rows]


def count(wiki_dir, actor_uid=None):
    path = db_path(wiki_dir)
    if not os.path.isfile(path):
        return 0
    try:
        con = sqlite3.connect(path)
        with con:
            if actor_uid:
                n = con.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE actor_uid = ?",
                                (actor_uid,)).fetchone()[0]
            else:
                n = con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        con.close()
        return n
    except sqlite3.Error:
        return 0


def get(wiki_dir, entry_id):
    path = db_path(wiki_dir)
    if not os.path.isfile(path):
        return None
    try:
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        with con:
            row = con.execute(f"SELECT * FROM {TABLE} WHERE id = ?",
                              (int(entry_id),)).fetchone()
        con.close()
    except (sqlite3.Error, ValueError, TypeError):
        return None
    return _row(row) if row is not None else None


def mark_undone(wiki_dir, entry_id, by_uid, note=""):
    """戻したことを記録に書き添える。"""
    try:
        con = sqlite3.connect(db_path(wiki_dir))
        with con:
            con.execute(f"UPDATE {TABLE} SET undone_at = ?, undone_by = ?, undo_note = ?"
                        " WHERE id = ?", (int(time.time()), by_uid or "", note or "",
                                          int(entry_id)))
        con.close()
        return True
    except sqlite3.Error:
        return False


# ---- 記録を作るときに使う小道具 ---------------------------------------------

def file_sha(path):
    """ファイルの中身のハッシュ。無ければNone。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def read_text(path):
    """テキストファイルの中身。無ければNone。"""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def stash(wiki_dir, path):
    """操作で消える・上書きされるファイルを、操作の前に一時的に控える。控えの場所を返す。

    記録を作るときに `record(..., blobs={名前: 控え})` で記録の置き場へ写し、
    そのあと `drop` で消す。控えられなければNone（記録は残すが、中身は戻せない）。"""
    if not path or not os.path.isfile(path):
        return None
    try:
        directory = farm_log_dir(wiki_dir, BLOB_DIR, "tmp")
        os.makedirs(directory, exist_ok=True)
        dst = os.path.join(directory, "{}-{}".format(os.getpid(), time.time_ns()))
        shutil.copy2(path, dst)
        return dst
    except OSError:
        return None


def drop(path):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass
