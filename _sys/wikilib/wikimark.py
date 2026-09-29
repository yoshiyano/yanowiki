"""そのWikiを取り違えていないかを確かめる目印。

**「いまそのWikiを実際に見ている人にしか書けない値」**を2つ作る。どちらも
テーマのフッターに出ているもので、Wikiごとに違い、しかも名前からは分からない。

    Last-modified: 2026-09-18 14:33          トップページの平文の更新日時
    DiskUsage: Page/Attached 88KB/4.7MB      wiki/ と attach/ の合計

毎回変わる `Convert-time` は使わない（Wiki設計者の指示、2026-09-08）。

## どこから呼ばれるか

    ./wiki.py resetpw     フッターを丸ごと貼ってもらう（`confirm_by_footer`）
    /.delwiki の3段目     2つの値を別々に書いてもらう（`wikilib.delwiki`）

**同じことを確かめているので、値の作りかたは1か所にまとめてある**（Wiki設計者の
指示、2026-09-13。「同じようなことをさせているのに別のコードを使っている事例
などがあれば共通化する」）。もとは `wiki.py` の `wiki_fingerprint` が持って
いたものを、画面側からも使えるようにここへ移した（2026-09-18）。

**訊きかたのほうは呼ぶ側に任せる。** 道具の側は端末に貼り付けるのが自然で、
画面の側は入力欄が2つ並ぶほうが素直——同じ形に揃える理由が無い。

## 防いでいるのは「取り違え」であって「なりすまし」ではない

（Wiki設計者の指示、2026-09-08）。ここへ来られるのは、サーバーで実行できる人か、
既定Wikiの管理者・助手として関門を通った人だけで、**その人が誰かは別の仕組みが
確かめている。** ここで止めたいのは、消す（あるいはパスワードを入れ直す）つもりの
無いWikiを、名前の写し間違いで指してしまうほう。だから目印は画面に出してよい
種類の値でよく、**一度そのWikiを開けば書ける**ことに意味がある。

## 書きかたの揺れは吸収する

確かめたいのは値を知っているかどうかで、書式を揃える練習ではない。前置きごと
貼り付けても、日付の区切りが違っても通す（`normalize_usage`・`normalize_day`）。
"""
import datetime
import os
import re

from wikilib.diskusage import DiskUsage
from wikilib.paths import resolve_page_ref

LAST_MODIFIED_FORMAT = "%Y-%m-%d %H:%M"  # テーマのフッター（themes.render_page）と同じ


def source_updated(wiki_dir):
    """トップページの**平文ファイル**の更新日時（`2026-09-18 14:33`）。無ければ None。

    DBの日時ではなく実ファイルの mtime を見る。フッターの `Last-modified:` が
    そちらだからで、理由は `wikilib.themes.render_page` の `source_mtime` の
    ところに書いてある（DBは取り込んだ時点の写しなので、直接編集した分は
    `updatepage` するまで動かない）。"""
    ref = resolve_page_ref(wiki_dir, "")
    if ref is None or not ref.exists:
        return None
    try:
        mtime = os.path.getmtime(ref.path)
    except OSError:
        return None
    return datetime.datetime.fromtimestamp(mtime).strftime(LAST_MODIFIED_FORMAT)


def usage_text(wiki_dir):
    """そのWikiのディスク使用量（`1.2MB/349KB`）。

    数えかたはフッターに出ているものと同じ（`wikilib.diskusage`）。**同じ
    関数を通す**ので、10分の使い回しも含めてフッターと食い違わない。"""
    return str(DiskUsage(wiki_dir))


def marks(wiki_dir):
    """フッターに出ている行そのもの（貼り付けと突き合わせるため）。

    読めなかったものは入らないので、**2つ揃っているかは呼ぶ側が見ること**。"""
    found = []
    updated = source_updated(wiki_dir)
    if updated is not None:
        found.append("Last-modified: " + updated)
    try:
        found.append(DiskUsage(wiki_dir).text)
    except OSError:
        pass
    return found


def missing_marks(wiki_dir, pasted):
    """貼り付けられた文字列に見つからなかった目印。全部あれば空リスト。

    突き合わせは**空白を1つに詰めてからの部分一致**。端末やブラウザを経ると
    空白の数は当てにならないため。"""
    return [m for m in marks(wiki_dir) if " ".join(m.split()) not in pasted]


# ---- 1つずつ書いてもらう場合 -------------------------------------------------

def normalize_usage(text):
    """打たれたディスク使用量を突き合わせ用に均す。

    フッターの行をまるごと貼っても通るようにしてある
    （`DiskUsage: Page/Attached 1.2MB/349KB` → `1.2MB/349KB`）。"""
    got = (text or "").strip()
    if ":" in got:
        got = got.split(":", 1)[1]
    got = re.sub(r"(?i)page\s*/\s*attached", "", got)
    return re.sub(r"\s+", "", got).upper()


def normalize_day(text):
    """打たれた日付を `YYYY-MM-DD` に均す。読めなければ空文字。

    通すのは `2026-09-18` `2026/09/18` `20260918` と、うしろに時刻が
    付いた形（`2026-09-18 14:33`。フッターの行をそのまま貼った場合）。"""
    got = (text or "").strip()
    if not got:
        return ""
    if ":" in got:
        # 「Last-modified: 2026-09-18 14:33」の前置きを落とす
        head, rest = got.split(":", 1)
        if re.search(r"(?i)modified|更新", head):
            got = rest.strip()
    parts = got.split()
    got = parts[0] if parts else ""
    matched = (re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", got)
               or re.match(r"^(\d{4})(\d{2})(\d{2})$", got))
    if matched is None:
        return ""
    return "{:04d}-{:02d}-{:02d}".format(*(int(v) for v in matched.groups()))


def updated_days(wiki_dir):
    """トップページの最終更新日として通す値（`YYYY-MM-DD` の集合）。

    **平文ファイルの更新時刻とDBの更新日時の、どちらでも通す。** フッターの
    `Last-modified:` は平文側だが、履歴やページの一覧はDB側の日時を出す。
    どちらを見て書いてもよいはずのものを片方だけに絞ると、正しく見ているのに
    弾かれる。

    **DBが既にあるときだけそちらを見る。** `pagedb.page_updated_at` は開く
    ついでにDBを作るので、素直に呼ぶと**見ただけのWikiに空のDBを生やす**。"""
    from wikilib import pagedb  # 循環を避けるため呼び出し時に読み込む
    from wikilib.paths import INDEX_NAME

    days = set()
    updated = source_updated(wiki_dir)
    if updated is not None:
        days.add(updated[:10])
    if pagedb.is_usable(wiki_dir):
        stamp = pagedb.page_updated_at(wiki_dir, INDEX_NAME)
        if stamp:
            days.add(stamp[:10])  # pagedb.TIME_FORMAT は "%Y-%m-%d %H:%M:%S"
    return days


def typed_matches(wiki_dir, typed_usage, typed_day):
    """書いてもらった2つの値が、いまのそのWikiと合っているか。

    **どちらが違ったかは返さない。** 片方ずつ当てられると、当て推量で通り抜ける
    手間が半分になる（呼ぶ側も「合いません」としか出さないこと）。"""
    if normalize_usage(typed_usage) != normalize_usage(usage_text(wiki_dir)):
        return False
    return normalize_day(typed_day) in updated_days(wiki_dir)
