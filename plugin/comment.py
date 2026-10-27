# 参照する共有モジュール: _polling.py（同じフォルダのものを importlib で読み込む）
"""comment — コメント投稿フォームと、投稿済みコメントの一覧を置く、
ブロック専用のプラグイン。

    #comment()
    #comment(見出し, noname, nodate, newbottom)

 1. legend … コメント欄の見出し（`<legend>`）に表示する文字列
       (default: "コメント")
 2. noname … 単語を書くと、名前欄を隠す (default: 出す)
 3. nodate … 単語を書くと、投稿日時を付けない (default: 付ける)
 4. newtop    … 単語を書くと、新しいコメントを上（フォームの直下）に
       追加する (default。書いても書かなくても同じ——上下どちらでも
       明示したいときのために残した書きかた)
 5. newbottom … 単語を書くと、新しいコメントを下（一覧の末尾）に追加する
       (default: 上に追加。本家PukiWikiと同じ、古い→新しい の並び順に
       したいときに使う)
 6. id … このコメント欄を見分ける ID（`id="cmtaB3xY"` の形）。書かなくて
       かまいません——ページを表示したときに、プラグイン自身が書き足します
       (default: 表示したときに書き足す)

投稿済みのコメントは`{{ }}`（波括弧2つ、複数行）の本体に溜まります。
**書かなくてもかまいません**——`#comment()`のように本体を省略すると、
最初の投稿があったときにプラグイン自身が`{{ }}`を書き足します（エラーに
はしません）。

フォーム・区切り線・本体（コメント一覧）は1つの`<fieldset>`（見出しは
`<legend>`）にまとめて表示され、枠線で囲われます。フォーム自体には
枠線は付きません。

1つのページに`#comment()`を複数置くと、それぞれ別々にコメントを溜め
られます。投稿の書き込み先は`id`で見分けます（`#comment()`を写して`id`が
重なっても、次に表示したときに後のほうへ新しい`id`が振られます）。

名前欄はブラウザのlocalStorageに前回使った値を覚えていて、次に開いた
ときの既定値として入れておきます（`comment.js`）。リンクは作りません
（ただの文字列として本文に書き足すだけです）。

投稿にはJavaScriptが必要です（使えない環境では「この環境では投稿ができません」と
出て、投稿できません）。ページを開いている間は、5分ごとに新しいコメントを取り込んで
コメント欄だけを更新します（書きかけの文はそのまま残ります）。コメント欄がページから
消されていたら「該当フォームがなくなりました」と出ます。
"""

r""" 技術資料
本家PukiWikiの`comment.inc.php`を土台にしつつ、「投稿済みコメントを
プラグイン自身の本体（`{{ }}`）に溜める」という、Wiki設計者の指示による
このシステム独自の再設計を行った。「プラグインにフォームを持たせ、その
送信でページ本文そのものを書き換えて保存し直す」という、このシステムで
初めての類のプラグイン（`ls`/`accesslog`はどちらも**読むだけ**）。

## なぜ本体（`{{ }}`）に溜める形にしたか

最初の実装は、投稿済みコメントを`#comment()`マーカー行の前後に**普通の
本文として**並べる形にしていた。この形だと、投稿済みコメント一覧と
フォームを1つの`<fieldset>`で視覚的に囲おうとしても、**どこまでが
「自分の描いたコメント」で、どこからが利用者が書いた別の本文かを
comment.py側が判定できない**という問題があった（コメント行の見た目
自体、利用者が手で書いた普通の箇条書きと区別が付かないため）。

`{{ }}`本体という、フレームワークが位置を明確に区切ってくれる仕組みに
コメントを収めることで、この境界判定の問題が構造的に無くなる
（`_sys/wikilib/plugins.py`の`plugin_block_rule`が`{{`〜`}}`の範囲を
`token.map`で正確に区切ってくれるので、それと同じ考えかたで
`_insert_comment`側も「開き括弧の行から、対応する閉じ括弧の行まで」を
機械的に扱える）。Wiki設計者の指示による方針転換。

## 全体の流れ

1. `_convert`がコメントフォーム（`<form method="post" action="{このプラグイン
   自身のaction URL}">`）と、本体（`body`。投稿済みコメントの生テキスト。
   まだ無ければ空文字列）を
   `<fieldset><legend>…</legend>{フォーム}<hr>{本体}</fieldset>`の形に
   まとめて描き、`_polling.wrap`で包む。隠しフィールドに、対象ページ（`page`）・
   この呼び出しの ID（`comment_id`）・`noname`/`nodate`/`newtop`を持たせる
2. 投稿されると`_action`が呼ばれ、`msg`（必須）・`name`（任意）を受け取り、
   コメント行を組み立てる
3. **そのページの現在の本文を読み直し**（フォームを開いてから他の人が
   編集したかもしれないので、投稿の直前に改めて読む）、ID が`comment_id`の
   `#comment(...)`を探す。`{{ ... }}`が無ければ**その場で付け足し**、
   本体の先頭（`newtop`。**既定はこちら**）または末尾（`newbottom`）に
   コメント行を挿し込む
4. `wikilib.pagesave.save_page`で保存し、204を返す。投稿は`comment.js`の
   fetchによるもの（`X-Requested-With: fetch`）だけを受け付ける（次の節）

## 投稿はページ遷移なしで反映する（2026-10-05）・JS 必須と polling（2026-10-23）

`comment.js`が送信を止めて`fetch`で投稿する。書き込み先のページへ303で移ってしまうと、
`#include`で取り込まれたコメント欄から投稿したときに、取り込み元に留まれないため
（フォームの`page`は書き込み先＝取り込まれた側のページ）。

- **JS が使えない環境では投稿を受け付けない**（Wiki設計者の指示、2026-10-20）。送信ボタンは
  `disabled`で描き、`_polling.js`が外す。`_action`は`X-Requested-With: fetch`の無い投稿を
  400で断る（`_polling.fetch_only`）。以前の「エラーなら通常の送信に切り替える」道は
  無くなった（通信が切れたときに同じ内容を2回送るおそれもあった）
- 成功したら、`location.reload()`ではなく、`_polling.js`にこのページを問い合わせてもらい、
  コメント欄だけを差し替える（ai-notes の E8）。断られたら、理由をフォームのそばに出し、
  入力した内容は残す（Wiki設計者の指示、2026-10-22「投稿データを待避できる状態」）
- ページを開いている間は、5分ごとに新しいコメントを取り込む（`_polling.py`。
  `PLUGIN_INFO["polling"]`）。書きかけの入力は引き継ぐ
- 以前（2026-10-05）、コメント欄だけを差し替える案は、Wiki設計者が再読み込みで足りるなら、と
  指示して見送っていた。polling で差し替えの仕組みができたので、投稿後もそれを使う
  （クロコの実装例）

## 書き込み先の見分けかた（ID、2026-09-30）

以前は「ページの中で何番目の`#comment(`行か」（`comment_no`）で書き込み先を
探していた。描く側（`_convert`）は描いた順に、投稿を受ける側（`_action`）は
本文の`#comment(`行を上から数えていたため、描かれない所（`#code`の本体、
`#table`のセル）に書いた`#comment(`行まで数えて、別の`#comment`の本体へ
書き込んでいた。

Wiki設計者の指示で、呼び出しごとの ID（`id="cmtaB3xY"`）で見分ける形に改めた。
ID は描いたときに書き足し、投稿は ID で探す。決まり（ID の形・重なったときの
振り直し・見つからないときの断りかた）と実装は、`vote`と共通の`_polling.py`にある。
描いている本文がこのページの保存済みの本文と対応しない（ファイルを直接直して取り込んで
いないときなど）と ID が決まらないので、投稿できないフォーム（`disabled`）にする。

フォームの部品の`id`属性（`comment-name-cmtaB3xY`など）は、呼び出しの ID から作る。
polling で1つのコメント欄だけを描き直しても、ページのほかの部品と重ならないようにするため。
ID が決まらない呼び出しには、`context._comment_counters`（1回の描画全体の通し番号）を使う。

## digest をやめた（2026-09-30）

以前は、フォームを描いた時点の本文ハッシュ（`digest`）を持たせ、投稿のときに本文が
変わっていたら409で断っていた（Wiki設計者の指示）。目的は、何番目の`#comment`かで
探していた書き込み先がずれるのを防ぐことだった。

ID で書き込み先を探すようにしたので、本文が変わっていても書き込み先は取り違え
ない。Wiki設計者の基準「ほかのフォームへ投稿が乗らないようにする ＞ 利用者の利便性」
（2026-09-30）に照らして、取り違えの心配が無くなった検査で投稿を断る理由は無いと
クロコが判断し、`digest`をやめた。同じ ID が付け直されたあとの古いフォームは、
polling で投稿の前に「該当フォームがなくなりました」と分かる（`_polling.py`）。

本家PukiWikiは`digest`が食い違うと警告しつつ追加していた。いまは警告も出さずに追加する。

## コメント行の組み立て

本家の`PLUGIN_COMMENT_FORMAT_STRING`（`"$msg -- $name $now"`）を素直に
Pythonへ移した。

- `msg`の先頭にある`-`/`--`（本家の慣習: 深い階層のコメントとして
  返信したいときに使う、リスト記法の階層記号）は`head`として取り出し、
  コメント行の先頭（`-{head} {本体}`）に使う。改行は本家と同じく
  すべて取り除く。**この「先頭の`-`の数で階層を表す」書きかたは
  PukiWiki記法のリストの決まりであり、Markdownのリストは記号の個数
  ではなく字下げで階層を表すため、Markdownページでは`--`と書いても
  期待どおりのネストにならない**（`build_markdown_renderer`で実際に
  確認した。`--`はMarkdown側では単なる地の文字として`<p>`になる）。
  本家の書きかた自体は削らず移植しているが、Markdownページで使う場合の
  見た目はPukiWiki記法とは異なることを承知しておくこと
- 既定（`noname`/`nodate`どちらも無し）は`msg -- 名前 日時`の形になる。
  名前が空欄のときは`名無しさん`（本家の`$_no_name`に相当する埋め込みの
  既定名。このシステムには本家のような多言語メッセージ表が無いため
  固定の日本語文字列にした）
- `noname`を指定すると、**`-- 名前`の部分ごと丸ごと省く**（Wiki設計者の指示。
  本家のように「名前欄が空なら名無しさんと出す」のではなく、`noname`の
  ときは名前という情報自体を跡形もなく残さない）。`nodate`も一緒に
  指定していなければ`msg 日時`（`--`区切りも付かない）、両方指定して
  いれば`msg`だけになる
- 日時は`wikilib.subst._now_str()`（`&now;`が保存時に置き換わるのと
  同じ書式、"YYYY-MM-DD (曜) HH:MM:SS"）をその場で評価した固定文字列を、
  本家と同じく **`&new{日時};`で囲んで**埋め込む（Wiki設計者の指示、
  2026-09-26。`new`プラグインができたため。それまでは印無しの日時だけだった）。
  新しいコメントに" New!"が付き、5日を過ぎると`new`が本文から外して日時の
  文字だけに戻す（`plugin/new.py`の技術資料）。**Markdownのページには
  `&new(){日時};`と丸括弧を付けて書く**——Markdownでは丸括弧の無い
  `&new{…};`はプラグインにならず、文字のまま出るため（`_date_call`）

**名前をページへのリンクにする本家の書きかた（`[[名前]]`）は実装していない**
（Wiki設計者の指示）。名前はただの文字列として本文に書き足すだけで、リンクは
生成しない。

## 名前のlocalStorage記憶（`comment.js`）

名前欄は`noname`が無ければ毎回出るが、**同じ人が何度も投稿するときに
毎回名前を打ち直すのは面倒**なので、ブラウザのlocalStorageに前回使った
名前を覚えておき、次に開いたときの既定値として入れておく（Wiki設計者の指示）。

- ページを開いたとき、名前欄が空ならlocalStorageの記録を入れておく
- 投稿（送信）時、名前欄の値がlocalStorageの記録と違っていれば、
  それを新しい記録として上書きする
- 投稿時、名前欄が空になっていれば記録を削除する

キーは1つだけ（`wikisys-comment-name`）で、1ページに複数の`#comment()`が
あってもサイト全体でも共有する（「自分の名前」はページ単位の情報では
なくブラウザ単位の情報のため）。localStorageは閲覧者のブラウザだけに
残る情報で、サーバには送られない（フォーム送信時に`name`欄の値として
初めてサーバへ渡る、これはlocalStorageを使わない場合と同じ経路）。

## 本体への差し込みかた

書き込む`#comment`の行は`_polling.find_call`が見つける（同じ ID が重なっていれば最初の
もの。行の中の位置と、閉じ
括弧の後ろの位置も返す）。閉じ括弧の後ろ（丸括弧の無い PukiWiki記法では
`#comment`の直後）を見て、3通りに分けて扱う。

1. **既に`{{ ... }}`本体がある**（`FENCE_TAIL_RE`——後ろに`{{`（2つ以上の`{`）
   だけがある。`_sys/wikilib/plugins.py`の`PLUGIN_BLOCK_FENCE_RE`と同じ考えかた）。
   開き括弧と同じ数以上の`}`だけの行が現れるまでを本体として扱い
   （`plugin_block_rule`の`close_re`と同じロジック）、`newtop`ならその
   先頭に、`newbottom`ならその末尾にコメント行を追加する。
2. **本体を何も書いていない素の`#comment(...)`**（後ろに何も無い）。**この場合は
   エラーにせず、その場で`{{`・コメント行・`}}`の3行を書き足す**（Wiki設計者の
   指示。技術資料「初期状態で{{ }}が無い場合」参照）。newtop/newbottomの違いは、
   コメントが1件も無い状態への挿入なので結果は同じになる。
3. どちらにも当てはまらない（1行の`{…}`形式など、壊れた・想定外の
   書きかた）。差し込めないので`inserted=False`のまま呼び出し元へ返し、
   409（「コメントを追加する場所が見つかりませんでした」）にする。

リストや引用の中に書かれた`#comment`は、書き足す行の頭を呼び出しの行にそろえる
（`- #comment()`なら字下げ2つ、`> #comment()`なら`> `）。以前は行頭の`#comment`
しか探していなかったので、ここは ID にしたときに広がった。

## #table のセルの中（2026-10-23）

`#table`のセルの中の`#comment`にも投稿できる（Wiki設計者の指示）。書き込み先の走査は
`_polling.py`がセルの中まで見る。書き足しは、セルの区切り（`|`）が同じ行に続くことがあるので、
次のようにする（`_insert_comment`）。

```
|#comment(id="cmtaB3xY")|\\     →   |#comment(id="cmtaB3xY"){{
                                     - コメント -- 名無しさん &new(){…};
                                     }}|\\
```

- **閉じ括弧（`}}`）の行には、セルの残り（`|\\`など）を続け、閉じ括弧だけの行にしない。**
  閉じ括弧だけの行は、外側の`#table(){{ … }}`の終わりと読まれるため（開き括弧と同じ数
  以上の`}`だけの行が終わり、という決まり）
- 本体がすでにある場合は、`}}|…`の行を閉じ括弧の行として探す
- セルの中は字下げしない（字下げすると、PukiWiki のページでは整形済みテキストになる）

## 初期状態で`{{ }}`が無い場合（Wiki設計者の指示）

`#comment()`は本体（`{{ }}`）を省略して書いてよい。**省略時にエラーには
せず**、`_convert`は本体を空文字列として扱ってフォームだけを描く（区切り
線の下は何も無い状態）。実際に最初の投稿があったときになって初めて、
`_action`（`_insert_comment`のケース2）が本体を書き足す。ページ作成の
手間を減らすための割り切りで、「本体を用意していないと使えない」という
初回実装時の不便さ（当初は`body is None`でエラーにしていた）を解消した。

## 丸括弧の無い `#comment`（2026-09-26）

PukiWiki記法は、丸括弧の無い `#comment`（本家の実データでいちばん多い書きかた）や
`#comment{{` もプラグインとして描く。ところが差し込む先を探す正規表現が
`^#comment\(` だったため、フォームは出るのに、投稿すると「書き足す場所が見つからない」
（409）で必ず断られていた。2026-09-30 からは書き込み先をページと同じパーサーで
探す（`_polling.py`）ので、書きかたごとの区別はパーサーに任せている。ID を書き足すと
`#comment(id="…")` のように丸括弧が付く。

## 表示（`<fieldset>`・区切り線）

Wiki設計者の指示: フォームと投稿済みコメント一覧を、プラグインの描画範囲
（フォーム＋本体）だけを対象に`<fieldset>`で囲み、左上に`<legend>`を
出す。フォームと本体（コメント一覧）の間には`<hr>`で区切り線を引く。
フォーム自体には枠線を付けない（`comment.css`の`.comment-form`は
これまでどおり枠線無し）。

`body`（本体、投稿済みコメントの生テキスト）は`_convert`が呼ばれる前に
フレームワーク側（`wikilib.plugins.expand_body()`）で展開済みのHTMLとして
渡ってくる（`expand_block`/`expand_inline`/`expand_plugin`を宣言している
ため。`img.py`/`note.py`と同じ仕組み）。エスケープせずそのまま埋め込む
だけでよい。

（過去の版では、`<hr>`と`body`の間に空行（`\n\n`）を挟む必要があった。
当時は「プラグインの返り値全体を再パースする」方式で、空行が無いと
Markdownの「生HTMLブロック」判定が`<hr>`の続きとして`body`の1行目まで
飲み込んでしまい、`<hr>`直後のコメント一覧が展開されない不具合を実際に
踏んだ。2026-09-02に`body`を先に展開して返り値を再パースしない方式へ
変わり、この問題自体が起きなくなったため空行は不要になった）。

**投稿の差し込みは`_convert`が受け取る`body`引数とは無関係**
（`_action`が`ref.body`＝ページの生ソースをディスクから読み直して処理する、
完全に独立した経路）で、この変更の影響を受けない。
"""

import datetime
import re
from html import escape

from bottle import HTTPResponse, request

from wikilib.auth import PAGE_NONE
from wikilib.pagedb import resolve_page_ref
from wikilib.pagesave import save_page
from wikilib.paths import PLUGIN_URLPATH, is_valid_pagepath
from wikilib.plugins import PluginArgumentError
from wikilib.render import is_pukiwiki
from wikilib.subst import _now_str
from wikilib.web import plain

DEFAULT_LEGEND = "コメント"

PLUGIN_INFO = {
    "help": "#comment(legend,noname,nodate,newtop,newbottom,id){{追加されたコメント}}",
    "expand_block": True,
    "expand_inline": True,
    "expand_plugin": True,
    # 開いている間、保存されている本文に合わせて描き直す（`_polling.py`）
    "polling": True,
    "args": [
        {"name": "legend", "num_order": 1, "default": DEFAULT_LEGEND, "label": "見出し"},
        {"name": "noname", "flag": True, "default": False, "label": "名前欄を隠す"},
        {"name": "nodate", "flag": True, "default": False, "label": "日時を付けない"},
        {"name": "newbottom", "flag": True, "default": False, "label": "下に追加"},
        # 呼び出しごとの ID（技術資料「書き込み先の見分けかた」）。描いたときに書き足す
        {"name": "id", "kw_only": True, "default": "", "label": "ID",
         "candidate": [(r"[0-9A-Za-z_-]+", "re")]},
        # newtop だけ num_order: -1（残り物の受け皿）にしている。num_order
        # を1つも宣言しないと自由順序モードに切り替わらない（pre.pyの
        # color引数で踏んだのと同じ落とし穴）。newtop/newbottomどちらを
        # 受け皿にするかは自由順序を成立させるための都合でしかなく、実際の
        # 既定方向（newtop）を決めているのは_convertの
        # `new_at_top = not newbottom`の方。
        {"name": "newtop", "num_order": -1, "candidate": ["newtop"], "default": "", "label": "上に追加"},
    ],
}

ANONYMOUS = "名無しさん"
FENCE_TAIL_RE = re.compile(r"\s*(\{\{+)\s*")
HEAD_RE = re.compile(r"^(-{1,2})-*\s*(.*)$")


def _convert(resolved, body, context):
    if not context.wiki_dir or context.page is None:
        raise PluginArgumentError("ページの場所が分かりません。")

    ref = resolve_page_ref(context.wiki_dir, context.page)
    if ref is None:
        raise PluginArgumentError("ページが見つかりません。")

    # フォームの部品の id を分けるための通し番号（ID が決まらないときだけ使う。技術資料
    # 「書き込み先の見分けかた」）。本文とメニューで重ならないよう、1回の描画全体で数える
    counters = getattr(context, "_comment_counters", None)
    if counters is None:
        counters = {}
        context._comment_counters = counters
    comment_no = counters.get("all", 0)
    counters["all"] = comment_no + 1

    # 書き込み先を見分ける ID。無ければここで本文へ書き足され、本体が描き直す（技術資料
    # 「書き込み先の見分けかた」）。None なら、このページの保存済みの本文と対応が取れない
    # （取り込み前など）ので、投稿できないフォームにする
    polling = _load_polling()
    comment_id = polling.call_id(context, "comment", resolved["id"])
    postable = comment_id is not None
    part = comment_id or comment_no

    # 本体（{{ }}）はまだ無くてもよい（Wiki設計者の指示）。エラーにはせず、
    # 空文字列として扱う。実際に本体を書き足すのは最初の投稿があった
    # ときの_action（技術資料「初期状態で{{ }}が無い場合」参照）。
    body_text = body if body is not None else ""

    legend = resolved["legend"] or DEFAULT_LEGEND
    noname = resolved["noname"]
    nodate = resolved["nodate"]
    newbottom = resolved["newbottom"]
    # newtop は num_order: -1 の受け皿のため、位置引数として書かれた場合は
    # candidate検証を素通りする（既知の抜け穴。SPECIFICATIONS.md参照）。
    # ここで自前に確かめる（pre.pyのcolor引数と同じ対処）。newtop自体は
    # 既定と同じ意味の書きかた（no-op）なので、値の正しさだけ見ればよい。
    newtop_raw = resolved["newtop"]
    if newtop_raw and newtop_raw != "newtop":
        raise PluginArgumentError(f"上に追加の指定が正しくありません: {newtop_raw}")
    new_at_top = not newbottom  # 既定は本体の先頭に追加（新しい投稿がフォーム直下、上ほど新しい）

    api = escape(f"{context.base_url}/{PLUGIN_URLPATH}/comment", quote=True)
    page_val = escape(context.page, quote=True)

    # 送信できるのは JS が動く環境だけ（`_polling.NEEDS_JS`。技術資料「投稿はページ遷移なしで…」）
    off = polling.NEEDS_JS if postable else " disabled"
    name_field = ""
    if not noname:
        name_field = (
            f'<label for="comment-name-{part}">名前</label>'
            f'<input type="text" name="name" id="comment-name-{part}" size="15">'
        )
    note = "" if postable else (
        '<p class="comment-note">このコメント欄には、ここからは投稿できません'
        '（書かれているページを開いて投稿してください）。</p>')

    form_html = (
        f'<form class="comment-form" method="post" action="{api}">'
        f'<input type="hidden" name="page" value="{page_val}">'
        f'<input type="hidden" name="comment_id" value="{escape(comment_id or "", quote=True)}">'
        f'<input type="hidden" name="noname" value="{"1" if noname else "0"}">'
        f'<input type="hidden" name="nodate" value="{"1" if nodate else "0"}">'
        f'<input type="hidden" name="newtop" value="{"1" if new_at_top else "0"}">'
        f"{name_field}"
        f'<label for="comment-msg-{part}">コメント</label>'
        f'<input type="text" name="msg" id="comment-msg-{part}" required>'
        f'<button type="submit"{off}>投稿</button>'
        "</form>"
        f"{note}"
    )

    html = (
        '<fieldset class="comment-fieldset">'
        f'<legend>{escape(legend)}</legend>'
        f'{form_html}'
        '<hr class="comment-divider">'
        f'{body_text}'
        "</fieldset>"
    )
    return polling.wrap(html, context, "comment", comment_id)


def _date_call(stamp, ext):
    """投稿日時を `&new` で囲んだもの。Markdownでは丸括弧が要る（技術資料参照）。"""
    if is_pukiwiki(ext):
        return f"&new{{{stamp}}};"
    return f"&new(){{{stamp}}};"


def _format_comment(msg, head, name, noname, nodate, ext=".txt"):
    parts = [msg]
    if not noname:
        # 名前はリンクにせず、ただの文字列として書き足す（Wiki設計者の指示）
        display_name = name.strip() if name and name.strip() else ANONYMOUS
        parts.append("--")
        parts.append(display_name)
    # noname のときは "-- 名前" ごと丸ごと省く（Wiki設計者の指示。--区切りも
    # 名前とセットで消す）。日時は noname とは独立に nodate だけで決まる
    if not nodate:
        parts.append(_date_call(_now_str(datetime.datetime.now()), ext))
    body = " ".join(parts)
    return f"-{head} {body}".rstrip()


def _insert_comment(source, call, comment_line, new_at_top):
    """`source`の、`call`（`_polling.find_call`が見つけた呼び出し）の本体
    （`{{`〜`}}`の中）の先頭（`new_at_top`）または末尾に`comment_line`を挿す。
    本体（`{{ }}`）をまだ書いていない素の`#comment(...)`なら、エラーにせずその場で
    `{{`・`comment_line`・`}}`を書き足す（Wiki設計者の指示。技術資料「初期状態で
    {{ }}が無い場合」参照）。`#table`のセルの中なら、閉じ括弧の行にセルの残り（`|\\`
    など）を続ける（技術資料「#table のセルの中」）。閉じ括弧が無い、1行の`{…}`形式など
    想定外の書きかたなら (source, False) をそのまま返す。"""
    lines = source.split("\n")
    i, loc = call["line"], call["loc"]
    line = lines[i]
    tail = line[loc["tail"]:]
    in_cell = "|" in line[:loc["pos"]]
    # リストや引用の中に書かれていたら、本体の行もその字下げ（`>`）にそろえる。
    # `#table` のセルの中は、セルの区切りより後ろが中身なので字下げしない
    indent = "" if in_cell else re.sub(r"[^\s>]", " ", line[:loc["pos"]])
    fence_m = FENCE_TAIL_RE.fullmatch(tail)
    if fence_m:
        fence = fence_m.group(1)
        # セルの中では、閉じ括弧の行にセルの区切り（`|`）が続く
        close_re = re.compile(r"^[\s>]*\}{" + str(len(fence)) + r",}\s*(\|.*)?$")
        for j in range(i + 1, len(lines)):
            if close_re.match(lines[j]):
                lines.insert(i + 1 if new_at_top else j, indent + comment_line)
                return "\n".join(lines), True
        return source, False
    if not tail.strip():
        # {{ }}を書いていない素の呼びかた。ここで自動的に用意する
        # （newtop/newbottomのどちらでも、コメントが1件も無い
        # 状態への挿入なので結果は同じ）
        lines[i:i + 1] = [line.rstrip() + "{{", indent + comment_line, indent + "}}"]
        return "\n".join(lines), True
    if in_cell and tail.lstrip().startswith("|"):
        # `#table` のセルの中で、呼び出しの後ろに同じ行でセルの区切りが続く。
        # 呼び出しの直後で行を分け、閉じ括弧の行にセルの残りを続ける（閉じ括弧だけの行に
        # すると、外側の `#table(){{ … }}` の終わりと読まれるため）
        lines[i:i + 1] = [line[:loc["tail"]] + "{{", comment_line, "}}" + tail.lstrip()]
        return "\n".join(lines), True
    # 1行の{…}形式など、上記どちらにも当てはまらない想定外の書きかた
    return source, False


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

    msg = (request.forms.getunicode("msg", "") or "").replace("\r", "").replace("\n", "")
    head = ""
    m = HEAD_RE.match(msg)
    if m:
        head, msg = m.group(1), m.group(2)
    msg = msg.strip()

    # 成功は 204 だけ返し、画面の更新は comment.js・_polling.js が行う（技術資料
    # 「投稿はページ遷移なしで反映する」）
    if not msg:
        # 本家と同じく、書く内容が無ければ何もせず戻すだけ（エラーにしない）
        return HTTPResponse(status=204)

    name = request.forms.getunicode("name", "")
    noname = request.forms.get("noname") == "1"
    nodate = request.forms.get("nodate") == "1"
    new_at_top = request.forms.get("newtop") == "1"
    comment_id = (request.forms.getunicode("comment_id", "") or "").strip()

    # 閲覧の権限が無いページには書き込ませない（Wiki設計者の指示、2026-09-15）。
    # R のページは通す——プラグインによる書き換えはユーザの編集とは別に数え、
    # 未ログインでも止めない決まり（Tech/PagePermissions「決まったこと」）
    if context.privilege.check(pagepath) == PAGE_NONE:
        return plain("このページを閲覧する権限がありません。", status=403)

    ref = resolve_page_ref(context.wiki_dir, pagepath)
    if ref is None or not ref.exists:
        return plain("そのページはまだありません。", status=404)

    # フォームを開いてから本文が変わっていても断らない（技術資料「digest をやめた」）。
    # 書き込み先は ID で探す（重なっていれば最初のもの）
    source = ref.body or ""
    call, reason = polling.find_call(context, source, ref.ext, "comment", comment_id)
    if call is None:
        return plain(reason, status=409)
    comment_line = _format_comment(msg, head, name, noname, nodate, ref.ext)
    new_source, inserted = _insert_comment(source, call, comment_line, new_at_top)
    if not inserted:
        return plain(
            "コメントを追加する場所（#comment(){{ }}の本体）が見つかりません"
            "でした。本体の書きかたが正しいか確かめてください。",
            status=409)

    save_page(context.wiki_dir, context.config, ref.subpath, ref.ext, new_source)
    return HTTPResponse(status=204)
