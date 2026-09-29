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

投稿済みのコメントは`{{ }}`（波括弧2つ、複数行）の本体に溜まります。
**書かなくてもかまいません**——`#comment()`のように本体を省略すると、
最初の投稿があったときにプラグイン自身が`{{ }}`を書き足します（エラーに
はしません）。

フォーム・区切り線・本体（コメント一覧）は1つの`<fieldset>`（見出しは
`<legend>`）にまとめて表示され、枠線で囲われます。フォーム自体には
枠線は付きません。

1つのページに`#comment()`を複数置くと、それぞれ別々にコメントを溜め
られます。

名前欄はブラウザのlocalStorageに前回使った値を覚えていて、次に開いた
ときの既定値として入れておきます（`comment.js`）。リンクは作りません
（ただの文字列として本文に書き足すだけです）。
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
   まとめて描く。隠しフィールドに、対象ページ（`page`）・このページ内で
   何番目の`#comment(...)`か（`comment_no`）・`noname`/`nodate`/`newtop`・
   **投稿時点の本文のハッシュ（`digest`）**を持たせる
2. 投稿されると`_action`が呼ばれ、`msg`（必須）・`name`（任意）を受け取り、
   コメント行を組み立てる
3. **そのページの現在の本文を読み直し**（フォームを開いてから他の人が
   編集したかもしれないので、投稿の直前に改めて読む）、`comment_no`
   番目の`#comment(...)`を探す。`{{ ... }}`が無ければ**その場で付け足し**、
   本体の先頭（`newtop`。**既定はこちら**）または末尾（`newbottom`）に
   コメント行を挿し込む
4. `wikilib.pagesave.save_page`で保存し、そのページの表示へ303リダイレクト
   する（フォームの2重送信を防ぐ、いつもの作法）

## `comment_no`（1ページに複数の#comment()があるとき）

本家は`static $numbers`（PHP、1リクエスト内で保持される連想配列）で
「このページで#commentが何回描かれたか」を数える。このシステムは
`build_markdown_renderer`のたびにプラグインが読み直されるためモジュール
直下の変数では持ち越せない（`ls.py`の`_action`・`include.py`の状態共有
と同じ制約）。ここでは`context`に直接カウンタを乗せる
（`context._comment_counters`、ページパスごとの辞書。`include.py`が
`PluginContext`にstateを乗せて手渡す設計と同じ考えかた）。

カウンタは`body is None`（本体をまだ書いていない`#comment()`）でも
**必ず増やす**（エラーにはしない。技術資料「初期状態で{{ }}が無い
場合」参照）。`_action`側の`_insert_comment`も本体の有無に関わらず
出現ごとに数を進めるため、両者の「何番目か」の数えかたは常に一致する。

## digest（投稿の競合検出）

`wikilib.editor.source_hash`（SHA256。編集画面の保存時の競合検出と
同じ関数）でdigestを作り、フォームを描いた時点の本文ハッシュとして
持たせる。

本家PukiWikiはdigestが食い違っていても（誰かが間に合わせて編集して
いても）警告を出しつつコメント自体は追加してしまうが、**このシステムは
食い違っていたら投稿を拒否する（コンフリクト扱い）**（Wiki設計者の指示）。
食い違っていたら409（`_insert_comment`が対象の本体を見つけられなかった
場合と同じステータス）で断り、投稿者に読み直してからやり直してもらう。
本家にあった「競合時の専用警告画面」（テーマのレンダリング一式を通す
必要がありスコープが大きい）は実装せず、簡素な断り文だけを返す。

digestが空（古いフォーム・外部からの直接POST等）のときは確かめようが
ないので素通しする（`editor.py`の`origin`/`sent_hash`チェックと同じ
考えかた）。

**なお、これで防げるのは「コメントを開いてから本文が変わっていた」
場合の食い違いだけ**であり、「編集画面を開いたまま一時中断し、その間に
コメントが増えたページを、中断から戻って保存する」という逆方向の
食い違いは、`_sys/wikilib/editor.py`側の一時中断／再開の設計（origin
再計算の穴）に関わる問題で、既にwikiSystem側で修正済み（2026-08-27、
`origin`をdraftと一緒に保存するようにした）。

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

## `#comment(...)`の探しかた・本体への差し込みかた

出現数を数える判定（`MARKER_RE`）は`^#comment\(`という緩い正規表現で、
本体の有無やフェンス記号の数に関わらず「`#comment(`で始まる行」を
すべて1つと数える（`_convert`側のカウンタと数を合わせるため。技術資料
「comment_no」参照）。

対象の行が見つかったら、3通りに分けて扱う。

1. **既に`{{ ... }}`本体がある**（`FENCE_OPEN_RE`——`#comment(...)`の
   直後に`{{`（2つ以上の`{`）だけを置いて終わっている行。
   `_sys/wikilib/plugins.py`の`PLUGIN_BLOCK_FENCE_RE`と同じ考えかた）。
   開き括弧と同じ数以上の`}`だけの行が現れるまでを本体として扱い
   （`plugin_block_rule`の`close_re`と同じロジック）、`newtop`ならその
   先頭に、`newbottom`ならその末尾にコメント行を追加する。
2. **本体を何も書いていない素の`#comment(...)`**（`BARE_RE`——閉じ括弧の
   直後に何も無く行が終わっている）。**この場合はエラーにせず、その場で
   `{{`・コメント行・`}}`の3行を書き足す**（Wiki設計者の指示。技術資料「初期
   状態で{{ }}が無い場合」参照）。newtop/newbottomの違いは、コメントが
   1件も無い状態への挿入なので結果は同じになる。
3. どちらにも当てはまらない（1行の`{…}`形式など、壊れた・想定外の
   書きかた）。差し込めないので`inserted=False`のまま呼び出し元へ返し、
   409（「コメントを追加する場所が見つかりませんでした」）にする。

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
（409）で必ず断られていた。`_insert_comment` に拡張子を渡し、PukiWiki記法では
`PUKI_*_RE`（丸括弧を省けるもの）で探して数える。Markdownでは丸括弧の無い
`#comment` は文字のまま出る（プラグインにならない）ので、これまでどおり数えない
（`comment_no` は描いた順の番号なので、数えかたを描画と合わせる必要がある）。

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

**投稿の差し込み・digest計算は`_convert`が受け取る`body`引数とは無関係**
（`_action`が`ref.body`＝ページの生ソースをディスクから読み直して処理する、
完全に独立した経路）で、この変更の影響を受けない。
"""

import datetime
import re
from html import escape

from bottle import HTTPResponse, request

from wikilib.auth import PAGE_NONE
from wikilib.editor import source_hash
from wikilib.pagedb import resolve_page_ref
from wikilib.pagesave import save_page
from wikilib.paths import PLUGIN_URLPATH, is_valid_pagepath
from wikilib.plugins import PluginArgumentError
from wikilib.render import is_pukiwiki
from wikilib.subst import _now_str
from wikilib.web import plain

DEFAULT_LEGEND = "コメント"

PLUGIN_INFO = {
    "help": "#comment(legend,noname,nodate,newtop,newbottom){{追加されたコメント}}",
    "expand_block": True,
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "legend", "num_order": 1, "default": DEFAULT_LEGEND, "label": "見出し"},
        {"name": "noname", "flag": True, "default": False, "label": "名前欄を隠す"},
        {"name": "nodate", "flag": True, "default": False, "label": "日時を付けない"},
        {"name": "newbottom", "flag": True, "default": False, "label": "下に追加"},
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
MARKER_RE = re.compile(r"^#comment\(")
FENCE_OPEN_RE = re.compile(r"^#comment\(.*\)(\{\{+)\s*$")
BARE_RE = re.compile(r"^#comment\(.*\)\s*$")
# PukiWiki記法は丸括弧の無い `#comment`・`#comment{{` もプラグインとして描く
# （本家の実データでいちばん多い書きかた）。Markdownでは文字のまま出るので数えない。
# 技術資料「丸括弧の無い #comment」
PUKI_MARKER_RE = re.compile(r"^#comment(?:\(|\{|\s*$)")
PUKI_FENCE_OPEN_RE = re.compile(r"^#comment(?:\(.*\))?\s*(\{\{+)\s*$")
PUKI_BARE_RE = re.compile(r"^#comment(?:\(.*\))?\s*$")
HEAD_RE = re.compile(r"^(-{1,2})-*\s*(.*)$")


def _convert(resolved, body, context):
    if not context.wiki_dir or context.page is None:
        raise PluginArgumentError("ページの場所が分かりません。")

    ref = resolve_page_ref(context.wiki_dir, context.page)
    if ref is None:
        raise PluginArgumentError("ページが見つかりません。")

    # 1ページに複数の#comment()があっても別々に数えられるよう、contextに
    # カウンタを乗せて持ち回す（build_markdown_rendererの呼び出し1回＝
    # 1回のページ描画の間だけ有効。詳しくは技術資料）。body無しでエラーに
    # なる場合も含め、出現するたびに必ず増やす（_action側の数えかたと
    # 一致させるため）。
    counters = getattr(context, "_comment_counters", None)
    if counters is None:
        counters = {}
        context._comment_counters = counters
    comment_no = counters.get(context.page, 0)
    counters[context.page] = comment_no + 1

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
    digest = source_hash(ref.body or "")

    api = escape(f"{context.base_url}/{PLUGIN_URLPATH}/comment", quote=True)
    page_val = escape(context.page, quote=True)

    name_field = ""
    if not noname:
        name_field = (
            f'<label for="comment-name-{comment_no}">名前</label>'
            f'<input type="text" name="name" id="comment-name-{comment_no}" size="15">'
        )

    form_html = (
        f'<form class="comment-form" method="post" action="{api}">'
        f'<input type="hidden" name="page" value="{page_val}">'
        f'<input type="hidden" name="comment_no" value="{comment_no}">'
        f'<input type="hidden" name="noname" value="{"1" if noname else "0"}">'
        f'<input type="hidden" name="nodate" value="{"1" if nodate else "0"}">'
        f'<input type="hidden" name="newtop" value="{"1" if new_at_top else "0"}">'
        f'<input type="hidden" name="digest" value="{digest}">'
        f"{name_field}"
        f'<label for="comment-msg-{comment_no}">コメント</label>'
        f'<input type="text" name="msg" id="comment-msg-{comment_no}" required>'
        '<button type="submit">投稿</button>'
        "</form>"
    )

    return (
        '<fieldset class="comment-fieldset">'
        f'<legend>{escape(legend)}</legend>'
        f'{form_html}'
        '<hr class="comment-divider">'
        f'{body_text}'
        "</fieldset>"
    )


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


def _insert_comment(source, comment_no, comment_line, new_at_top, ext=".md"):
    """`source`の`comment_no`番目の`#comment(...)`を探し、その本体
    （`{{`〜`}}`の中）の先頭（`new_at_top`）または末尾に`comment_line`を
    挿す。本体（`{{ }}`）をまだ書いていない素の`#comment(...)`なら、
    エラーにせずその場で`{{`・`comment_line`・`}}`を書き足す（Wiki設計者の
    指示。技術資料「初期状態で{{ }}が無い場合」参照）。対象が見つから
    ない、閉じ括弧が無い、1行の`{…}`形式など想定外の書きかたの、
    いずれかなら (source, False) をそのまま返す。"""
    if is_pukiwiki(ext):
        marker_re, fence_open_re, bare_re = PUKI_MARKER_RE, PUKI_FENCE_OPEN_RE, PUKI_BARE_RE
    else:
        marker_re, fence_open_re, bare_re = MARKER_RE, FENCE_OPEN_RE, BARE_RE
    lines = source.split("\n")
    out = []
    count = 0
    inserted = False
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if marker_re.match(line) and count == comment_no and not inserted:
            fence_m = fence_open_re.match(line)
            if fence_m:
                fence = fence_m.group(1)
                close_re = re.compile(r"^\}{" + str(len(fence)) + r",}\s*$")
                j = i + 1
                inner = []
                close_idx = None
                while j < n:
                    if close_re.match(lines[j]):
                        close_idx = j
                        break
                    inner.append(lines[j])
                    j += 1
                if close_idx is not None:
                    inner = [comment_line] + inner if new_at_top else inner + [comment_line]
                    out.append(line)
                    out.extend(inner)
                    out.append(lines[close_idx])
                    i = close_idx + 1
                    count += 1
                    inserted = True
                    continue
            elif bare_re.match(line):
                # {{ }}を書いていない素の呼びかた。ここで自動的に用意する
                # （newtop/newbottomのどちらでも、コメントが1件も無い
                # 状態への挿入なので結果は同じ）
                out.append(line.rstrip() + "{{")
                out.append(comment_line)
                out.append("}}")
                i += 1
                count += 1
                inserted = True
                continue
            # 1行の{…}形式など、上記どちらにも当てはまらない想定外の
            # 書きかた。差し込めないのでそのまま出力して次へ進む。
            out.append(line)
            count += 1
            i += 1
            continue
        if marker_re.match(line):
            count += 1
        out.append(line)
        i += 1
    return "\n".join(out), inserted


def _action(context):
    pagepath = (request.forms.getunicode("page", "") or "").strip("/")
    if pagepath and not is_valid_pagepath(pagepath):
        return plain("ページの指定が正しくありません。", status=400)

    msg = (request.forms.getunicode("msg", "") or "").replace("\r", "").replace("\n", "")
    head = ""
    m = HEAD_RE.match(msg)
    if m:
        head, msg = m.group(1), m.group(2)
    msg = msg.strip()

    redirect_to = context.base_url + "/" + pagepath

    if not msg:
        # 本家と同じく、書く内容が無ければ何もせず戻すだけ（エラーにしない）
        return HTTPResponse(status=303, headers={"Location": redirect_to})

    name = request.forms.getunicode("name", "")
    noname = request.forms.get("noname") == "1"
    nodate = request.forms.get("nodate") == "1"
    new_at_top = request.forms.get("newtop") == "1"
    digest = request.forms.get("digest", "")
    try:
        comment_no = int(request.forms.get("comment_no", "0"))
    except ValueError:
        comment_no = 0

    # 閲覧の権限が無いページには書き込ませない（Wiki設計者の指示、2026-09-15）。
    # R のページは通す——プラグインによる書き換えはユーザの編集とは別に数え、
    # 未ログインでも止めない決まり（Tech/PagePermissions「決まったこと」）
    if context.privilege.check(pagepath) == PAGE_NONE:
        return plain("このページを閲覧する権限がありません。", status=403)

    ref = resolve_page_ref(context.wiki_dir, pagepath)
    if ref is None or not ref.exists:
        return plain("そのページはまだありません。", status=404)

    # コンフリクト検出（Wiki設計者の指示）。フォームを開いてから本文が変わって
    # いたら、comment_no（何番目の#comment(...)か）の勘定がずれている
    # かもしれないので、本家PukiWikiと違い黙って続行せず投稿を拒否する。
    # digestが空（古いフォーム・外部からの直接POST等）のときは確かめようが
    # ないので、その場合は素通しする（editor.pyのorigin/sent_hashチェックと
    # 同じ考えかた）。
    if digest and digest != source_hash(ref.body or ""):
        return plain(
            "コメントフォームを開いてから、このページは別の場所で更新されて"
            "います。ページを読み直してから、もう一度コメントを投稿して"
            "ください。",
            status=409)

    comment_line = _format_comment(msg, head, name, noname, nodate, ref.ext)
    new_source, inserted = _insert_comment(ref.body or "", comment_no, comment_line, new_at_top,
                                           ref.ext)
    if not inserted:
        return plain(
            "コメントを追加する場所（#comment(){{ }}の本体）が見つかりません"
            "でした。ページが編集されて位置がずれた可能性があります。",
            status=409)

    save_page(context.wiki_dir, context.config, ref.subpath, ref.ext, new_source)

    return HTTPResponse(status=303, headers={"Location": redirect_to})
