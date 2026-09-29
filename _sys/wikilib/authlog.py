"""認証の履歴（wikidata/<Wiki名>/log/auth.log.db）を読む。

ログインの回数制限とロックを入れるにあたって、**何が起きたかを後から辿れる
ように**残す記録（Wiki設計者の指示、2026-09-06）。仕様は
`Tech/Accounts/AuthLog`（照合の記録とロック）にまとめてある。

    authlog(unixtime, uid, remote, authstate)

    unixtime   いつ（UNIX時刻）
    uid        入力されたID（登録されていない名前も、そのまま残す）
    remote     どこから（接続元のIP）
    authstate  どうなったか（下記）

`authstate` の値（Wiki設計者の指示）。

    0        成功
    1〜99    失敗。**値はその時点の連続失敗回数**
    100      ロック
    101      そのIDが登録されていない
    102      無視した（止めているあいだの試み。パスワードは違っていた）
    103      無視した（止めているあいだの試み。**パスワードは合っていた**）

101〜103 の意味は2026-09-06に付け替えた（Wiki設計者の指示）。**それより前の記録は
古い意味のまま残っている**（当時は 101:無視、102:未登録。直していない）。

## いま記録しているもの

**パスワードで照合したときだけ**残す（`/.login` と `/.passwd`）。合言葉
（cookie）で通ったぶんは残さない——あれは開くたびに起きるので、残すと
履歴がページ閲覧で埋まってしまう。

    0        照合が通った
    1〜99    パスワードが違った。**値はその時点の連続失敗回数**（fail_count）
    101      そのIDが登録されていない
    102/103  無視した（5回まちがえたあとの10分間。下記）

**100（ロック）はまだ付かない。** ロックする仕組みがまだ無いため。

`uid` には**送られてきた文字列をそのまま**残す（Wiki設計者の指示、2026-09-06）。
前後の空白も、登録されていない名前も、打たれたとおりに残す——何が打たれたかを
見るための記録なので、こちらで整えると元が分からなくなる。

## 5回まちがえたら、しばらく無視する（Wiki設計者の指示、2026-09-06）

    IGNORE_AFTER    5     **この回数ごと**に無視に入る
    IGNORE_SECONDS  600   **最後の失敗から**この長さのあいだ（10分）
    FORGET_SECONDS  1200  これだけ間が空いた失敗は、判断から落とす（倍時間。20分）
    LOCK_TURNS      3     何ターン止めたらロックするか
    LOCK_AFTER      15    ロックまでの失敗回数（上の掛け算）

**運用の値は「5回・10分・3セット」**（Wiki設計者の指示、2026-09-06。運用に出す
2026-09-21に、試験用の暫定値「3回・2分・2ターン」から切り替えた）。

    5回まちがえた            → そこから10分は止まる（1ターン目）
    10分たった                → **また5回まで試せる**（6回目〜9回目は通す）
    10回目                   → また10分止まる（2ターン目）
    15回目                   → **ロック**（3ターン目の終わり）
    20分だれも失敗しなかった → 判断の数は0から。また5回まで試せる

**記録に残す連続失敗回数（authstate）はリセットしない**（Wiki設計者の指示）。
判断から落ちるだけで、通算は最後に通るまで伸びる——記録（`log/auth.log.db`）を見れば
「明けてはまた止まって、を何回繰り返しているか」が分かる。

無視しているあいだは、**パスワードが合っていてもNGとして扱う**。断りの文言も、
ふつうにまちがえたときと同じにする——止めていることを外から見て分からない
ようにするため（Wiki設計者の指示）。

記録には 102（パスワードも違った）か 103（**パスワードは合っていた**）を残す。
**合っていたかどうかは記録にだけ残す**——応答は同じなので、外からこの違いは
見えない。103 は見つけたら重い印で、まちがえて止められた本人か、当てられたかの
どちらか。**どちらであってもパスワードを変えたほうがよい。**

数えは 1〜99 の記録から見るので、**無視したぶん（102/103）は数を進めない**。
待ってもらえば、また試せる。数が0に戻るのは**通ったときだけ**。止めるかどうかは、
直近 `FORGET_SECONDS` のぶんの失敗が `IGNORE_AFTER` の倍数に達したかで決まる
（`is_ignored`）ので、明けたあとに次に止まるのは、失敗がまたそこまで積み上がったとき。

ロック（100）は `LOCK_AFTER` 回目の失敗で掛かる。掛けるのは
`wikilib.userdb.lock_user`——**`pw` を `LOCKED` に書き換える**だけで、
ここは「そろそろか」を数えて知らせるところまでを受け持つ（`lock_left` /
`should_lock`）。

## 連続失敗回数は、この記録から数える

**別に数えを持たない。** `fail_count()` が「そのIDの、最後に通ってから
あとの失敗の数」をここから数える。数えの置き場所を別に作ると、記録と
食い違ったときにどちらが本当か分からなくなる——**記録そのものを唯一の
拠りどころにしておく。**

回数制限を作るときも、10分止めるかどうか・ロックするかどうかは、この数えを
見て決められる（ロックの解除だけは、解除したという印を別に持つ必要がある）。

## IPを残すことについて

接続元のIPを残すが、**IPによる制限は当面かけない**（Wiki設計者の指示）。記録は
残るので、`log/` の扱い（Git管理外・個人情報を含む）は
`wikilib.paths.farm_log_dir` の断りのとおり。
"""
import sqlite3
import time

from wikilib.paths import farm_auth_log_path

TABLE = "authlog"

# 記録するほうを作るときも、表の形はここを使う（2か所で書かない）
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    unixtime  INTEGER NOT NULL,
    uid       TEXT    NOT NULL DEFAULT '',
    remote    TEXT    NOT NULL DEFAULT '',
    authstate INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS {TABLE}_time ON {TABLE}(unixtime);
"""

STATE_OK = 0             # 成功
STATE_LOCK = 100         # ロック
STATE_NO_USER = 101      # そのIDが登録されていない
STATE_IGNORED = 102      # 無視した（パスワードは違っていた）
STATE_IGNORED_OK = 103   # 無視した（**パスワードは合っていた**）

# `recent` が返す件数の既定と上限（記録を読み返すテストや道具のため）
DEFAULT_LIMIT = 20
MAX_LIMIT = 5000


def db_path(wiki_dir):
    return farm_auth_log_path(wiki_dir)


def exists(wiki_dir):
    import os

    return os.path.isfile(db_path(wiki_dir))


def describe(state):
    """`authstate` の値を言葉にする。記録を読む道具を書くときのためと、値の
    意味を1か所にまとめておくために置いてある。"""
    if state == STATE_OK:
        return "成功"
    if state == STATE_LOCK:
        return "ロック"
    if state == STATE_NO_USER:
        return "未登録のID"
    if state == STATE_IGNORED:
        return "無視（パスワードも違う）"
    if state == STATE_IGNORED_OK:
        return "無視（パスワードは合っていた）"
    if 1 <= state <= 99:
        return f"失敗（{state}回目）"
    return f"不明（{state}）"


def record(wiki_dir, uid, remote, state):
    """1件残す。**記録は積むだけで、消したり書き換えたりしない。**

    記録するほうは、無ければDBを作る。`config/users.db` を勝手に作らない
    のとは逆の構えだが、こちらは**作られて困るものが無い**（あちらは既定の
    パスワードを持つ管理者アカウントが生えるのが問題だった）。

    残せなかったとき（置き場所が書けないなど）は**黙って諦める。**
    履歴が残らないことと、ログインできないことは別の話で、記録の都合で
    利用者を閉め出すほうがよほど困る。"""
    import os

    path = db_path(wiki_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        con = sqlite3.connect(path)
        with con:
            con.executescript(SCHEMA)
            con.execute(f"INSERT INTO {TABLE} (unixtime, uid, remote, authstate)"
                        " VALUES (?, ?, ?, ?)",
                        (int(time.time()), uid or "", remote or "", int(state)))
        con.close()
        return True
    except (sqlite3.Error, OSError):
        return False


# 数えるためにさかのぼる件数。全部を読むことはしない
SCAN_LIMIT = 200

# 5回まちがえたら、そこから10分は無視する（Wiki設計者の指示、2026-09-06）。
# 試験のあいだは「3回・2分」に縮めていたが、運用に出す2026-09-21に本来の値へ戻した。
IGNORE_AFTER = 5
IGNORE_SECONDS = 10 * 60
# 何ターン止めたらロックするか（Wiki設計者の指示、2026-09-06。「3セット」）。
# ロックまでの失敗回数はこの掛け算で決まる（試験のあいだは2ターンだった）
LOCK_TURNS = 3
LOCK_AFTER = IGNORE_AFTER * LOCK_TURNS

# 残り何回から画面に出すか（Wiki設計者の指示、2026-09-07）。**止めに入る回（残りが
# IGNORE_AFTER の倍数になる回）では出さない**——あそこで出すと、その次の
# 「止めているあいだは出さない」との差で、止められていることが読めてしまう。
WARN_LEFT = IGNORE_AFTER - 1

# 数え直しがあったときに、最低限そこまでは戻す残り回数（Wiki設計者の指示、2026-09-07）。
# 「残り1回」のまま置いておくと、久しぶりに1回まちがえただけでロックになる
RESCUE_LEFT = 2
# 判断から古い失敗を落とすまでの長さ。**無視時間の倍**（Wiki設計者の指示、2026-09-06）。
# これだけ間が空けば、また最初の IGNORE_AFTER 回から数え直す（記録の通算は伸びたまま）
FORGET_SECONDS = 2 * IGNORE_SECONDS


def _scan(wiki_dir, uid, now=None):
    """そのIDの失敗を記録から拾う。(通算, 最後の時刻, 最近のぶん) を返す。

    **2つの数を分けて返すのが肝。**

      通算      最後に通ってからあとの失敗の数。**記録に残す値**（authstate）
      最近のぶん 直近 FORGET_SECONDS 以内の失敗の数。**止めるかの判断に使う**

    古い失敗は、記録の上では通算に残ったまま、判断からは外れていく
    （Wiki設計者の指示、2026-09-06。「失敗回数をリセットし3回まで許容、ただし
    失敗回数はリセットしません」）。

    **突き合わせは前後の空白を落としてから。** 記録には打たれたものを
    そのまま残す（Wiki設計者の指示）ので、素直に比べると «admin» と «admin␣» が
    別人になり、**空白を1つ足すだけで数えを逃げられる**。

    さかのぼるのは直近 `SCAN_LIMIT` 件まで。数えのために全部を読むことは
    しない。"""
    want = (uid or "").strip()
    if not want:
        return 0, 0, 0
    since = (time.time() if now is None else now) - FORGET_SECONDS
    total, last, fresh = 0, 0, 0
    for row in recent(wiki_dir, SCAN_LIMIT):
        if (row["uid"] or "").strip() != want:
            continue
        state = row["authstate"]
        if state == STATE_OK:
            break          # 通ったところで数えは切れる
        if 1 <= state <= 99:
            total += 1
            last = max(last, row["unixtime"])
            if row["unixtime"] > since:
                fresh += 1
    return total, last, fresh


def fail_count(wiki_dir, uid):
    """そのIDの**連続失敗回数**（最後に通ってからあとの失敗の数）。

    数えの置き場所を別に持たず、**記録そのものから数える**（モジュール冒頭
    参照）。通った記録（0）が1つでもあれば、そこで数えは切れる。

    **数えるのは 1〜99 だけ。** 101（未登録のID）も 102/103（無視）も数に
    入らない——前者は止めようのない相手、後者はこちらが止めたぶんで、
    どちらも「まちがえた回数」ではない。

    **これは記録に残す値**（`authstate`）。止めるかどうかの判断には、
    ここから古いぶんを落とした数を使う（`is_ignored`）。"""
    return _scan(wiki_dir, uid)[0]


def lock_left(wiki_dir, uid, now=None):
    """ロックまであと何回まちがえられるか。0ならもう掛かっている。

    **数えるのは通算のほう**（最後に通ってからの失敗の数）。無視の判断に使う
    「最近のぶん」とは別で、こちらは**間を空けても戻らない**——Wiki設計者の指示の
    「失敗回数はリセットしません」がここに当たる。

    ## ただし、数え直しがあったときは「残り1回」で放置しない

    倍時間あけて数え直し（`FORGET_SECONDS`）が起きたのに残りが1回のままだと、
    **久しぶりに1回まちがえただけでロック**になる。そこだけ `RESCUE_LEFT`
    （＝2回）まで戻す（Wiki設計者の指示、2026-09-07）。

    戻したあとは、数え直しのあとに数えた失敗のぶんだけまた減る。つまり
    **間を空けても、そのたびに2回までしか買えない**——止めそのものは緩まない。

    **救済は残りを増やすだけで、減らさない**（`max`）。運用の値（5回ごとに
    10分、3ターンでロック）では、1ターン目の失敗が判断から落ちる（倍時間を
    すぎる）のは3ターン目の途中で起きる。そのとき通算はロックの一歩手前
    （残り1回）なのに、救済の式 `RESCUE_LEFT - fresh` は `fresh` が大きいので
    0以下になり、**残りが0と返って最後の警告（「次回失敗したらロックします」）が
    出なくなっていた**。試験の値（2ターン）では、判断から落ちる前にロックに
    届くので起きなかった。
    """
    total, _last, fresh = _scan(wiki_dir, uid, now)
    left = LOCK_AFTER - total
    if left < RESCUE_LEFT and fresh < total:
        left = max(left, RESCUE_LEFT - fresh)
    return max(0, left)


def should_lock(wiki_dir, uid, now=None):
    """**次の1回**をまちがえたらロックに達するか。

    呼ぶ側は、失敗を記録する前にこれを見て、真ならロックを掛ける。"""
    return lock_left(wiki_dir, uid, now) <= 1


def is_ignored(wiki_dir, uid, now=None):
    """いまこのIDは無視するか（Wiki設計者の指示、2026-09-06）。

    呼ぶ側は、真が返ったら**合っていても通さず**、まちがえたときと同じ断りを
    返すこと（止めていることを外から分からせないため）。

    ## いつ止まるか

    **5回ごとに、そこから10分。** 数えるのは直近20分（無視時間の倍）のあいだの
    失敗だけ。

      5回まちがえた            → そこから10分は止まる
      10分たった                → **また5回まで試せる**（6回目〜9回目は通す）
      10回目でまた止まる        → 5回ごとに、また10分
      20分だれも失敗しなかった  → 判断の数は0から。また5回まで試せる

    最後の1つが「**過去の失敗が無視時間の倍だけ経過したら、失敗回数を
    リセットして3回まで許容。ただし失敗回数（記録に残す値）はリセット
    しない**」（Wiki設計者の指示）。記録の `authstate` は通算のまま伸びる。
    """
    _total, last, fresh = _scan(wiki_dir, uid, now)
    if not fresh or not last:
        return False
    # **IGNORE_AFTER回ごと**に止める。止まっているあいだの試み（102/103）は数に入らない
    # ので、待って明けたあとは、また IGNORE_AFTER 回まで試せる
    if fresh % IGNORE_AFTER != 0:
        return False
    return (time.time() if now is None else now) - last < IGNORE_SECONDS


def note_attempt(wiki_dir, uid, remote, passed, known=True):
    """パスワードでの照合を1件残す。失敗のときは連続回数も入れる。

    `/.login` と `/.passwd` の**どちらもここを通す**（Wiki設計者の了承、
    2026-09-06）。`/.passwd` も「いまのパスワード」で照合する画面なので、
    片方だけ数えていると、そちらから何回でも試せてしまう。

    `known` が偽——**そのIDが登録されていない**ときは 101 を残す（Wiki設計者の指示、
    2026-09-06）。回数としては数えない。無いアカウントは止めようがないし、
    「打ち間違い・当てずっぽう」と「あるアカウントへの試み」は別々に見たい。

    `uid` は**送られてきたそのまま**を渡すこと（整えない）。"""
    if passed:
        return record(wiki_dir, uid, remote, STATE_OK)
    if not known:
        return record(wiki_dir, uid, remote, STATE_NO_USER)
    # 100 以上は別の意味（ロック・未登録・無視）なので、そこまで届かせない
    return record(wiki_dir, uid, remote, min(99, fail_count(wiki_dir, uid) + 1))


def note_ignored(wiki_dir, uid, remote, passed):
    """止めているあいだの試みを1件残す（Wiki設計者の指示、2026-09-06）。

    **パスワードが合っていたかどうかで分ける**（102 / 103）。応答はどちらも
    同じ——止めているあいだは通さない——ので、**外からこの違いは見えない。
    記録にだけ残す。**

    103（止めているあいだに正解が来た）は、見つけたら重い印。まちがえて
    止められた本人か、当てられたかのどちらかで、**どちらであっても
    パスワードを変えたほうがよい。**"""
    return record(wiki_dir, uid, remote,
                  STATE_IGNORED_OK if passed else STATE_IGNORED)


def recent(wiki_dir, limit=DEFAULT_LIMIT):
    """新しいほうから `limit` 件返す。**無ければ空**（作らない）。

    記録が無いWikiは、中身が空のWikiと同じに見えればよい——`userdb` の
    読み出しと同じ構えにしてある。表がまだ無い場合（DBだけある）も同じ。"""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    if not exists(wiki_dir):
        return []
    try:
        con = sqlite3.connect(db_path(wiki_dir))
        con.row_factory = sqlite3.Row
        with con:
            rows = con.execute(
                f"SELECT unixtime, uid, remote, authstate FROM {TABLE}"
                " ORDER BY unixtime DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
    except (sqlite3.Error, OSError):
        return []
    return [dict(r) for r in rows]


def count(wiki_dir):
    """全部で何件あるか。読めなければ0。"""
    if not exists(wiki_dir):
        return 0
    try:
        con = sqlite3.connect(db_path(wiki_dir))
        with con:
            return con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    except (sqlite3.Error, OSError):
        return 0
