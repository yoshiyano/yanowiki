"""recent — 最近更新されたページの一覧を差し込むブロックプラグイン。

    #recent()                    最大10件（既定）
    #recent(5)                   最大5件
    #recent(5, Tech/ChangeLog)   Tech/ChangeLog を除いて5件
    #recent(num=5, exclude=...)  同上（名前付きでも書ける）

主にサイドバーのメニューページ（mainmenu など）に置くことを想定しています。
一覧が縦に長くならないようページ名だけを並べ、更新日時はリンクのツールチップ
（title属性）で表示します。

 1. num     … 表示する最大件数 (default: 10)
 2. exclude … 除外するページ名 (default: 除外しない)
       "*" や "?" を含めばワイルドカード、含まなければ部分一致。
       複数指定するときは ";" で区切る（";" そのものを含めたい場合は "\\;"）
"""

""" 技術資料
元になるのはページのデータベース (pageinfo/wikiall.db) の更新日時です。
全ページが対象で件数の上限は無く、消えたページは並びから外れます。

除外の照合は検索の絞り込みと同じ規則 (wikilib.search.name_matches) です。
同じ書きかたを2か所で覚えなくて済むよう、実装ごと借りています。**照合は
item["name"]（実体のsubpath。フォルダの入口ページなら末尾に"/index"が
付いたまま）に対して行う**（表示用に変換する前の生の値。exclude="index"
でフォルダの入口ページをまとめて除外できる、という副次的な使いかたを
崩さないため）。

";" 区切りの解析は split_filters が行う。"\\;" は ";" そのものとして扱う
エスケープで、"\\\\" 自体は特別扱いしない（ページ名に "\\" は使えないため）。

## 一覧は wikilib.pagelist から取る（2026-09-17）

以前は `context.recent_pages()`（実体のsubpathとURLを組み立てた辞書）を受け取り、
表示名をこのプラグイン側で `pagepath_of_subpath` に通していた。いまは
`pagelist.walk()` が返す `PageItem` に `pagepath`（URL上の名前）が入っているので、
その変換は要らない。**閲覧の権限もそこで見ている**ので、読めないページは並ばない
（[ページの一覧を作る](/Tech/PageList)）。

`PageItem` は「フォルダの入口ページ（実体が `…/index`）は、フォルダの側の名前で
返す」形に揃えてあるので、`ls` など他の一覧と表示が食い違わない。

**Wikiの一番上（トップページ）は `pagepath` が空文字列。** 表示名が空だとリンクの
文字が無い状態になってしまうため、空文字列のときだけ"/"に差し替える。

## 並べ替えと件数

`pagelist.walk()` は名前順で返すので、**更新の新しい順に並べ直す**のはこちらの仕事。
同じ日時のときは名前順になるよう、名前で並べてから日時で並べ直している
（Pythonの並べ替えは安定なので、2段に分けて書ける）。

除外（exclude）の照合は、**実体のsubpath**（`…/index` が付いたまま）に対して行う。
`exclude="index"` でフォルダの入口ページをまとめて除ける、という使いかたを崩さない
ため（上の「除外の指定」参照）。
"""

from html import escape

from wikilib import pagelist
from wikilib.plugins import PluginArgumentError
from wikilib.search import name_matches, split_filters

PLUGIN_INFO = {
    "help": "#recent(num,exclude)",
    "args": [
        {"name": "num", "type": "int", "default": 10, "min": 1, "label": "表示件数"},
        {"name": "exclude", "default": None},
    ],
}


def _read_excludes(value):
    """除外するページ名を読む。(一覧, エラー文言) を返す。

    「;」区切りの解析はPLUGIN_INFO["args"]の型（"bool"/"int"）では表せない
    このプラグイン固有の意味づけなので、束ねた値（resolved["exclude"]）を
    さらにここで読む。"""
    if value is None or str(value).strip() == "":
        return [], None
    parts = split_filters(str(value))
    # 空の区切り（"a;;b" や末尾の ";"）は書き間違いのことが多い。
    # 黙って読み飛ばすと「効かないフィルタ」に気づけないので、その場で知らせる
    if any(p == "" for p in parts):
        return None, "除外するページ名が空です（; の前後を確かめてください）: {}".format(value)
    return parts, None


def _convert(resolved, body, context):
    excludes, err = _read_excludes(resolved["exclude"])
    if err:
        raise PluginArgumentError(err)
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")

    # 除いてから件数を切る。先に切ると、除いたぶんだけ減ってしまう
    entries = [i for i in pagelist.walk(context.wiki_dir, privilege=context.privilege)
               if not any(name_matches(i.subpath, f) for f in excludes)]
    entries.sort(key=lambda i: i.pagepath)            # 同じ日時のときの並び
    entries.sort(key=lambda i: i.updated, reverse=True)
    entries = entries[:resolved["num"]]
    if not entries:
        return '<div class="recent recent-empty">（まだ更新の記録はありません）</div>'

    html = ['<nav class="recent">',
            '<div class="recent-title">最新の更新({}件)</div>'.format(len(entries)),
            "<ul>"]
    for item in entries:
        html.append(
            '<li><a href="{}" title="{}">{}</a></li>'.format(
                escape("/" + item.pagepath, quote=True),
                escape(item.updated, quote=True),
                escape(item.pagepath or "/"),
            )
        )
    html.append("</ul></nav>")
    return "".join(html)
