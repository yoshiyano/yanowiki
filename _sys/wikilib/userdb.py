"""利用者アカウントの記録（wikidata/<Wiki名>/config/users.db）。

**ここが受け持つのは記録の読み書きだけ。** アカウントを持つこと、送られてきた
IDとパスワードがそのアカウントのものかを確かめること（`authenticate`）が範囲で、
**ログイン状態（cookieと合言葉）も権限の判断も持たない**——それは
`wikilib.auth` の受け持ち。合言葉の作りかた（`session_token`ほか）は以前ここに
あったが、「アカウントの記録」とは別の主題なのでそちらへ移した（Wiki設計者の指示、
2026-09-13のリファクタリング方針）。

## 表の形（Wiki設計者の指示、2026-09-05）

    passwd(uidnum PRIMARY KEY, uid, pw, name, approved, cnt)

    uidnum    内部の番号。主キー
    uid       ログインに使う名前（ログイン画面で入れるほう）
    pw        パスワードのハッシュ値（下記）
    name      画面に出す名前
    approved  承認済みか（1 / 0）。**0は承認待ち**（下記）
    cnt       ログイン状態の世代（整数。無い・空は0）。**上げると、いま持ち出されている
              合言葉がすべて通らなくなる**（`bump_cnt`。`wikilib.auth.session_token`
              が材料に混ぜる）。パスワードのハッシュ（`pw`）には**混ぜない**——
              生のパスワードを持たないので、混ぜると上げた瞬間に誰もパスワードで
              入れなくなる。
              **パスワードを変えたときは0に戻す**（`update_user`。合言葉には `pw` が混ざるので、
              変えた時点で旧い合言葉は通らない）

## 承認待ち（`approved`）

`account.policy` が `approval` のWikiでは、「アカウント作成」で作られたアカウントは
**承認待ち（`approved = 0`）**で始まり、助手か管理者が承認する（`set_approved`）まで
使えない（Wiki設計者の指示、2026-09-21）。承認待ちのアカウントは、ログインできず
（`wikilib.auth.verify_token`）、`g:all` にも入らない——**権限の上では未ログインと
同じ**。承認を取り消す（`approved = 0` に戻す）と、その場でログイン状態も効かなくなる。

**列は後から足したもの**なので、古いDBを開いたときは `connect` が列を足す
（`ALTER TABLE`。既存のアカウントはすべて承認済み＝`1`）。管理者が作るアカウント
（`/.admin/accounts`・`./wiki.py initusers` など）は、常に承認済み。

`uidnum = 1` に `admin` / `adminpw` / `管理者` を最初から入れておく。

## いつ作るか

**画面を開いても勝手には作らない**（Wiki設計者の指示、2026-09-05）。作るのは
次の2つのときだけ。

  - `/.newwiki` で新しいWikiを作ったとき（`wikilib.newwiki.create_wiki`）
  - `./wiki.py initusers =Wiki名` を実行したとき（既にあるWiki向け）

以前は、どの画面でも触れた時点で作っていた。**そうすると「誰でも開ける画面へ
アクセスした見ず知らずの相手が、既定のパスワードを持つ管理者アカウントを
そのWikiに生やす」**ことになる（しかもその値は一覧の画面に出る）。作るのを
明示的な操作だけに限って、この経路を塞いである。

記録が無いWikiでは、照合は必ず失敗し、一覧は「まだありません」と出る。

`uid` に使えるのは**半角の英数字だけ**（`check_uid`）。番号（`uidnum`）は
**いま残っている行の最大値 + 1** で決める（`next_uidnum`）。どちらも
Wiki設計者の指示（2026-09-05）。

## パスワードの持ちかたと、その弱さ

**生のパスワードは持たない。** `account.pw_salt` ＋ `uid` ＋ パスワードを、**`\\x00`（NUL）を
挟んで**連結し、SHA-1 でハッシュ化した値を `pw` に入れる（Wiki設計者の指示、2026-09-21）。

    pw = SHA-1( pw_salt + "\\x00" + uid + "\\x00" + パスワード )

- **`account.pw_salt` は設定 `account.pw_salt`（`default.yaml`）**。**書かなければ（空なら）
  Wiki名**。塩は秘密ではない。**別のWikiで同じID・同じパスワードでも、値が違う**ように
  するためのもの
- **IDが混ざる**ので、同じパスワードの人でも値が違う（表を1枚見ても「この2人は同じ
  パスワード」と分からない）
- **`\\x00` を挟むのは、境目を曖昧にしないため**。`uid` は半角英数字だけ（`check_uid`）で、
  画面から打てる文字にも `\\x00` は無い。素の連結だと `("a", "bc")` と `("ab", "c")` が
  同じ値になる（Wiki設計者の指示で、2026-09-21に区切りを入れた）
- **`pw_salt` を変えると、全アカウントのパスワードが通らなくなる**（生のパスワードは
  持っていないので作り直せない）。**Wiki名を変えるときは、旧名を `pw_salt` に固定して
  から移す**（`wikilib.farmrename`）。Wiki名を `pw_salt` に使う既定のままだと、
  名前を変えた全員のパスワードが通らなくなるため
- **IDを変えても通らなくなる**。`update_user` は、IDを変えるときはパスワードも付け直す
  ことを求める

**旧い形のハッシュは通さない**（Wiki設計者の指示、2026-09-21）。はじめは
`パスワード + "wiki"`（全員共通の固定文字列）、そのあと区切りなしの `塩 + uid + パスワード`
だったが、**どちらも照合しない**。**移行の仕組みも持たない**——旧い形のアカウントは、
管理者がパスワードを付け直すまでログインできない（`./wiki.py resetpw`、または
`/.admin/accounts` に `/.pwhash` で作った値を入れる）。

- **SHA-1 は速い。** パスワードを守るための関数ではなく、総当たりが安い。
  よくあるパスワードなら、手元のPCでも突き合わせられる（塩とIDが混ざる分、
  表1枚で全員を一度に解くことはできなくなった）
- **ハッシュ値を画面に出す**（アカウント一覧）ので、その画面に届く人には
  上の総当たりの入口が渡る

守りを強くするなら、意図的に遅い関数（`hashlib.pbkdf2_hmac` / `scrypt` など）へ移す。
**その差し替えが `hash_password` の1か所で済むように**、ハッシュの作りかたを知っているのは
この関数だけにしてある。
"""
import hashlib
import os
import re
import sqlite3

from wikilib.paths import farm_users_db_path
from wikilib.wikiconfig import account_pw_salt, load_wiki_config

# ハッシュの材料（塩・ID・パスワード）の区切り。**入力できない文字**（Wiki設計者の
# 指示、2026-09-21）。
HASH_SEPARATOR = "\x00"

# ログインに使う名前に使える文字（Wiki設計者の指示、2026-09-05）。**半角の英数字だけ。**
# `str.isalnum()` は使えない——あれは「あ」も真になるので、日本語のIDが
# 通ってしまう。範囲を書いた正規表現で見る。
UID_RE = re.compile(r"^[0-9A-Za-z]+$")

# ロックしたアカウントの `pw` に入れる値（Wiki設計者の指示、2026-09-06）。
# **ハッシュ値が入るはずのところに、ハッシュ値ではない文字列を置く**という
# 単純なやりかた。hash_password() は必ず40文字の16進を返すので、この値と
# 一致することはない＝どんなパスワードでも通らなくなる。
#
# 別に「ロック中」の欄を持たないので、**古いDBでもそのまま動く**。解除は
# 「ハッシュ値を入れ直す」——つまり /.admin/accounts でパスワードを付け直すこと
# で、あの画面は管理者しか開けない（＝解除できるのは管理者だけ）。
# /.passwd からは解除できない。あちらは「いまのパスワード」を照合するが、
# LOCKED と一致する入力は作れないため。
LOCKED_PW = "LOCKED"

ADMIN_UIDNUM = 1
ADMIN_UID = "admin"
ADMIN_PASSWORD = "adminpw"
ADMIN_NAME = "管理者"

SCHEMA = """
CREATE TABLE IF NOT EXISTS passwd (
    uidnum   INTEGER PRIMARY KEY,
    uid      TEXT NOT NULL,
    pw       TEXT NOT NULL,
    name     TEXT NOT NULL DEFAULT '',
    approved INTEGER NOT NULL DEFAULT 1,
    cnt      INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS passwd_uid ON passwd(uid);
CREATE TABLE IF NOT EXISTS group_members (
    gname     TEXT    NOT NULL,
    uidnum    INTEGER NOT NULL,
    joined_at INTEGER NOT NULL,
    PRIMARY KEY (gname, uidnum)
);
"""

# 助手グループの管理は `wikilib.groups`（`/.groups`。`group_members`表の
# `gname = "staff"`）に統合した（Wiki設計者の指示、2026-09-12。「助手の管理も
# 作成したグループと同様に扱う」）。以前ここにあった専用の表（`usergroup`）と
# 関数（`join_group`/`leave_group`/`is_assistant`/`is_staff`）は廃止した。


def farm_name(wiki_dir):
    """`wikidata/<Wiki名>/wiki` からWiki名を取り出す。"""
    return os.path.basename(os.path.dirname(os.path.normpath(wiki_dir)))


def password_salt(wiki_dir):
    """このWikiのパスワードの塩（設定 `account.pw_salt`。空ならWiki名）。"""
    return account_pw_salt(load_wiki_config(wiki_dir), farm_name(wiki_dir))


def hash_password(wiki_dir, uid, raw):
    """パスワードからハッシュ値を作る。**作りかたを知っているのはここだけ。**

    `account.pw_salt` ＋ `\\x00` ＋ `uid` ＋ `\\x00` ＋ パスワードを SHA-1 に通した
    16進表記を返す（Wiki設計者の指示、2026-09-21）。弱さと、強くするときの差し替え先、
    塩を変えると全員のパスワードが通らなくなることは、モジュール冒頭に書いてある。

    `uid` は**そのアカウントの、いまのID**（前後の空白を落としたもの）。"""
    joined = HASH_SEPARATOR.join((password_salt(wiki_dir), uid or "", raw))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def db_path(wiki_dir):
    return farm_users_db_path(wiki_dir)


NO_DB_MESSAGE = ("このWikiにはアカウントの記録がありません。"
                 "`./wiki.py initusers` で用意してください。")


def exists(wiki_dir):
    """このWikiにアカウントの記録があるか。"""
    return os.path.isfile(db_path(wiki_dir))


def connect(wiki_dir, create=False, password=None):
    """DBを開く。**無ければ作らない**（`FileNotFoundError`）。

    `create=True` のときだけ、フォルダごと作って表を用意し、`admin` を入れる。
    そのときの `password` は**作る人が決める**（Wiki設計者の指示、2026-09-08）。
    省略したときだけ、これまでどおり既定の `adminpw` になる——**既知の値が
    必ず1つ通る状態から始まってしまう**ので、省略できるのは行きがかり上の
    逃げ道であって、勧められる使いかたではない。「いつ作るか」はモジュール
    冒頭を参照。

    無いときに投げるのを `FileNotFoundError`（＝`OSError`）にしてあるのは、
    読み出しの関数がもともと `OSError` を「読めなかった」として空で返すため。
    **記録がまだ無いWikiは、中身が空のWikiと同じに見えればよい。**"""
    path = db_path(wiki_dir)
    if not create and not os.path.isfile(path):
        raise FileNotFoundError(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    # 古いDB（`approved` の列が無い）には列を足す。既存のアカウントは承認済み。
    # 毎回確かめるのは、DBを古いものに差し替えられた（復元など）場合も拾うため
    if "approved" not in {r[1] for r in con.execute("PRAGMA table_info(passwd)")}:
        con.execute("ALTER TABLE passwd ADD COLUMN approved INTEGER NOT NULL DEFAULT 1")
        con.commit()
    if "cnt" not in {r[1] for r in con.execute("PRAGMA table_info(passwd)")}:
        con.execute("ALTER TABLE passwd ADD COLUMN cnt INTEGER NOT NULL DEFAULT 0")
        con.commit()
    if create:
        con.execute(
            "INSERT OR IGNORE INTO passwd (uidnum, uid, pw, name) VALUES (?, ?, ?, ?)",
            (ADMIN_UIDNUM, ADMIN_UID,
             hash_password(wiki_dir, ADMIN_UID, password or ADMIN_PASSWORD), ADMIN_NAME))
        con.commit()
    return con


def create_db(wiki_dir, password=None):
    """アカウントの記録を用意する。(成否, 知らせる文言) を返す。

    **既にあれば何もしない**（中身は触らない）。新しいWikiを作るときと、
    `./wiki.py initusers` から呼ぶ。

    `password` は `admin` の最初のパスワード。**呼ぶ側が決めて渡す**
    （Wiki設計者の指示、2026-09-08）。省略すると既定の `adminpw` になるが、
    そのWikiは**誰でも知っている値で管理者に入れる**状態から始まるので、
    知らせる文言でもそのことを断っている。"""
    if exists(wiki_dir):
        return False, "アカウントの記録はすでにあります。"
    try:
        connect(wiki_dir, create=True, password=password).close()
    except (sqlite3.Error, OSError) as e:
        return False, f"用意できませんでした（{e}）。"
    if password:
        return True, (f"アカウントの記録を用意しました"
                      f"（{ADMIN_UID} / 入力されたパスワード）。")
    return True, (f"アカウントの記録を用意しました"
                  f"（{ADMIN_UID} / {ADMIN_PASSWORD}）。"
                  "**この値は誰でも知っています。** すぐに変えてください。")


def all_users(wiki_dir):
    """登録されているアカウントを uidnum 順で返す。"""
    try:
        with connect(wiki_dir) as con:
            return [dict(r) for r in con.execute(
                "SELECT uidnum, uid, pw, name, approved, cnt FROM passwd ORDER BY uidnum")]
    except (sqlite3.Error, OSError):
        return []


def get_user(wiki_dir, uidnum):
    """番号で1件引く。無ければNone。"""
    try:
        with connect(wiki_dir) as con:
            row = con.execute(
                "SELECT uidnum, uid, pw, name, approved, cnt FROM passwd WHERE uidnum = ?",
                (uidnum,)).fetchone()
    except (sqlite3.Error, OSError):
        return None
    return dict(row) if row is not None else None


def find_by_uid(wiki_dir, uid):
    """ログインに使う名前で1件引く。無ければNone。"""
    try:
        with connect(wiki_dir) as con:
            row = con.execute(
                "SELECT uidnum, uid, pw, name, approved, cnt FROM passwd WHERE uid = ?",
                (uid,)).fetchone()
    except (sqlite3.Error, OSError):
        return None
    return dict(row) if row is not None else None


def next_uidnum(wiki_dir):
    """次に使う番号。空なら1から。**いま残っている行の最大値 + 1**（Wiki設計者の
    指示、2026-09-05。管理用の表は別に持たない）。

    そのため、**いちばん大きい番号の人を消すと、その番号は次の人に回る**
    （途中の番号は空いたまま埋めない）。番号だけを手がかりに「誰だったか」を
    後から辿ることはできない、ということでもある。"""
    try:
        with connect(wiki_dir) as con:
            row = con.execute("SELECT MAX(uidnum) AS m FROM passwd").fetchone()
    except (sqlite3.Error, OSError):
        return 1
    return (row["m"] or 0) + 1


def check_uid(uid):
    """ログインに使う名前として使えるか。使えれば None、駄目なら理由を返す。

    **使えるのは半角の英数字だけ**（Wiki設計者の指示、2026-09-05）。空白・記号・
    日本語は通さない。ログインの入力欄に打つものなので、環境によって入り
    かたが変わる文字（全角/半角、日本語入力の切り替え）を持ち込ませない
    ほうが、入れたつもりで入らない事故が減る。"""
    if not uid:
        return "IDを入力してください。"
    if len(uid) > 64:
        return "IDが長すぎます（64文字まで）。"
    if not UID_RE.match(uid):
        return "IDに使えるのは半角の英数字だけです。"
    return None


def add_user(wiki_dir, uid, pw_hash, name, approved=True):
    """アカウントを1つ足す。(成否, 知らせる文言) を返す。

    `pw_hash` は **ハッシュ済みの値**（`hash_password` の戻り値）。生の
    パスワードをそのまま渡さないよう、名前で区別してある。

    `approved` を偽にすると**承認待ち**で足す（`account.policy` が `approval` の
    Wikiの「アカウント作成」。モジュール冒頭参照）。既定は承認済み。"""
    if not exists(wiki_dir):
        return False, NO_DB_MESSAGE
    problem = check_uid(uid)
    if problem:
        return False, problem
    if not pw_hash:
        return False, "パスワードのハッシュ値を入力してください。"
    if find_by_uid(wiki_dir, uid) is not None:
        return False, f"«{uid}» はすでに登録されています。"
    try:
        with connect(wiki_dir) as con:
            con.execute(
                "INSERT INTO passwd (uidnum, uid, pw, name, approved) VALUES (?, ?, ?, ?, ?)",
                (next_uidnum(wiki_dir), uid, pw_hash, name or "", 1 if approved else 0))
            con.commit()
    except (sqlite3.Error, OSError):
        return False, "登録できませんでした。"
    return True, f"«{uid}» を登録しました。"


def user_cnt(user):
    """アカウントの `cnt`（ログイン状態の世代）。**無い・空は0**。"""
    return int(user.get("cnt") or 0)


def bump_cnt(wiki_dir, uidnum):
    """`cnt` を1つ上げる。上げたあとのアカウントを返す（無い・書けないときはNone）。

    `session_token` に `cnt` が混ざっているので、**上げる前に作られた合言葉は
    すべて通らなくなる**。呼んだ側が今のセッションだけは残したいときは、
    返ったアカウントで合言葉を作り直して置き直す（`auth.do_revoke_others`）。"""
    try:
        with connect(wiki_dir) as con:
            con.execute("UPDATE passwd SET cnt = COALESCE(cnt, 0) + 1 WHERE uidnum = ?",
                        (uidnum,))
            con.commit()
    except (sqlite3.Error, OSError):
        return None
    return get_user(wiki_dir, uidnum)


def is_approved(user):
    """そのアカウントは承認済みか。`None`（居ない）は偽。

    **`approved` の列を持たない辞書は承認済みとして扱う**——古い形のまま持ち回された
    値を、承認待ちと取り違えて締め出さないため。"""
    if user is None:
        return False
    return bool(user.get("approved", 1))


def pending_users(wiki_dir):
    """承認待ちのアカウントを、古い順（uidnum順）で返す。"""
    return [u for u in all_users(wiki_dir) if not is_approved(u)]


def set_approved(wiki_dir, uidnum, approved=True):
    """承認する（`approved=False` なら承認を取り消す）。(成否, 知らせる文言) を返す。

    **`admin`（uidnum=1）の承認は取り消せない。** 管理者が居なくなるため
    （`delete_user` が `admin` を消さないのと同じ考えかた）。"""
    if not exists(wiki_dir):
        return False, NO_DB_MESSAGE
    current = get_user(wiki_dir, uidnum)
    if current is None:
        return False, "そのアカウントはありません。"
    if not approved and uidnum == ADMIN_UIDNUM:
        return False, f"«{ADMIN_UID}» の承認は取り消せません（管理者が居なくなるため）。"
    try:
        with connect(wiki_dir) as con:
            con.execute("UPDATE passwd SET approved = ? WHERE uidnum = ?",
                        (1 if approved else 0, uidnum))
            con.commit()
    except (sqlite3.Error, OSError):
        return False, "書き換えられませんでした。"
    return True, f"«{current['uid']}» を{'承認' if approved else '承認待ちに戻'}しました。"


def update_user(wiki_dir, uidnum, uid, pw_hash, name):
    """アカウントを1つ書き換える。(成否, 知らせる文言) を返す。

    `pw_hash` が空なら**パスワードは変えない**（一覧の画面で、変えるつもりの
    ない行のハッシュ値を消してしまう事故を避けるため）。

    **IDを変えるときは、パスワードも付け直してもらう。** ハッシュにIDが混ざっている
    ので（モジュール冒頭）、IDだけ変えてハッシュを据え置くと、そのアカウントの
    パスワードが誰にも通らなくなる。**ハッシュが空か、いまと同じ値のとき**は
    「付け直していない」として断る。"""
    if not exists(wiki_dir):
        return False, NO_DB_MESSAGE
    problem = check_uid(uid)
    if problem:
        return False, problem
    current = get_user(wiki_dir, uidnum)
    if current is None:
        return False, "そのアカウントはありません。"
    other = find_by_uid(wiki_dir, uid)
    if other is not None and other["uidnum"] != uidnum:
        return False, f"«{uid}» は他のアカウントが使っています。"
    if uid != current["uid"] and (not pw_hash or pw_hash == current["pw"]):
        return False, ("IDを変えるときは、パスワードも付け直してください"
                       "（パスワードのハッシュにIDが混ざっているため）。")
    try:
        with connect(wiki_dir) as con:
            # **パスワードが実際に変わるときは `cnt` を0に戻す。** 合言葉には `pw` が
            # 混ざっているので、変えた時点で旧い合言葉はすべて通らなくなり、
            # 世代を積んでおく意味がなくなる。同じハッシュで上書きしたときは
            # 戻さない（戻すと、取り消し済みの `cnt=0` 時代の合言葉が復活する）
            changed = bool(pw_hash) and pw_hash != current["pw"]
            con.execute(
                "UPDATE passwd SET uid = ?, pw = ?, name = ?, cnt = ? WHERE uidnum = ?",
                (uid, pw_hash or current["pw"], name or "",
                 0 if changed else user_cnt(current), uidnum))
            con.commit()
    except (sqlite3.Error, OSError):
        return False, "書き換えられませんでした。"
    return True, f"«{uid}» を書き換えました。"


def restore_user(wiki_dir, row):
    """消したアカウントを、**消す前の行のまま**（番号・ID・ハッシュ・名前・承認）
    入れ直す。(成否, 文言) を返す。助手の操作を元に戻すとき（wikilib.staffundo）
    だけに使う。番号かIDがすでに使われていれば断る（別の人に回っているため）。"""
    if not exists(wiki_dir):
        return False, NO_DB_MESSAGE
    if get_user(wiki_dir, row["uidnum"]) is not None:
        return False, f"番号 {row['uidnum']} はすでに別のアカウントが使っています。"
    if find_by_uid(wiki_dir, row["uid"]) is not None:
        return False, f"«{row['uid']}» はすでに登録されています。"
    try:
        with connect(wiki_dir) as con:
            con.execute(
                "INSERT INTO passwd (uidnum, uid, pw, name, approved, cnt)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (row["uidnum"], row["uid"], row["pw"], row.get("name") or "",
                 row.get("approved", 0), row.get("cnt", 0)))
            con.commit()
    except (sqlite3.Error, OSError):
        return False, "入れ直せませんでした。"
    return True, f"«{row['uid']}» を入れ直しました。"


def delete_user(wiki_dir, uidnum):
    """アカウントを1つ消す。(成否, 知らせる文言) を返す。

    **`admin`（uidnum=1）は消さない。** 全部消すと誰も管理できなくなるので、
    最後の1人になりうる既定のアカウントだけは残す。"""
    if not exists(wiki_dir):
        return False, NO_DB_MESSAGE
    if uidnum == ADMIN_UIDNUM:
        return False, f"«{ADMIN_UID}» は消せません（管理者が居なくなるため）。"
    current = get_user(wiki_dir, uidnum)
    if current is None:
        return False, "そのアカウントはありません。"
    try:
        with connect(wiki_dir) as con:
            con.execute("DELETE FROM passwd WHERE uidnum = ?", (uidnum,))
            # **グループからも消す。** 番号だけが残ると、あとで同じ番号が
            # 別の人に回ったときにその人が別のグループのメンバー（助手を
            # 含む）になってしまう
            con.execute("DELETE FROM group_members WHERE uidnum = ?", (uidnum,))
            con.commit()
    except (sqlite3.Error, OSError):
        return False, "消せませんでした。"
    return True, f"«{current['uid']}» を消しました。"


def reset_admin_password(wiki_dir, password):
    """管理者（`uidnum = 1`）のパスワードを入れ直す。(成否, 文言) を返す。

    `./wiki.py resetpw` から呼ぶ（Wiki設計者の指示、2026-09-08）。**画面からは
    戻れなくなった場合の逃げ道**——管理者がパスワードを忘れたときや、
    自分をロックしてしまったときに使う。`pw` を書き直すので、
    **ロックもこれで解ける**（ロックは `pw` が `LOCKED` なだけ）。

    `uid` と `name` は触らない。管理者の名前を変えて使っている場合に、
    パスワードを直したいだけで名前まで戻っては困るため。"""
    current = get_user(wiki_dir, ADMIN_UIDNUM)
    if current is None:
        return False, "管理者のアカウントがありません。"
    if not password:
        return False, "パスワードを入力してください。"
    try:
        with connect(wiki_dir) as con:
            con.execute("UPDATE passwd SET pw = ? WHERE uidnum = ?",
                        (hash_password(wiki_dir, current["uid"], password), ADMIN_UIDNUM))
            con.commit()
    except (sqlite3.Error, OSError) as e:
        return False, f"書き換えられませんでした（{e}）。"
    was_locked = is_locked(current)
    return True, (f"«{current['uid']}» のパスワードを入れ直しました。"
                  + ("ロックも解けました。" if was_locked else ""))


def is_admin(user):
    """このアカウントは管理者か（Wiki設計者の指示、2026-09-06）。

    **見るのは `uidnum` であって `uid` ではない。** 名前のほうは一覧の画面から
    書き換えられる（`update_user`）ので、`uid == "admin"` で見ると、名前を
    `admin` に変えるだけで管理者になれてしまう。番号のほうは主キーで、
    書き換える手立てを用意していないうえ、`uidnum = 1` は消せないように
    してある（`delete_user`）——**管理者の座はこの番号に紐づいている。**

    `None`（ログインしていない相手）を渡してよい。偽になる。"""
    return user is not None and user.get("uidnum") == ADMIN_UIDNUM


def is_locked(user):
    """このアカウントはロックされているか（`pw` が `LOCKED`）。

    `None` を渡してよい。偽になる。"""
    return user is not None and user.get("pw") == LOCKED_PW


def lock_user(wiki_dir, uidnum):
    """アカウントをロックする。(成否, 知らせる文言) を返す。

    **`pw` を `LOCKED` に書き換えるだけ**（Wiki設計者の指示、2026-09-06）。
    元のハッシュ値は消える——解除するときは、どのみち付け直してもらう
    （元に戻せると、ロックされた本人が元のパスワードで入れてしまう）。

    **`admin` も止める。** 例外にすると、そこだけ何回でも試せる入口が
    残る。ただし管理者が自分を締め出すと、画面からは戻れない
    （`Tech/Accounts/AuthLog` に記録を直す手順を書いてある）。"""
    current = get_user(wiki_dir, uidnum)
    if current is None:
        return False, "そのアカウントはありません。"
    if is_locked(current):
        return True, f"«{current['uid']}» はすでにロックされています。"
    try:
        with connect(wiki_dir) as con:
            con.execute("UPDATE passwd SET pw = ? WHERE uidnum = ?",
                        (LOCKED_PW, uidnum))
            con.commit()
    except (sqlite3.Error, OSError):
        return False, "ロックできませんでした。"
    return True, f"«{current['uid']}» をロックしました。"


def authenticate(wiki_dir, uid, raw_password):
    """送られてきたIDとパスワードを照合する。合っていればそのアカウント、違えばNone。

    **ロックされているアカウント（`pw` が `LOCKED`）は必ず落とす。**

    照合は `hmac.compare_digest` で行う。ハッシュ値の**先頭から何文字目まで
    合っていたか**が応答時間に出ないようにするため（`==` は違いが見つかった
    時点で止まるので、そこが漏れる）。

    **旧い形のハッシュは通さない**（Wiki設計者の指示、2026-09-21。モジュール冒頭）。"""
    import hmac

    if not uid or raw_password is None:
        return None
    user = find_by_uid(wiki_dir, uid)
    if is_locked(user):
        # ハッシュ値は40文字の16進なので «LOCKED» と一致することは無いが、
        # **止めていることを読める形に**しておく
        return None
    if user is None:
        # 居ない相手でも、居る相手と同じだけ手間をかける（在不在を時間で
        # 悟られないようにするため）
        hash_password(wiki_dir, uid, raw_password)
        return None
    if not hmac.compare_digest(user["pw"], hash_password(wiki_dir, user["uid"], raw_password)):
        return None
    return user
