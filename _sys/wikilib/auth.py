"""**いま誰が入っていて、その人は何をしてよいか**を決める（画面は作らない）。

記録（`wikilib.userdb`・`wikilib.groups`）と画面（`wikilib.accounts` ほか）の
あいだに立つ層。ここが受け持つのは次の3つで、どれも「ログイン状態」という
1つの主題に属する（Wiki設計者の指示、2026-09-13のリファクタリング方針）。

    誰が入っているか   cookie 2つ（wikiuser_<Wiki名> / wikiauth_<Wiki名>）と
                       その照合
    何をしてよいか     プリンシパル（admin / g:<グループ名>）の展開と判定
    入る・出る操作     `#login` プラグインから呼ばれる do_login ほか

**画面は作らない。** 断りの画面（403）や一覧のHTMLは`wikilib.sysui`と各画面が
受け持つ。ここから呼ぶのは`themes.make_plugin_context`だけで、それも
`base_url`（cookieのPathと戻り先URLの組み立て）を得るためである。

## 権限は「プリンシパル」のリストで表す（Wiki設計者の指示、2026-09-12）

    admin           管理者（uidnum=1）そのひと1人
    g:<グループ名>  そのグループのメンバー全員
    g:all           すべての登録ユーザ（承認待ちを除く）。**内容は編集できない**
    g:any           誰でも。**未ログインも含む**。内容は編集できない

`g:all`・`g:any` は記録に持たず、その都度計算で決まる特別なグループ（Wiki設計者の
指示、2026-09-21。`wikilib.groups.VIRTUAL_GROUPS`）。この名前ではグループを作れない。

**この`g:XXXX`という書きかたは、グループ以外の場面でも今後使う**ため、
展開する部分を`expand_principal`/`expand_principals`として独立させてある。
判定は`allows`1つに集約し、画面は「自分に必要なプリンシパル」を宣言する
だけにした（`ADMIN_ONLY`/`STAFF`/`ANY_USER`）——以前は入口ごとに
`is_admin`・`is_staff`・`current_user is not None`と3通りの判定が散って
いたのを、1つの土台に乗せたもの（Wiki設計者の指示、2026-09-13。「個別対応を
少なくして共通化の土台に乗せる」）。

`ANY_USER`（空のリスト）は「絞り込む条件が無い＝ログインしていれば誰でも」。
特別な記号を足さず、リストが空かどうかで表している。

## 合言葉（wikiauth）の作りかたと、守れないこと

`uid` ＋ `wikiname` ＋ 日付番号 ＋ `pw`（保存されているハッシュ値）＋
この設置に固有の文字列（`site_secret`）＋ `cnt`（ログイン状態の世代）を連結して
SHA-1 にかけた値。**1日ごとに変わり、昨日のぶんまで通す**（`TOKEN_GRACE`）。

- **パスワードを変えると、持ち出された合言葉は通らなくなる**（材料に
  パスワードのハッシュが入っているため）
- **「他端末からの認証を解除する」（`do_revoke_others`）で取り消せる。** `cnt` を
  上げるので、それまでの合言葉はすべて通らなくなり、押した端末だけ作り直して残す
  （Wiki設計者の指示、2026-09-24）。サーバー側の控えは `cnt` の1つの数だけ
  で、**期限を待たずに切れるのは、この操作かパスワード変更のときだけ**
- **`wikiuser` だけでは何も認めない。** あちらは手で書き換えられる名前に
  すぎず、`wikiauth` と揃ってはじめて意味を持つ（`current_user`）

## cookieの名前はWikiごとに分ける

置く名前は `wikiuser_<Wiki名>` / `wikiauth_<Wiki名>`（`paths.wiki_cookie_name`）。
Pathでの分離だけに頼ると、Pathの付かない既定のWikiのcookieが他のWikiにも
送られ、同じ名前どうしで取り違えが起きる（同関数のdocstringに経緯）。

## ロックと、しばらく無視する仕組み（Wiki設計者の指示、2026-09-06）

パスワードでの照合は`try_password`1か所に集約してある（`#login`プラグイン
経由のログインと`/.passwd`の両方が通る）。回数の数えかた・無視する長さは
`wikilib.authlog`が持ち、ここはその判断に従って通す・通さないを決める。
"""
import contextlib
import contextvars
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import parse_qs, quote, urlsplit

from bottle import HTTPResponse, request

from wikilib import authlog, groups, privilege_records, userdb
from wikilib.paths import (
    LOGIN_AUTH_COOKIE, LOGIN_COOKIE, LOGIN_COOKIE_MAX_AGE, LOGIN_URLPATH, SECRET_LENGTH,
    SECRET_PATH, is_valid_pagepath, wiki_cookie_name,
)
from wikilib.themes import make_plugin_context
from wikilib.wikiconfig import account_policy, load_wiki_config

# ---- プリンシパル（誰を指すか） ---------------------------------------------

# 管理者を指す予約語。**`uid`の文字列一致ではなく番号で見る**——`uid`は
# 書き換えられる名前なので、それに頼ると管理者の名前を変えられたときに
# 権限の対象がずれてしまう（`userdb.is_admin`が`uidnum`で見るのと同じ理由）。
ADMIN_PRINCIPAL = "admin"
GROUP_PREFIX = "g:"
# 記録に持たない特別なグループ（モジュール冒頭参照）
ALL_PRINCIPAL = GROUP_PREFIX + groups.ALL_GROUP
ANY_PRINCIPAL = GROUP_PREFIX + groups.ANY_GROUP

# 画面が宣言に使う組み合わせ。**入口ごとに判定を書かず、これを渡す。**
ADMIN_ONLY = (ADMIN_PRINCIPAL,)
STAFF = (ADMIN_PRINCIPAL, GROUP_PREFIX + groups.STAFF_GROUP)
ANY_USER = ()   # 絞り込む条件が無い＝ログインしていれば誰でも

# ---- 合言葉（ログイン状態を持ち回る） ---------------------------------------

# 合言葉が変わる間隔（Wiki設計者の指示、2026-09-06）。**1日ごと。** ただし1つ前の
# ぶんも通す（TOKEN_GRACE）ので、毎日開いている人は入れ直しにならない。
TOKEN_PERIOD = 24 * 60 * 60
TOKEN_GRACE = 1  # いくつ前のぶんまで通すか。1 = 昨日のぶんまで
SECRET_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# 照合に失敗したときに待つ秒数（Wiki設計者の指示、2026-09-05）。総当たりの速度を
# 落とすのが目的なので、**画面側ではなくサーバー側で待つ**（画面側の待ちは
# 素通りできるため、待たせたことにならない）。
RETRY_DELAY = 1.0

# 結果をページのURLに付けて知らせる（`#login`プラグインがそれを見て文言を出す）
LOGIN_RESULT_KEY = "login"
LOGIN_RESULT_DONE = "done"      # 入れた
LOGIN_RESULT_NG = "ng"          # 通らなかった
LOGIN_RESULT_OUT = "out"        # 出た
LOGIN_RESULT_LOCK = "lock"      # ロックされている
LOGIN_RESULT_MADE = "made"      # アカウントを作った
LOGIN_RESULT_APPLIED = "applied"  # 申請した（承認待ち）
LOGIN_RESULT_PENDING = "pending"  # 承認待ちのアカウントでログインしようとした
LOGIN_RESULT_REVOKED = "revoked"  # 他の端末のログイン状態を取り消した


def site_secret():
    """この設置に固有の文字列（`config/secret.txt`）。無ければ作る。

    合言葉に混ぜるためのもので、**画面には出さない**。これがあると、
    アカウント一覧（`/.admin/accounts`）に届いてハッシュ値を読めた相手でも、
    合言葉そのものは作れない。

    紛らわしい字（`l` `1` `I` `0` `O`）は使わない。手で書き写す場面が
    あっても取り違えないため。"""
    try:
        with open(SECRET_PATH, encoding="utf-8") as f:
            kept = f.read().strip()
        if kept:
            return kept
    except OSError:
        pass
    made = "".join(secrets.choice(SECRET_ALPHABET) for _ in range(SECRET_LENGTH))
    try:
        os.makedirs(os.path.dirname(SECRET_PATH), exist_ok=True)
        # 他人に読ませない。作るときだけ気にすればよい（あとから直さない）
        fd = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(made + "\n")
    except FileExistsError:
        # 競争で先を越された。書けたほうを読み直す
        try:
            with open(SECRET_PATH, encoding="utf-8") as f:
                return f.read().strip() or made
        except OSError:
            return made
    except OSError:
        pass  # 置けなくても、その場では動く（次回また作りにいく）
    return made


def token_period(now=None, back=0):
    """いまが何日目か。**この値が変わると合言葉も変わる**＝1日ごとの更新。

    `back` はいくつ前のぶんを見るか。1 なら昨日ぶん（`verify_token` が使う）。"""
    return str(int((time.time() if now is None else now) // TOKEN_PERIOD) - back)


def session_token(uid, wikiname, pw_hash, now=None, back=0, cnt=0):
    """ログイン状態を持ち回るための合言葉（Wiki設計者の指示、2026-09-06）。

    材料と、それぞれを混ぜる理由はモジュール冒頭を参照。はじめの案は `pw` の
    **先頭2文字**だけを混ぜる形だったが、それだと推測すべき部分が256通りしか
    なく（uid・wikiname・日付番号はどれも公開情報）、サーバーに問い合わせる
    までもなく手元で総当たりできる。`pw` 全体と設置ごとの合言葉を混ぜる形に
    変えた（Wiki設計者の判断）。

    **`cnt`（そのアカウントのログイン状態の世代。`userdb.bump_cnt`）を最後に混ぜる**
    （Wiki設計者の指示、2026-09-24）。上げると、それまでに作られた合言葉は
    すべて通らなくなる＝**パスワードを変えずに、持ち出された分を取り消せる**。
    0のときも `\x00` ＋ `0` を混ぜる（無い・空は0として扱う）。"""
    joined = (uid + wikiname + token_period(now, back) + pw_hash + site_secret()
              + "\x00" + str(int(cnt or 0)))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def verify_token(wiki_dir, wikiname, uid, token, now=None):
    """持ち回られた合言葉を確かめる。合っていればそのアカウント、違えばNone。

    **今日のぶんと、昨日のぶんを通す**（Wiki設計者の指示、2026-09-06）。日付が
    変わった瞬間に全員が閉め出されては使いものにならないためで、通した側は
    呼び出し元が今日のぶんに置き換える（`remember_login`）。その結果、
    **毎日開いている人は入れ直しにならず、開かない日が続くとそこで切れる**。"""
    if not uid or not token:
        return None
    user = userdb.find_by_uid(wiki_dir, uid)
    if user is None or not userdb.is_approved(user):
        # 承認待ちは入れない。**承認を取り消したときも、持ち出された合言葉が
        # その場で効かなくなる**（`userdb.set_approved`）
        return None
    for back in range(TOKEN_GRACE + 1):
        want = session_token(user["uid"], wikiname, user["pw"], now, back,
                             userdb.user_cnt(user))
        if hmac.compare_digest(want, token):
            return user
    return None


# ---- いま誰が入っているか ---------------------------------------------------

def current_user(wiki_dir, wikiname):
    """cookieから、いまログインしている相手を取り出す。していなければNone。

    **2つが揃ってはじめて認める。** `wikiuser`（名前）は手で書き換えられる
    ので、それだけでは何も意味しない。`wikiauth`（合言葉）と突き合わせて、
    サーバー側で作り直した値と一致したときだけ通す（`verify_token`）。"""
    return verify_token(wiki_dir, wikiname,
                        request.get_cookie(wiki_cookie_name(LOGIN_COOKIE, wikiname)) or "",
                        request.get_cookie(wiki_cookie_name(LOGIN_AUTH_COOKIE, wikiname)) or "")


# ---- 成り代わり（システムとして動くとき） -----------------------------------

# システムとして動くときの名前（Wiki設計者の指示、2026-09-14）。`updatepage` などの
# コマンドや取り込み時の描画は、この名前に成り代わって読み書きする。判定器
# （`PagePrivilege`）はこの名前ならすべてのページで `W` を返す。
#
# **ログインIDとしては登録できない形にしてある。** ログインIDは英数字だけ
# （`userdb.UID_RE`）、許可者も英数字か `g:グループ名`（`privilege_records.WHO_RE`）
# なので、`$` を含むこの名前がアカウントや許可者と重なることは無い。cookie で
# `$sys` を名乗っても、アカウントの記録に無いので `verify_token` が通さない。
SYSTEM_UID = "$sys"

# 成り代わっている相手。**要求・スレッドごとに独立**（contextvars）で、新しく
# 立てたスレッドには引き継がれない——引き継ぎ漏れは「成り代わっていない」側、
# つまり権限の弱い側に倒れる。
_acting_as = contextvars.ContextVar("wikisystem_acting_as", default=None)


@contextlib.contextmanager
def act_as(uid):
    """`with` の中だけ、閲覧者を `uid` として扱う（Wiki設計者の指示、2026-09-14）。

        with auth.act_as(auth.SYSTEM_UID):
            ...   # この中では current_uid() が "$sys" を返す

    **成り代わりは明示したときだけ起きる。** 「要求が無いからシステム」と推し量る
    形にすると、画面から呼ばれた取り込み（名前の変更・`#updateDB`）が
    ログイン中の人の権限で動いてしまい、コマンドは未ログイン扱いになる
    （要求の外では cookie が読めず None になるため）。宣言し忘れた場合は
    成り代わらないので、読めるページが減る側に倒れる。

    入れ子にしてよい。抜けるときは（例外で抜けても）一つ外側の状態に戻す。
    `uid` は `SYSTEM_UID` かログインIDの形のものだけを受け付ける。書き間違い
    （`$system` など）を黙って「知らないユーザ」として通さないため。"""
    if uid != SYSTEM_UID and not (isinstance(uid, str) and userdb.UID_RE.match(uid)):
        raise ValueError(f"成り代われない名前です: {uid!r}")
    token = _acting_as.set(uid)
    try:
        yield uid
    finally:
        _acting_as.reset(token)


def acting_as():
    """いま成り代わっている相手。成り代わっていなければ None。"""
    return _acting_as.get()


def current_uid(wiki_dir, wikiname):
    """**いまの閲覧者**のログインID（システムへの問い合わせ窓口）。

    成り代わり中（`act_as`）ならその相手、そうでなければ cookie でログインして
    いる人、どちらでもなければ None（未ログイン）。ページごとの判定器
    （`page_privilege`）へ渡す名前は、ここから取る。"""
    uid = _acting_as.get()
    if uid is not None:
        return uid
    user = current_user(wiki_dir, wikiname)
    return user["uid"] if user else None


def remember_login(out, config, farm, wiki_dir, explicit_farm, user):
    """ログインできた相手を控える（Wiki設計者の指示、2026-09-06）。

    名前（`wikiuser`）と合言葉（`wikiauth`）の2つを置く。次からはこれで
    ログインを済ませられる。

    **ログインが通っている画面を出すたびに呼ぶ。** 合言葉は1日ごとに変わり、
    昨日のぶんまで通す作りなので、通ったその場で今日のぶんに置き換えないと、
    毎日開いている人でも2日で切れてしまう。`user` に None を渡してよい
    （何もしない）。

    **cookieは「返すHTTPResponse自身」に設定する。** bottleは、ハンドラが
    HTTPResponseを返した場合、スレッドローカルの `response` ではなく返された
    ほうを使う。`response.set_cookie(...)` と書くとSet-Cookieが落ちる
    （テーマのcookieで一度これに引っかかっている。wikilib.themes参照）。

    Pathはこのwikiの入口に限る。アカウントはWikiごとに別なので、隣のWikiへ
    持ち出されないようにするため。どちらも `httponly`——画面側のJavaScriptから
    読む用が無いうえ、合言葉のほうは読めてしまうと持ち出しが容易になる。"""
    if user is None:
        return
    path = _base_url(config, farm, wiki_dir, explicit_farm) or "/"
    token = session_token(user["uid"], farm, user["pw"], cnt=userdb.user_cnt(user))
    for base, value in ((LOGIN_COOKIE, user["uid"]), (LOGIN_AUTH_COOKIE, token)):
        out.set_cookie(wiki_cookie_name(base, farm), value, path=path,
                       max_age=LOGIN_COOKIE_MAX_AGE,
                       samesite="lax", httponly=True)


def forget_login(out, config, farm, wiki_dir, explicit_farm):
    """ログイン状態のcookieを捨てる（ログアウト）。

    **`Path` を置いたときと同じにしないと消えない。** cookieは名前とPathの
    組で決まるので、`/` で消しにいっても `/=<Wiki名>` に置いたものは残る。
    置く側（`remember_login`）と同じ求めかたにしてある。

    **これはブラウザ側から捨てるだけで、合言葉そのものは無効にならない。**
    サーバー側に控えを持たない作りなので、同じ値をもう一度送られれば通る
    （その日のうちは）。取り消したいときは「他端末からの認証を解除する」
    （`do_revoke_others`）か、パスワードを変える。"""
    path = _base_url(config, farm, wiki_dir, explicit_farm) or "/"
    for base in (LOGIN_COOKIE, LOGIN_AUTH_COOKIE):
        out.delete_cookie(wiki_cookie_name(base, farm), path=path)


def _base_url(config, farm, wiki_dir, explicit_farm):
    """このWikiの入口のURL。cookieのPathと戻り先の組み立てに使う。"""
    return make_plugin_context(config, farm, wiki_dir, "", explicit_farm).base_url


# ---- その人は何をしてよいか -------------------------------------------------

def expand_principal(wiki_dir, principal):
    """1つのプリンシパルを、実際のuidnumの集合に展開する（Wiki設計者の指示、
    2026-09-12。「g:XXXX とは XXXX に所属のユーザを展開したものを意味する。
    この表現は今後も利用するので、関数化してユーザ展開ができるように」）。

        "admin"          管理者（uidnum=1）そのひと1人
        "g:<グループ名>" そのグループのメンバー全員
        "g:all"          すべての登録ユーザ
        "g:any"          同じ（uidnumの集合には**未ログインを入れられない**ので、
                         登録ユーザ全員になる。未ログインを含めて判定するのは
                         `PagePrivilege`）

    どの形でもない文字列は空集合（安全側——書き間違いや未知の記法を、
    誰にでも当てはまるものとして扱わない）。"""
    if principal == ADMIN_PRINCIPAL:
        return {userdb.ADMIN_UIDNUM}
    if principal in (ALL_PRINCIPAL, ANY_PRINCIPAL):
        return {u["uidnum"] for u in userdb.all_users(wiki_dir) if userdb.is_approved(u)}
    if principal.startswith(GROUP_PREFIX):
        gname = principal[len(GROUP_PREFIX):]
        return {m["uidnum"] for m in groups.members(wiki_dir, gname)}
    return set()


def expand_principals(wiki_dir, principals):
    """複数のプリンシパルを展開した、和集合のuidnum集合を返す。"""
    found = set()
    for principal in principals:
        found |= expand_principal(wiki_dir, principal)
    return found


def allows(wiki_dir, farm, principals):
    """いまログインしている相手が、`principals` のどれかに当たるか。

    **判定はここ1つに集約してある**（Wiki設計者の指示、2026-09-13）。画面は
    `ADMIN_ONLY`/`STAFF`/`ANY_USER` のような組み合わせを渡すだけでよい。

    `principals` が空（`ANY_USER`）なら、**ログインしていればよい**
    ——絞り込む条件が無いという意味をそのまま使っている。"""
    user = current_user(wiki_dir, farm)
    if user is None:
        return False
    if not principals:
        return True
    return user["uidnum"] in expand_principals(wiki_dir, principals)


def is_staff(wiki_dir, user):
    """そのアカウントは管理者か助手か（＝`STAFF`に当たるか）。

    `allows`と違い、**cookieではなく渡されたアカウントで見る**（一覧の画面が
    行ごとに調べるなど、いまログインしている相手以外を問う場面のため）。
    `None` を渡してよい。偽になる。"""
    if user is None:
        return False
    return user["uidnum"] in expand_principals(wiki_dir, STAFF)


def can_edit_group(wiki_dir, gname, uidnum):
    """そのグループを編集できるか。**g:<グループ名>、admin、g:staff の誰か**
    （Wiki設計者の指示、2026-09-12。「foo グループの編集権は、g:foo, admin,
    g:staff とする」）。`gname`が`staff`自身のときも同じ式で計算される
    （結局`admin`と`g:staff`の合併になる）。"""
    if not uidnum:
        return False
    return uidnum in expand_principals(wiki_dir, (GROUP_PREFIX + gname,) + STAFF)


# ---- ページごとに何をしてよいか ---------------------------------------------

# `PagePrivilege.check` が返す値。記録ファイル（`config/privileges`）の1文字と同じ
PAGE_NONE = "-"
PAGE_READ = privilege_records.READ     # "R" 閲覧だけ
PAGE_WRITE = privilege_records.WRITE   # "W" 閲覧・編集


def _user_principals(wiki_dir, uid):
    """その人を指す許可者の名前の集合（ログインIDと、入っているグループの `g:名前`、
    それに `g:all`）。`g:any` は誰にでも当てはまるので、ここには入れない
    （呼び出し側が足す）。

    未ログイン・記録に無いID・ロックされたアカウント・承認待ちのアカウントなら None。**グループの
    所属は1回の問い合わせでまとめて引く**（`groups.groups_of`）——許可者に
    `g:` が出てくるたびに問い合わせると、ページ数×規則数だけDBを開くことになる。"""
    user = userdb.find_by_uid(wiki_dir, uid) if uid else None
    if user is None or userdb.is_locked(user) or not userdb.is_approved(user):
        return None
    names = {user["uid"], ALL_PRINCIPAL}
    names.update(GROUP_PREFIX + g for g in groups.groups_of(wiki_dir, user["uidnum"]))
    return names


# 緩さの度合い（`PagePrivilege.check` が system・plugin の答えを比べるのに使う）。
# 数字が大きいほど緩い——厳しいほうを選ぶときは、小さいほうを選べばよい
_ACCESS_LEVEL = {PAGE_NONE: 0, PAGE_READ: 1, PAGE_WRITE: 2}


def _build_tables(entries, principals):
    """1つの記録ソース（`privilege_records.load`／`load_plugin` の結果）を、
    種類（R/W）ごとに素早く引ける形にする（`_best` が読む。`PagePrivilege.__init__`
    が system・plugin それぞれに1回ずつ呼ぶ）。"""
    kinds = (privilege_records.READ, privilege_records.WRITE)
    exact = {k: {} for k in kinds}
    prefix = {k: {} for k in kinds}   # 長さ -> {先頭の文字列: 載っているか}
    suffix = {k: {} for k in kinds}   # 長さ -> {末尾の文字列: 載っているか}
    star = {k: None for k in kinds}   # 「*」だけの行（既定の行）。無ければ None
    for e in entries:
        listed = not principals.isdisjoint(e["who"])
        rule, kind = e["page"], e["kind"]
        if rule == privilege_records.WILDCARD:
            star[kind] = bool(star[kind]) or listed
            continue
        if rule.endswith(privilege_records.WILDCARD):
            table, literal = prefix[kind], rule[:-1]
        elif rule.startswith(privilege_records.WILDCARD):
            table, literal = suffix[kind], rule[1:]
        else:
            exact[kind][rule] = exact[kind].get(rule, False) or listed
            continue
        bucket = table.setdefault(len(literal), {})
        bucket[literal] = bucket.get(literal, False) or listed
    lengths = {k: sorted(set(prefix[k]) | set(suffix[k]), reverse=True) for k in kinds}
    return {"exact": exact, "prefix": prefix, "suffix": suffix, "star": star, "lengths": lengths}


def _best(tables, kind, page):
    """`(当たる行があるか, いちばん具体的な指定にその人が載っているか)`。

    **完全一致はワイルドカードより常に上**。ワイルドカード同士は `*` 以外の
    部分が長いほうが上で、同じ長さで前方一致と後方一致が両方当たれば
    合わせる（`Tech/Secret` に `Tech/*` と `*ecret` が当たる、など）。記録
    ファイルは保存のたびに並べ直すので、「あとの行が勝つ」は決めごとにできない。
    **`Tech/*` は `Tech` 自身にも当たる**（Wiki設計者の指示、2026-09-21。
    `privilege_records.matches`）。フォルダの指定（末尾が `/*`）は `/` までを含む長さで
    数えるので、ページ名に `/` を足した形（`Tech` → `Tech/`）でも引く。`Tech` だけ
    別に決めたいときは完全一致の行を書けばよい（完全一致が常に上）。

    **`*` だけの行（既定の行）は、いちばん下の行**（ほかの行が当たらないときだけ効く）。
    R と W を別々に判断するので、種類ごとにこの中で決まる。プラグインの記録には
    ワイルドカード・既定の行が無いので、そちらでは常に完全一致だけが当たる。"""
    listed = tables["exact"][kind].get(page)
    if listed is not None:
        return True, listed
    n = len(page)
    prefix, suffix = tables["prefix"][kind], tables["suffix"][kind]
    for length in tables["lengths"][kind]:
        if length > n + 1:
            continue
        hit = listed = False
        bucket = prefix.get(length)
        if bucket is not None:
            # 先頭 `length` 文字。フォルダの入口（`Tech`）は、`/` を足した `Tech/` で引く
            head = page[:length] if length <= n else page + "/"
            found = bucket.get(head)
            if found is not None:
                hit, listed = True, found
        bucket = suffix.get(length) if length <= n else None
        if bucket is not None:
            found = bucket.get(page[n - length:])
            if found is not None:
                hit, listed = True, listed or found
        if hit:
            return True, listed
    if tables["star"][kind] is not None:
        return True, tables["star"][kind]
    return False, False


class PagePrivilege:
    """1人の利用者について、ページごとの**アクセス権(R/W/-)**を返す判定器
    （Wiki設計者の指示、2026-09-14）。

        privilege = page_privilege(wiki_dir, uid)   # 下ごしらえはここで1回だけ
        privilege.check("Tech/Secret")              # → "W"

        PAGE_WRITE ("W")  閲覧・編集
        PAGE_READ  ("R")  閲覧だけ
        PAGE_NONE  ("-")  どちらも禁止

    `uid` はログインID。**未ログインなら None か空文字**を渡す。
    記録に無いIDやロックされたアカウントも、未ログインと同じに扱う。

    **1ページでも複数ページでも、判定器を作ってから `check` で聞く**
    （Wiki設計者の指示、2026-09-14。`page_mode`・`page_modes` はこの形に置き換えて
    消し、複数ページ用の `multi` も、`check` を回すだけなのでやめた）。

    ## アクセス権決めかた

    `config/privileges` の `R` の行と `W` の行を、**ページごとに別々に判断**する
    （Wiki設計者の指示、2026-09-21。それまでは「`W` は `R` を含む」で、`R` に載っていない
    人が `W` の行だけで読み書きできた）。

    各ページで、R の指定・W の指定が**あるか**を、当たる行（後述の「いちばん具体的な行」）
    で見る。ここでいう「指定がある」とは、そのページに当たる行が1つでもあること
    （既定の行 `*` も1つの行として数える）。

        読める   = R の指定が無い、または R の行に載っている
        書ける   = 読める、かつ（W の指定が無い、または W の行に載っている）

    答えは、書ければ `W`、読めるだけなら `R`、読めなければ `-`。

    **「書けるのは、読める人だけ」**（`R` が無ければ `W` も無い）。W の行に載っていても、
    R の行で読めない人には何も付かない。R の行が W の天井になる。
    **「指定が無い」側は誰にでも許す**ので、R も W も指定が無いページは誰でも読み書きできる
    （Wikiを作った直後はアカウントがまだ無く、誰も何も書けない状態から始まってしまうため）。

    | R の指定 | W の指定 | 答え |
    |---|---|---|
    | 無い | 無い | 誰でも `W`（未ログインも） |
    | 無い | ある | W に載っている人は `W`、それ以外は `R`（読めるだけ） |
    | ある | 無い | R に載っている人は `W`、それ以外は `-` |
    | ある | ある | R に載っている人のうち、W に載っている人は `W`、載っていない人は `R`。R に載っていない人は `-`（W に載っていても） |

    かつては設定 `edit.no_onlooker_permission` で締められたが、**Wiki設計者の
    指示（2026-09-21）で削除した**。締めたいWikiは、次の「既定の行」で書く。

    ## 既定の行（`*`）——Wikiを作るときに与える権限の既定値

    ページ名が `*` だけの行は、**いちばん具体さの低い行**として、R・W それぞれの
    既定になる（Wiki設計者の指示、2026-09-21。「Wiki構築時に権限のデフォルト値として
    与える仕組み」）。ふつうの行が当たるページでは、そちらが優先される。

        *:R:g:any        閲覧は誰でも（未ログインも）
        *:W:g:all        編集はログインしている登録ユーザだけ

    R と W を別々に判断するので、`Tech/Secret:R:alice` と `*:W:g:all` があるとき、
    `Tech/Secret` は「R は alice だけ（exact）、W は既定の g:all」——alice は `W`、
    ほかの人は読めないので `-`。**既定の行がひとつも無いWikiは、これまでの動き**
    （閲覧も編集も誰でも）。

    ## 許可者の書きかた

    ログインID、`g:<グループ名>`、それに記録に持たない特別なグループ2つ。

        g:all   登録ユーザ全員（承認待ちを除く）。未ログインは含まない
        g:any   誰でも。**未ログインも含む**

    未ログイン・記録に無いID・ロックされたアカウントは、`g:any` にだけ当たる。

    **1つのページに同じ種類の行が複数当たるとき**は、ページ名の指定が
    いちばん具体的なものを使う（`_best`）。`Tech/*` で広く絞り、
    `Tech/Secret` だけさらに絞る、という書きかたができる。

    ## 特殊ルール
    - 管理者・助手は常に閲覧編集権限を持つが、ここでの権限回答はアクセス権ルールに従う。
        ( 編集や表示のページで特別対応する。 )
    - `uid` が `SYSTEM_UID`（`$sys`）なら、規則にかかわらずすべてのページで `W`
      （Wiki設計者の指示、2026-09-14。システムは低水準の読み書きと同じくすべて許可）

    ## `config/privileges.plugin`（`#readauth`・`#writeauth`）との優先順位（2026-09-23）

    **プラグインが書き出す記録（`privilege_records.load_plugin`）も、手で書く
    `config/privileges` と同じ形で読む**（Wiki設計者の指示）。ただし対等ではない。

    - **プラグインは、システムの規則（`config/privileges`）より優先される。**
      同じページ・同じ種類でも、プラグインの記録があればそちらで決まる
    - **ただし、緩和する方向には働かない。** プラグインの記録があるせいで、
      システムの規則だけで判定したときより**答えが緩くなることはない**

    実装は、**system側・plugin側をそれぞれ独立に判定してから、答えが厳しいほうを
    採る**（`_check_with`。厳しい順は `-` > `R` > `W`）。この形なら「優先」と
    「緩和しない」の両方が同時に成り立つ——プラグインの記録がそのページ・その
    種類に無ければ、plugin側の判定は制限なし（`W`）になるので、system側の答えが
    そのまま通る（緩めなければ、優先させても実害が無い）。プラグインの記録が
    あれば、system側がどれだけ緩くても、plugin側がそれより厳しい答えを持ち込める
    （それが「優先」の中身）。一方、plugin側がsystem側より**緩い**答えを持って
    いても、厳しいほうを採る規則により採用されない（それが「緩和しない」の中身）。

    **プラグインの記録にワイルドカード・既定の行（`*`）は無い**（`plugin/
    _authcommon.py`。`#readauth`・`#writeauth` はページ名にワイルドカードが
    あれば断る）。plugin側の判定でも同じ `_build_tables`/`_best` を使うが、
    実際に当たるのは完全一致だけになる。

    ## なぜ速いのか

    **下ごしらえ（1回）**
        - 記録（`config/privileges`）を読むのは1回。利用者とその所属グループも
          1回で引く（`_user_principals`）
        - 利用者が決まっているので、各行は「その人が載っているか」の真偽1つに
          畳んでしまう。ページごとに許可者の集合を開く必要が無い
        - ページ名の指定を、完全一致の辞書と、**ワイルドカードの `*` 以外の
          部分の長さごとの辞書**（前方一致用・後方一致用）に振り分けておく

    **ページごと**
        - 完全一致は辞書を1回引くだけ
        - ワイルドカードは、長い順に「ページ名の先頭（末尾）をその長さで切り出して
          辞書を引く」。最初に当たった長さがいちばん具体的な指定になる。手間は
          **規則の数ではなく、長さの種類の数**で決まる

    実測（5000ページ、2026-09-14）で、1件ずつ判定器を作り直す形が1400〜6400ms
    だったのに対し、この形は規則10件で5ms・2000件でも13msだった。規則を1つずつ
    `startswith` で見る形は2000件で521ms、選択肢をつないだ正規表現は400件で458msと
    規則の数に比例して遅くなったので、採っていない。

    **記録の変更は、作り直すまで効かない。** 1回の要求（1つの画面・1回の検索）の
    あいだだけ使い、要求をまたいで持ち回らないこと。"""

    def __init__(self, wiki_dir, uid):
        # `$sys`（システム）は規則を見ずにすべて W。アカウントの記録も引かない
        self.system = uid == SYSTEM_UID
        found = None if self.system else _user_principals(wiki_dir, uid)
        self.logged_in = found is not None
        # 誰にでも当てはまる `g:any` は、未ログインも含めて全員が持つ
        principals = {ANY_PRINCIPAL} | (found or set())
        # system（手で書く config/privileges）と plugin（#readauth・#writeauth が
        # 書き出す config/privileges.plugin）を、別々の下ごしらえとして持つ
        # （クラスの説明「`config/privileges.plugin` との優先順位」参照）
        self._tables = _build_tables(privilege_records.load(wiki_dir), principals)
        self._plugin_tables = _build_tables(privilege_records.load_plugin(wiki_dir), principals)

    def _check_with(self, tables, page):
        """1つの記録ソース（system または plugin）だけで見た、1ページの答え。"""
        read_hit, read_listed = _best(tables, privilege_records.READ, page)
        write_hit, write_listed = _best(tables, privilege_records.WRITE, page)
        can_read = (not read_hit) or read_listed
        can_write = can_read and ((not write_hit) or write_listed)
        if can_write:
            return PAGE_WRITE
        if can_read:
            return PAGE_READ
        return PAGE_NONE

    def check(self, pagepath):
        """1ページのアクセス権（`PAGE_WRITE`・`PAGE_READ`・`PAGE_NONE`）。

        R と W を別々に判断し、**書けるのは読める人だけ**にする（クラスの説明の表）。
        system・plugin それぞれで判定し、**厳しいほうを答えにする**
        （クラスの説明「`config/privileges.plugin` との優先順位」参照）。"""
        if self.system:
            return PAGE_WRITE
        page = (pagepath or "").strip("/")
        system_result = self._check_with(self._tables, page)
        plugin_result = self._check_with(self._plugin_tables, page)
        # 緩さが低いほう（＝厳しいほう）を答えにする（クラスの説明を参照）
        return min(system_result, plugin_result, key=_ACCESS_LEVEL.get)


def _spec(rule):
    """ワイルドカードの具体さ（`_best`・`explain_privilege` と同じ並び順）。
    完全一致は常に上、ワイルドカード同士は `*` 以外の部分が長いほうが上。"""
    return (0, len(rule) - 1) if privilege_records.WILDCARD in rule else (1, len(rule))


def _matching_rule(rows, kind, page):
    """このページに当たる、その種類（R/W）の行。**ページ名と種類だけで決まり、
    誰が見るかには関係ない。** 同じ具体さで複数当たれば全部まとめて返す。指定が
    無ければ None。"""
    hits = [e for e in rows if e["kind"] == kind and privilege_records.matches(e["page"], page)]
    if not hits:
        return None
    top = max(_spec(e["page"]) for e in hits)
    chosen = [e for e in hits if _spec(e["page"]) == top]
    return {
        "rules": sorted({e["page"] for e in chosen}),
        "who": sorted({w for e in chosen for w in e["who"]}),
    }


def page_privilege_rules(wiki_dir, pagepath, rows=None):
    """このページに当たる R・W の指定（ページ名の指定と、書かれている許可者）。
    **誰が見るかには関係ない、ページだけで決まる情報。** `explain_privilege` の
    「当たった行」の部分を、利用者を問わず知りたいときに使う（`/.admin/privileges`
    の「アクセス権を評価する」、ページ名だけ入れたときの表向け。Wiki設計者の指示、
    2026-09-22）。

        page_privilege_rules(wiki_dir, "Tech/Secret")
        {"read": {"rules": […], "who": […]} or None, "write": {…} or None}

    `rows` に `privilege_records.load(wiki_dir)` の結果を渡すと、読み直さない
    （同じページを何人ぶんも判定するときの下ごしらえの使い回し。`explain_privilege`
    と同じ）。"""
    page = (pagepath or "").strip("/")
    if rows is None:
        rows = privilege_records.load(wiki_dir)
    return {"read": _matching_rule(rows, privilege_records.READ, page),
            "write": _matching_rule(rows, privilege_records.WRITE, page)}


def explain_privilege(wiki_dir, uid, pagepath, rows=None, plugin_rows=None):
    """1ページ・1人ぶんの判定を、**当たった行までさかのぼって**返す
    （`/.admin/privileges` の「アクセス権を評価する」向け。Wiki設計者の指示、2026-09-22）。

    `page_privilege(...).check(...)` と同じ決めかた（読める＝Rの指定が無いか、Rの行に
    載っている。書ける＝読める、かつWの指定が無いか、Wの行に載っている）だが、**大量の
    ページを速く判定するための下ごしらえ（`PagePrivilege`）は使わない**——1回の
    問い合わせにしか使わない評価フォームのために、当たった行のページ名の指定・
    書かれている許可者・どの許可者で通ったかまで返す、分かりやすさ優先の作り。

        explain_privilege(wiki_dir, "alice", "Tech/Secret")
        {
          "result": "W",       # PAGE_WRITE/PAGE_READ/PAGE_NONE。system・plugin
                                # のうち厳しいほう（PagePrivilege.checkと同じ）
          "logged_in": True,   # 記録に無いID・ロック中・未承認はFalse（未ログインと同じ扱い）
          "system": {"read": {…} or None, "write": {…} or None},   # config/privileges
          "plugin": {"read": {…} or None, "write": {…} or None},   # config/privileges.plugin
        }

    `system`/`plugin` それぞれの中身は、`_explain_for_principals` が返す1ソース
    ぶんの判定（`result`・`logged_in`・`read`・`write`）。`read`/`write` の中身
    （指定があるとき。「当たった行」の部分は `page_privilege_rules` と共通）:

        rules       当たった行のページ名の指定（同じ具体さで複数当たれば全部。並べ替え済み）
        who         その行に書かれている許可者（並べ替え済み）
        listed      その人が許可者に当たるか
        matched_by  当たった具体的な許可者（例: "alice"・"g:staff"・"g:any"）

    `rows`（`config/privileges`）・`plugin_rows`（`config/privileges.plugin`）は、
    どちらも `page_privilege_rules` と同じ（下ごしらえの使い回し）。"""
    page = (pagepath or "").strip("/")
    if rows is None:
        rows = privilege_records.load(wiki_dir)
    if plugin_rows is None:
        plugin_rows = privilege_records.load_plugin(wiki_dir)
    found = _user_principals(wiki_dir, uid) if uid else None
    logged_in = found is not None
    principals = {ANY_PRINCIPAL} | (found or set())
    return _explain_multi(wiki_dir, page, principals, logged_in, rows, plugin_rows)


def explain_privilege_generic(wiki_dir, pagepath, rows=None, plugin_rows=None):
    """**特別な立場を持たない、ふつうの認証済みユーザ**だったら何が許されるか
    （評価フォームの「一般の認証済みユーザ」向け。Wiki設計者の指示、2026-09-23）。

    実在のアカウントを1つ選ぶ代わりに、**`g:all`・`g:any` にだけ当たる**という架空の
    立場で判定する。管理者でも助手でもなく、個別に名指しされた許可者（`"alice"` など）にも、
    カスタムグループ（`"g:editors"` など）にも当たらない。

    **未登録のIDとは違う。** 未登録のIDは未ログインと同じ扱い（`g:any` にしか当たらない）
    だが、ここは「ログインはしているが、特別な立場は何も無い」という状態を表す
    （`g:all` にも当たる）。登録ユーザが増えても、rules に個別の名前やカスタムグループが
    書かれていないかぎり、答えはこの関数の結果と一致する。

    返り値の形・`rows`/`plugin_rows` は `explain_privilege` と同じ。"""
    page = (pagepath or "").strip("/")
    if rows is None:
        rows = privilege_records.load(wiki_dir)
    if plugin_rows is None:
        plugin_rows = privilege_records.load_plugin(wiki_dir)
    return _explain_multi(wiki_dir, page, {ANY_PRINCIPAL, ALL_PRINCIPAL}, True, rows, plugin_rows)


def _explain_multi(wiki_dir, page, principals, logged_in, rows, plugin_rows):
    """system（`config/privileges`）・plugin（`config/privileges.plugin`）を
    それぞれ独立に判定し、**厳しいほうを最終結果にする**——実際のアクセス制御
    （`PagePrivilege.check`）と同じ考えかた（クラスの説明「`config/privileges.
    plugin` との優先順位」参照）。"""
    system = _explain_for_principals(principals, logged_in,
                                     page_privilege_rules(wiki_dir, page, rows=rows))
    plugin = _explain_for_principals(principals, logged_in,
                                     page_privilege_rules(wiki_dir, page, rows=plugin_rows))
    result = min(system["result"], plugin["result"], key=_ACCESS_LEVEL.get)
    return {"result": result, "logged_in": logged_in, "system": system, "plugin": plugin}


def _explain_for_principals(principals, logged_in, rules):
    """`explain_privilege`・`explain_privilege_generic` が共有する、判定の中身。
    `principals`（その人を指す許可者の名前の集合）と `rules`（`page_privilege_rules` の
    戻り値）から、`explain_privilege` と同じ形の辞書を組み立てる。"""
    def side(rule):
        if rule is None:
            return None
        matched_by = sorted(principals & set(rule["who"]))
        return {**rule, "listed": bool(matched_by), "matched_by": matched_by}

    read = side(rules["read"])
    write = side(rules["write"])
    can_read = read is None or read["listed"]
    can_write = can_read and (write is None or write["listed"])
    result = PAGE_WRITE if can_write else (PAGE_READ if can_read else PAGE_NONE)
    return {"result": result, "logged_in": logged_in, "read": read, "write": write}


def page_privilege(wiki_dir, uid):
    """その利用者のアクセス権の判定器（`PagePrivilege`）を作る。
    **1ページでも複数ページでも、ここから聞く**。

        privilege = page_privilege(wiki_dir, uid)
        privilege.check("Tech/Secret")                       # → "W"
        [privilege.check(p) for p in ("Tech/A", "Tech/B")]   # → ["W", "R"]

    名前は、呼んでいる場所で**何が返るか**が読み取れるように `privilege` にした
    （Wiki設計者の指示、2026-09-14。「access.XXX では処理や戻り値がわかりにくいので
    privilege.XXX のほうが良い」）。記録を読み書きするモジュールは
    `wikilib.privilege_records` で、判定器とは名前でも見分けがつく。

    複数ページ用のメソッド（旧 `multi`）は置かない（Wiki設計者の指示、2026-09-14）。
    中身が `check` を回すだけで、下ごしらえはすでに判定器を作るときに1回で済んでいる
    ——メソッドにしても速くならず、呼ぶ側の内包表記と変わらない。これには賛成で、
    検索や木をたどる一覧のように**ページ名があとから1つずつ出てくる場所**でも、
    並びが先に揃っている場所でも、同じ `check` の書きかた1つで済む。"""
    return PagePrivilege(wiki_dir, uid)

# ---- 入る・出る（#login プラグインの _action から呼ばれる） -----------------
#
# **`/.login` という専用のログイン画面は持たない**（Wiki設計者の指示、2026-09-11）。
# `#login` プラグインがページの中にフォームを置き、送信先は `_action` の汎用の
# 窓口（`POST /.plugin/login`）。**画面はプラグインが作り、cookieとDBの
# 書き換えはこちらが受け持つ**（`Tech/LoginPlugin`参照）。
#
# POSTの結果は**その場で返さず、`back`（`#login`を置いたページ）へ303で
# 転送する**。通っても通らなくても同じ（Wiki設計者の指示、2026-09-06/2026-09-11）。
# そのまま出すと、再読み込みでブラウザが「もう一度送りますか」と聞き、送られた
# IDとパスワードが履歴に残り続ける。**打った値は転送先へ持ち回さない**
# （IDの欄にパスワードを打つ人が居るため）。


def _checked_page(raw):
    """ページパスとして受けてよい値か。よければ前後の `/` を落とした値（ルートは空文字）、
    駄目なら None。

    **受け取るのはページパスだけ。** URLはこちらで組み立てるので、好きなURLへ飛ばす
    踏み台にはならない。`//どこか` はブラウザには「別のホストへ」と読める形で、組み立て上
    そこへは飛ばないが、**そう読める値は受けない**ほうが分かりやすい。`:` と `\\` も
    弾く——組み立てが `base_url + "/" + page` なので、いまのままでも自分のところから
    出ないが、**URLらしく見える値を戻り先に通さない**ほうが、あとで組み立てを変えたときに
    事故らない。"""
    raw = (raw or "").strip()
    if raw.startswith("/"):
        return None
    page = raw.strip("/")
    if page and (not is_valid_pagepath(page) or ":" in page or "\\" in page):
        return None
    return page


def back_page_url(config, farm, wiki_dir, explicit_farm):
    """フォームの `back`（ページパス）から、戻り先のURLを作る。無ければNone。

    ページのルート（空文字）も戻り先として正しいので、`back` が入っているかどうかで
    見分ける。

    **`back` が `.login`（ログインの入口）のときだけ、システムのURLを受ける**
    （Wiki設計者の指示、2026-09-21）。ログインの入口から送られたフォームは、失敗の
    知らせを出すために入口へ戻す必要がある。ログインしたあとに戻るページは、別の
    欄 `next` で受ける（同じ確かめを通す）。組み立てるURLは
    `…/.login?back=<next>` で、`_back_to` が成功したときだけ `next` のページへ振り替える。"""
    if "back" not in request.forms:
        return None
    raw = (request.forms.getunicode("back", "") or "").strip()
    base = _base_url(config, farm, wiki_dir, explicit_farm)
    if raw == LOGIN_URLPATH:
        url = f"{base}/{LOGIN_URLPATH}"
        after = _checked_page(request.forms.getunicode("next", "") or "")
        if after:
            url += "?back=" + quote(after, safe="/")
        return url
    page = _checked_page(raw)
    if page is None:
        return None
    return base + "/" + page


# ログインの入口から送られたフォームで、**成功したら入口に留まらず元のページへ戻す**結果
_LEAVE_LOGIN_RESULTS = (LOGIN_RESULT_DONE, LOGIN_RESULT_MADE)


def _back_to(url, result, left=None):
    """戻り先へ303。結果は `?login=…` で知らせる。

    戻り先が**ログインの入口**（`/.login?back=<ページ>`）のときは、ログイン・登録が
    できたら入口に留まらず、`back` のページ（無ければそのWikiの入口）へ振り替える。
    できなかった・出た・申請した、のときは入口に留まる（知らせを出すため）。"""
    parts = urlsplit(url)
    if parts.path.endswith("/" + LOGIN_URLPATH) and result in _LEAVE_LOGIN_RESULTS:
        after = _checked_page((parse_qs(parts.query).get("back") or [""])[0]) or ""
        url = parts.path[:-len(LOGIN_URLPATH)] + quote(after, safe="/")
        query = f"?{LOGIN_RESULT_KEY}={result}"
    else:
        query = ("&" if "?" in url else "?") + f"{LOGIN_RESULT_KEY}={result}"
    if left is not None:
        query += f"&left={int(left)}"
    return HTTPResponse(status=303, headers={"Location": url + query})


def _redirect(config, farm, wiki_dir, explicit_farm, back, result, left=None):
    """`back` があればそこへ、無ければそのWikiの入口へ303。

    `back` は `#login` プラグインが必ず送ってくる（ルートページでも空文字列を
    送る）ので、通常は `None` にならない。**`None` になるのは、プラグインを
    経由しない直接のPOSTだけ**（想定していない使いかた）。"""
    if back is not None:
        return _back_to(back, result, left)
    fallback = _base_url(config, farm, wiki_dir, explicit_farm) or "/"
    return HTTPResponse(status=303, headers={"Location": fallback})


def do_login(config, farm, wiki_dir, explicit_farm, back):
    """ID・パスワードで照合し、通れば cookie を置いて `back` へ303。

    **通らなかったときも303**（`?login=ng|lock`）。待つのはサーバー側
    （画面側の待ちは素通りできるため）。ロックとそうでない場合の分けかたは
    `try_password` を参照。"""
    typed = request.forms.getunicode("uid", "") or ""
    uid = typed.strip()
    password = request.forms.getunicode("pw", "") or ""
    user, locked, left = try_password(wiki_dir, uid, typed, password)
    if user is None:
        time.sleep(RETRY_DELAY)
        return _redirect(config, farm, wiki_dir, explicit_farm, back,
                         LOGIN_RESULT_LOCK if locked else LOGIN_RESULT_NG,
                         None if locked else left)
    if not userdb.is_approved(user):
        # パスワードは合っているが、まだ承認されていない。**入れない**（cookieを置かない）
        return _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_PENDING)
    out = _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_DONE)
    remember_login(out, config, farm, wiki_dir, explicit_farm, user)
    return out


def do_logout(config, farm, wiki_dir, explicit_farm, back):
    """ログアウト（Wiki設計者の指示、2026-09-08）。cookieを捨てて戻す。

    **捨てるのはブラウザ側の控えだけ**で、合言葉そのものは無効にならない
    （`forget_login` 参照）。"""
    out = _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_OUT)
    forget_login(out, config, farm, wiki_dir, explicit_farm)
    return out


def do_revoke_others(config, farm, wiki_dir, explicit_farm, back):
    """他の端末のログイン状態を取り消す（Wiki設計者の指示、2026-09-24）。

    `cnt` を1つ上げる（`userdb.bump_cnt`）。合言葉の材料なので、**いま出回っている
    合言葉は、この操作をしたブラウザのぶんも含めてすべて通らなくなる**。そのため、
    **このセッションだけは今日ぶんを作り直して置き直す**（`remember_login`）。

    ログインしていない相手には何もしない（`back` へ戻すだけ。cookieも置かない）。
    パスワードは問わない——すでに入っている人が自分のアカウントに対してだけ
    できる操作で、他人のアカウントには届かない（対象は `current_user` から決める）。"""
    user = current_user(wiki_dir, farm)
    if user is None:
        return _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_NG)
    fresh = userdb.bump_cnt(wiki_dir, user["uidnum"])
    if fresh is None:
        return _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_NG)
    out = _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_REVOKED)
    remember_login(out, config, farm, wiki_dir, explicit_farm, fresh)
    return out


def do_signup(config, farm, wiki_dir, explicit_farm, back):
    """自分でアカウントを作る（Wiki設計者の指示、2026-09-08）。

    **受け入れかたは設定 `account.policy` で決まる**（Wiki設計者の指示、2026-09-20・
    2026-09-21）。

      open      誰でも作れて、**作れたらそのまま入る**（これまでの動き）
      approval  誰でも申請できるが、**承認待ちで始まり、入れない**。助手か管理者が
                承認する（`/.admin/approvals`）まで使えない。承認待ちのアカウントは
                権限の上では未ログインと同じで、`g:all` にも入らない
                （`userdb` の冒頭）

    **決めるのは登録だけ**で、誰が何を読めて書けるかはページごとの権限が決める。
    はじめは「作ったばかりのアカウントには何の権限も付かないので、作られて困るものが
    無い」という前提だったが、2026-09-17からログインした人は編集できるので崩れている
    （誰でも作れるかぎり、ログインを求めても制限にならない）。

    パスワードは2回入れてもらう。打ち間違えたまま登録すると、本人が入れなく
    なるため（`/.pwhash` と同じ考えかた）。"""
    uid = (request.forms.getunicode("uid", "") or "").strip()
    name = (request.forms.getunicode("name", "") or "").strip()
    first = request.forms.getunicode("pw", "") or ""
    second = request.forms.getunicode("pw2", "") or ""
    pending = account_policy(load_wiki_config(wiki_dir)) == "approval"
    ok = bool(first) and first == second
    if ok:
        ok, _message = userdb.add_user(wiki_dir, uid, userdb.hash_password(wiki_dir, uid, first), name,
                                       approved=not pending)
    if not ok:
        return _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_NG)
    authlog.note_attempt(wiki_dir, uid, request.remote_addr, passed=True)
    if pending:
        # 入れない（cookieを置かない）。承認されたらログインしてもらう
        return _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_APPLIED)
    user = userdb.find_by_uid(wiki_dir, uid)
    out = _redirect(config, farm, wiki_dir, explicit_farm, back, LOGIN_RESULT_MADE)
    remember_login(out, config, farm, wiki_dir, explicit_farm, user)
    return out


def try_password(wiki_dir, uid, typed, password):
    """パスワードでの照合を1回。**記録もロックもここで済ませる。**

    `#login` プラグイン経由のログイン照合と `/.passwd` の両方が通る道
    （Wiki設計者の了承、2026-09-06）。
    返すのは (通ったアカウント, ロック中か, ロックまでの残り)。
    **残りは「いま1つ減ったとき」だけ数を返す**——止めているあいだは
    `None`（画面に出さない。Wiki設計者の指示、2026-09-07）。

    ## 順番に意味がある

      1. そのIDが無い          → 101。数えない（止めようがない）
      2. ロックされている      → 100。**照合しない**（何を送っても通らない）
      3. 無視のあいだ          → 102/103。合っていたかは記録にだけ残す
      4. ふつうに照合          → 0 か 1〜99

    4 でまちがえたとき、それが `LOCK_AFTER` 回目なら**そこでロックする**
    （`userdb.lock_user`。`pw` を `LOCKED` に書き換える）。その1回は失敗
    ではなく 100 として残す——記録を見たときに、どこで掛かったかが分かる。

    `typed` は**打たれたそのまま**の文字列（記録用）、`uid` は前後の空白を
    落としたもの（照合と数え用）。"""
    remote = request.remote_addr
    row = userdb.find_by_uid(wiki_dir, uid)
    if row is None:
        authlog.note_attempt(wiki_dir, typed, remote, passed=False, known=False)
        return None, False, None
    if userdb.is_locked(row):
        authlog.record(wiki_dir, typed, remote, authlog.STATE_LOCK)
        return None, True, 0
    if authlog.is_ignored(wiki_dir, uid):
        # **合っていても通さない**（Wiki設計者の指示）。合っていたかは記録にだけ。
        # **残り回数は出さない**（Wiki設計者の指示、2026-09-07）——止めている
        # あいだは数が動かないので、出すと「減らない数」が並んで壊れて
        # 見える。明けたあと、実際にまちがえたところで1つ減って出る
        authlog.note_ignored(
            wiki_dir, typed, remote,
            passed=userdb.authenticate(wiki_dir, uid, password) is not None)
        return None, False, None
    user = userdb.authenticate(wiki_dir, uid, password)
    if user is not None:
        authlog.note_attempt(wiki_dir, typed, remote, passed=True)
        return user, False, None
    if authlog.should_lock(wiki_dir, uid):
        userdb.lock_user(wiki_dir, row["uidnum"])
        authlog.record(wiki_dir, typed, remote, authlog.STATE_LOCK)
        return None, True, 0
    authlog.note_attempt(wiki_dir, typed, remote, passed=False)
    return None, False, authlog.lock_left(wiki_dir, uid)


def lock_warning(left):
    """ロックが近いことの断り。出さないときは空文字。

    **`#login` プラグインもこれを呼ぶ**（Wiki設計者の指示、2026-09-08の依頼）。
    同じ文言を2か所に書くと、片方だけ直したときに食い違う。

    **出しはじめは「残り WARN_LEFT 回」から**（Wiki設計者の指示、2026-09-07）。
    止めに入る回（残りが `IGNORE_AFTER` の倍数になる回）で出すと、その次の
    「止めているあいだは出さない」との差で、止められていることが読めてしまう。

    最後の1回は数ではなく言葉にする——「残り1回」だと、いま失敗したら
    掛かるのか、次に失敗したら掛かるのかが読み手に分からない。"""
    if not left.isdigit():
        return ""
    n = int(left)
    if n == 1:
        return "（次回失敗したらロックします）"
    if 1 < n <= authlog.WARN_LEFT:
        return f"（ロックまで残り{n}回）"
    return ""
