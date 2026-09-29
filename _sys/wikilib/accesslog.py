"""ページ・添付ファイルへのアクセスログ（wikidata/<Wiki名>/log/access.log.db）。

**正常にアクセスできた場合だけ**を記録する。ページが存在して表示できた、
添付ファイルが存在して配信できた、という場面（views.render_page /
attach.serve_attach）から呼ばれる。存在しないページ・添付ファイルへの
アクセス（404）や、システム内部のURL（/.theme/ 等）は対象外。

置き場所を pageinfo/ と分けている理由は paths.farm_log_dir を参照。
DBが壊れた・読めない場合は作り直す（pagedb.py と同じ流儀）。ログはあくまで
付随情報なので、書き込みに失敗してもページ表示・添付配信そのものは止めない。

`os`列にはOS名だけでなくブラウザ種別もまとめて入れる（Wiki設計者の指示。列を
増やさず"OS;ブラウザ"の形にする）。書き込みは`format_os_browser()`、
読み出しは`split_os_browser()`を使う。2026-08-27より前に記録された行は
`;`を含まないOS名だけなので、`split_os_browser()`側でその形も読める
ようにしてある（過去の行を書き換える必要はない）。
"""
import os
import sqlite3
import time

from wikilib.paths import farm_log_dir

DB_NAME = "access.log.db"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"  # 画面にそのまま出せる書式（pagedb.pyと同じ）
# 同一(remote_addr, url)への連続アクセスをまとめる時間幅（秒）。ページ本体は
# render_page側にキャッシュの仕組みが無く常に200を返すため、304では
# リロード連打を見分けられない（pagedb.pyのBACKUP_MERGE_SECONDSと同じ
# 「短時間の連続操作は1件に畳む」考え方。Wiki設計者の指示で180秒に設定）。
DEDUP_WINDOW_SECONDS = 180

SCHEMA = """
CREATE TABLE IF NOT EXISTS access_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    accessed_at TEXT NOT NULL,
    url         TEXT NOT NULL,
    remote_addr TEXT,
    os          TEXT
);
CREATE INDEX IF NOT EXISTS access_log_accessed_at ON access_log (accessed_at);
"""

# User-Agent文字列から端末種別（OS）を大まかに判定するための手がかり。
# 判定は上から順に見るので並び順が重要（例: AndroidのUser-Agentには
# "Linux" も含まれるため、Androidを先に当てる必要がある。iOSも
# "like Mac OS X" を含むため、Macより先に判定する）。
_OS_PATTERNS = (
    ("Windows", ("windows",)),
    ("iOS", ("iphone", "ipad", "ipod")),
    ("Android", ("android",)),
    ("Mac", ("mac os x", "macintosh")),
    ("Linux", ("linux",)),
)

# User-Agent文字列からブラウザ種別を大まかに判定するための手がかり。
# OSと同じく判定は上から順に見るので並び順が重要——Chromiumベースの
# Edge/Operaや、多くのブラウザはUser-Agentに互換用の"Chrome"や"Safari"
# という語も含めているため、素性の分かる語（Edg/, OPR/等）を先に
# 当てないと、すべてChrome/Safariに判定されてしまう。
_BROWSER_PATTERNS = (
    ("Edge", ("edg/", "edge/", "edga/", "edgios/")),
    ("Opera", ("opr/", "opera")),
    ("Chrome", ("chrome/", "crios/")),
    ("Firefox", ("firefox/", "fxios/")),
    ("Safari", ("safari/",)),
)


def db_path(wiki_dir):
    return farm_log_dir(wiki_dir, DB_NAME)


def connect(wiki_dir):
    """DBを開く。無ければ作る。スキーマは毎回そろえる（安いので）。"""
    path = db_path(wiki_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def detect_os(user_agent):
    """User-Agent文字列から端末種別（OS）を大まかに判定する。分からなければ"不明"。"""
    if not user_agent:
        return "不明"
    ua = user_agent.lower()
    for name, keywords in _OS_PATTERNS:
        if any(keyword in ua for keyword in keywords):
            return name
    return "不明"


def detect_browser(user_agent):
    """User-Agent文字列からブラウザ種別を大まかに判定する。分からなければ"不明"。"""
    if not user_agent:
        return "不明"
    ua = user_agent.lower()
    for name, keywords in _BROWSER_PATTERNS:
        if any(keyword in ua for keyword in keywords):
            return name
    return "不明"


def format_os_browser(user_agent):
    """`os`列に入れる値を組み立てる。"OS;ブラウザ" の形（Wiki設計者の指示）。
    区切りは`;`固定（OS名・ブラウザ名のどちらにもこの文字は現れないため
    分割時にエスケープを考えなくてよい）。"""
    return f"{detect_os(user_agent)};{detect_browser(user_agent)}"


def split_os_browser(value):
    """`os`列の値を (OS名, ブラウザ名) に戻す。

    2026-08-27以前に記録された古い行は`os`列に"Windows"のようなOS名だけが
    入っており、`;`が無い。その場合はブラウザ側を"不明"にして読む
    （新しい形式に合わせて解釈するだけで、古い行を書き換える必要は無い）。"""
    if not value:
        return "不明", "不明"
    osname, sep, browser = value.partition(";")
    if not sep:
        return osname, "不明"
    return osname, browser or "不明"


def record_access(wiki_dir, url, remote_addr, user_agent, now=None, content_updated_at=None):
    """1件のアクセスを記録する。

    url にはブラウザが実際にアクセスしたURLパス（ページ or 添付ファイル）を
    そのまま渡す。DBが無ければ作る（ensure_db相当の処理をconnect内で毎回行う）。
    `os`列には"OS;ブラウザ"の形でまとめて入れる（Wiki設計者の指示。列を増やさず
    済ませるため）。

    直前に記録した同一(remote_addr, url)の行が`DEDUP_WINDOW_SECONDS`以内
    なら、新規行を増やさずその行の`accessed_at`を今回の日時に更新するだけに
    する（ページのリロード連打を1件に畳む。os列は最初の記録のまま変えない）。

    `content_updated_at`（そのページ本文DBの`updated`。pagedb.page_updated_at
    が返す、この関数と同じTIME_FORMAT形式の文字列）が、直前の記録
    （`accessed_at`）より新しければ、DEDUP_WINDOW_SECONDS以内でも統合せず
    新規行として記録する（Wiki設計者の指示）。ページ内容が変わった後の最初の
    アクセスは、単なるリロード連打とは違う「新しい内容へのアクセス」なので、
    まとめずに残すため。同じTIME_FORMAT同士の文字列比較は時系列の比較と
    一致するので、日時へ変換し直さず文字列のまま比較する。"""
    when = time.time() if now is None else now
    stamp = time.strftime(TIME_FORMAT, time.localtime(when))
    try:
        with connect(wiki_dir) as con:
            row = con.execute(
                "SELECT id, accessed_at FROM access_log"
                " WHERE url = ? AND remote_addr IS ?"
                " ORDER BY id DESC LIMIT 1",
                (url, remote_addr)).fetchone()
            if row is not None:
                prev_stamp = row[1]
                prev_when = time.mktime(time.strptime(prev_stamp, TIME_FORMAT))
                within_window = 0 <= when - prev_when <= DEDUP_WINDOW_SECONDS
                updated_since = (
                    content_updated_at is not None and content_updated_at > prev_stamp)
                if within_window and not updated_since:
                    con.execute(
                        "UPDATE access_log SET accessed_at = ? WHERE id = ?",
                        (stamp, row[0]))
                    return
            con.execute(
                "INSERT INTO access_log (accessed_at, url, remote_addr, os)"
                " VALUES (?, ?, ?, ?)",
                (stamp, url, remote_addr, format_os_browser(user_agent)))
    except sqlite3.Error:
        pass
