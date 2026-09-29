"""vote — 簡易投票（アンケート）フォームを置く、ブロック専用のプラグイン。

    #vote(選択肢1,選択肢2,選択肢3, ...)

 1. **candidates** … 選択肢を`,`区切りで並べます（省略不可。2つ以上必要）

投票結果はページ本文そのもの（`#vote(...)`の引数）に書き戻して保存し直します
（投票結果という別のデータベースがあるわけではなく、本家PukiWiki譲りの
仕組みです）。投票のたびに、それぞれの選択肢の横に票数と割合の棒グラフが
表示されます。

```markdown
#vote(カレー,ラーメン,寿司)
```
"""

""" 技術資料
本家PukiWikiの`vote.inc.php`を移植した。`comment.py`と同じく「プラグインの
送信でページ本文そのものを書き換えて保存し直す」プラグイン。

## 選択肢の受け取りかた（`rest_params`）

`#vote(A,B,C)`はフレームワークの引数パーサがトップレベルの`,`ごとに
別々の位置引数へ分解してから渡してくる。可変長（いくつ書くか決まって
いない）の選択肢を1つの宣言で受け取るため、`rest_params: True`
（技術ドキュメント参照。`num_order`とは別の仕組みで、残りの位置引数
すべてを`","`で連結した1つの文字列にする）を使った。`_convert`側で
改めて`,`で割り直して個々の選択肢に戻す。

**選択肢の名前そのものに`,`を含めることはできない**（`rest_params`が
連結し直した時点で元の引用符の情報が失われるため、`"名前, 付き"`の
ように引用符で囲んでも区別が復元できない）。本家も同様の制約を持つ
（区切り文字が`,`であるという設計そのものに起因するため）。

## 得票数の埋め込みかた（`名前[票数]`）

投票が無いうちは`#vote(カレー,ラーメン,寿司)`のように選択肢名だけを
並べる。投票があるたびに、`_action`がその選択肢の`#vote(...)`行を
書き換え、`名前[票数]`という形で票数を埋め込み直す
（`#vote(カレー[3],ラーメン[1],寿司[0])`）。本家PukiWikiの書式を踏襲
した（Wiki設計者の指摘により、当初アンダースコア区切りで実装していたのを
角括弧に訂正した。2026-09-01）。

- 選択肢名の末尾が`[数字]`であれば「票数付き」、そうでなければ「まだ0票」
  として扱う（`_parse_candidate`）。そのため**選択肢名の末尾を`[数字]`の
  形にすると、書いた時点の票数と誤認される**
  （例: `#vote(第1[2])`は「選択肢『第1』に2票入っている」と解釈される）。
  本家PukiWikiも同じ書式・同じ制約を持つ
- 角括弧はこのシステムの引数パーサでも特別扱いされない文字（`img.py`の
  `zoom`の`[MIN;VALUE%;MAX]`と同じ理由）なので、`,`区切りの1トークン
  （選択肢1つぶん）の中に書いても引数の解析を壊さない

## `vote_no`（1ページに複数の#voteがあるとき）

`comment.py`と同じ考えかたで、`context._vote_counters`（ページパスごとの
辞書）を`context`に乗せて持ち回す。`_action`側の`_find_vote_line`も
出現順に数えて同じ番号の行を探す（両者の数えかたを一致させる必要が
あるため、`#vote(`で始まる行はすべて1つと数える）。

## 投票の直前に本文を読み直す・厳密な競合検出はしない、という判断

`comment.py`はフォームを開いた時点の本文ハッシュ（`digest`）を投票時に
照合し、食い違っていたら投稿そのものを拒否する（Wiki設計者の指示による、
本家より厳しい仕様）。**voteはこれを踏襲しない。** 投票は同じ
`#vote(...)`に対して短時間に何人も連続で押すのが通常の使いかたであり、
`comment`のような低頻度の書き込みと違って、他の投票者が一瞬前に
投票しただけで毎回「別の場所で更新されています」と撥ねられるのは
使い物にならない。そのため`_action`は**投票の直前にその`#vote(...)`行を
改めて読み直し**、その時点の票数に1票足して書き戻す（`comment.py`が
本文全体を読み直すのと同じ発想を、行単位に狭めて適用したもの）。
本文全体を対象にした`digest`照合は行わないため、`#vote(...)`と無関係な
箇所が同時に編集されていた場合の競合は防げない（本家にも無い保護であり、
理論上のごく狭い競合ウィンドウを許容する）。

## 棒グラフをCSSで作る（本家は画像を引き伸ばすgif/pngだった）

本家は1x1pxの画像を目的の幅まで引き伸ばして棒グラフを表現していたが、
これは「出力の技術的な手段」の範囲として`width`を指定した`<span>`へ
現代化した（`../CLAUDE.md`の後方互換方針に沿う。画像を使うか
CSSを使うかは書き手から見える機能ではなく実装の手段のため）。幅は
**その`#vote()`内の総得票数に対する割合**（`count / total * 100`、
総得票数0のときは0%）。本家がどちらの基準だったかは実装を確認できて
いないが、割合表示として素直な基準を採った。Wiki設計者に実際の見た目を
確認してもらったところ、「本家と見た目は違うが、こちらのほうが洗練
されている」との評価で、本家と一致させる必要は無いことが確定した
（`Syntax/Plugin/vote.md`の表示例に実物の画像を添付済み）。

## 重複投票の防止は無い（本家どおり）

本家vote.inc.phpにはCookie等による二重投票の防止機能が無く、同じ人が
何度でも投票し直せる。この挙動をそのまま踏襲した（新たに制限を加えると
本家との後方互換方針に反するため）。
"""

import re
from html import escape

from bottle import HTTPResponse, request

from wikilib.auth import PAGE_NONE
from wikilib.pagedb import resolve_page_ref
from wikilib.pagesave import save_page
from wikilib.paths import PLUGIN_URLPATH, is_valid_pagepath
from wikilib.plugins import PluginArgumentError
from wikilib.web import plain

MARKER_RE = re.compile(r"^#vote\(")
LINE_RE = re.compile(r"^#vote\((.*)\)\s*$")
TOKEN_RE = re.compile(r"^(.*)\[(\d+)\]$")

PLUGIN_INFO = {
    "help": "#vote(candidate1,candidate2,...)",
    "args": [
        {"name": "candidates", "rest_params": True},
    ],
}


def _parse_candidate(token):
    """1つの選択肢トークンを (名前, 票数) にする。末尾が`[数字]`なら
    その数字を票数として読み、それ以外は0票の新しい選択肢として扱う。"""
    token = token.strip()
    m = TOKEN_RE.match(token)
    if m:
        return m.group(1), int(m.group(2))
    return token, 0


def _parse_candidates(raw):
    """`rest_params`で受け取った"，"連結済みの文字列を、(名前, 票数) の
    一覧にする。空トークンは読み飛ばす（連続するコンマ等の書き間違い）。"""
    result = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        result.append(_parse_candidate(token))
    return result


def _render(candidates, comment_no, api, page_val):
    total = sum(count for _name, count in candidates)
    rows = []
    for i, (name, count) in enumerate(candidates):
        percent = (count / total * 100) if total else 0
        rows.append(
            "<tr>"
            f'<td class="vote-label">{escape(name)}</td>'
            '<td class="vote-bar-cell">'
            f'<span class="vote-bar" style="width:{percent:.1f}%"></span>'
            "</td>"
            f'<td class="vote-count">{count}票（{percent:.0f}%）</td>'
            "<td class=\"vote-action\">"
            f'<button type="submit" name="index" value="{i}">投票</button>'
            "</td>"
            "</tr>"
        )
    return (
        '<div class="vote-box">'
        f'<form method="post" action="{api}">'
        f'<input type="hidden" name="page" value="{page_val}">'
        f'<input type="hidden" name="vote_no" value="{comment_no}">'
        '<table class="vote-table"><tbody>'
        f"{''.join(rows)}"
        "</tbody></table>"
        "</form>"
        "</div>"
    )


def _convert(resolved, body, context):
    if not context.wiki_dir or context.page is None:
        raise PluginArgumentError("ページの場所が分かりません。")

    candidates = _parse_candidates(resolved["candidates"])
    if len(candidates) < 2:
        raise PluginArgumentError(
            "選択肢を2つ以上指定してください: #vote(選択肢1,選択肢2,...)"
        )

    # 1ページに複数の#voteがあっても別々に数えられるよう、contextに
    # カウンタを乗せて持ち回す（comment.pyと同じ考えかた。技術資料参照）
    counters = getattr(context, "_vote_counters", None)
    if counters is None:
        counters = {}
        context._vote_counters = counters
    vote_no = counters.get(context.page, 0)
    counters[context.page] = vote_no + 1

    api = escape(f"{context.base_url}/{PLUGIN_URLPATH}/vote", quote=True)
    page_val = escape(context.page, quote=True)
    return _render(candidates, vote_no, api, page_val)


def _find_vote_line(source, vote_no):
    """`source`の`vote_no`番目の`#vote(...)`行の (行番号, 選択肢一覧) を返す。
    見つからなければ (None, None)。"""
    lines = source.split("\n")
    count = 0
    for i, line in enumerate(lines):
        if MARKER_RE.match(line):
            if count == vote_no:
                m = LINE_RE.match(line)
                if not m:
                    return None, None
                return i, _parse_candidates(m.group(1))
            count += 1
    return None, None


def _action(context):
    pagepath = (request.forms.getunicode("page", "") or "").strip("/")
    if pagepath and not is_valid_pagepath(pagepath):
        return plain("ページの指定が正しくありません。", status=400)

    try:
        vote_no = int(request.forms.get("vote_no", "0"))
        index = int(request.forms.get("index", "-1"))
    except ValueError:
        return plain("投票の指定が正しくありません。", status=400)

    redirect_to = context.base_url + "/" + pagepath

    # 閲覧の権限が無いページには書き込ませない（Wiki設計者の指示、2026-09-15）。
    # R のページは通す——プラグインによる書き換えはユーザの編集とは別に数え、
    # 未ログインでも止めない決まり（Tech/PagePermissions「決まったこと」）
    if context.privilege.check(pagepath) == PAGE_NONE:
        return plain("このページを閲覧する権限がありません。", status=403)

    ref = resolve_page_ref(context.wiki_dir, pagepath)
    if ref is None or not ref.exists:
        return plain("そのページはまだありません。", status=404)

    # 投票の直前に改めて読み直す（他の人の投票が間に合わせで反映された
    # 状態に、自分の1票を積み増す。厳密な競合検出をしない理由は技術資料）
    source = ref.body or ""
    line_no, candidates = _find_vote_line(source, vote_no)
    if line_no is None:
        return plain(
            "投票先（#vote）が見つかりませんでした。"
            "ページが編集されて位置がずれた可能性があります。",
            status=409)
    if not (0 <= index < len(candidates)):
        return plain("選択肢の指定が正しくありません。", status=400)

    name, count = candidates[index]
    candidates[index] = (name, count + 1)
    new_line = "#vote(" + ",".join(f"{n}[{c}]" for n, c in candidates) + ")"
    lines = source.split("\n")
    lines[line_no] = new_line
    new_source = "\n".join(lines)

    save_page(context.wiki_dir, context.config, ref.subpath, ref.ext, new_source)

    return HTTPResponse(status=303, headers={"Location": redirect_to})
