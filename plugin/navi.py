"""navi — 目次ページと子ページを行き来する送り（ナビゲーション）を出すプラグイン。

    #navi()                    目次ページに置く：下の子ページを一覧にする
    #navi(Tech)                子ページに置く：前後と目次への送りを出す
    #navi(Tech, reverse)       並びを逆順にする
    #navi(Tech, , "/_")        一覧・前後送りから外すページを正規表現で選ぶ

 1. home     … 目次にするページ (default: いま開いているページ自身)
       `Tech` も `/Tech` もwikiの先頭から、`./Tech` は今のページの下、
       `../Tech` は1つ上から（本文のリンク `[[Tech]]` とまったく同じ決まりです）
 2. reverse  … 単語を書くと並びを逆順にする (default: 名前順のまま)
 3. exclude  … 一覧・前後送りから外すページを選ぶ正規表現 (default: 何も外さない)
       ページパス（`Tech/_memo` のような形）に**部分一致**で当てます

**置いた場所によって出るものが変わります。**

- **目次ページ**（引数を省くか、`home`に自分自身を書いた場合）…
  下にある子ページを一覧にします。
- **子ページの1回目** … 「前へ／目次／次へ」の送りと区切り線を出します。
  ページの先頭に置くのを想定しています。
- **子ページの2回目** … 区切り線と、送り先のページ名・「上へ」を添えた
  詳しい送りを出します。ページの末尾に置くのを想定しています。

つまり**子ページには先頭と末尾に2つ書く**のが本来の使いかたです。3つ以上
書いた場合、3つめ以降は2つめと同じ（末尾用の詳しい送り）になります。

並び順は名前順で、数字は数として比べます（`page2` が `page10` より前に
来る）。大文字小文字は区別しません。送り先の表示は**ページの見出し
（タイトル）**で、見出しが無いページはページパスを出します。

`exclude`で自分自身を外した場合でも、そのページに書いた`#navi`は今までどおり
前後送りを出します（外れるのは一覧と、他のページから見た送り先としてです）。
"""

""" 技術資料
本家PukiWikiの`navi.inc.php`（`~/pukiwiki/.wkcommon/plugin/navi.inc.php`）の
移植。本家の3面構成——**目次ページでは子ページ一覧、子ページの1回目は
DocBook風のヘッダー、2回目はフッター**——をそのまま引き継いでいる。

## 何回目の呼び出しかを覚える

本家は関数内の`static $navi = array()`（`$home`をキーにした配列）で「1回目か
2回目か」を持っていた。PHPは1リクエスト内で静的変数が生き残るためこれで
済むが、このシステムはリクエストごとにプラグインを読み直すのでモジュール
直下の変数では持ち越せない。`context._navi_state`（`home`をキーにした辞書）を
`context`に直接乗せる形にした（`include.py`が確立し、`comment.py`/`vote.py`が
踏襲しているパターン。`../README.md`「ページ本文を書き換えて保存し直す
プラグイン」参照）。

**キーは本家と同じく`home`だけにしている。** 同じページに`#navi(A)`と
`#navi(B)`を書けば別々に数えられる（本家と同じ）。`#include`で埋め込まれた
ページは別の`PluginContext`（`sub`）で描かれ、`include.py`は`_include_state`
しか引き継がないので、埋め込み先の`#navi`が埋め込み元の回数に混ざることは
無い。

## 一覧の取りかたと「番兵」

本家は`get_existpages()`を`preg_grep` で `^home($|/)` に当ててで絞っていた。ここは
`pagelist.walk(wiki_dir, under=home)`（読み手に見えるページだけを返す層。
`Tech/index`はページ`Tech`として1件にまとまる）に置き換えている。
**閲覧の権限はこの層が見てくれる**ので、読めないページは一覧にも前後送りにも
出てこない。

本家が`$pages[] = $current;`で**自分自身を番兵として足していた**のも引き継いだ。
まだ公開されていない（DBに無い）ページをプレビューしている場合でも、自分が
並びの中に位置を持ち、前後送りが働く。番兵は`exclude`の適用**後**に足すので、
`exclude`で外したページ自身に書いた`#navi`も前後送りを出す（本家と同じ順序）。

並び順は本家の`natcasesort()`に合わせ、数字のかたまりをintとして比べる
大文字小文字を区別しない鍵（`_natcase_key`）で並べる。`ls`の既定（素の
文字列比較で、数値扱いは`natural`オプション）とは違うが、こちらは本家に
合わせた。

## 「子ページか」の判定は本家より厳しくした

本家は`preg_match('/^' . preg_quote($home) . '/', $current)`と**`/`の境界を
見ない前方一致**で判定しており、`Tech2`に`#navi(Tech)`と書いてもエラーに
ならなかった。ただしその場合`$pages`の側は`^home($|/)`で厳密に絞られる
ため、自分だけが番兵として変な位置に入った並びができるだけで、実用的な
結果にはならない（本家の取りこぼしと判断した）。ここでは`home + "/"`で
始まるかを見て、外れていればエラーにしている。

Wikiのトップページ（ページパスが空文字列）を`home`にした場合は、
`home + "/"`が`"/"`になって判定が成り立たないため、`_is_under`で個別に
扱っている（トップページ以外はすべて子、という判定）。本家にトップページを
`home`にする概念は無い（`FrontPage`という普通のページ名だった）。

## 「上へ」は本家より控えめ

本家は`make_pagelink()`が**まだ無いページにも「?」付きのリンク**を出すため、
`up`（`current`の1つ上）にページが無くてもリンクが出ていた。このシステムでは
ページを持たない「通り道だけのフォルダ」が普通に在りうる（`Tech/Sub`に
ページが無くても`Tech/Sub/Page`は在れる）ので、**`up`にページが無い・読めない
ときはリンクを出さない**（そのマスが空になる）。本家どおり、`current`に`/`が
無い深さ1のページでは`up`をそもそも出さない（本家の`$pos > 0`）。

## 本家から持ち込まなかったもの

- **`PLUGIN_NAVI_LINK_TAGS`（既定`FALSE`）** … `<head>`に
  `<link rel="start|next|prev|up">`を差し込む機能。このシステムには
  プラグインから`<head>`へタグを足す窓口が無く、実装にはwikiSystem側の
  変更が要る。本家も既定で無効だったため、既定の挙動としては差が無い
  （Wiki設計者と相談のうえ今回は移植しないと決めた。要るようになったら
  汎用の受け口をwikiSystem側へ依頼する）。
- **`PLUGIN_NAVI_EXCLUSIVE_REGEX`（既定は空＝無効）** … PHPの`define`で、
  ソースを書き換えないと使えなかった。同じ働きを`exclude`引数として
  ページ側から書ける形にした（Wiki設計者の判断。私の提案どおりで、
  本家がサイト全体の設定にしていたものを呼び出しごとに選べるようにした
  ぶんだけ後方互換の範囲内で広がっている）。

## 表示はページ名ではなく見出し（タイトル）優先

本家の`make_pagelink($page)`は**ページ名**を出していた。ここは
「タイトル優先・無ければページパス」にしている（Wiki設計者の判断）。
`ls`の`format=TITLE`・`recent`と同じ流儀で、読み手には分かりやすい。

**私の意見**: 読みやすさでは賛成だが、横3列の送りに長いタイトルが入ると
列が潰れる懸念があるので、`navi.css`側で手当てした（下記）。表示に使う
文字列の選択は書き手から見える「機能」ではないので、後方互換の問題にも
ならないと判断した。

## CSSは本家のクラス名を保ち、floatをflexに置き換えた

本家スキン（`pukiwiki.css`）は`li.navi_left{float:left}`/`li.navi_right
{float:right}`/`li.navi_none{float:none}`で3列を作っていた。クラス名は
そのまま残し（本家の知識でテーマを書ける）、`plugin/navi.css`では
`display:flex`で組み直している。これに伴い**DOMの順番を「前へ・目次・次へ」の
論理順に変えた**（本家はfloatの都合で left, right, none の順だった）。CSSが
効かない場面や読み上げでも順番どおりに読める。

長いタイトルへの手当ては、`flex:1 1 0`＋`min-width:0`＋`overflow-wrap:anywhere`
で**列の中で折り返させる**形にした。`text-overflow:ellipsis`で省略する案も
あったが、フッターは`<br>`で2行になる（`text-overflow`は単一行が前提）ため、
折り返しのほうが素直で、タイトルも削れずに済む。
"""
import re
from html import escape

from wikilib import pagelist
from wikilib.paths import (
    full_pagepath, is_valid_pagepath, pagepath_of_subpath, resolve_page_ref,
)
from wikilib.plugins import FREE_TEXT, PluginArgumentError

PLUGIN_INFO = {
    "help": "#navi(home,reverse,exclude)",
    "args": [
        {"name": "home", "num_order": 1, "candidate": [FREE_TEXT], "default": None, "link": True},
        {"name": "reverse", "num_order": 2, "flag": True, "default": False, "label": "逆順"},
        {"name": "exclude", "num_order": 3, "candidate": [FREE_TEXT], "default": None},
    ],
}

# 送りのラベル。本家は $_navi_prev などの言語変数だったが、ja.lng.php でも
# 'Prev'/'Next'/'Up'/'Home' と英語のままだった。このシステムの表示は日本語で
# 揃えているので、ここは日本語にしている（$_navi_home は「目次ページ」の
# 意味なので「ホーム」ではなく「目次」とした）。
LABEL_PREV = "前へ"
LABEL_NEXT = "次へ"
LABEL_UP = "上へ"
LABEL_HOME = "目次"

# 自然順ソート用（ls.py の _NATURAL_SPLIT と同じ考えかた）。\d は Unicode の
# decimal digit 全般にマッチするので、全角の番号も数として比べられる。
_NATURAL_SPLIT = re.compile(r"(\d+)")


def _natcase_key(pagepath):
    """本家の natcasesort() に相当する並べ替えの鍵。

    数字のかたまりだけ int にし、文字列側は小文字にして比べる。re.split の
    結果は「区切られなかった部分」と「数字のかたまり」が必ず交互に並ぶので、
    同じ位置どうしで str と int を比べて落ちることは無い。"""
    return [int(p) if p.isdecimal() else p.lower() for p in _NATURAL_SPLIT.split(pagepath)]


def _state(context):
    """このリクエストの間、home ごとに「もう1回呼ばれたか」を覚えておく入れもの。"""
    state = getattr(context, "_navi_state", None)
    if state is None:
        state = {}
        context._navi_state = state
    return state


def _current_pagepath(context):
    """いま描いているページのページパス。`Tech/` や `Tech/index` も `Tech` に揃える。"""
    ref = resolve_page_ref(context.wiki_dir, context.page or "")
    if ref is None:
        return (context.page or "").strip("/")
    return pagepath_of_subpath(ref.subpath)


def _is_under(home, pagepath):
    """pagepath が home の下にあるか。

    home がWikiのトップ（ページパスが空文字列）のときは `home + "/"` が
    `"/"` になってしまうので、トップ以外はすべて子とみなす。"""
    if home == "":
        return pagepath != ""
    return pagepath.startswith(home + "/")


def _path_text(pagepath):
    """人に見せるページパスの書きかた。トップページ（空文字列）は "/"。"""
    return "/" + pagepath if pagepath else "/"


def _exclude_pattern(raw):
    """exclude に書かれた正規表現をコンパイルする。書かれていなければ None。"""
    if raw is None or not raw.strip():
        return None
    try:
        return re.compile(raw)
    except re.error as err:
        raise PluginArgumentError(f"exclude の正規表現が正しくありません: {raw}（{err}）")


def _items_of(context, pagepaths):
    """ページパスの並びを {ページパス: PageItem} にする。**在って読めるものだけ**。

    `pagelist.filter` は権限を見て絞り、DBに無い名前も exists=False で返すので、
    ここで exists まで見てふるいにかける。"""
    wanted = [p for p in dict.fromkeys(pagepaths) if p is not None]
    items = pagelist.filter(context.wiki_dir, wanted, by="pagepath",
                            privilege=context.privilege)
    return {item.pagepath: item for item in items if item.exists}


def _label(item, pagepath):
    """リンクに出す文字。見出し（タイトル）優先、無ければページパス。"""
    title = (item.title or "").strip() if item is not None else ""
    return title or _path_text(pagepath).lstrip("/") or "/"


def _link(pagepath, text):
    """ページへのリンク1つ。`/`始まりにすると base_url は本体が補ってくれる。"""
    return '<a href="{}">{}</a>'.format(
        escape("/" + pagepath, quote=True), escape(text))


def _survey(context, home, current, up, outside, reverse, raw_exclude):
    """一覧と前後送りの材料をまとめて作る（home ごとに1回だけ呼ばれる）。

    `outside` は `home`・`up` を引いておいた分（`walk` の範囲に入らないことが
    あるため、呼ぶ側が1回だけ問い合わせて渡す）。"""
    pattern = _exclude_pattern(raw_exclude)
    items = pagelist.walk(context.wiki_dir, under=home, privilege=context.privilege)
    known = {item.pagepath: item for item in items}

    names = [p for p in known if p != home]
    if pattern is not None:
        names = [p for p in names if not pattern.search(p)]
    names.append(home)
    if current not in names:
        names.append(current)          # 本家の番兵。自分は exclude より後に足す
    names = sorted(set(names), key=_natcase_key)
    if reverse:
        names.reverse()

    # 本家と同じ走査。prev の初期値が home なので、並びの先頭のページの
    # 「前へ」は目次ページを指す。
    prev, nxt = home, ""
    for index, name in enumerate(names):
        if name == current:
            if index + 1 < len(names):
                nxt = names[index + 1]
            break
        prev = name

    for path, item in outside.items():
        known.setdefault(path, item)

    def link_of(pagepath, text=None):
        item = known.get(pagepath)
        if pagepath != current and item is None:
            return ""                  # 在らない・読めないページへのリンクは出さない
        return _link(pagepath, text if text is not None else _label(item, pagepath))

    return {
        "home": home,
        "children": [(p, _label(known.get(p), p)) for p in names
                     if p != home and p in known],
        "prev_nav": link_of(prev, LABEL_PREV) if prev else "",
        "prev_page": link_of(prev) if prev else "",
        "next_nav": link_of(nxt, LABEL_NEXT) if nxt else "",
        "next_page": link_of(nxt) if nxt else "",
        "home_nav": link_of(home, LABEL_HOME),
        "home_page": link_of(home),
        "up_nav": link_of(up, LABEL_UP) if up else "",
    }


def _render_contents(info):
    """目次ページ側。子ページの一覧を出す（本家 is_home の枝）。"""
    items = "".join(
        '<li><a href="{}">{}</a></li>'.format(
            escape("/" + path, quote=True), escape(label))
        for path, label in info["children"])
    return f'<ul class="navi_contents">{items}</ul>'


def _render_header(info):
    """子ページの1回目。ページの先頭に置く送り（本家のDocBook風ヘッダー）。"""
    return (
        '<ul class="navi" aria-label="ページ送り">'
        f'<li class="navi_left">{info["prev_nav"]}</li>'
        f'<li class="navi_none">{info["home_page"]}</li>'
        f'<li class="navi_right">{info["next_nav"]}</li>'
        "</ul>"
        '<hr class="full_hr">'
    )


def _render_footer(info):
    """子ページの2回目以降。ページの末尾に置く送り（本家のDocBook風フッター）。"""
    return (
        '<hr class="full_hr">'
        '<ul class="navi" aria-label="ページ送り">'
        f'<li class="navi_left">{info["prev_nav"]}<br>{info["prev_page"]}</li>'
        f'<li class="navi_none">{info["home_nav"]}<br>{info["up_nav"]}</li>'
        f'<li class="navi_right">{info["next_nav"]}<br>{info["next_page"]}</li>'
        "</ul>"
    )


def _convert(resolved, body, context):
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")

    current = _current_pagepath(context)
    # 「上へ」は current の1つ上。本家の `$pos > 0` と同じで、深さ1のページ
    # （`/` を含まない）には出さない。
    pos = current.rfind("/")
    up = current[:pos] if pos > 0 else ""

    raw_home = resolved["home"]
    if raw_home is None:
        # 本家と同じ。引数を省いた #navi() は「このページが目次」の意味になり、
        # 自分自身の存在は確かめない（いま描いているページなので在る）。
        home, is_home = current, True
    else:
        home = full_pagepath(current, (raw_home or "").strip())
        if not is_valid_pagepath(home):
            raise PluginArgumentError(f"目次ページの指定が正しくありません: {raw_home}")
        is_home = (home == current)

    # home・up は walk（home の下）の範囲に入らないことがあるので個別に引く。
    # 1回の呼び出しにつき問い合わせ1回で済むよう、ここでまとめて取る。
    outside = _items_of(context, [home, up])
    if raw_home is not None:
        if home not in outside:
            raise PluginArgumentError(f"目次ページがありません: {_path_text(home)}")
        if not is_home and not _is_under(home, current):
            raise PluginArgumentError(
                "{} の子ページではありません（{}/{} のような、その下のページに"
                "書いてください）".format(_path_text(home), _path_text(home).rstrip("/"),
                                    current.rsplit("/", 1)[-1] or "ページ名"))

    state = _state(context)
    footer = home in state             # 1回目: False、2回目以降: True
    if not footer:
        state[home] = _survey(context, home, current, up, outside,
                              resolved["reverse"], resolved["exclude"])
    info = state[home]

    if is_home:
        if footer:
            # 本家の "You already view the result" にあたる。一覧を出す材料は
            # 1回目で使い切っているので、2つめは書きかたの間違いとして知らせる。
            raise PluginArgumentError(
                "子ページの一覧はすでにこのページに出ています"
                "（目次ページに #navi を2つ以上書くことはできません）")
        if not info["children"]:
            raise PluginArgumentError(
                "子ページがありません（{}/... のようなページを作ってください）".format(
                    _path_text(home).rstrip("/")))
        return _render_contents(info)

    if not footer:
        return _render_header(info)
    return _render_footer(info)
