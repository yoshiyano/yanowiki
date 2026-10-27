"""助手に与える権限（`config/users.db` の `staff_perms` 表）。

管理者は何でもできる。助手（`staff` グループのメンバー）は、**権限ごとに、人ごとに**
管理者が与える・外すことができる。与える画面は `/.admin/staffperms`（管理者だけ。
`wikilib.staffpermsui`）。それまでは「管理者と助手」「管理者だけ」の二択で、助手には
一括で同じものが与えられていた。

    staff_perms(uidnum, perm, allowed)

    uidnum   助手のアカウント番号
    perm     権限の名前（`PERMS` のキー。`accounts.view` など）
    allowed  1 = 与える / 0 = 外す

## 既定は「それまでの状態」（`Perm.default`）

**表に行が無い権限は、`Perm.default` で決まる**。既定は、この仕組みを入れる前の
状態そのもの——助手が使えた画面は使え、管理者だけだった画面は使えない。そのため、
**表が空なら、動きはこれまでと変わらない**。新しく助手になった人も、既定から始まる。

行を持つのは**既定と違う設定だけ**。画面で既定と同じにして保存すると行は消える。
そのため、**あとから権限を増やしたとき（新しい `Perm` を足したとき）、行を持たない人には
その権限の既定が効く**。既定を変えるときは、行を持たない全員の動きが変わることに注意。

## 前提の権限（`Perm.needs`）

「アカウントを消す」は「アカウントの一覧を見る」が無いと意味がない（消す相手を選ぶ
画面を開けない）。そのような組には `needs` を書き、**前提が外れていれば、その権限も
効かない**ことにする（`resolve`）。画面の側でも、前提を外すと従属を外す・従属を付けると
前提も付ける、と揃える。矛盾した行（従属だけ許してある）が表にあっても、**効かない側
（厳しい側）**に倒れる。

## 設定できないもの（管理者だけ）

次は権限の表に載せない。**助手が自分に権限を足せてしまうため**。

- `/.admin/staffperms`（この設定の画面）
- 管理者のアカウント（`uidnum = 1`）の書き換え・削除。助手に `accounts.password` を
  与えても、**管理者のパスワードを書き換えて管理者になることはできない**
  （`accounts.can_modify`）

## 助手に権限を与えるときの注意

権限の中には、**与えると、それ以上の権限を間接的に得られる**ものがある。画面では
`Perm.warn` を添えて見せる。

- `accounts.password` … 相手のパスワードを書き換えて、その人になりすませる。
  すでに多くの権限を持つ助手になりすませば、自分に無い権限も使える
- `groups.staff` … 助手を増やせる。**新しい助手は既定の権限から始まる**ので、自分に無い
  権限を持つ助手を作れる（その助手のアカウントを自分で操作できる場合）

## 判定

**判定は `granted_set` 1つに集約**（人ごとに1回、DBを開く）。画面は
`wikilib.auth.can`（いまログインしている人）か、アカウントを渡す `granted` を使う。
未ログイン・助手でない人は何も持たない。DBが読めないときも**何も持たない側**に倒す。
"""
import sqlite3
from collections import namedtuple

from wikilib import groups, userdb

# 権限の1項目。
#   key      名前（DBに入る）。`<画面>.<操作>`
#   group    縦の見出し（画面ごとにまとめる）。`GROUPS` のキー
#   label    表に出す名前
#   default  既定（行が無いときの値）。**これまでの状態**
#   needs    前提の権限（すべて効いていなければ、この権限も効かない）
#   warn     与えるときの注意（空なら無し）
Perm = namedtuple("Perm", "key group label default needs warn")


def _p(key, group, label, default, needs=(), warn=""):
    return Perm(key, group, label, default, tuple(needs), warn)


# 縦に並べる見出し。(キー, 名前, 画面のURL)。URLは表の見出しの脇に出すだけ。
GROUPS = [
    ("accounts", "アカウント", ".admin/accounts"),
    ("approvals", "アカウントの承認", ".admin/approvals"),
    ("groups", "グループ", ".groups"),
    ("config", "Wikiの設定", ".admin/configwiki"),
    ("privileges", "アクセス制限", ".admin/privileges"),
    ("stafflog", "助手の操作の記録", ".admin/stafflog"),
    ("operations", "中断した操作", ".admin/operations"),
    ("themes", "テーマのファイル", ".admin/themes/"),
    ("garbagecollect", "削除したページの添付", ".garbagecollect"),
    ("site", "Wikiの作成・削除・一覧・再起動（起点Wikiだけ）", ""),
]

# 並べる順がそのまま依存の順（`needs` は先に出てきたものだけを指す。下で確かめる）。
# **既定の列は、この仕組みを入れる前の状態**: 助手が使えた画面は True、管理者だけの
# 画面は False。
PERMS = [
    _p("accounts.view", "accounts", "アカウントの一覧を見る", False,
       warn="パスワードのハッシュ値も一覧に出ます"),
    _p("accounts.add", "accounts", "アカウントを追加する", False, ("accounts.view",)),
    _p("accounts.rename", "accounts", "IDと名前を書き換える", False, ("accounts.view",)),
    _p("accounts.password", "accounts", "パスワードを入れ直す・ロックする", False,
       ("accounts.view",),
       warn="相手のパスワードを書き換えて、その人になりすませます。"
            "管理者のアカウントは助手には書き換えられません"),
    _p("accounts.delete", "accounts", "アカウントを消す", False, ("accounts.view",)),

    _p("approvals.approve", "approvals", "申請を承認する", True),
    _p("approvals.reject", "approvals", "申請を断る（アカウントを消す）", True),

    _p("groups.others", "groups", "助手グループ以外のグループを編集する", True),
    _p("groups.staff", "groups", "助手グループを編集する（助手を増やす・外す）", True,
       warn="新しい助手は既定の権限から始まります。自分に無い権限を持つ助手を作れます"),

    _p("config.view", "config", "設定を見る", True),
    _p("config.edit", "config", "設定の値を変える", True, ("config.view",)),
    _p("config.extrarules", "config", "定義ルール（書きかたの置き換え）を編集する", True,
       ("config.view",)),
    _p("config.rename", "config", "Wiki名を変える", True, ("config.view",)),

    _p("privileges.view", "privileges", "アクセス制限を見る", True),
    _p("privileges.edit", "privileges", "アクセス制限を書き換える", True, ("privileges.view",)),

    _p("stafflog.view", "stafflog", "助手の操作の記録を見る", False),
    _p("stafflog.undo", "stafflog", "助手の操作を元に戻す", False, ("stafflog.view",),
       warn="ほかの助手の操作も戻せます"),

    _p("operations.view", "operations", "中断した操作を見る", True),
    _p("operations.resume", "operations", "中断した操作の続きを行う", True,
       ("operations.view",)),

    _p("themes.view", "themes", "テーマのファイルを開き、共通のテーマを見る", True),
    _p("themes.slot", "themes", "スロット型のテーマ（slottheme）を編集する", True,
       ("themes.view",)),
    _p("themes.site.view", "themes", "Jinja2 のテーマ（sitetheme）を見る", False,
       ("themes.view",)),
    _p("themes.site.edit", "themes", "Jinja2 のテーマ（sitetheme）を編集する", False,
       ("themes.site.view",)),

    _p("garbagecollect.run", "garbagecollect", "削除したページの添付を集める", True),

    _p("site.newwiki", "site", "新しいWikiを作る", True),
    _p("site.delwiki", "site", "Wikiを消す", True),
    _p("site.allwiki", "site", "Wikiの一覧を見る", True),
    _p("site.restart", "site", "サービスを再起動する", True),
]

BY_KEY = {p.key: p for p in PERMS}
ALL_KEYS = frozenset(BY_KEY)
GROUP_NAMES = {key: name for key, name, _url in GROUPS}

# `needs` は先に出てきたキーだけを指し、見出しは `GROUPS` にあるものだけ（`resolve` が
# 並べた順に1回で解けるのは、これが守られているから）
_seen = set()
for _perm in PERMS:
    assert _perm.group in GROUP_NAMES, _perm.key
    assert all(n in _seen for n in _perm.needs), _perm.key
    _seen.add(_perm.key)
del _seen, _perm

# 「管理者だけ」の印（`adminui.TOOLS` が、設定できない画面に付ける）
ADMIN_ONLY = "admin"


def default_set():
    """既定で効いている権限（行が無い助手が持つもの）。"""
    return resolve({})


def resolve(overrides):
    """設定（`{キー: 真偽}`。無いキーは既定）から、**効く権限の集合**を作る。

    前提（`needs`）が効いていない権限は、設定が真でも効かない。知らないキーは無視。"""
    granted = set()
    for perm in PERMS:
        want = overrides.get(perm.key, perm.default)
        if want and all(n in granted for n in perm.needs):
            granted.add(perm.key)
    return frozenset(granted)


def check_keys(keys):
    """知らない権限の名前なら `KeyError`。**呼び出し側の書き間違いが、黙って
    「誰にも与えない」になるのを防ぐ**（画面の関門に誤字があっても気づけないため）。"""
    for key in keys:
        if key not in BY_KEY:
            raise KeyError(f"知らない権限です: {key!r}")


def _is_assistant_row(con, uidnum):
    return con.execute(
        "SELECT 1 FROM group_members WHERE gname = ? AND uidnum = ?",
        (groups.STAFF_GROUP, uidnum)).fetchone() is not None


def granted_set(wiki_dir, user):
    """そのアカウントが持つ権限の集合。**ここが判定の1か所。**

    管理者は全部（`ALL_KEYS`）。助手（`staff` のメンバー）は、設定と既定で決まる。
    それ以外・`None` は何も持たない。読めないときも何も持たない。

    `user` はアカウントの辞書（`uidnum` を持つもの）。"""
    if user is None:
        return frozenset()
    if userdb.is_admin(user):
        return ALL_KEYS
    uidnum = user.get("uidnum")
    if not uidnum:
        return frozenset()
    try:
        with userdb.connect(wiki_dir) as con:
            if not _is_assistant_row(con, uidnum):
                return frozenset()
            rows = con.execute("SELECT perm, allowed FROM staff_perms WHERE uidnum = ?",
                               (uidnum,)).fetchall()
    except (sqlite3.Error, OSError):
        return frozenset()
    return resolve({r[0]: bool(r[1]) for r in rows})


def granted(wiki_dir, user, key):
    """そのアカウントが権限 `key` を持つか。"""
    check_keys((key,))
    return key in granted_set(wiki_dir, user)


def overrides(wiki_dir, uidnum):
    """そのアカウントの設定（既定と違うものだけ）。`{キー: 真偽}`。"""
    try:
        with userdb.connect(wiki_dir) as con:
            rows = con.execute("SELECT perm, allowed FROM staff_perms WHERE uidnum = ?",
                               (uidnum,)).fetchall()
    except (sqlite3.Error, OSError):
        return {}
    return {r[0]: bool(r[1]) for r in rows if r[0] in BY_KEY}


def all_overrides(wiki_dir):
    """全助手の設定を1回で引く。`{uidnum: {キー: 真偽}}`（設定を持つ人だけ）。"""
    try:
        with userdb.connect(wiki_dir) as con:
            rows = con.execute("SELECT uidnum, perm, allowed FROM staff_perms").fetchall()
    except (sqlite3.Error, OSError):
        return {}
    found = {}
    for uidnum, perm, allowed in rows:
        if perm in BY_KEY:
            found.setdefault(uidnum, {})[perm] = bool(allowed)
    return found


def assistants(wiki_dir):
    """設定の対象になる助手（`staff` のメンバーのうち管理者を除く）。
    1件は `{"uid", "name", "uidnum", "joined_at"}`（`groups.members` と同じ形）。
    加わった順。"""
    return [m for m in groups.members(wiki_dir, groups.STAFF_GROUP)
            if m["uidnum"] != userdb.ADMIN_UIDNUM]


def save(wiki_dir, wanted):
    """助手ごとの権限を、`wanted` のとおりに保存する。

    `wanted` は `{uidnum: 与える権限のキーの集合}`。**含めた助手だけ**を直す
    （画面を開いたあとに増えた助手は触らない）。助手でない番号（管理者・一般の人）は
    無視する。前提を外した権限は外れる（`resolve`）。**既定と同じになった権限の行は消す。**

    変わった助手ごとの変更を、`[(uidnum, [付けた権限], [外した権限])]` で返す
    （画面の知らせと、`wikilib.adminlog` の記録に使う）。
    保存できなかった・変わらなかったときは空。"""
    changes = []
    try:
        with userdb.connect(wiki_dir) as con:
            for uidnum, keys in wanted.items():
                if uidnum == userdb.ADMIN_UIDNUM or not _is_assistant_row(con, uidnum):
                    continue
                before = resolve({r[0]: bool(r[1]) for r in con.execute(
                    "SELECT perm, allowed FROM staff_perms WHERE uidnum = ?", (uidnum,))})
                after = resolve({k: k in keys for k in BY_KEY})
                for perm in PERMS:
                    want = perm.key in after
                    if want == perm.default:
                        con.execute("DELETE FROM staff_perms WHERE uidnum = ? AND perm = ?",
                                    (uidnum, perm.key))
                    else:
                        con.execute(
                            "INSERT OR REPLACE INTO staff_perms (uidnum, perm, allowed)"
                            " VALUES (?, ?, ?)", (uidnum, perm.key, 1 if want else 0))
                if before != after:
                    changes.append((uidnum, [k for k in BY_KEY if k in after and k not in before],
                                    [k for k in BY_KEY if k in before and k not in after]))
            con.commit()
    except (sqlite3.Error, OSError):
        return []
    return changes
