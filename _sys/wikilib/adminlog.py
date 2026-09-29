"""管理操作の履歴（wikidata/<Wiki名>/log/admin.log.db）を書き残す。

`/.admin/accounts` の一覧操作（更新・削除）をAPI化するにあたり、**誰が・
どのアカウントに・何をしたか**を後から辿れるように積み上げる記録（Wiki設計者の
指示、2026-09-12。「サーバー側ではどのユーザが何を処理したかログを残す」）。

    adminlog(unixtime, actor_uid, cmd, target_uidnum, target_uid, ok, message)

    unixtime       いつ（UNIX時刻）
    actor_uid      誰が（そのAPI呼び出しのときログイン中だったuid）
    cmd            何を（"update" / "delete"）
    target_uidnum  対象アカウントの番号
    target_uid     対象アカウントのuid（削除後も読めるように、操作時点の値を残す）
    ok             成功したか
    message        userdb側が返した文言（失敗の理由など）

認証の照合結果を残す `wikilib.authlog` とは別物（**照合したかどうか**では
なく**何を書き換えたか**の記録）なので、ファイルも分ける
（`wikilib.paths.farm_admin_log_path` 参照）。
"""
import os
import sqlite3
import time

from wikilib.paths import farm_admin_log_path

TABLE = "adminlog"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    unixtime      INTEGER NOT NULL,
    actor_uid     TEXT    NOT NULL DEFAULT '',
    cmd           TEXT    NOT NULL DEFAULT '',
    target_uidnum INTEGER,
    target_uid    TEXT    NOT NULL DEFAULT '',
    ok            INTEGER NOT NULL,
    message       TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS {TABLE}_time ON {TABLE}(unixtime);
"""


def db_path(wiki_dir):
    return farm_admin_log_path(wiki_dir)


def record(wiki_dir, actor_uid, cmd, target_uidnum, target_uid, ok, message):
    """1件残す。**記録は積むだけで、消したり書き換えたりしない。**

    記録するほうは、無ければDBを作る（`wikilib.authlog.record` と同じ構え）。
    残せなかったとき（置き場所が書けないなど）は**黙って諦める**——記録が
    残らないことと、操作そのものが行えないことは別の話で、記録の都合で
    操作を止める理由が無い。"""
    path = db_path(wiki_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        con = sqlite3.connect(path)
        with con:
            con.executescript(SCHEMA)
            con.execute(
                f"INSERT INTO {TABLE} "
                "(unixtime, actor_uid, cmd, target_uidnum, target_uid, ok, message)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(time.time()), actor_uid or "", cmd or "",
                 target_uidnum, target_uid or "", 1 if ok else 0, message or ""))
        con.close()
        return True
    except (sqlite3.Error, OSError):
        return False
