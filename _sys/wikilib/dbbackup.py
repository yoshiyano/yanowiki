"""ページ本文のDB（pageinfo/wikiall.db）の控えを1日1回とる。

## なぜ要るか

**DBを失うと、バックアップ（差分の履歴）が過去へたどれなくなる。**
差分は「そのとき公開されていた内容（DB）→ 新しい内容」として記録されるので、
DBの行が消えた状態でページを取り込み直すと、その差分は「空→内容」として
記録される。すると、それより古い記録は逆適用が当たらなくなり、二度と
たどれない（2026-08-18に実際に起きている。詳しくは
[2026-09-01の記録](/Tech/ChangeLog/2026-09-01)）。

壊れていないDBが1つ残っていれば、そこまでの履歴は生き延びる。新しく作り直す
場合でも、古いDBから最新までの差分を組み立て直せるので、途中の細かい履歴は
失われても**過去へさかのぼる道は残る**（Wiki設計者の判断、2026-09-01）。

## いつ動くか

ページか添付ファイルへのアクセスがあったとき、`maybe_backup()` が呼ばれる。
控え（wikiall.db.zip）の更新日が前日以前なら、**そのアクセスの応答を
待たせないよう別のスレッドで**控えを取り直す。

判定に使うのは控え自身の日付だけ。「控えが古ければ取り直す」という目的を
そのまま表すので、別に印を置く必要がない。控えが無ければ初回として動く。

## 何をするか

1. 元のDBの壊れていないことを確かめる（`PRAGMA integrity_check` と、
   実際に読めるかの確認）。**壊れていたら何もしない**（壊れたもので
   無事な控えを上書きしないため）
2. sqliteの複製機能で、書き込み途中でない揃った状態の写しを作る
3. それをzipに固め、`wikiall.db.zip` へ置き換える

置き換えは、いったん別名で作ってから `os.replace` で入れ替える。途中で
落ちても、中途半端なzipが控えとして残らない。
"""
import datetime
import os
import shutil
import sqlite3
import tempfile
import threading
import zipfile

from wikilib.backup import DB_NAME as BACKUP_DB_NAME
from wikilib.pagedb import DB_NAME as PAGE_DB_NAME
from wikilib.paths import farm_pageinfo_dir

ZIP_NAME = PAGE_DB_NAME + ".zip"
# 控えの中に入れる目印。どこまでの記録に対応する控えかを書いておく
MARK_NAME = "snapshot.txt"

# 履歴のDB（差分そのもの）も同じやりかたで控える（Wiki設計者の指示、2026-09-01）。
# ページ本文のDBと**同じ瞬間に**取るので、2つの控えは辻褄が合っている
HIST_DB_NAME = BACKUP_DB_NAME
HIST_ZIP_NAME = HIST_DB_NAME + ".zip"

# いま控えを取っている最中のWiki。同じWikiで何本も走らせないための札
# （アクセスが立て込むと、判定を抜けたスレッドが同時に何本も立ちうる）
_running = set()
_lock = threading.Lock()

# 控えを作る途中の一時ファイル（sqliteの写し `.copy` と、入れ替える前の `.zip`）の
# 名前の頭。ふだんは作り終えるか失敗した時点で消すが、**プロセスごと止められると
# （再起動の SIGTERM など）残る**。残ったものは起動時に `sweep_leftovers` が消す。
# 頭を決めておくのは、そのとき pageinfo/ のほかのファイルを巻き込まないため
TEMP_PREFIX = "dbbackup-"
TEMP_SUFFIXES = (".copy", ".zip")


def zip_path(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, ZIP_NAME)


def db_path(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, PAGE_DB_NAME)


def hist_zip_path(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, HIST_ZIP_NAME)


def hist_db_path(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, HIST_DB_NAME)


def is_stale(wiki_dir, today=None):
    """控えが無いか、前日以前のものなら True。"""
    today = today or datetime.date.today()
    try:
        taken = datetime.date.fromtimestamp(os.path.getmtime(zip_path(wiki_dir)))
    except OSError:
        return True   # まだ一度も取っていない
    return taken < today


def healthy(path, table="pages"):
    """そのDBが読める状態か。壊れていれば False。

    `integrity_check` だけでは「開けるが中身が空」のような壊れかたを
    見落とすので、実際に表を数えるところまで確かめる。table は数える表の
    名前（ページ本文なら pages、履歴なら backup）。"""
    try:
        con = sqlite3.connect("file:{}?mode=ro".format(path), uri=True)
    except sqlite3.Error:
        return False
    try:
        row = con.execute("PRAGMA integrity_check").fetchone()
        if row is None or row[0] != "ok":
            return False
        con.execute("SELECT COUNT(*) FROM {}".format(table)).fetchone()
        return True
    except sqlite3.Error:
        return False
    finally:
        con.close()


def _zip_db(src, dst, arcname, table, mark=None):
    """DB1つをzipに固めて置く。置けたら True。壊れていれば触らずに False。

    `mark` を渡すと `snapshot.txt` として一緒に入れる。"""
    if not os.path.isfile(src) or not healthy(src, table):
        return False
    work = None
    try:
        # 書き込み途中の状態を掴まないよう、sqliteの複製機能で揃った写しを作る
        fd, work = tempfile.mkstemp(dir=os.path.dirname(dst), prefix=TEMP_PREFIX,
                                    suffix=".copy")
        os.close(fd)
        source = sqlite3.connect("file:{}?mode=ro".format(src), uri=True)
        try:
            copy = sqlite3.connect(work)
            try:
                source.backup(copy)
            finally:
                copy.close()
        finally:
            source.close()

        # いったん別名で作ってから入れ替える（途中で落ちても控えは壊れない）
        fd, tmp_zip = tempfile.mkstemp(dir=os.path.dirname(dst), prefix=TEMP_PREFIX,
                                        suffix=".zip")
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(work, arcname=arcname)
                if mark is not None:
                    z.writestr(MARK_NAME, mark)
            os.replace(tmp_zip, dst)
        except Exception:
            _remove(tmp_zip)
            raise
        return True
    except (OSError, sqlite3.Error, zipfile.BadZipFile):
        return False
    finally:
        if work:
            _remove(work)


def write_backup(wiki_dir):
    """控えを取り直す。ページ本文と履歴の2つとも。取れたら True。

    **2つを同じ瞬間に取る。** どちらの控えも「同じ時点のもの」でなければ、
    戻したときに辻褄が合わない（履歴の控えが持つ記録の続きが、本文の控えの
    内容と噛み合う必要がある）。

    どちらか一方でも壊れていたら、**両方とも触らない**。片方だけ新しい控えに
    なると、そのずれ自体が戻すときの食い違いになるため。

    呼ぶ側（run_backup）が別スレッドにしているので、ここは順番に行う。"""
    # 目印は「控えを取った時点でいちばん新しい記録の日時」。**先に控えるほうの
    # DBを読む前に**決めておく（2つの控えで同じ値を使うため）
    mark = latest_stamp(wiki_dir)
    if not healthy(db_path(wiki_dir), "pages"):
        return False
    if os.path.isfile(hist_db_path(wiki_dir)) and not healthy(
            hist_db_path(wiki_dir), "backup"):
        return False

    ok = _zip_db(db_path(wiki_dir), zip_path(wiki_dir), PAGE_DB_NAME, "pages", mark)
    if ok and os.path.isfile(hist_db_path(wiki_dir)):
        # 履歴のDBは、まだ一度も保存していないWikiでは無い（そのときは飛ばす）
        _zip_db(hist_db_path(wiki_dir), hist_zip_path(wiki_dir),
                HIST_DB_NAME, "backup", mark)
    return ok


def sweep_leftovers(wiki_dir):
    """控えを作る途中で残った一時ファイルを消す。消した数を返す。

    **起動時、前のプロセスを止めたあとに呼ぶ**（`wiki.py` の `main`）。その時点では
    控えを取っているスレッドが無いので、残っているものはどれも途中で止まった
    作業の残り。動いている最中に呼ぶと、取っている途中の一時ファイルを消してしまう。"""
    folder = farm_pageinfo_dir(wiki_dir)
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    count = 0
    for name in names:
        if name.startswith(TEMP_PREFIX) and name.endswith(TEMP_SUFFIXES):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                _remove(path)
                count += not os.path.exists(path)
    return count


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def latest_stamp(wiki_dir):
    """いちばん新しいバックアップの記録の日時。無ければ空文字列。"""
    from wikilib.backup import connect as backup_connect
    try:
        with backup_connect(wiki_dir) as con:
            row = con.execute("SELECT MAX(stamp) AS s FROM backup").fetchone()
        return (row["s"] or "") if row else ""
    except sqlite3.Error:
        return ""


def restore_from_zip(wiki_dir):
    """DBが無いときに、控えから戻す。戻せたら True。

    **これをせずにページを取り込み直すと、それ以前の履歴が失われる。**
    取り込みは「そのとき公開されていた内容（DB）→ ファイルの内容」を差分に
    するので、DBが空だと「空→内容」として記録され、それより古い記録が
    現在とつながらなくなるため（2026-09-01に実測。5件の履歴が0件になった）。

    控えを戻せば、取り込みは「控えの時点の内容 → いまの内容」という
    まっとうな1本になる。控え以後の細かい履歴は失われるが、**そこから
    先の過去へはそのまま辿れる**（Wiki設計者の構想、2026-09-01）。

    ## 控えより後の記録は、捨てずに当てて進める

    控えを戻しただけでは、DBの内容は控えを取った時点のものになる。そこへ
    **控え以後の記録を順向きに当てていき、最後に保存された状態まで進める**
    （roll_forward。Wiki設計者の指示、2026-09-01）。こうすれば、その期間の細かい
    履歴もそのまま使える。当てられない記録だけを消す。

    どこから当てるかの目印は、控えの中に入れてある `snapshot.txt`
    （控えを取った時点でいちばん新しい記録の日時）。ファイルの日時ではなく
    記録の日時を使うので、時計のずれや、あとからファイルを触った影響を
    受けない。

    **飛ばしながら辿る、という方法は採らない。** 差分は変更した箇所しか
    書いていないため、離れた場所が違うテキストにも当たってしまうことがあり、
    そのページが持ったことのない内容を過去として並べかねない
    （2026-09-01に実際に確かめた）。"""
    src, dst = zip_path(wiki_dir), db_path(wiki_dir)
    if os.path.exists(dst) or not os.path.isfile(src):
        return False
    try:
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            if PAGE_DB_NAME not in names:
                return False
            # 控えを取った時点の「いちばん新しい記録」。古い控えには入って
            # いないので、そのときはファイルの日時で代用する
            if MARK_NAME in names:
                taken = z.read(MARK_NAME).decode("utf-8").strip()
            else:
                taken = datetime.datetime.fromtimestamp(
                    os.path.getmtime(src)).strftime("%y%m%d_%H%M%S")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            # いったん別名で出してから置く（途中で落ちても半端なDBを残さない）
            tmp = dst + ".restoring"
            with z.open(PAGE_DB_NAME) as fin, open(tmp, "wb") as fout:
                shutil.copyfileobj(fin, fout)
        if not healthy(tmp):
            _remove(tmp)
            return False
        os.replace(tmp, dst)
    except (OSError, zipfile.BadZipFile, ValueError):
        _remove(dst + ".restoring")
        return False
    # 控え以後の記録を当てて、最後に保存された状態まで進める
    roll_forward(wiki_dir, taken)
    return True


def restore_history_from_zip(wiki_dir):
    """履歴のDBが無いときに、控えから戻す。戻せたら True。

    `backup.connect` が空で作る前に呼ばれる。

    ## 戻しただけでは足りない

    履歴の控えが持っているのは、控えを取った時点までの記録。**そのあいだに
    ページが保存されていれば、いまの本文はその先へ進んでいる。** 現在の本文
    から逆にたどろうとしても、いちばん新しい記録の「後」の状態と食い違って
    当たらず、履歴がまるごと行き止まりになる。

    そこで、**控えの時点の本文といまの本文を見比べて、違っていれば橋渡しの
    記録を1本足す**。控えの時点の本文は、対になる本文DBの控え
    （wikiall.db.zip）から読む。2つの控えは同じ瞬間に取っているので、
    履歴の控えの続きがちょうどそこから始まる。

    これで「控えまでの細かい履歴 ＋ そこからいまへの1本」という、ひと続きの
    形になる（Wiki設計者の指示、2026-09-01。本文DBのときと同じ考えかた）。"""
    src, dst = hist_zip_path(wiki_dir), hist_db_path(wiki_dir)
    if os.path.exists(dst) or not os.path.isfile(src):
        return False
    try:
        with zipfile.ZipFile(src) as z:
            if HIST_DB_NAME not in z.namelist():
                return False
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + ".restoring"
            with z.open(HIST_DB_NAME) as fin, open(tmp, "wb") as fout:
                shutil.copyfileobj(fin, fout)
        if not healthy(tmp, "backup"):
            _remove(tmp)
            return False
        os.replace(tmp, dst)
    except (OSError, zipfile.BadZipFile, ValueError):
        _remove(dst + ".restoring")
        return False
    bridge_to_now(wiki_dir)
    return True


def snapshot_bodies(wiki_dir):
    """本文DBの控えに入っている、各ページの本文。取り出せなければ空。"""
    src = zip_path(wiki_dir)
    if not os.path.isfile(src):
        return {}
    work = None
    try:
        with zipfile.ZipFile(src) as z:
            if PAGE_DB_NAME not in z.namelist():
                return {}
            fd, work = tempfile.mkstemp(suffix=".snap")
            os.close(fd)
            with z.open(PAGE_DB_NAME) as fin, open(work, "wb") as fout:
                shutil.copyfileobj(fin, fout)
        con = sqlite3.connect("file:{}?mode=ro".format(work), uri=True)
        try:
            return {r[0]: r[1] for r in con.execute("SELECT subpath, body FROM pages")}
        finally:
            con.close()
    except (OSError, sqlite3.Error, zipfile.BadZipFile):
        return {}
    finally:
        if work:
            _remove(work)


def bridge_to_now(wiki_dir, now=None):
    """控えの時点の本文と、いまの本文が違うページに、橋渡しの記録を1本足す。

    足した本数を返す。履歴のDBを控えから戻した直後に呼ぶ。"""
    from wikilib import pagedb
    from wikilib.backup import (
        BACKUP_STAMP, backup_name_of, connect as backup_connect, make_diff,
    )
    snapshot = snapshot_bodies(wiki_dir)
    if not snapshot:
        return 0
    now = now or datetime.datetime.now()
    added = 0
    try:
        for row in pagedb.all_pages(wiki_dir):
            subpath = row["subpath"]
            before = snapshot.get(subpath, "")
            after = pagedb.published_body(wiki_dir, subpath, "")
            if before == after:
                continue
            with backup_connect(wiki_dir) as con:
                # 同じ日時の記録があれば1秒ずらす（日時がその記録を指す名前）
                while True:
                    stamp = now.strftime(BACKUP_STAMP)
                    taken = con.execute(
                        "SELECT 1 FROM backup WHERE subpath = ? AND stamp = ?",
                        (subpath, stamp)).fetchone()
                    if taken is None:
                        break
                    now += datetime.timedelta(seconds=1)
                diff = make_diff(before, after, backup_name_of(subpath), "", stamp)
                if diff:
                    con.execute(
                        "INSERT INTO backup (subpath, stamp, diff, size)"
                        " VALUES (?,?,?,?)",
                        (subpath, stamp, diff, len(diff.encode("utf-8"))))
                    added += 1
    except sqlite3.Error:
        pass
    return added


def roll_forward(wiki_dir, cutoff):
    """控えの時点より後の記録を順に当てて、DBの内容をそこまで進める。

    戻り値は (進めたページ数, 当てられずに消した記録の本数)。

    控えを戻しただけでは、DBの内容は控えを取った時点のものになる。そこへ
    **控え以後の記録を順向きに当てていけば、最後に保存された状態まで
    戻せる**（Wiki設計者の指示、2026-09-01:「バックアップの日時からの差分履歴を
    反映させることが可能なら、履歴は捨てずにそこまで戻したファイルを用意し、
    現状のファイルまでで最後の差分を追加で記録するほうが良い」）。

    こうすると、控え以後の細かい履歴も**そのまま使える**。進めずに捨てると、
    その期間の記録が丸ごと失われていた。

    当てられない記録が出たら、そのページはそこで打ち切り、**それ以降の
    記録を消す**（Wiki設計者の指示:「適用できない履歴は削除して構わない」）。
    後続の記録は、当てられなかった記録のあとの状態を前提にしているので、
    どのみち使えない。

    このあと平文ファイルを取り込むと、「ここまで進めた内容 → いまの
    ファイル」という最後の1本が記録され、履歴がひと続きになる。"""
    from wikilib import pagedb
    from wikilib.backup import apply_diff, connect as backup_connect
    if not cutoff:
        return 0, 0
    try:
        with backup_connect(wiki_dir) as con:
            rows = con.execute(
                "SELECT subpath, stamp, diff FROM backup WHERE stamp > ?"
                " ORDER BY subpath, stamp", (cutoff,)).fetchall()
    except sqlite3.Error:
        return 0, 0

    by_page = {}
    for row in rows:
        by_page.setdefault(row["subpath"], []).append(row)

    moved, dropped = 0, []
    for subpath, records in by_page.items():
        text = pagedb.published_body(wiki_dir, subpath, "")
        advanced = False
        for i, row in enumerate(records):
            nxt = apply_diff(text, row["diff"])
            if nxt is None:
                # ここから先はこの記録の結果を前提にしているので、まとめて捨てる
                dropped.extend((subpath, r["stamp"]) for r in records[i:])
                break
            text, advanced = nxt, True
        if advanced and pagedb.replace_body(wiki_dir, subpath, text):
            moved += 1
    if dropped:
        try:
            with backup_connect(wiki_dir) as con:
                con.executemany(
                    "DELETE FROM backup WHERE subpath = ? AND stamp = ?", dropped)
        except sqlite3.Error:
            pass
    return moved, len(dropped)


def drop_after(wiki_dir, cutoff):
    """控えの時点より後に作られたバックアップの記録を消す。消した本数を返す。

    いまは roll_forward が当てられない記録だけを選んで消すので、ここは
    使っていない（当てられる記録まで捨ててしまうため）。"""
    from wikilib.backup import connect as backup_connect
    if not cutoff:
        return 0
    try:
        with backup_connect(wiki_dir) as con:
            return con.execute("DELETE FROM backup WHERE stamp > ?", (cutoff,)).rowcount
    except sqlite3.Error:
        return 0


def run_backup(wiki_dir):
    """控えを取り、終わったら札を下ろす（スレッドから呼ばれる）。"""
    try:
        write_backup(wiki_dir)
    finally:
        with _lock:
            _running.discard(wiki_dir)


def maybe_backup(wiki_dir):
    """控えが前日以前なら、別のスレッドで取り直す。走らせたら True。

    アクセスのたびに呼ばれるので、**ふだんは日付を1つ見るだけで帰る**
    （控えが今日のものなら何もしない）。控えを取る処理そのものは
    応答を待たせないよう別スレッドに出す。"""
    if not is_stale(wiki_dir):
        return False
    with _lock:
        if wiki_dir in _running:
            return False   # すでに走っている
        _running.add(wiki_dir)
    threading.Thread(target=run_backup, args=(wiki_dir,), daemon=True).start()
    return True
