"""保存時の差分バックアップ（wikidata/<Wiki名>/pageinfo/backup.db）。

全文を世代ごとに複製せず、「上書き前 → 上書き後」のunified diffを1本ずつ残す。
差分を新しいほうから順に逆適用すれば、過去の内容を復元できる。

## 置き場所をファイルからDBに移した（2026-08-31、Wiki設計者の指示）

以前は1回の保存につき1つの `.diff` ファイル（`pageinfo/backup/` の中に
`Tech_ChangeLog.260813_214056.diff` のような名前で）だった。同じ日に
世代数の上限（1ページ20本）を撤廃して大きさ（各Wiki50MB）で区切る形に
したことで、**1つのフォルダに1万本を超えるファイルが並びうる**ように
なったため、DBへ移した。ファイルのままだと次の costs が効いてくる。

  - 1ページの履歴を出すだけで、フォルダ全体を舐めて名前を照合していた
    （保存のたび・履歴を見るたび）。DBならページ名の索引で1回引くだけ
  - 上限の判定も毎回すべてのファイルの大きさを足していた
  - 差分の中央値は2KBほどなので、4KBのブロックに1本ずつ置くと
    実バイトの1.8倍ほどをディスク上で占めていた
  - ページ名をファイル名に押し込むため `/` を `_` に退避する仕掛けが
    必要だった（`backup_name_of`）。DBでは列に入れるだけで済む

**外から見た振る舞いは変えていない。** 呼び出し口（backup_page /
backup_history / backed_up_subpaths / find_backup_version / purge_backups）
はそのままで、`tests/test_backup.py` は移行の前後で同じものが通る。

既存の `.diff` ファイルは、DBを初めて作るときに一度だけ取り込む
（`_import_diff_files`）。取り込み元のファイルは消さずに残してある。
"""
import datetime
import difflib
import hashlib
import os
import re
import sqlite3

from wikilib.paths import (
    BACKUP_MERGE_SECONDS, BACKUP_MIN_KEEP, BACKUP_PRUNE_TARGET, BACKUP_STAMP,
    BACKUP_TOTAL_BYTES, farm_pageinfo_dir,
)

DB_NAME = "backup.db"
# 1回の保存ぶんの記録。stamp は "yymmdd_hhmmss"（表示にも、画面から時点を
# 指す key にも使う）。size は diff のバイト数で、上限の判断に使う
# （文字数ではなくバイト数で数えたいので、その場で計算せず列に持つ）。
SCHEMA = """
CREATE TABLE IF NOT EXISTS backup (
    subpath TEXT NOT NULL,
    stamp   TEXT NOT NULL,
    diff    TEXT NOT NULL,
    size    INTEGER NOT NULL,
    PRIMARY KEY (subpath, stamp)
);
CREATE INDEX IF NOT EXISTS backup_stamp ON backup (stamp);

-- 改名の記録（move_backups）。差分の記録は改名のときに新しい名前へ付け替えるので、
-- ここに残さないと「その時点にはどの名前だったか」が分からなくなる
-- （wikilib.snapshot が使う）。同じ秒の改名の前後は rowid で決まる。
CREATE TABLE IF NOT EXISTS moves (
    stamp       TEXT NOT NULL,
    old_subpath TEXT NOT NULL,
    new_subpath TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS moves_stamp ON moves (stamp);
"""

BACKUP_NAME_RE = re.compile(r"^(?P<name>.+)\.(?P<stamp>\d{6}_\d{6})\.diff$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")
# 順向きに当てるとき用。同じhunkヘッダの「変更前」側（-）を見る
HUNK_OLD_RE = re.compile(r"^@@ -(?P<start>\d+)(?:,(?P<count>\d+))? \+\d+(?:,\d+)? @@")
NO_NEWLINE_MARK = "\\ No newline at end of file"


def backup_name_of(subpath):
    """ページの実体パスを、差分の中に書く見出し（--- / +++ の行）に変換する。

    もとは**ファイル名**を作るためのもので、階層の "/" が使えないため "_" に
    置き換えていた（元から含まれる "_" は "__" に退避。例: "Tech/My_Page" →
    "Tech_My__Page"）。DBへ移して以降、置き場所を決めるのには使わないが、
    次の2つで今も要る。

      - 差分そのものに書く見出し（過去に記録した差分と書式をそろえるため）
      - 旧形式のファイルを取り込むときの照合（subpath_of_backup_name の逆）
    """
    return subpath.replace("_", "__").replace("/", "_")


def make_diff(old_text, new_text, name, old_stamp, new_stamp):
    """unified diffを作る。末尾に改行が無い行は、diffコマンドと同じ書きかたで印を付ける
    （そうしないと次の行と続いてしまい、差分として読み戻せなくなる）。"""
    lines = difflib.unified_diff(
        old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
        fromfile=name, tofile=name, fromfiledate=old_stamp, tofiledate=new_stamp)
    out = []
    for line in lines:
        out.append(line)
        if not line.endswith("\n"):
            out.append("\n" + NO_NEWLINE_MARK + "\n")
    return "".join(out)


def content_rev(text):
    """本文の中身を短いハッシュにする。楽観ロック用（「保存しようとしている今の内容」と
    「画面を開いたときに見ていた現在の内容」が一致するかを、本文そのものを送らずに
    確かめるため）。差分の記録・復元には使わない。"""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def apply_diff(old_text, diff_text):
    """unified diffを**順向きに**適用し、その差分を取ったあとの内容を作る。
    辻褄が合わなければNoneを返す。

    控えからDBを戻したあと、控え以後の記録を順に当てて内容をそこまで
    進めるために使う（dbbackup.restore_from_zip。2026-09-01、Wiki設計者の指示:
    「バックアップの日時からの差分履歴を反映させることが可能なら、履歴は
    捨てずにそこまで戻したファイルを用意し」）。

    reverse_diff の裏返しで、見る側が逆になる。

        " " 変更前にも後にもある  → 元の行と照合して、そのまま持ち越す
        "-" 変更前にだけある      → 元の行と照合して、落とす
        "+" 変更後にだけある      → 元は読まずに、書き足す
    """
    old_lines = old_text.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)
    out = []
    pos = 0  # old_lines のどこまで読んだか
    i = 0
    while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
        i += 1  # ---/+++ のヘッダを読み飛ばす
    if diff_lines and i >= len(diff_lines):
        return None   # 中身はあるのに hunk が無い＝壊れている（reverse_diffと同じ）
    while i < len(diff_lines):
        m = HUNK_OLD_RE.match(diff_lines[i])
        if m is None:
            return None
        count = 1 if m.group("count") is None else int(m.group("count"))
        # 変更前が0行のhunkは、開始行が「その直前の行」を指す決まりになっている
        idx = int(m.group("start")) - 1 if count else int(m.group("start"))
        if not pos <= idx <= len(old_lines):
            return None
        out.extend(old_lines[pos:idx])  # hunkとhunkの間はそのまま持ち越す
        pos = idx
        i += 1
        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            line = diff_lines[i]
            i += 1
            if line.startswith(NO_NEWLINE_MARK):
                continue  # 直前の行の処理で消費済み
            tag, body = line[:1], line[1:]
            if i < len(diff_lines) and diff_lines[i].startswith(NO_NEWLINE_MARK):
                body = body[:-1] if body.endswith("\n") else body
            if tag in (" ", "-"):  # 変更前にあった行 → 照合して読み進める
                if pos >= len(old_lines) or old_lines[pos] != body:
                    return None
                pos += 1
            elif tag != "+":
                return None
            if tag in (" ", "+"):  # 変更後にある行 → 結果に残す
                out.append(body)
    out.extend(old_lines[pos:])
    return "".join(out)


def reverse_diff(new_text, diff_text):
    """unified diffを逆向きに適用し、その差分を取る前の内容を復元する。
    差分を統合するとき、直前の差分の「変更前」を取り戻すために使う。
    少しでも辻褄が合わなければNoneを返す（呼び出し側は統合をあきらめる）。"""
    new_lines = new_text.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)
    out = []
    pos = 0  # new_lines のどこまで読んだか
    i = 0
    while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
        i += 1  # ---/+++ のヘッダを読み飛ばす
    if diff_lines and i >= len(diff_lines):
        # **中身はあるのに hunk（@@）が1つも無い＝壊れている。**
        # ここで None を返さないと「変更なし」と同じ扱いになり、
        # さかのぼれていないのに次の差分をその位置から当ててしまう。
        # 結果、そのページが一度も持ったことのない内容が「過去の状態」として
        # 履歴に並び、復元もできてしまっていた（2026-09-01に修正）。
        #
        # 記録される差分には必ず hunk がある（backup_page は差分が空なら
        # 書かない）ので、「中身はあるが hunk が無い」は壊れていると判断してよい。
        return None
    while i < len(diff_lines):
        m = HUNK_RE.match(diff_lines[i])
        if m is None:
            return None
        count = 1 if m.group("count") is None else int(m.group("count"))
        # 変更後が0行のhunkは、開始行が「その直前の行」を指す決まりになっている
        idx = int(m.group("start")) - 1 if count else int(m.group("start"))
        if not pos <= idx <= len(new_lines):
            return None
        out.extend(new_lines[pos:idx])  # hunkとhunkの間はそのまま持ち越す
        pos = idx
        i += 1
        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            line = diff_lines[i]
            i += 1
            if line.startswith(NO_NEWLINE_MARK):
                continue  # 直前の行の処理で消費済み
            tag, body = line[:1], line[1:]
            if i < len(diff_lines) and diff_lines[i].startswith(NO_NEWLINE_MARK):
                body = body[:-1] if body.endswith("\n") else body
            if tag in (" ", "+"):  # 変更後にある行 → 読み進める
                # **中身も照合する。** " " も "+" も「変更後にこの行がある」と
                # 言っているので、渡されたテキストと食い違えばこの差分は
                # そのテキストのものではない。以前は " " しか比べておらず、
                # 別の内容にも当たってしまった結果、**そのページが持ったことの
                # ない内容が過去の状態として出ていた**（2026-09-01に修正。
                # 当たらない記録を飛ばして辿るようにしたことで、この照合の
                # 甘さがそのまま偽の履歴になるため）
                if pos >= len(new_lines) or new_lines[pos] != body:
                    return None
                pos += 1
            elif tag != "-":
                return None
            if tag in (" ", "-"):  # 変更前にあった行 → 復元結果に残す
                out.append(body)
    out.extend(new_lines[pos:])
    return "".join(out)


# ---- 置き場所（DB） ---------------------------------------------------------

def db_path(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, DB_NAME)


def connect(wiki_dir):
    """DBを開く。無ければ作り、そのとき既存の.diffファイルを一度だけ取り込む。

    スキーマは毎回そろえる（安いので。pagedb.connect と同じ流儀）。"""
    path = db_path(wiki_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fresh = not os.path.exists(path)
    if fresh:
        # 空で作る前に、控え（backup.db.zip）があれば戻す（2026-09-01）。
        # 戻したあと、控えの時点からいまの本文までの橋渡しも足される
        # （dbbackup.restore_history_from_zip）
        from wikilib.dbbackup import restore_history_from_zip
        if restore_history_from_zip(wiki_dir):
            fresh = False
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    if fresh:
        # 作ったばかりのときだけ取り込む。**2度は行わない**ので、取り込みの
        # あとに履歴を消しても、次に開いたときに復活したりはしない
        _import_diff_files(con, backup_root_of(wiki_dir))
    return con


def _import_diff_files(con, backup_root):
    """旧形式（1保存＝1ファイル）の差分をDBへ移す。移した本数を返す。

    **元のファイルは消さない。** 履歴はほかに複製の無い記録なので、
    移せたことを確かめてから手で片付けられるようにしておく。"""
    try:
        entries = sorted(os.listdir(backup_root))
    except OSError:
        return 0
    rows = []
    for fname in entries:
        m = BACKUP_NAME_RE.match(fname)
        if m is None:
            continue
        try:
            with open(os.path.join(backup_root, fname), encoding="utf-8") as f:
                diff = f.read()
        except OSError:
            continue  # 読めないものは移さない（元のファイルは残る）
        rows.append((subpath_of_backup_name(m.group("name")), m.group("stamp"),
                     diff, len(diff.encode("utf-8"))))
    if rows:
        con.executemany(
            "INSERT OR IGNORE INTO backup (subpath, stamp, diff, size) VALUES (?,?,?,?)",
            rows)
        con.commit()
    return len(rows)


def _rows_of(con, subpath):
    """そのページの記録を古い順に返す。"""
    return con.execute(
        "SELECT stamp, diff FROM backup WHERE subpath = ? ORDER BY stamp",
        (subpath,)).fetchall()


def latest_backup(con, subpath):
    """そのページの最も新しい記録を (日時文字列, 日時) で返す。無ければ (None, None)。"""
    row = con.execute(
        "SELECT stamp FROM backup WHERE subpath = ? ORDER BY stamp DESC LIMIT 1",
        (subpath,)).fetchone()
    if row is None:
        return None, None
    return row["stamp"], datetime.datetime.strptime(row["stamp"], BACKUP_STAMP)


def backup_page(wiki_dir, subpath, old_text, new_text, now=None, merge=True):
    """保存時の差分を1件記録する（DBの backup 表に1行）。

    直前の差分が10分以内に作られていれば、そこまでさかのぼった1本の差分にまとめ直す
    （日時は最後に保存した時刻になる）。短い間隔の推敲がそのまま何十世代にもなるのを
    防ぐためで、まとめた結果として変化が無くなった場合は記録そのものを取り下げる。

    merge=False にすると、この統合を行わず必ず1本の差分として残す。
    ページの削除がこれにあたる。作ってすぐ消した場合、統合すると「空→空」で
    差し引きゼロになり、消える直前の内容がどこにも残らなくなってしまうため。

    新規作成（保存前の内容が空）の場合も記録する。**最初に記録された
    内容として履歴に残す価値があるため**（一覧での見せかたは
    backup_history側で調整する。そこより古い記録は辿らない、という形）。"""
    if old_text == new_text:
        return
    now = now or datetime.datetime.now()
    with connect(wiki_dir) as con:
        base_text, merged_stamp = old_text, None
        prev_stamp, prev_time = latest_backup(con, subpath)
        if (merge and prev_time is not None
                and (now - prev_time).total_seconds() < BACKUP_MERGE_SECONDS):
            row = con.execute(
                "SELECT diff FROM backup WHERE subpath = ? AND stamp = ?",
                (subpath, prev_stamp)).fetchone()
            # 直前の差分を今の内容に逆適用すると、その差分を取る前の内容が戻る
            restored = reverse_diff(old_text, row["diff"]) if row is not None else None
            if restored is not None:
                base_text, merged_stamp = restored, prev_stamp

        if merged_stamp is not None:
            con.execute("DELETE FROM backup WHERE subpath = ? AND stamp = ?",
                        (subpath, merged_stamp))

        # 同じ秒に2回保存すると日時が衝突する（日時はその記録を指す名前でもある）。
        # 空くまで1秒ずつずらす（書式と時系列の並びを保ったまま避けられる）。
        while True:
            stamp = now.strftime(BACKUP_STAMP)
            taken = con.execute(
                "SELECT 1 FROM backup WHERE subpath = ? AND stamp = ?",
                (subpath, stamp)).fetchone()
            if taken is None:
                break
            now += datetime.timedelta(seconds=1)

        diff = make_diff(base_text, new_text, backup_name_of(subpath), "", stamp)
        if diff:  # 統合の結果、元に戻っていた場合は何も残さない
            con.execute(
                "INSERT INTO backup (subpath, stamp, diff, size) VALUES (?,?,?,?)",
                (subpath, stamp, diff, len(diff.encode("utf-8"))))
            # つながりの切れた古い記録を捨てる（そのページぶんだけ）。
            # 消したあとに全体の大きさを見るので、この順で呼ぶ
            prune_unreachable(con, subpath, new_text)
            prune_by_total_size(con, protect=(subpath, stamp))


def prune_unreachable(con, subpath, current_text):
    """そのページの記録のうち、**現在からどうやっても当たらない**ものを消す。
    消した本数を返す。

    現在の内容から新しい順に逆適用していき、当たらなかった記録を捨てる。
    復元先としても比較相手としても使えないため（Wiki設計者の判断、2026-09-01）。

    **当たらない記録を飛ばして先を試す、ということはしない**（backup_history
    と同じ理由。差分は変更箇所しか書いていないので、飛ばして辿ると偽の
    履歴を作りかねない）。DBを控えから戻したときに出る「宙に浮いた記録」は、
    戻すその場で片付ける（dbbackup.restore_from_zip）ので、ここへは来ない。

    **「新規作成で打ち切っているだけ」のものは消さない。** 履歴の一覧は
    新規作成の記録に達したところで止めるが（backup_history参照）、その先の
    記録は差分としては続いており、機械的には辿れる。ページを消して作り直す
    前の履歴がこれにあたる。見せていないだけで壊れてはいないので残す。
    ここが逆適用を「打ち切らずに」最後まで試すのは、その2つを見分けるため。

    つながりが切れるのは、システムを通さずにDBを作り直したときなど
    （内容のある状態から、差分を残さずに空になっている）。ふだんの保存では
    起こらない。

    保存のたびにそのページぶんだけ辿り直す。記録の数はページあたり
    せいぜい数十本で、逆適用も1本あたり短いので、保存の重さとして問題に
    ならない。"""
    rows = con.execute(
        "SELECT stamp, diff FROM backup WHERE subpath = ? ORDER BY stamp",
        (subpath,)).fetchall()
    text, broken_at = current_text, None
    for i in range(len(rows) - 1, -1, -1):
        older = reverse_diff(text, rows[i]["diff"])
        if older is None:
            broken_at = i   # この記録から古いほうは、もう辿れない
            break
        text = older
    if broken_at is None:
        return 0
    con.executemany(
        "DELETE FROM backup WHERE subpath = ? AND stamp = ?",
        [(subpath, rows[i]["stamp"]) for i in range(broken_at + 1)])
    return broken_at + 1


def total_backup_bytes(wiki_dir):
    """そのWikiのバックアップが使っているバイト数。上限の判断とテストで使う。"""
    with connect(wiki_dir) as con:
        return con.execute("SELECT COALESCE(SUM(size), 0) AS n FROM backup").fetchone()["n"]


def prune_by_total_size(con, protect=None):
    """記録の合計が上限（BACKUP_TOTAL_BYTES）に達していたら掃除する。消した本数を返す。

    上限は**各Wikiごと**（DBが wikidata/<Wiki名>/pageinfo/backup.db なので、
    渡された1つのWikiの中だけを見る）。全Wikiの合計ではない。

    ページごとの世代数で区切るのをやめて大きさにしたのは、1回の変更量が
    大小さまざまで、世代数では場所の使用量が読めないため（2026-08-31）。

    ## 掃除のしかた（Wiki設計者の指示、2026-09-01）

    上限に達したら、**上限の半分（BACKUP_PRUNE_TARGET）まで**減らしにいく。
    ぎりぎりまでしか減らさないと、以後は保存のたびに掃除が走り、そのたびに
    いちばん古い記録が1件ずつ削られていく。半分まで空けておけば、掃除は
    たまにしか起きない。

    **記録が BACKUP_MIN_KEEP（20）に満たないページからは消さない。** 上限に
    触れる原因はたいてい保存の多い一部のページで、履歴の浅いページまで
    巻き添えにすると、めったに更新しないページの数少ない記録が先に消えて
    しまう。消していくうちに20件を割ったページも、そこで対象から外れる
    （＝どのページにも19件は残る）。

    **消すのはいつも最も古い保存から。** 差分は新しいほうから逆にたどる
    仕組み（backup_history）なので、古い側を削っても残りはそのまま
    たどれる。「どこまで戻せるか」が縮むだけで、履歴が途中で欠けることはない。

    半分まで減らせなくても、**消せる候補が尽きたらそこで打ち切る**
    （20件以上のページが無ければ1件も消えない）。上限は目安であって、
    履歴を削ってでも必ず収める、という約束ではない。

    protect には今書いたばかりの記録を (subpath, stamp) で渡す。書いた直後の
    記録が自分で自分を消してしまうのを避けるため。"""
    total = con.execute("SELECT COALESCE(SUM(size), 0) AS n FROM backup").fetchone()["n"]
    if total <= BACKUP_TOTAL_BYTES:
        return 0
    target = BACKUP_TOTAL_BYTES * BACKUP_PRUNE_TARGET

    # ページごとの残り本数。消すたびに減らし、20件を割ったページは対象から外す
    counts = {r["subpath"]: r["n"] for r in con.execute(
        "SELECT subpath, COUNT(*) AS n FROM backup GROUP BY subpath")}
    # 日時の書式が桁揃えなので、そのまま並べれば時系列になる（ページをまたいでも同じ）。
    # 消しながら辿らずに済むよう、先に読み切っておく
    rows = con.execute(
        "SELECT subpath, stamp, size FROM backup ORDER BY stamp, subpath").fetchall()

    removed = 0
    for row in rows:
        if total <= target:
            break
        if protect is not None and (row["subpath"], row["stamp"]) == protect:
            continue
        if counts.get(row["subpath"], 0) < BACKUP_MIN_KEEP:
            continue
        con.execute("DELETE FROM backup WHERE subpath = ? AND stamp = ?",
                    (row["subpath"], row["stamp"]))
        counts[row["subpath"]] -= 1
        total -= row["size"]
        removed += 1
    return removed


# ---- 履歴の読み出しと復元 ---------------------------------------------------
# 差分は「上書き前 → 上書き後」なので、現在の内容に新しいほうから順に逆適用すると
# 過去の各時点の内容が得られる。バックアップ管理画面はこれを使う。

def backup_root_of(wiki_dir):
    """旧形式（1保存＝1ファイル）の置き場所。いまは取り込み元としてだけ見る。"""
    return farm_pageinfo_dir(wiki_dir, "backup")


def subpath_of_backup_name(name):
    """旧形式の差分ファイル名の見出し部分から、ページの実体パスに戻す。
    backup_name_of の逆（"Tech_My__Page" → "Tech/My_Page"）。取り込みで使う。"""
    mark = "\x00"
    return name.replace("__", mark).replace("_", "/").replace(mark, "_")


def move_backups(wiki_dir, old_subpath, new_subpath, now=None):
    """そのページの記録を、新しいページ名のものとして付け替える。移した本数を返す。

    ページの改名から呼ぶ。内容は変わっていないので新しい差分は作らず、
    どのページの記録かという結び付けだけを変える。

    移動先に同じ日時の記録があるものは触らない（そちらを壊さないため。
    改名先に既に履歴があるのは、同じ名前のページを作り直した場合など）。

    改名したこと自体も moves 表に1行残す（移す記録が無くても残す。記録の
    付かない古いページでも、その時点の名前が要るため）。"""
    now = now or datetime.datetime.now()
    with connect(wiki_dir) as con:
        con.execute("INSERT INTO moves (stamp, old_subpath, new_subpath) VALUES (?,?,?)",
                    (now.strftime(BACKUP_STAMP), old_subpath, new_subpath))
        taken = {r["stamp"] for r in con.execute(
            "SELECT stamp FROM backup WHERE subpath = ?", (new_subpath,))}
        moved = 0
        for row in con.execute(
                "SELECT stamp FROM backup WHERE subpath = ?", (old_subpath,)).fetchall():
            if row["stamp"] in taken:
                continue
            con.execute("UPDATE backup SET subpath = ? WHERE subpath = ? AND stamp = ?",
                        (new_subpath, old_subpath, row["stamp"]))
            moved += 1
        return moved


def first_backup_stamp(wiki_dir, subpath):
    """そのページのいちばん古い記録の日時（"yymmdd_hhmmss"）。無ければNone。

    pagedbがDBを作り直すとき、初回登録日時の代わりに使う（そのページを
    システムが最初に知った時刻として、いちばん古い記録の日時が近いため）。"""
    with connect(wiki_dir) as con:
        row = con.execute(
            "SELECT stamp FROM backup WHERE subpath = ? ORDER BY stamp LIMIT 1",
            (subpath,)).fetchone()
    return row["stamp"] if row is not None else None


def backed_up_subpaths(wiki_dir):
    """バックアップが1本でもあるページの実体パスを、名前順で返す。"""
    with connect(wiki_dir) as con:
        return [r["subpath"] for r in con.execute(
            "SELECT DISTINCT subpath FROM backup ORDER BY subpath")]


def count_changed_lines(diff_text):
    """差分に書かれた、増えた行数と減った行数を返す。

    **数えるのは最初の `@@` より後だけ。** `+++`／`---` で始まる行をヘッダと
    見なして除く方法だと、本文の行そのものが `++`／`--` で始まるとき
    （PukiWikiの入れ子の箇条書き `++ x`、差分では `+++ x`）に、増えた行なのに
    数え落とす。ヘッダは `@@` より前にしか無いので、位置で区別する。"""
    added = removed = 0
    in_hunk = False
    for ln in diff_text.splitlines():
        if not in_hunk:
            in_hunk = ln.startswith("@@")
            continue
        if ln.startswith("+"):
            added += 1
        elif ln.startswith("-"):
            removed += 1
    return added, removed


def backup_history(wiki_dir, subpath, current_text):
    """そのページの各時点の内容を、新しい順に復元して返す。

    戻り値は [{key, stamp, text, added, removed, broken}] で、stamp は
    その保存が行われた日時。

    **text はその保存を行う「前」の内容**（Wiki設計者の指示、2026-08-31）。
    つまり「この時刻に保存されたぶんを取り消したら、どうなるか」を表す。
    バックアップは「その保存で何が変わったか」を記録したものなので、
    選んで戻す先も「その保存が行われる前」でなければ辻褄が合わない
    （added/removed に出ている増減が、ちょうど打ち消される先になる）。

    **ページが作られた記録（＝その保存の「前」が空）は一覧に入れない。**
    その「前」はページが無かった状態で、戻す先として意味が無いため。
    一度も実質的な変更が無いページ（記録がその1件だけ）は、一覧そのものが
    空になる。

    **ただし、そこで辿るのをやめない**（Wiki設計者の指示、2026-09-01）。もっと古い
    記録があれば、同じ名前で使われていた前の一生のぶん。消してから作り直した
    だけなので、その内容も戻す先として意味がある。**履歴があれば再作成、
    無ければこれまでどおりの新規作成**、という分かれかたになる。境目の項目には
    `recreated` を立てるので、画面は「これより古いのは作り直す前」と示せる。

    差分が読めなくなっていた場合は、そこまでに拾えた最も古い項目に broken
    を立てて打ち切る（これより前は辿れない、という印）。

    **当たらない記録を飛ばして先を試す、ということはしない。** 差分は
    変更した箇所しか書いていないので、離れた場所が違うテキストにも
    「当たって」しまうことがある。飛ばして辿ると、そのページが持ったことの
    ない内容を過去の状態として並べてしまう（2026-09-01に実際に確かめた）。
    宙に浮いた記録は、控えから戻すときにその場で片付ける
    （dbbackup.restore_from_zip）。"""
    with connect(wiki_dir) as con:
        rows = _rows_of(con, subpath)  # 古い順
    history, text = [], current_text
    recreated = False   # 直前に「作られた記録」を跨いだか（次の項目に印を付ける）
    for row in reversed(rows):  # 新しい順にさかのぼる
        stamp, diff = row["stamp"], row["diff"]
        # その保存を取り消した状態＝この差分を逆適用した結果。これが
        # この項目の中身になる（＝「前」の内容）
        older = reverse_diff(text, diff) if diff is not None else None
        if older is None:
            # ここから先はさかのぼれない。この保存の「前」が作れないので
            # 項目そのものを作れず、直前まで拾えたぶんに印を付けて打ち切る
            if history:
                history[-1]["broken"] = True
            return history

        if not older.strip():
            # この保存の「前」はページが無かった状態（＝作られた記録）。
            # その「前」は戻す先として意味が無いので**一覧には入れない**。
            #
            # ただし**そこで辿るのをやめない**（Wiki設計者の指示、2026-09-01）。
            # もっと古い記録があれば、それは同じ名前で使われていた前の一生の
            # ぶん。消してから作り直した、というだけで、その前の内容も
            # 戻す先として意味がある。**履歴があれば再作成、無ければ
            # これまでどおりの新規作成**、という分かれかたになる。
            #
            # ここから先は「ページが無い状態」を起点に辿る。次に来るのは
            # 消したときの記録（内容→空）のはずで、それを逆適用すれば
            # 消える直前の内容が戻る。噛み合わなければ当たらずに打ち切られる
            text = older
            recreated = True
            continue
        added, removed = count_changed_lines(diff)
        history.append({"key": stamp, "stamp": stamp, "text": older,
                        "added": added, "removed": removed, "broken": False,
                        # これより古いのは、作り直す前の一生のぶん、という印
                        "recreated": recreated})
        recreated = False
        text = older
    return history


def find_backup_version(wiki_dir, subpath, key, current_text):
    """key で指した時点の記録を1つ返す。見つからなければNone。"""
    for item in backup_history(wiki_dir, subpath, current_text):
        if item["key"] == key:
            return item
    return None


def purge_backups(wiki_dir, subpath):
    """そのページのバックアップをすべて消す。消した本数を返す。"""
    with connect(wiki_dir) as con:
        return con.execute("DELETE FROM backup WHERE subpath = ?", (subpath,)).rowcount
