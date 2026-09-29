"""popular — アクセスログ（access.log.db）を集計し、人気ページの順位を
差し込むブロック専用のプラグイン。

    #popular()          直近30日・上位10件（既定）
    #popular(7, 5)       直近7日・上位5件
    #popular(7d, 5)      同上（"d"を付けて日数だと分かりやすく書ける）
    #popular(day=7, num=5)  同上（名前付きでも書ける）
    #popular(10d, 10, Tech/ChangeLog)  Tech/ChangeLog を除いて上位10件

 1. day … 集計する日数 (default: 30)。数字だけでも、末尾に`d`を付けても
       同じ意味（`7`でも`7d`でも「7日」）
 2. num … 表示する順位（最大何位まで出すか） (default: 10)
 3. exclude … 除外するページ名 (default: 除外しない)。書きかたは #recent と同じ
       （"*" や "?" を含めばワイルドカード、含まなければ部分一致。複数は ";" で区切る）

添付ファイルへのアクセスは数えません（ページのアクセスだけを集計します）。
"""

r""" 技術資料
`#recent`を参考に作った、`accesslog`（sandboxのfarm-local実験プラグイン）
と同じ`wikilib.accesslog`のDB（`access_log`テーブル）を集計するプラグイン。
本家PukiWikiに対応するプラグインは無い（新規の独自機能）。

sandboxでfarm-localの試験運用をしたのち、`_system`（このドキュメント
サイト自身）のmainmenuで使いたいという要望を受け、共有プラグイン
（`plugin/`）へ昇格した。`access.log.db`はfarmごとに別ファイルなので、
どのfarmで使っても、そのfarm自身のログだけを集計する（`accesslog.py`が
farm-localのままなのは、そちら固有の運用判断であり、`popular`が共有に
なったこととは別の話）。

## 集計の考えかた

`accessed_at >= 集計開始日時` をSQL側の`WHERE`で絞ってから（件数を減らす
ための素朴な最適化。全件スキャンよりは軽い）、`url`をPython側で
ページパスへ変換し、ページ単位（`accesslog.py`の`_parse_log_url`と同じ
考えかた）で件数を数え直す。1つの論理ページが複数の生`url`（`/=farm/...`
とデフォルトfarmとしての`/...`の両方の形）で記録されている場合があるため
（`accesslog.py`の技術資料参照）、SQLの`GROUP BY url`ではなく、正規化した
あとのページパスをキーにPython側で集計し直す必要がある。

添付ファイルへのアクセス（`_parse_log_url`が`is_attach=True`を返すもの）は
「ページの人気」には数えない（Wiki設計者の指示: 「上位numの**ページ**への
リンクを表示する」）。

## `_parse_log_url`を複製している理由

同じロジックが`accesslog.py`にも既にあるが、プラグイン同士で import
し合う仕組み・慣習はこのシステムに無い（各プラグインファイルは
`_sys/wikilib`配下の共有モジュールだけに依存し、自己完結させる設計。
`plugin/`ディレクトリはプラグイン名からモジュールを動的に読み込む
構造で、プラグイン間の相互importは前提にされていない）。そのため
小さな関数をここに複製した。

## 日時の絞り込み

`wikilib.accesslog.TIME_FORMAT`（"%Y-%m-%d %H:%M:%S"、`accessed_at`列と
同じ書式）はこの書式のまま文字列として辞書式順序で比較できるため、
`day`日前の時刻を同じ書式の文字列にしてSQLの`>=`に渡すだけでよい
（`datetime`への変換をSQL側でしない）。

## `day`の書式（数字だけ、または末尾に`d`）

利用者が「30d」のように単位付きで書きたい場合があるため、`day`は
`type: "int"`を宣言せず（自動の整数変換に「30d」を通せないため）、生の
文字列のまま受け取って`_parse_day()`で自前に読む。`^(\d+)d?$`——数字の
並びの後ろに`d`が有っても無くても良い、という緩い正規表現で、`"30"`
`"30d"`のどちらも30という数値に変換する。それ以外（`"30日"`や空文字列、
負の数など）は`PluginArgumentError`にする。`min`検証（1以上）もここで
行う（`type`を宣言していないと、フレームワークの`min`チェックも自動では
掛からないため）。

## タイトル・順位表示

タイトルは「人気ページTop{num}({day}d)」固定（Wiki設計者の指示）。`<ol>`で
順位を表現し、それぞれの右にアクセス件数を添える。件数が同数のページは
`accessed_at`の新しい順（実装上はPythonの`sorted`が安定ソートである
ことを利用し、集計前の並び——SQLの`ORDER BY accessed_at DESC`——を
保つことで、同数内では「直近によく見られている」ものが上に来るように
した）で決まる。

## 除外（exclude）

`#recent` の `exclude` と同じ書きかた・同じ照合（`wikilib.search.name_matches` を、実体の
subpath に対して）にした（Wiki設計者の指示で足した、2026-09-29。メニューの人気ページから
更新履歴を除くため）。`;` 区切りを読む `_read_excludes` は `recent.py` から写した
（プラグイン同士は import し合わない。上の「`_parse_log_url`を複製している理由」）。
**除いてから上位を切る**（先に切ると、除いたぶんだけ減ってしまう）。

## 消えたページは並べない

アクセスの記録には、あとで消したページも残る。`pagelist.filter` は DB に無い名前も
「まだ無いページ」（`exists=False`）として返すので、そのままだと消えたページへの
リンクが並ぶ。これは外す（Wiki設計者の指示、2026-09-30）。除いてから上位を切るのは
exclude と同じ。

## 表示名: index はフォルダの入口ページを指す

`recent.py`と同じ理由・同じ変換（`pagepath_of_subpath`）で、フォルダの
入口ページ（実体パスの末尾が"/index"）は"index"を見せずフォルダの側を
見せる。トップページ（実体パスが"index"そのもの）は表示名が空になるため
"/"に差し替える。
"""

import os
import re
import sqlite3
import time
from html import escape

from wikilib import pagelist
from wikilib.accesslog import TIME_FORMAT, db_path
from wikilib.paths import ATTACH_URLPATH, pagepath_of_subpath
from wikilib.plugins import PluginArgumentError
from wikilib.search import name_matches, split_filters
from wikilib.wikiconfig import split_farm_and_page, strip_url_prefix, url_prefix

PLUGIN_INFO = {
    "help": "#popular(day,num,exclude)",
    "args": [
        # dayはtype:"int"にしない（"30d"のような単位付きの書きかたを自動
        # 変換に通せないため）。生の文字列のまま受け取り、_parse_day()で
        # 自前に読む（詳しくは技術資料）。
        {"name": "day", "default": "30", "label": "集計する日数"},
        {"name": "num", "type": "int", "default": 10, "min": 1, "label": "表示する順位"},
        {"name": "exclude", "default": None},
    ],
}

DAY_RE = re.compile(r"^(\d+)d?$")


def _parse_day(raw):
    m = DAY_RE.match(str(raw).strip())
    if not m:
        raise PluginArgumentError(f"日数の指定が正しくありません: {raw}")
    value = int(m.group(1))
    if value < 1:
        raise PluginArgumentError(f"日数の指定が正しくありません: {raw}（1以上で指定してください）")
    return value


def _pagepath_of_url(url, config):
    """ログの`url`から、ページのアクセスなら実体パスを、添付ファイルへの
    アクセスや無関係なURLならNoneを返す（`accesslog.py`の`_parse_log_url`
    の縮小版。詳しくは技術資料）。"""
    urlpath = strip_url_prefix(url.lstrip("/"), url_prefix(config))
    _farm, rest, _explicit = split_farm_and_page(urlpath, config)
    rest = rest.strip("/")
    if rest == ATTACH_URLPATH or rest.startswith(ATTACH_URLPATH + "/"):
        return None
    return rest


def _collect(wiki_dir, config, day):
    path = db_path(wiki_dir)
    if not os.path.isfile(path):
        return []
    con = sqlite3.connect(path)
    try:
        con.row_factory = sqlite3.Row
        cutoff = time.strftime(TIME_FORMAT, time.localtime(time.time() - day * 86400))
        rows = con.execute(
            "SELECT accessed_at, url FROM access_log WHERE accessed_at >= ?"
            " ORDER BY accessed_at DESC",
            (cutoff,)).fetchall()
    finally:
        con.close()

    counts = {}
    for row in rows:
        pagepath = _pagepath_of_url(row["url"], config)
        if pagepath is None:
            continue
        # フォルダの入口（"Tech/index"）はフォルダの側の名前に寄せてから数える。
        # 一覧を絞る `pagelist.filter` が返す名前と突き合わせるため（2026-09-17）
        pagepath = pagepath_of_subpath(pagepath)
        counts[pagepath] = counts.get(pagepath, 0) + 1

    # counts.items() はPython 3.7+の辞書の挿入順（＝accessed_at DESCで
    # 最初に出てきた順）を保つため、sortedの安定性により件数が同じ
    # ページどうしは「直近によく見られている」側が先に残る（技術資料参照）
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)


def _read_excludes(value):
    """除外するページ名を読む。(一覧, エラー文言) を返す（recent.py と同じ）。"""
    if value is None or str(value).strip() == "":
        return [], None
    parts = split_filters(str(value))
    # 空の区切り（"a;;b" や末尾の ";"）は書き間違いのことが多い。
    # 黙って読み飛ばすと「効かないフィルタ」に気づけないので、その場で知らせる
    if any(p == "" for p in parts):
        return None, "除外するページ名が空です（; の前後を確かめてください）: {}".format(value)
    return parts, None


def _convert(resolved, body, context):
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")
    excludes, err = _read_excludes(resolved["exclude"])
    if err:
        raise PluginArgumentError(err)

    day = _parse_day(resolved["day"])
    num = resolved["num"]
    ranking = _collect(context.wiki_dir, context.config, day)
    # **閲覧できるページだけに絞ってから上位を切る**（先に切ると、絞ったぶんだけ
    # 減ってしまう）。絞り込みは `pagelist.filter` が受け持つので、ここには
    # 権限の判定が出てこない（[ページの一覧を作る](/Tech/PageList)）
    counts = dict(ranking)
    # 消えたページ（DBに無い。`pagelist.filter` は「まだ無いページ」として返す）は並べない。
    # 行き止まりのリンクになるため（Wiki設計者の指示、2026-09-30）
    items = [i for i in pagelist.filter(context.wiki_dir, [name for name, _ in ranking],
                                        privilege=context.privilege)
             if i.exists and not any(name_matches(i.subpath, f) for f in excludes)][:num]

    title = f"人気ページTop{num}({day}d)"
    html = ['<nav class="popular">', f'<div class="popular-title">{escape(title)}</div>']
    if not items:
        html.append('<p class="popular-empty">（この期間のアクセスの記録はありません）</p>')
    else:
        html.append("<ol>")
        for item in items:
            html.append(
                '<li><a href="{}">{}</a> <span class="popular-count">{}件</span></li>'.format(
                    escape("/" + item.pagepath, quote=True),
                    escape(item.pagepath or "/"), counts.get(item.pagepath, 0),
                )
            )
        html.append("</ol>")
    html.append("</nav>")
    return "".join(html)
