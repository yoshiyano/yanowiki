"""グループの記録（`config/users.db` の `group_members` 表）。

**ここが受け持つのは記録の読み書きだけ。**「そのグループを編集してよいか」
などの権限の判断は`wikilib.auth`の受け持ち（プリンシパルの展開もあちら）。
以前はここに`expand_principal`/`can_edit`/`is_staff`があったが、「グループの
記録」とは別の主題なので移した（Wiki設計者の指示、2026-09-13のリファクタリング方針）。

**助手の管理も、この仕組みに統合してある**（Wiki設計者の指示、2026-09-12。
「助手の管理も作成したグループと同様に扱う」）。助手グループの名前は
`STAFF_GROUP`（`staff`）で、他のグループと同じ`group_members`表に入る。
かつての専用の表（`usergroup`）・専用の画面（`/.admin/staff`）は廃止した。

    group_members(gname, uidnum, joined_at)

    gname      グループ名（半角小文字・数字・ハイフン・アンダースコアのみ）
    uidnum     メンバーのアカウント番号
    joined_at  加わった時刻（UNIX時刻）

**グループの「存在」は、メンバーが1人以上いることで判断する。**
全員を外せばグループは消えたことになる。専用の「グループ一覧」の表は
持たない——`/.groups`の編集タブは、開きたいグループの名前を自分で入れて
開く作りにしている（Wiki設計者の指示、2026-09-12）。

## `staff` の特別さは「削除時の挙動」だけ（Wiki設計者の指示、2026-09-12）

`staff`は**あらかじめ作っておく**（Wiki作成時・`initusers`実行時に
`ensure_staff_group`で先に`admin`を1人加えておく）。それ以外は普通の
グループと同じ扱いで、`create_group`に`staff`専用の分岐は無い——**すでに
ある名前は作れない**という、他のグループにも効く決まりがそのまま
「`staff`は再利用できない」ことになる。

**特殊なのは、削除でメンバーが0人になったときだけ。** 消えたままにせず、
`remove_members`がその場で`admin`だけを含む状態に戻す（`ensure_staff_group`。
「staff が削除された場合に限り staff を再生成」）。呼ぶのは**予め作る2か所**
（`newwiki.create_wiki`・`wiki.run_initusers`）と**この削除の1か所**だけで、
読み取りのついでに保証する形は採らない（Wiki設計者の指示、2026-09-13。同じことを
あちこちで確かめる作りをやめ、単純なルールを保つ）。

アカウントの記録（`config/users.db`）そのものが無いWikiでは、
`userdb.connect` が `FileNotFoundError`（`OSError`のサブクラス）を投げる。
ここではそれを「空」として扱い、呼び出し側（`wikilib.groupsui`）で
`userdb.exists()` を見て案内文を出す（`wikilib.accounts` と同じ構え）。
"""
import re
import sqlite3
import time

from wikilib import userdb

# 半角の小文字・数字・ハイフン・アンダースコアだけ（Wiki設計者の指示、2026-09-12）。
# ログインID（`userdb.UID_RE`）の「半角英数字だけ」とは別に定めている——
# 大文字を許さないのは、URLの一部（`/.groups?group=…`）になっても
# 大小文字の違いで迷わないようにするため。
GNAME_RE = re.compile(r"^[a-z0-9_-]+$")

# 助手グループの名前（Wiki設計者の指示、2026-09-12。「助手グループは (staff) と
# する」）。旧`userdb.ASSISTANT_GROUP`（`"assistant"`）の後継。一般ユーザーは
# この名前でグループを作れない（`create_group`参照）。
STAFF_GROUP = "staff"

# **記録に持たず、計算で決まる特別なグループ**（Wiki設計者の指示、2026-09-21）。
#
#   all   すべての登録ユーザ（承認待ちを除く）。内容は編集できない
#   any   誰でも。**未ログインも含む**。内容は編集できない
#
# 権限の許可者として `g:all` `g:any` と書ける（`wikilib.auth.expand_principal`・
# `PagePrivilege`）。**この名前でグループを作れない**——作れると、`g:all` と書いた
# 権限がそのグループのメンバーだけに効くようになり、全員に開けたつもりの
# ページが閉じる（逆に、権限を書いたあとで同名のグループを作った相手に、書いた
# 覚えのない権限が渡る）。
ALL_GROUP = "all"
ANY_GROUP = "any"
VIRTUAL_GROUPS = (ALL_GROUP, ANY_GROUP)


def check_gname(gname):
    """グループ名として使えるか。使えれば `None`、駄目なら理由を返す
    （`wikilib.userdb.check_uid` と同じ形）。"""
    if not gname:
        return "グループ名を入力してください。"
    if not GNAME_RE.match(gname):
        return "グループ名は半角の小文字・数字・ハイフン(-)・アンダースコア(_)だけが使えます。"
    if gname in VIRTUAL_GROUPS:
        return f"«{gname}» は特別なグループの名前なので使えません。"
    return None


def exists(wiki_dir, gname):
    """そのグループにメンバーが1人以上いるか。"""
    try:
        with userdb.connect(wiki_dir) as con:
            row = con.execute(
                "SELECT 1 FROM group_members WHERE gname = ? LIMIT 1", (gname,)).fetchone()
        return row is not None
    except (sqlite3.Error, OSError):
        return False


def is_member(wiki_dir, gname, uidnum):
    """そのアカウント（`uidnum`）がそのグループの**直接の**メンバーか。

    `uidnum` に `None`（未ログイン）を渡してよい。偽になる。**これは
    「編集できるか」ではない。** admin・g:staffも編集できるという判断は
    `can_edit` を使うこと（このグループのメンバーかどうかだけを見たい
    ときだけ、こちらを使う）。"""
    if not uidnum:
        return False
    try:
        with userdb.connect(wiki_dir) as con:
            row = con.execute(
                "SELECT 1 FROM group_members WHERE gname = ? AND uidnum = ?",
                (gname, uidnum)).fetchone()
        return row is not None
    except (sqlite3.Error, OSError):
        return False


def create_group(wiki_dir, gname, creator_uidnum):
    """グループを1つ作り、作成者を加える。(成否, 文言) を返す。

    **既に存在するグループは作れない。** `staff`固有の特別扱いはここには
    無い——`staff`は他のグループと同じ`exists`判定を受けるだけ（Wiki設計者の
    指示、2026-09-12。「予め作る、存在する名前を再利用できない、staff が
    削除された場合に限り staff を再生成。とするだけです。特殊な点は
    削除時の挙動だけ」）。`staff`が常に「ある」のは、Wiki作成時・
    `initusers`実行時に`ensure_staff_group`で先に作っておくため
    （`wikilib.newwiki.create_wiki`・`wiki.run_initusers`参照）。それより
    前からある記録では、`expand_principal`が`"g:staff"`を展開する際にも
    同じ関数を呼んで補っている。"""
    problem = check_gname(gname)
    if problem:
        return False, problem
    if exists(wiki_dir, gname):
        return False, f"«{gname}» はすでに存在します。"
    try:
        with userdb.connect(wiki_dir) as con:
            con.execute(
                "INSERT INTO group_members (gname, uidnum, joined_at) VALUES (?, ?, ?)",
                (gname, creator_uidnum, int(time.time())))
            con.commit()
    except (sqlite3.Error, OSError):
        return False, "作れませんでした。"
    return True, f"«{gname}» を作りました。"


def groups_of(wiki_dir, uidnum):
    """そのアカウント（`uidnum`）が入っているグループの名前を、名前順のリストで返す。

    **1回の問い合わせでまとめて引く。** ページごとのアクセス権を大量に判定するとき
    （`wikilib.auth.PagePrivilege`）、許可者に `g:` が出てくるたびに `is_member` で
    問い合わせると、ページ数×規則数だけDBを開くことになるため。
    `uidnum` が無い（未ログイン）・記録が無いときは空リスト。"""
    if not uidnum:
        return []
    try:
        with userdb.connect(wiki_dir) as con:
            rows = con.execute(
                "SELECT gname FROM group_members WHERE uidnum = ? ORDER BY gname",
                (uidnum,)).fetchall()
        return [r[0] for r in rows]
    except (sqlite3.Error, OSError):
        return []


def members(wiki_dir, gname):
    """メンバーの一覧を返す。1件は `{"uid", "name", "uidnum", "joined_at"}`。
    無ければ（存在しないグループも含めて）空リスト。"""
    try:
        with userdb.connect(wiki_dir) as con:
            rows = con.execute(
                "SELECT p.uid AS uid, p.name AS name, p.uidnum AS uidnum,"
                " g.joined_at AS joined_at"
                " FROM group_members g JOIN passwd p ON p.uidnum = g.uidnum"
                " WHERE g.gname = ? ORDER BY g.joined_at", (gname,)).fetchall()
        return [dict(r) for r in rows]
    except (sqlite3.Error, OSError):
        return []


def member_rows(wiki_dir, gname):
    """メンバーの `[番号, 加わった時刻]` を番号順で返す（記録の突き合わせ用。
    wikilib.stafflog・staffundo）。"""
    try:
        with userdb.connect(wiki_dir) as con:
            rows = con.execute(
                "SELECT uidnum, joined_at FROM group_members WHERE gname = ?"
                " ORDER BY uidnum", (gname,)).fetchall()
        return [[r[0], r[1]] for r in rows]
    except (sqlite3.Error, OSError):
        return []


def set_member_rows(wiki_dir, gname, rows):
    """メンバーを `member_rows` の形のとおりに置き換える（元に戻すときに使う）。"""
    try:
        with userdb.connect(wiki_dir) as con:
            con.execute("DELETE FROM group_members WHERE gname = ?", (gname,))
            con.executemany(
                "INSERT INTO group_members (gname, uidnum, joined_at) VALUES (?, ?, ?)",
                [(gname, uidnum, joined) for uidnum, joined in rows])
            con.commit()
        return True
    except (sqlite3.Error, OSError):
        return False


def add_members(wiki_dir, gname, uids):
    """ユーザIDのリストをグループへ加える。

    `(加われたメンバーの情報のリスト, [uid, 理由]のリスト)` を返す。前者の
    1件は `{"uid", "name", "uidnum", "joined_at"}`（`members()` と同じ形。
    画面がその場でDOMに行を足せるように、追加できたぶんの詳細をそのまま
    返す）。**まとめて1回で処理するが、結果は1件ずつ分ける**（Wiki設計者の指示、
    2026-09-12。どのIDがなぜ加われなかったかを画面側で示せるようにする
    ため）。"""
    added, failed = [], []
    added_uids = set()
    now = int(time.time())
    try:
        with userdb.connect(wiki_dir) as con:
            for uid in uids:
                row = con.execute(
                    "SELECT uidnum, name FROM passwd WHERE uid = ?", (uid,)).fetchone()
                if row is None:
                    failed.append([uid, "そのIDは登録されていません。"])
                    continue
                already = con.execute(
                    "SELECT 1 FROM group_members WHERE gname = ? AND uidnum = ?",
                    (gname, row["uidnum"])).fetchone()
                if already is not None:
                    failed.append([uid, "すでにメンバーです。"])
                    continue
                con.execute(
                    "INSERT INTO group_members (gname, uidnum, joined_at) VALUES (?, ?, ?)",
                    (gname, row["uidnum"], now))
                added.append({"uid": uid, "name": row["name"], "uidnum": row["uidnum"],
                             "joined_at": now})
                added_uids.add(uid)
            con.commit()
    except (sqlite3.Error, OSError):
        failed += [[uid, "追加できませんでした。"] for uid in uids if uid not in added_uids]
    return added, failed


def remove_members(wiki_dir, gname, uidnums):
    """アカウント番号のリストをグループから外す。実際に外れた件数を返す。

    対象が`staff`で、外した結果メンバーが0人になった場合は、その場で
    `ensure_staff_group`を呼んで`admin`だけを含む状態に戻す（Wiki設計者の指示、
    2026-09-12。「staff が削除された場合は admin のみを追加したグループ
    として再登録」）。"""
    removed = 0
    try:
        with userdb.connect(wiki_dir) as con:
            for uidnum in uidnums:
                cur = con.execute(
                    "DELETE FROM group_members WHERE gname = ? AND uidnum = ?",
                    (gname, uidnum))
                removed += cur.rowcount
            con.commit()
    except (sqlite3.Error, OSError):
        pass
    if gname == STAFF_GROUP:
        ensure_staff_group(wiki_dir)
    return removed


def ensure_staff_group(wiki_dir):
    """`staff`グループが空（未作成、または全員抜けて消えた）なら、
    `admin`だけを含む状態に戻す。すでに1人以上いれば何もしない。"""
    if exists(wiki_dir, STAFF_GROUP):
        return
    try:
        with userdb.connect(wiki_dir) as con:
            con.execute(
                "INSERT OR IGNORE INTO group_members (gname, uidnum, joined_at)"
                " VALUES (?, ?, ?)",
                (STAFF_GROUP, userdb.ADMIN_UIDNUM, int(time.time())))
            con.commit()
    except (sqlite3.Error, OSError):
        pass

