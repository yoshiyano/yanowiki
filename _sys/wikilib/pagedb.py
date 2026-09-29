"""ページ本文のデータベース（pageinfo/wikiall.db）。

平文ファイルと同じ内容をSQLiteにも持たせ、**二重化**する。公開文書の情報を
1か所に集めたもので、次に使う。

  - 全文検索（当たりそうなページをSQLで絞ってから読む）
  - 更新順の一覧（recent）
  - ページ一覧やプラグインからの参照（タイトル・目次）
  - ページ間のリンクと逆リンク
  - **保存時の差分の基準**（システムが最後に知っていた内容）

最後のものがとくに重要で、これが無いと「システムを通さずに書き換えられたページ」を
正しく記録できない。平文ファイルだけを見ていると、直接編集された内容が
「元の内容」に見えてしまい、差分が取れないためである。

## DBが公開済み、平文は作業中

**DBに入っているものが「公開されたページ」**で、平文ファイルはその materialize
（書き出したもの）と、まだ取り込んでいない作業中の内容が混ざったものになる。

平文ファイルだけを直に書き換えた状態は、**他の人が編集の途中である**のと同じ扱い
にする。まだ公開されていないので、次の場面ではDBのほうを見る。

  - **ページの表示**（published_ref）とメニュー
  - 保存時の差分の基準（確定していない現存ファイルと比べても意味がない）
  - 「更新状況」に出す差分
  - 検索・更新順の一覧・ページ一覧のタイトル・プラグインが見る目次

**編集画面だけは平文ファイルを読む。** 編集で扱うのは作業中のものなので、
直に書き換えた内容がそのまま出てほしい。ここでDBを読むと、直接編集した分が
画面に出ないまま上書き保存され、どこにも残らずに消えてしまう。

取り込みは `updatepage`（全体、または1ページだけ）で行う。平文とDBの食い違いは
`stale_pages()` が **ページごとに** 大きさと更新時刻を見て拾うので、1ページだけ
取り込んでも他のページの検出には影響しない（全体の走査時刻を持たないため）。

平文を捨てるわけではない。DBが壊れても平文から作り直せるようにしてある。

## 記録する内容

1ページにつき1行だけ。履歴は持たない（履歴は pageinfo/backup/ の差分が持つ）。

    subpath  wiki/ からのパス（拡張子抜き）。ページの識別子
    path     ファイル名（wiki/ からのパス、拡張子込み）
    body     平文
    created  初回登録日時
    updated  最終更新日時
    size     ファイルの大きさ
    mtime    登録した時点のファイル更新時刻
    bodyhash 本文のCRC32。中身が本当に変わったかを見分ける
    title    ページの見出し（本文から取り出したもの）
    toc      目次（JSON）。**NULL は「まだ取り出していない」** の意味で、
             "[]"（見出しが無かった）とは区別する

## 食い違いの見つけかたは2段階

`mtime` と `size` を持つのは、**中身を読まずに** 平文との食い違いを見つけるため。
ページ数が増えても、その2つを見るだけなら stat だけで済む。

ただし**更新時刻が新しくても中身は同じ**ということがよくある。`git reset --hard`
での更新や、ファイルのコピー・`touch` がそれにあたる。これを取り込み対象と
みなすと、中身が変わっていないのにバックアップが1本増え、全文のパースもやり直す
ことになる。そこで2段階にしてある。

    1段階目  大きさが違えば、中身も必ず違う（読まずに確定）
             大きさが同じで更新時刻だけ新しければ、2段階目へ
    2段階目  本文を読んでCRC32を取り、DBの値とくらべる

CRC32を選んだのは速さのため（実測 約4.0GB/秒で、sha256の2.4倍、md5の7倍）。
更新されたかどうかを見分けるだけの用途で、同じページの新旧を1対1でくらべる。

ページ間のリンクは別の表に行として持つ。**書かれたままの文字列（href）を
主キーの一部にした、解決結果のキャッシュ**という形にしてある（位置ではなく
文字列をキーにする理由は SCHEMA 中のコメントを参照）。

    links(source, href, kind, owner, filename)   ← owner に索引を張る

`owner`（指し先の持ち主。添付ファイルならそれを持つページ、ページ自身なら
その先そのもの）に索引を張ってあるので、逆リンク（どのページから指されて
いるか）が問い合わせ1回で出る。

## 本文と派生情報を同じDBに入れている理由

title・toc・links は本文から一意に決まる値なので、**同じDBに置いて一度に書けば、
両者が食い違うことが原理的に起こらない**。別ファイルに分けると、本文を書いた
直後に落ちた場合に「本文は新しいが目次は古い」状態が生まれ、しかもそれを
安く見つける手立てが無い。

ただし取り出しには全文のパースが要るため、本文の登録にくらべて5倍以上の時間が
かかる（1万ページで本文7秒に対し37秒）。そのため**作り直しのときは本文だけを
先に戻す**。取り出しは次の2つで埋める。

  - ページを開いたとき（themes.render_with_theme → links.ensure_page_info）。
    1ページあたり数ミリ秒なので気づかれない
  - `./wiki.py updatepage`（pagesync）でまとめて。**逆リンクは全ページ分が
    揃わないと数えられない**ので、開かれていないページも埋めておく必要がある

## 壊れたとき

開けない・読めない場合は作り直す（`ensure_db()`）。平文ファイルが正本なので、
中身はそのまま戻る。ただし `created`（初回登録日時）は平文からは分からないので、
バックアップの差分がいちばん古い日時を使い、それも無ければファイルの更新時刻で代える。
"""
import json
import os
import re
import sqlite3
import time
import zlib

from wikilib.backup import first_backup_stamp as _first_backup_stamp
from wikilib.paths import (
    INDEX_NAME, PAGE_EXTS, PageRef, farm_pageinfo_dir, iter_pages,
    pagepath_of_subpath, resolve_page_ref,
)

DB_NAME = "wikiall.db"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"  # 画面にそのまま出せる書式

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    subpath TEXT PRIMARY KEY,
    path    TEXT NOT NULL,
    body    TEXT NOT NULL,
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    size    INTEGER NOT NULL,
    mtime   REAL NOT NULL,
    bodyhash INTEGER NOT NULL DEFAULT 0,
    title   TEXT,
    toc     TEXT
);
CREATE INDEX IF NOT EXISTS pages_updated ON pages (updated DESC);

-- href は本文に書かれたままの文字列（"../neighbor/pic.png" 等）で、
-- 位置ではなくこれをキーにする。理由は2つ。位置（文字オフセット）は
-- 本文が少しでも変われば古くなるが、その本文はどのみち保存のたびに
-- 全文取り出し直すので、位置を持ち歩く意味が薄い。もう1つは、リライトの
-- 際にリンクを探す処理（pagelinks.link_spans）はそのときの本文へ毎回
-- 素直にかければよく、ここは「その文字列は何を指しているか」という
-- “解決結果のキャッシュ”だけを持てば足りるため（resolve_link を
-- リライトのたびに呼ばずに済む）。
-- kind は "page" か "attach"。owner は絶対パス（"/ページパス"）で、
-- ページ自身か、添付ファイルの持ち主。filename は添付ファイル名
-- （ページなら NULL）。
CREATE TABLE IF NOT EXISTS links (
    source   TEXT NOT NULL,
    href     TEXT NOT NULL,
    kind     TEXT NOT NULL,
    owner    TEXT NOT NULL,
    filename TEXT,
    PRIMARY KEY (source, href)
);
CREATE INDEX IF NOT EXISTS links_owner ON links (owner);
"""


def db_path(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, DB_NAME)


def connect(wiki_dir):
    """DBを開く。無ければ作る。スキーマは毎回そろえる（安いので）。

    **空で作る前に、控え（wikiall.db.zip）があればそれを戻す**
    （dbbackup.restore_from_zip。2026-09-01）。ここを素通りして空のまま
    作ると、次にページを取り込んだ差分が「空→内容」として記録され、
    それより古い履歴が現在とつながらなくなる。控えを戻しておけば、
    取り込みは「控えの時点 → いま」というまっとうな1本になり、そこから
    先の過去へは辿れる。"""
    path = db_path(wiki_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        # 読み込みの途中で呼ばれることもあるので、失敗しても黙って進む
        # （控えが無い・壊れているなら、これまでどおり空で作る）
        from wikilib.dbbackup import restore_from_zip
        restore_from_zip(wiki_dir)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def stamp_of(when=None):
    return time.strftime(TIME_FORMAT, time.localtime(when))


def body_hash(body):
    """本文のCRC32。更新されたかどうかを見分けるためのもの。"""
    return zlib.crc32(body.encode("utf-8"))


# ---- 書き込み ---------------------------------------------------------------

def record_page(wiki_dir, subpath, ext, body, path=None, now=None, created=None):
    """1ページ分を登録する。すでにあれば中身を差し替える。

    `created`（初回登録日時）は最初の1回だけ入れ、以後は引き継ぐ。
    `mtime` と `size` は実ファイルから採る（平文との食い違いを見つける手がかりに
    するので、DBに書いた時刻ではなくファイル側の値でなければ意味がない）。

    created を渡すと、**新しく入れるときだけ**その日時を使う（すでに行があれば
    これまでどおり引き継ぐので、渡しても上書きにはならない）。行を失ったページを
    入れ直す場面で、バックアップから分かる本当の日時を戻すためのもの。

    **`updated`（最終更新日時）は、本文か記法（拡張子）が変わったときだけ進める。**
    同じ中身を入れ直すたびに進めると、`updatepage --force` のような全ページの
    取り込み直しで、どのページも取り込んだ時刻になり、「最新の更新」やファイル一覧の
    更新日時が並んでしまう（2026-09-29 に起きた）。中身が同じ保存は差分も残らない
    （backup_page）ので、それとそろえる。

    **進めるときの値は、本文のファイルが書き換わった時刻（ファイルの mtime）にする**
    （`now` を渡したときはその時刻）。DB に書いた時刻にすると、直接編集したページを
    取り込んだときに「取り込んだ時刻」になり、ファイルの最終更新日時（フッターの
    Last-modified）とずれる。ファイル一覧の更新日時について、Wiki設計者は「この値と
    ファイルの最終更新日とで違いがあるのがおかしい」「ファイルから参照していますか？
    DBで完結するようにすべきです」とした（2026-09-29）。両方を満たすため、DB に記録する
    値をファイルの時刻にした（この方法はクロコの実装）。

    **本文が同じままファイルの時刻だけ変わったとき（touch・git pull など）は進めない**
    （`touch_page`）。そのページでは、一覧の日時がフッターの Last-modified より古く出る。
    最終更新日時は「本文が変わった時刻」とする、と設計者が選んだ（2026-09-29。
    「ファイルの時刻に常に合わせる」案は、時刻だけ変わったページが「最新の更新」に
    上がってくるので採らなかった）。"""
    file_path = path or os.path.join(wiki_dir, subpath + ext)
    try:
        stat = os.stat(file_path)
        size, mtime = stat.st_size, stat.st_mtime
    except OSError:
        size, mtime = len(body.encode("utf-8")), time.time()
    stamp = stamp_of(now if now is not None else mtime)
    try:
        with connect(wiki_dir) as con:
            con.execute(
                "INSERT INTO pages"
                " (subpath, path, body, created, updated, size, mtime, bodyhash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(subpath) DO UPDATE SET"
                "   updated=CASE WHEN pages.bodyhash = excluded.bodyhash"
                "                 AND pages.path = excluded.path"
                "            THEN pages.updated ELSE excluded.updated END,"
                "   path=excluded.path, body=excluded.body,"
                "   size=excluded.size, mtime=excluded.mtime,"
                "   bodyhash=excluded.bodyhash",
                (subpath, subpath + ext, body, created or stamp, stamp, size, mtime,
                 body_hash(body)))
    except sqlite3.Error:
        return False
    return True


def replace_body(wiki_dir, subpath, body, now=None):
    """本文だけを差し替える（平文ファイルは見ない）。入れ替えたらTrue。

    控えから戻したDBを、控え以後の差分を当てて進めるために使う
    （dbbackup.restore_from_zip。2026-09-01）。

    **平文ファイルの大きさ・時刻は写さず、`mtime` を 0 にしておく。**
    ここで入れる本文は「差分をたどって組み立てた、平文より前の状態」なので、
    平文の値をそのまま書くと `stale_pages` が「DBと平文は同じ」と見なして
    しまい、**最後の1本（ここから平文まで）の差分が記録されなくなる**。
    0にしておけば必ず読み直しの対象になり、中身が同じなら `touch_page` で
    そろえ直されるだけで済む。"""
    stamp = stamp_of(now)
    try:
        with connect(wiki_dir) as con:
            cur = con.execute(
                "UPDATE pages SET body = ?, updated = ?, size = ?, mtime = 0,"
                " bodyhash = ? WHERE subpath = ?",
                (body, stamp, len(body.encode("utf-8")), body_hash(body), subpath))
            return cur.rowcount > 0
    except sqlite3.Error:
        return False


def record_page_info(wiki_dir, subpath, title, toc, links, now=None):
    """本文から取り出した情報（タイトル・目次・リンク）を記録する。

    links は [(href, kind, owner, filename), ...]（links.page_links の
    戻り値そのまま）。行として持つので、いったん消してから入れ直す。
    本文の登録と同じDBなので、片方だけ古いという状態にはならない。"""
    try:
        with connect(wiki_dir) as con:
            con.execute(
                "UPDATE pages SET title = ?, toc = ? WHERE subpath = ?",
                (title or "", json.dumps(toc or [], ensure_ascii=False), subpath))
            con.execute("DELETE FROM links WHERE source = ?", (subpath,))
            con.executemany(
                "INSERT OR IGNORE INTO links (source, href, kind, owner, filename)"
                " VALUES (?, ?, ?, ?, ?)",
                [(subpath, href, kind, owner, filename)
                 for href, kind, owner, filename in (links or ())])
    except sqlite3.Error:
        return False
    return True


def remove_page(wiki_dir, subpath):
    """ページを消したときに、その行も消す。そのページから出ていたリンクも消す
    （ページが無くなれば、そこから出ていたリンクも無くなるため）。"""
    try:
        with connect(wiki_dir) as con:
            con.execute("DELETE FROM pages WHERE subpath = ?", (subpath,))
            con.execute("DELETE FROM links WHERE source = ?", (subpath,))
    except sqlite3.Error:
        return False
    return True


def rename_page(wiki_dir, old_subpath, new_subpath, new_ext):
    """ページの置き場所が変わったときに、識別子を付け替える。

    中身は変わらないので、`created` も `updated` もそのまま引き継ぐ。
    そのページから出ているリンクも、指し先は変わらないので付け替えるだけ
    （なぜ拾い直さなくてよいかは pagemove.move_links を参照）。"""
    try:
        with connect(wiki_dir) as con:
            con.execute(
                "UPDATE pages SET subpath = ?, path = ? WHERE subpath = ?",
                (new_subpath, new_subpath + new_ext, old_subpath))
            con.execute("UPDATE links SET source = ? WHERE source = ?",
                        (new_subpath, old_subpath))
    except sqlite3.Error:
        return False
    return True


# ---- 読み出し ---------------------------------------------------------------

def load_page_body(wiki_dir, subpath):
    """**システムが最後に知っている**そのページの中身。無ければNone。

    保存時の差分を取るときの「変更前」はこれを使う。平文ファイルのほうを使うと、
    システムを通さない書き換えがあった場合に、その書き換え後の内容を
    「変更前」と見なしてしまい、直接編集した分が記録から抜け落ちる。"""
    try:
        with connect(wiki_dir) as con:
            row = con.execute(
                "SELECT body FROM pages WHERE subpath = ?", (subpath,)).fetchone()
    except sqlite3.Error:
        return None
    return row["body"] if row is not None else None


def published_ref(wiki_dir, pagepath):
    """**表示に使う**ページを取り出す。wiki_dirの外を指す場合だけNone。

    どのファイルを指すかは resolve_page_ref がこれまでどおり決め、**中身だけを
    DBから差し替える**。表示されるのは「公開された内容」で、平文ファイルだけを
    **書き換えた**分は、取り込む（updatepage）まで出てこない。

    ただし**まだDBに無いページは、平文ファイルがあればその場で取り込む**
    （pagesync.adopt_page）。ファイルを置けば読める、という素直な振る舞いを
    優先している。取り込みは updatepage と同じ経路を通るので、バックアップにも
    残り、タイトル・目次・リンクも揃う。取り込んでから改めてDBを読むため、
    表示に出るのは（平文の代わりではなく）取り込んだあとの公開された内容になる。

    取り込みは pagesync が持つ。ここから関数の中で import しているのは、
    pagesync がこのモジュールを読むため（モジュールの先頭で import すると輪になる）。

    返す PageRef の `exists` は「公開されているか」の意味になる。resolve_page_ref が
    作るPageRefの `exists`（平文ファイルがあるか）とは見ている先が違う。詳しくは
    PageRef を参照。

    ## `privilege`（いまの閲覧者のアクセス権）

    **`privilege` に、いまの閲覧者（`auth.current_uid`）のそのページのアクセス権
    （`W`/`R`/`-`）を入れて返す**（Wiki設計者の指示、2026-09-15）。表示する側は
    判定器を別に作らず、この値で出す・出さないを決める。

    **`-` でも本文などのデータは入れて返す。** いまの表示には要らないが、今後の
    拡張で本文が要る場面がある、という指示による。そのぶん**受け取った側が
    `privilege` を見ずに `body` を出すと、読めない人に本文が漏れる**。

    **公開されていないページも None にせず、`exists=False` で返す**（本文は空）。
    None では `privilege` を載せる先が無く、**無いページについて、その人がそこを
    読めるか・書けるかが分からない**（表示は、読めない名前に作成の誘いを出さずに
    403にしている。`views.render_no_view` 参照）。ページが在るかどうかを隠す
    目的ではない（Wiki設計者、2026-09-15。知られても問題ない）。呼び出し側は
    どこも `ref is None or not ref.exists` で見ているので、それまでの扱いは変わらない。
    取り込めなかった場合（書き込めない等）も同じく `exists=False`。

    判定器はここで毎回作る（1回あたり1ms前後。メニューや `#include` の分だけ
    呼ばれる）。auth は画面寄りの層（bottle・テーマ）を読むので、pagesync と同じく
    関数の中で import している。"""
    ref = resolve_page_ref(wiki_dir, pagepath)
    if ref is None:
        return None
    from wikilib import auth
    from wikilib.pagesync import farm_of_wiki_dir
    uid = auth.current_uid(wiki_dir, farm_of_wiki_dir(wiki_dir))
    privilege = auth.page_privilege(wiki_dir, uid).check(ref.pagepath)

    row = load_page(wiki_dir, ref.subpath)
    if row is None and ref.exists:
        from wikilib.pagesync import adopt_page
        adopt_page(wiki_dir, ref.subpath)
        row = load_page(wiki_dir, ref.subpath)
    if row is None:
        # 公開されていない（取り込めなかった場合も含む）。平文の本文は入れない
        return PageRef(ref.pagepath, ref.subpath, ref.ext, ref.path, "", False, privilege)
    ext = os.path.splitext(row["path"])[1] or ref.ext
    return PageRef(ref.pagepath, ref.subpath, ext,
                   os.path.join(wiki_dir, row["path"]), row["body"], True, privilege)


def published_body(wiki_dir, subpath, fallback=None):
    """公開されている本文。DBに無ければ fallback を返す。

    ページを丸ごと取り出すまでもなく、本文だけが要る場面で使う。"""
    body = load_page_body(wiki_dir, subpath)
    return fallback if body is None else body


def load_page(wiki_dir, subpath):
    """1ページ分の記録をそのまま返す（dict）。無ければNone。"""
    try:
        with connect(wiki_dir) as con:
            row = con.execute(
                "SELECT * FROM pages WHERE subpath = ?", (subpath,)).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row is not None else None


def page_updated_at(wiki_dir, subpath):
    """そのページの本文が最後に更新された日時（TIME_FORMAT形式の文字列）。
    無ければNone。accesslog.record_access の content_updated_at に渡すためのもの。"""
    try:
        with connect(wiki_dir) as con:
            row = con.execute(
                "SELECT updated FROM pages WHERE subpath = ?", (subpath,)).fetchone()
    except sqlite3.Error:
        return None
    return row["updated"] if row is not None else None


def load_page_info(wiki_dir, subpath):
    """取り出し済みの情報（タイトル・目次）を返す。まだ無ければNone。

    リンクはここには含めない。呼び出し側はどれもタイトル・目次だけを見ており、
    リンクが要る場面は `links_of`/`link_rows_of`/`backlinks_of` を別に使う
    （目的の違うクエリを1つの戻り値にまとめると、使っていない側の変更で
    壊れやすくなるため）。"""
    try:
        with connect(wiki_dir) as con:
            row = con.execute(
                "SELECT title, toc FROM pages WHERE subpath = ?",
                (subpath,)).fetchone()
    except sqlite3.Error:
        return None
    if row is None or row["toc"] is None:
        return None  # まだ取り出していない
    try:
        toc = json.loads(row["toc"] or "[]")
    except ValueError:
        toc = []
    return {"title": row["title"] or "", "toc": toc}


def links_of(wiki_dir, subpath):
    """そのページが参照している先（絶対パス、名前順）。ページと、参照している
    添付ファイルの持ち主の両方を含む（重複は1つにまとめる）。"""
    try:
        with connect(wiki_dir) as con:
            return [r["owner"] for r in con.execute(
                "SELECT DISTINCT owner FROM links WHERE source = ? ORDER BY owner",
                (subpath,))]
    except sqlite3.Error:
        return []


def link_rows_of(wiki_dir, subpath):
    """そのページのリンクの解決結果を `{書かれた文字列: (種別, 持ち主, ファイル名)}`
    で返す。DBに引きにいかずに書き換え判断ができるよう、
    `pagelinks.rewrite_links` の cache 引数にそのまま渡す想定。"""
    try:
        with connect(wiki_dir) as con:
            return {r["href"]: (r["kind"], r["owner"], r["filename"]) for r in con.execute(
                "SELECT href, kind, owner, filename FROM links WHERE source = ?",
                (subpath,))}
    except sqlite3.Error:
        return {}


def backlinks_of(wiki_dir, owner):
    """そのページを指している（または、そのページの添付ファイルを指している）
    ページ（名前順）。

    owner はページパス（`/` から始まるURLの形）。索引が張ってあるので、
    ページ数が増えても問い合わせ1回で済む。"""
    try:
        with connect(wiki_dir) as con:
            return [r["source"] for r in con.execute(
                "SELECT DISTINCT source FROM links WHERE owner = ? ORDER BY source",
                (owner,))]
    except sqlite3.Error:
        return []


def all_pages(wiki_dir):
    """登録されている全ページ（subpath順）。"""
    try:
        with connect(wiki_dir) as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM pages ORDER BY subpath")]
    except sqlite3.Error:
        return []


def page_entries(wiki_dir, prefix=""):
    """**本文を除いた**ページの一覧（subpath順）。

    一覧を組み立てるだけの用途に使う。名前・見出し・更新日時・大きさが揃うので、
    ページ一覧やフォルダの木はこれだけで作れる。all_pages() と違って本文を
    運ばないのは、ページ数が増えたときに運ぶだけで時間がかかるため
    （検索をDB化したときに実測してある。冒頭の「記録する内容」を参照）。

    prefix（"Tech/" のように末尾の "/" 込み）を与えると、その下にあるものだけを
    返す。**絞り込みはSQLiteに任せる。** subpath は主キーなので、大小の比較で
    範囲を切れば索引がそのまま効き、フォルダ1つ分を見るのにWiki全体を運ばずに済む。
    上限に "\\uffff" を使うのは、これより大きい文字がページ名に現れないため。"""
    sql = "SELECT subpath, path, title, created, updated, size FROM pages"
    args = ()
    if prefix:
        sql += " WHERE subpath >= ? AND subpath < ?"
        args = (prefix, prefix + "\uffff")
    sql += " ORDER BY subpath"
    try:
        with connect(wiki_dir) as con:
            return [dict(r) for r in con.execute(sql, args)]
    except sqlite3.Error:
        return []


def page_children(wiki_dir, prefix="", entries=None):
    """`prefix` の1階層下にあるものを、**wikiの意味でのページとして**返す。

    OSのフォルダとwikiのフォルダは意味が違う。OSから見れば `講義/第07回/` は
    ただのフォルダだが、そこに入口（`第07回/index`）があれば、wikiの世界では
    `/講義/第07回` という**1枚のページ**である。この読み替えを呼び出し側に
    書かせないための関数で、`os.listdir` にあたるものだと思えばよい
    （Wiki設計者の指示、2026-09-05。プラグインが名前の形だけでページかどうかを
    判断していて、入口を持つフォルダが一覧から丸ごと消えていた）。

    `prefix` は `"Tech"` でも `"Tech/"` でもよい（空ならWikiの直下）。
    返すのは、直下の名前ごとに1つずつの辞書。

        name      直下の名前（`"第07回"`）
        page      その名前のページ。無ければ None
        has_more  その名前の下に、page 以外の公開ページがまだあるか

    `page` は `page_entries` の1行に `pagepath`（URL上の名前）を足したもの。
    直下に実体（`prefix + name`）があればそれを、無くて入口
    （`prefix + name + "/index"`）があればそちらを使う。**どちらも無ければ
    None** で、これは「通り道でしかないフォルダ」（下位にページはあるが、
    その階層自身は開けない）を表す。

    `has_more` は、そこからさらに下へ辿る価値があるか（折りたたんで見せる
    必要があるか）の判断に使う。`page` に選ばれた入口は数えない。

    **そのフォルダ自身の入口も、名前 `index` の要素として1つ返る。**
    `#ls()` を入口ページに置いたときに自分自身を落とすかどうかは、見せかたの
    都合なので呼び出し側に決めてもらう。

    `entries` を渡すと、DBを引き直さずにそこから絞り込む（階層をたどるとき、
    同じ一覧を階層の数だけ引かないようにするため。`page_entries` の戻り値を
    そのまま渡せる）。"""
    prefix = (prefix or "").strip("/")
    prefix = prefix + "/" if prefix else ""
    if entries is None:
        entries = page_entries(wiki_dir, prefix)
    groups, order = {}, []
    for entry in entries:
        subpath = entry["subpath"]
        if not subpath.startswith(prefix):
            continue
        name, sep, rest = subpath[len(prefix):].partition("/")
        if not name:
            continue
        if name not in groups:
            groups[name] = {"page": None, "more": False}
            order.append(name)
        if not sep:
            # 直下の実体。入口（下の分岐）が見つかれば、そちらで上書きされる。
            # 実体と入口が両方あるのは本来ありえない形（X.txt と X/ は同居
            # できない）だが、そうなっていたら resolve_page_ref と同じく
            # 入口のほうを採る（subpath順で入口が後に来る）
            groups[name]["page"] = entry
        elif rest == INDEX_NAME:
            groups[name]["page"] = entry
        else:
            groups[name]["more"] = True
    out = []
    for name in order:
        entry = groups[name]["page"]
        page = None
        if entry is not None:
            page = dict(entry, pagepath=pagepath_of_subpath(entry["subpath"]))
        out.append({"name": name, "page": page, "has_more": groups[name]["more"]})
    return out


LIKE_ESCAPE_RE = re.compile(r"([%_\\])")


def like_pattern(term):
    """LIKE に渡す部分一致のパターン。

    LIKE では `%` と `_` が特別な意味を持つので、語の中にあれば逃がす
    （"100%" を探したときに何にでも当たってしまうのを防ぐ）。"""
    return "%" + LIKE_ESCAPE_RE.sub(r"\\\1", term) + "%"


def subpaths_containing(wiki_dir, term):
    """その語を本文か見出しに含むページ（実体パス）の集合。

    **絞り込みをSQLiteに任せるためのもの。** 全ページの本文をPythonへ運んで
    から見比べると、運ぶだけで時間がかかる。当たりそうなページだけを先に
    選んでおけば、本文を読むのはその分だけで済む。

    大文字小文字の扱いはPythonの lower() と同じ（LIKE は半角英字について
    区別しない。日本語には大小が無いので差は出ない）。"""
    pattern = like_pattern(term)
    try:
        with connect(wiki_dir) as con:
            return {r["subpath"] for r in con.execute(
                "SELECT subpath FROM pages"
                " WHERE body LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'",
                (pattern, pattern))}
    except sqlite3.Error:
        return set()


def all_subpaths(wiki_dir):
    """登録されている全ページの実体パス（名前順）。本文は読まない。"""
    try:
        with connect(wiki_dir) as con:
            return [r["subpath"] for r in con.execute(
                "SELECT subpath FROM pages ORDER BY subpath")]
    except sqlite3.Error:
        return []


def iter_page_texts_of(wiki_dir, subpaths):
    """指定したページを (subpath, title, body) で1件ずつ返す（名前順）。

    page_texts_of() と違って一度に全部をメモリへ載せない。**当たったページを
    数えるだけ**の場面で使う。当たりが多いほど本文の総量は大きくなるので、
    数えるためだけに全部を抱えると、件数に比例してメモリを食うことになる。"""
    wanted = sorted(set(subpaths))
    if not wanted:
        return
    try:
        con = connect(wiki_dir)
    except sqlite3.Error:
        return
    try:
        # 一度に渡す数が多くなりすぎないよう小分けにする
        # （SQLiteのプレースホルダ数には上限があるため）
        for i in range(0, len(wanted), 500):
            chunk = wanted[i:i + 500]
            marks = ",".join("?" * len(chunk))
            for row in con.execute(
                    f"SELECT subpath, title, body FROM pages"
                    f" WHERE subpath IN ({marks}) ORDER BY subpath", chunk):
                yield row["subpath"], row["title"] or "", row["body"]
    except sqlite3.Error:
        return
    finally:
        con.close()


def page_texts_of(wiki_dir, subpaths):
    """指定したページだけを (subpath, title, body) で返す（名前順）。"""
    return list(iter_page_texts_of(wiki_dir, subpaths))


def iter_page_texts(wiki_dir):
    """全ページを (subpath, title, body) で1件ずつ返す。

    all_pages() と違って一度に全部をメモリへ載せない。検索のように
    「全ページを順に見るだけ」の用途に使う。本文はDBに入っているので、
    ページの数だけファイルを開く必要がない。"""
    try:
        con = connect(wiki_dir)
    except sqlite3.Error:
        return
    try:
        for row in con.execute(
                "SELECT subpath, title, body FROM pages ORDER BY subpath"):
            yield row["subpath"], row["title"] or "", row["body"]
    except sqlite3.Error:
        return
    finally:
        con.close()


def recent_pages(wiki_dir, limit=None):
    """更新の新しい順にページを返す。

    全ページが対象で件数の上限は無い。消えたページは行ごと消えているので、
    後から取り除く手当ても要らない。"""
    sql = "SELECT * FROM pages ORDER BY updated DESC, subpath"
    args = ()
    if limit is not None:
        sql += " LIMIT ?"
        args = (limit,)
    try:
        with connect(wiki_dir) as con:
            return [dict(r) for r in con.execute(sql, args)]
    except sqlite3.Error:
        return []


def touch_page(wiki_dir, subpath, size, mtime):
    """中身は同じだがファイルの更新時刻だけ変わっていた場合に、DB側を合わせる。

    こうしておかないと、そのページを見るたびに本文を読んでハッシュを取り直す
    ことになる。中身は変わっていないので、`updated` には触らない。"""
    try:
        with connect(wiki_dir) as con:
            con.execute("UPDATE pages SET size = ?, mtime = ? WHERE subpath = ?",
                        (size, mtime, subpath))
    except sqlite3.Error:
        return False
    return True


def stale_pages(wiki_dir):
    """平文ファイルとDBが食い違っているページを返す。

    見分けかたは2段階（このモジュールの冒頭を参照）。まず大きさと更新時刻だけを
    見て、それで決まらないものだけ本文を読んでハッシュをくらべる。更新時刻が
    新しいだけで中身が同じなら食い違いとせず、DB側の時刻を合わせておく。

    戻り値は次の3種類を混ぜた一覧。

        {"subpath": …, "kind": "updated"}  … 平文のほうが新しい（直接編集された）
        {"subpath": …, "kind": "added"}    … 平文にあるがDBに無い
        {"subpath": …, "kind": "removed"}  … DBにあるが平文に無い
    """
    known = {row["subpath"]: row for row in all_pages(wiki_dir)}
    found = []
    seen = set()
    for pagepath, _ in iter_pages(wiki_dir):
        ref = resolve_page_ref(wiki_dir, pagepath)
        if ref is None or not ref.exists:
            continue
        seen.add(ref.subpath)
        row = known.get(ref.subpath)
        if row is None:
            found.append({"subpath": ref.subpath, "kind": "added"})
            continue
        try:
            stat = os.stat(ref.path)
        except OSError:
            continue
        if stat.st_size != row["size"]:
            found.append({"subpath": ref.subpath, "kind": "updated"})
            continue
        # 1秒はゆとりを見る。保存の書き込みとDBへの記録の間に秒がまたぐことがあるため
        if stat.st_mtime <= row["mtime"] + 1:
            continue
        # 大きさは同じで時刻だけ新しい。中身が本当に変わったかを確かめる
        if body_hash(ref.body) != row["bodyhash"]:
            found.append({"subpath": ref.subpath, "kind": "updated"})
        else:
            touch_page(wiki_dir, ref.subpath, stat.st_size, stat.st_mtime)
    for subpath in known:
        if subpath not in seen:
            found.append({"subpath": subpath, "kind": "removed"})
    return found


def shadowed_pages(wiki_dir):
    """`X.拡張子` と、同じ場所を指すフォルダ `X/` が両方あるため読めなくなって
    いるページパスを返す（名前順）。

    `iter_pages` はファイルを直に見つけるので `X.拡張子` を拾うが、
    `resolve_page_ref` はフォルダがあると常にその中の `index` を優先する
    （[Tech/Reference](/Tech/Reference/Resolve#対象ページの特定)参照）ため、`X/index` が
    無ければ「そのページは無い」ことになってしまう。`X.拡張子` の中身は
    残っているのに読めないという、気づきにくい食い違いだけを拾う
    （直しかたは決めていない。手でファイルを置いたときだけ起きるまれな形
    なので、ここでは知らせるだけにとどめる）。"""
    found = []
    for pagepath, _ in iter_pages(wiki_dir):
        ref = resolve_page_ref(wiki_dir, pagepath)
        if ref is not None and not ref.exists:
            found.append(pagepath)
    return sorted(set(found))


# ---- 作り直し ---------------------------------------------------------------

def first_backup_stamp(wiki_dir, subpath):
    """そのページのいちばん古いバックアップの日時。無ければNone。

    DBを作り直すとき、初回登録日時の代わりに使う。"""
    stamp = _first_backup_stamp(wiki_dir, subpath)
    if stamp is None:
        return None
    try:
        return time.strftime(TIME_FORMAT, time.strptime(stamp, "%y%m%d_%H%M%S"))
    except ValueError:
        return None


def rebuild(wiki_dir):
    """平文ファイルからDBを作り直す。登録したページ数を返す。

    平文が正本なので中身はそのまま戻る。分からないのは初回登録日時だけで、
    バックアップの差分がいちばん古い日時を使い、それも無ければファイルの
    更新時刻で代える。"""
    path = db_path(wiki_dir)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass

    rows = []
    for pagepath, _ in iter_pages(wiki_dir):
        ref = resolve_page_ref(wiki_dir, pagepath)
        if ref is None or not ref.exists:
            continue
        try:
            stat = os.stat(ref.path)
        except OSError:
            continue
        updated = stamp_of(stat.st_mtime)
        created = first_backup_stamp(wiki_dir, ref.subpath) or updated
        rows.append((ref.subpath, ref.subpath + ref.ext, ref.body,
                     created, updated, stat.st_size, stat.st_mtime,
                     body_hash(ref.body)))
    try:
        with connect(wiki_dir) as con:
            # 本文だけを戻す。title/toc/links は全文のパースが要って重いので、
            # ここでは作らず、ページを開いたときに ensure_page_info が作る
            con.executemany(
                "INSERT OR REPLACE INTO pages"
                " (subpath, path, body, created, updated, size, mtime, bodyhash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    except sqlite3.Error:
        return 0
    return len(rows)


def is_usable(wiki_dir):
    """DBが開けて読める状態か。"""
    path = db_path(wiki_dir)
    if not os.path.isfile(path):
        return False
    try:
        with connect(wiki_dir) as con:
            con.execute("SELECT count(*) FROM pages").fetchone()
    except sqlite3.Error:
        return False
    return True


def ensure_db(wiki_dir):
    """DBが使えることを確かめ、駄目なら作り直す。作り直したらTrueを返す。"""
    if is_usable(wiki_dir):
        return False
    rebuild(wiki_dir)
    return True
