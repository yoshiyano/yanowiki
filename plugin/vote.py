# 参照する共有モジュール: _polling.py（同じフォルダのものを importlib で読み込む）
"""vote — 簡易投票（アンケート）フォームを置く、ブロック専用のプラグイン。

    #vote(選択肢1,選択肢2,選択肢3, ...)

 1. **candidates** … 選択肢を`,`区切りで並べます（省略不可。2つ以上必要）
 2. id … この投票フォームを見分ける ID（`id="votaB3xY"` の形）。書かなくて
       かまいません——ページを表示したときに、プラグイン自身が書き足します
       (default: 表示したときに書き足す)

投票結果はページ本文そのもの（`#vote(...)`の引数）に書き戻して保存し直します
（投票結果という別のデータベースがあるわけではなく、本家PukiWiki譲りの
仕組みです）。投票のたびに、それぞれの選択肢の横に票数と割合の棒グラフが
表示されます。

```markdown
#vote(カレー,ラーメン,寿司)
```

投票にはJavaScriptが必要です（使えない環境では「この環境では投稿ができません」と
出て、投票できません）。ページを開いている間は、5分ごとに票数を取り込んで投票の欄
だけを更新します。投票の欄がページから消されていたら「該当フォームがなくなりました」と
出ます。
"""

""" 技術資料
本家PukiWikiの`vote.inc.php`を移植した。`comment.py`と同じく「プラグインの
送信でページ本文そのものを書き換えて保存し直す」プラグイン。

## 選択肢の受け取りかた（`num_order: -1`）

`#vote(A,B,C)`はフレームワークの引数パーサがトップレベルの`,`ごとに
別々の位置引数へ分解してから渡してくる。可変長（いくつ書くか決まって
いない）の選択肢を1つの宣言で受け取るため、残りの位置引数すべてを`","`で
連結した1つの文字列にする宣言を使い、`_convert`側で改めて`,`で割り直して
個々の選択肢に戻す。

当初は`rest_params: True`だったが、`rest_params`は名前付き引数と一緒に使えない
（`id=…`が「知らない引数です」になる）ため、2026-09-30に`id`を足すときに、
同じ働きをする自由順序の`num_order: -1`へ替えた（`id`は`kw_only`）。書ける形は
変わらない。

**選択肢の名前そのものに`,`を含めることはできない**（連結し直した時点で
元の引用符の情報が失われるため、`"名前, 付き"`の
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

## 投票先の見分けかた（ID、2026-09-30）

以前は「ページの中で何番目の`#vote(`行か」（`vote_no`）で投票先を探していたが、
描かれない所（`#code`の本体など）に書いた`#vote(`行まで数えてずれることがあった。
Wiki設計者の指示で、呼び出しごとの ID（`id="votaB3xY"`）で見分ける形に改めた。
ID は描いたときに書き足す。決まりと実装は共有の`_polling.py`（`comment`と共通）に
ある。投票で行を書き直すときは、`id`をそのまま残す（`_action`）。

## JS 必須と polling（2026-10-23）

`comment`と同じ（`comment.py`の技術資料「投稿はページ遷移なしで反映する…」）。投票は
`vote.js`の fetch だけを受け付け（`_polling.fetch_only`）、成功は204。画面は
`_polling.js`が投票の欄だけを差し替える。ページを開いている間は5分ごとに票数を取り込む
（`PLUGIN_INFO["polling"]`）。「ここからは投票できません」の注意書きも描画範囲
（`_polling.wrap`の中）に入れた（以前は`<div class="vote-box">`の外に足していた）。

## 投票の直前に本文を読み直す・厳密な競合検出はしない、という判断

`comment.py`は以前、フォームを開いた時点の本文ハッシュ（`digest`）を投稿時に
照合し、食い違っていたら拒否していた（2026-09-30に ID で書き込み先を探す形にして
やめた）。**voteは当初からこれを持たない。** 投票は同じ`#vote(...)`に対して短時間に
何人も連続で押すのが通常の使いかたで、他の投票者が一瞬前に投票しただけで撥ねられる
のは使い物にならないため。`_action`は**投票の直前にその`#vote(...)`行を改めて
読み直し**、その時点の票数に1票足して書き戻す。投票先は ID で探すので、本文のほかの
場所が編集されていても取り違えない。

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
from wikilib.plugins import PluginArgumentError, parse_plugin_args
from wikilib.web import plain

TOKEN_RE = re.compile(r"^(.*)\[(\d+)\]$")

PLUGIN_INFO = {
    "help": "#vote(candidate1,candidate2,...,id)",
    # 開いている間、保存されている本文に合わせて描き直す（`_polling.py`）
    "polling": True,
    "args": [
        # 呼び出しごとの ID（技術資料「投票先の見分けかた」）。描いたときに書き足す
        {"name": "id", "kw_only": True, "default": "", "label": "ID",
         "candidate": [(r"[0-9A-Za-z_-]+", "re")]},
        # 残りの位置引数をすべて受ける（技術資料「選択肢の受け取りかた」）
        {"name": "candidates", "num_order": -1, "default": "", "label": "選択肢"},
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


def _render(candidates, vote_id, api, page_val, off):
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
            f'<button type="submit" name="index" value="{i}"{off}>投票</button>'
            "</td>"
            "</tr>"
        )
    return (
        '<div class="vote-box">'
        f'<form method="post" action="{api}">'
        f'<input type="hidden" name="page" value="{page_val}">'
        f'<input type="hidden" name="vote_id" value="{escape(vote_id, quote=True)}">'
        '<table class="vote-table"><tbody>'
        f"{''.join(rows)}"
        "</tbody></table>"
        "</form>"
        "</div>"
    )


def _convert(resolved, body, context):
    if not context.wiki_dir or context.page is None:
        raise PluginArgumentError("ページの場所が分かりません。")

    # 投票先を見分ける ID。無ければここで本文へ書き足され、本体が描き直す（技術資料
    # 「投票先の見分けかた」）。None なら、このページの保存済みの本文と対応が取れない
    # （取り込み前など）ので、投票できなくする
    polling = _load_polling()
    vote_id = polling.call_id(context, "vote", resolved["id"])

    candidates = _parse_candidates(resolved["candidates"])
    if len(candidates) < 2:
        raise PluginArgumentError(
            "選択肢を2つ以上指定してください: #vote(選択肢1,選択肢2,...)"
        )

    api = escape(f"{context.base_url}/{PLUGIN_URLPATH}/vote", quote=True)
    page_val = escape(context.page, quote=True)
    # 投票できるのは JS が動く環境だけ（`_polling.NEEDS_JS`）
    html = _render(candidates, vote_id or "", api, page_val,
                   polling.NEEDS_JS if vote_id is not None else " disabled")
    if vote_id is None:
        html += ('<p class="vote-note">この投票には、ここからは投票できません'
                 '（書かれているページを開いて投票してください）。</p>')
    return polling.wrap(html, context, "vote", vote_id)


def _load_polling():
    """兄弟の`_polling.py`（共有モジュール）を読み込む（呼び出しごと）。"""
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_polling.py")
    spec = importlib.util.spec_from_file_location("wikiplugin__polling", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _action(context):
    polling = _load_polling()
    if request.method == "GET" and request.query.get("poll"):
        return polling.handle(context)
    refused = polling.fetch_only()
    if refused is not None:
        return refused

    pagepath = (request.forms.getunicode("page", "") or "").strip("/")
    if pagepath and not is_valid_pagepath(pagepath):
        return plain("ページの指定が正しくありません。", status=400)

    vote_id = (request.forms.getunicode("vote_id", "") or "").strip()
    try:
        index = int(request.forms.get("index", "-1"))
    except ValueError:
        return plain("投票の指定が正しくありません。", status=400)

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
    # 投票先は ID で探す（重なっていれば最初のもの）
    call, reason = polling.find_call(context, source, ref.ext, "vote", vote_id)
    if call is None:
        return plain(reason, status=409)
    lines = source.split("\n")
    line, loc = lines[call["line"]], call["loc"]
    if not loc["paren"]:
        return plain("投票先（#vote）の書きかたが正しくありません。", status=409)
    a0, a1 = loc["args"]
    positional, _keyword = parse_plugin_args(line[a0:a1])
    candidates = _parse_candidates(",".join(p for p in positional if p))
    if not (0 <= index < len(candidates)):
        return plain("選択肢の指定が正しくありません。", status=400)

    name, count = candidates[index]
    candidates[index] = (name, count + 1)
    # 引数だけを書き直す（ID はそのまま残す。行頭の字下げや閉じ括弧の後ろも変えない）
    args = ",".join(f"{n}[{c}]" for n, c in candidates) + f', id="{call["id"]}"'
    lines[call["line"]] = line[:a0] + args + line[a1:]
    new_source = "\n".join(lines)

    save_page(context.wiki_dir, context.config, ref.subpath, ref.ext, new_source)

    # 成功は 204 だけ返し、画面の更新は vote.js・_polling.js が行う
    # （303 だと、メニューや include で取り込まれた投票から、書き込み先のページへ移ってしまう）
    return HTTPResponse(status=204)
