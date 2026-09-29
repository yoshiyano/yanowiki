"""updateDB — 平文ファイルの直接編集をDBへ取り込む、action専用のプラグイン。

    /.plugin/updateDB
    /.plugin/updateDB?page=Tech/dev_plugin
    /.plugin/updateDB?force=1

GET（POSTでも動きます）でアクセスすると、そのWiki（アクセスしたURLの
farm。例: `/=sandbox/.plugin/updateDB`なら`sandbox`）の平文ファイルと
DBの食い違いを取り込みます。`./wiki.py updatepage`と同じ土台
（`wikilib.pagesync`）を使った、HTTP経由の取り込み窓口です。

 1. page  … 対象のページ名 (default: そのWiki全体)
       省略するとそのWiki全体を見ます。指定すると、そのページ1つだけを
       見ます（他のページの検出には影響しません）
 2. force … 単語（`1`等の真偽値）を書くと、平文とDBの食い違いを見ずに、
       実在するページをすべて読み直して取り込みます (default: 食い違って
       いるものだけ)。**ログインが要ります。** 管理者と助手以外は、
       15分に1回・1日20回までです

このプラグイン自身は表示（`#updateDB()`/`&updateDB();`）を持ちません。
結果はプレーンテキストで返します（`./wiki.py updatepage`が画面に出す
のと同じ1行）。
"""

""" 技術資料
本家PukiWikiに対応するプラグインは無い、このシステム独自の実装
（Wiki設計者の依頼）。

## 既にある仕組みとの関係

平文ファイルの直接編集（エディタで直に書いた・`git pull`で入れ替わった・
別のスクリプトが書き出した等）をDBへ取り込む仕組み自体は、
`wikilib.pagesync`に既にある。

    サービス起動時      全Wikiを1回まとめて取り込み
    1時間おき           バックグラウンドスレッドが自動で全Wikiを見に行く
    ページを開いたとき   平文ファイルはあるがDBに無いページを、その場で
                        取り込む（`adopt_page`）
    ./wiki.py updatepage  手で動かす（CLI、SSH/シェルアクセスが要る）

このプラグインは、**HTTP（GET）で明示的に叩ける窓口**を追加するもの
（Wiki設計者の依頼:「GetRequestでページ情報からDBに更新するスクリプト」）。
1時間おきの自動取り込みを待たずに、外部のスクリプト・webhook・cronから
即座に反映させたい場合に使う。土台（`sync_wiki`）は`updatepage`・自動
取り込みと完全に同じで、このプラグイン独自の取り込みロジックは持たない
（経路を1つに保つ。`pagesync.py`のdocstring「取り込む処理を分けて持つと
どちらかだけ直す事故が起きる」と同じ考えかた）。

## `_convert`/`_inline`を持たない理由（action専用）

このプラグインの役目はHTTP経由の取り込みトリガーであり、ページ本文に
`#updateDB()`のように書いて表示する対象が無い（Wiki設計者の指示どおり
「action専用のプラグイン」として作った）。`ls.py`/`comment.py`/`vote.py`
は`_action`と`_convert`を両方持つ（AJAX読み込み・フォーム送信の受け口を
兼ねる）が、こちらは`_action`だけを持つ、このシステムで最初の完全
action専用プラグインになる。

## `page`引数（`resolve_page_ref`でのsubpath変換）

`sync_wiki(wiki_dir, config, subpath=..., force=...)`が受け取る`subpath`
（`wiki_dir`相対の実体パス）は、URL上のページパス（`page`引数）とは
folder/indexの解決でずれることがある（`PageRef`のdocstring「"/Tech" →
"Tech/index" のようにずれる」参照）。`resolve_page_ref(wiki_dir, page)`
に一度通してから`.subpath`を使うことで、このずれを自前で計算し直さず
正しく解決している（`ls.py`の`_action`が`published_ref`で同じことを
しているのと同じ考えかた。ただしこちらは「公開されているか」ではなく
「平文ファイルの実体パス」だけが要るので`resolve_page_ref`を使う）。

`page`が空・存在しないページを指す場合はエラーにせず、そのWiki全体を
対象にする（`sync_wiki`の`subpath=None`の意味そのまま。存在しない
ページ名を指定したら黙ってWiki全体を取り込む、という挙動は少し緩いが、
「無いページ名だからエラー」より「とりあえず取り込みは実行される」ほうが
安全側だと判断した）。

## 誰が使えるか

取り込みそのもの（`force` なし）は、ログインも権限も確かめず**誰でも実行できる**。
平文ファイルの内容をDBへ映すだけで、実行した人が内容を差し込むことはできず、
1時間おきの自動取り込みを前倒しするだけだから。

**`force=1` だけは絞る**（Wiki設計者の指示）。全ページを読み直して描き直すので重く、
繰り返されると負荷をかける手段になるため。

| 実行する人 | `force=1` |
|---|---|
| ログインしていない | 使えない（403） |
| ログインしている | 同じ人が15分に1回、1日（0時から）20回まで（超えたら429） |
| そのWikiの管理者と助手 | 制限なし |

実行の記録は一時フォルダの `wikisystem-updatedb-force-<設置場所の要約>.json` に置く
（重要な記録ではないのでシステムのフォルダには置かない。プラグインはリクエストの
たびに読み込み直されるので、モジュールの変数には残せない）。中身は Wiki名とIDごとの
今日の実行時刻だけで、書くたびに前日以前の分を捨てる。同時に届いても数えがずれない
よう `flock` で順番に書く。一時フォルダが消えれば数え直しになるが、負荷を抑えるための
制限なので構わない。

`/.restart`と違い確認画面を挟んでいない。DB取り込みは**冪等**（同じ
状態を何度取り込んでも結果は変わらない）で、GETの先読み・誤クリックで
サービスが止まる`/.restart`のような実害が無いため、単純な即時実行に
した。
"""

import datetime
import fcntl
import hashlib
import json
import os
import tempfile
import time

from bottle import request

from wikilib.auth import current_user, is_staff
from wikilib.pagesync import format_result, sync_wiki
from wikilib.paths import BASE_DIR, resolve_page_ref
from wikilib.web import plain

PLUGIN_INFO = {
    "help": "/.plugin/updateDB?page=ページ名&force=1",
}

# force=1 の制限（管理者と助手には掛けない）
FORCE_INTERVAL = 15 * 60   # 同じ人が続けて使うときの間隔（秒）
FORCE_DAILY_MAX = 20       # 同じ人が1日（0時から）に使える回数

# 実行の記録。プラグインはリクエストのたびに読み込み直されるので、モジュールの
# 変数には残せない。重要な記録ではないので、システムのフォルダではなく一時
# フォルダに置く。名前に設置場所の要約を入れ、同じマシンの別の設置と混ざらないようにする
FORCE_LOG = os.path.join(
    tempfile.gettempdir(),
    "wikisystem-updatedb-force-{}.json".format(
        hashlib.sha1(os.path.abspath(BASE_DIR).encode("utf-8")).hexdigest()[:10]))


def _action(context):
    if not context.wiki_dir:
        return plain("Wikiが特定できません。", status=400)

    page = (request.query.getunicode("page", "") or "").strip()
    force = request.query.get("force", "") not in ("", "0", "false", "no")

    if force:
        refused = _check_force(context)
        if refused is not None:
            return refused

    subpath = None
    if page:
        ref = resolve_page_ref(context.wiki_dir, page)
        if ref is not None:
            subpath = ref.subpath

    result = sync_wiki(context.wiki_dir, context.config, subpath=subpath, force=force)
    return plain(format_result({context.farm or "": result}))


def _check_force(context):
    """force=1 を使ってよいか。よければ実行を記録してNone、だめなら断りの応答。"""
    user = current_user(context.wiki_dir, context.farm)
    if user is None:
        return plain("force=1 はログインしてから使えます。", status=403)
    if is_staff(context.wiki_dir, user):
        return None
    return _count_force("{}\t{}".format(context.farm or "", user["uid"]), time.time())


def _count_force(key, now):
    """key（Wiki名とID）の今日の実行を数え、使えるなら記録してNoneを返す。"""
    today = datetime.datetime.fromtimestamp(now).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    fd = os.open(FORCE_LOG, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            log = json.loads(f.read() or "{}")
        except ValueError:
            log = {}
        # 前日以前の分は捨てる（数えるのは今日の分だけ）
        log = {k: [t for t in v if t >= today] for k, v in log.items()}
        log = {k: v for k, v in log.items() if v}
        runs = log.get(key, [])

        if len(runs) >= FORCE_DAILY_MAX:
            return plain("force=1 は1日{}回までです。明日（0時以降）に使えます。".format(
                FORCE_DAILY_MAX), status=429)
        if runs and now - runs[-1] < FORCE_INTERVAL:
            wait = int(FORCE_INTERVAL - (now - runs[-1]) + 59) // 60
            return plain("force=1 は{}分に1回までです。あと{}分ほどで使えます。".format(
                FORCE_INTERVAL // 60, wait), status=429)

        log[key] = runs + [now]
        f.seek(0)
        f.truncate()
        json.dump(log, f)
    return None
