"""include — 別のページの本文をそのままこのページに差し込むプラグイン。

    #include(ページ名)                そのページの本文をここに差し込む（見出しつき）
    #include(ページ名, notitle)       見出し（ページ名＋編集リンク）を付けない
    #include(ページ名, title)         見出しつき（省略時と同じ）

 1. **page** … 差し込むページ名
       "/" 始まり・裸の名前はどちらもwikiの先頭からの絶対
       （本家PukiWikiと同じ決まり。隣ではない）
       "./" はいまのページの下、"../" は1つ上
 2. title    … 見出しの有無 (default: title)
       指定外の値を書いても既定（title）として扱われます

差し込んだ先のページがさらに`#include`を持っていれば、そちらも辿って
差し込みます（入れ子OK）。ただし次の場合はページの中身の代わりに案内を
表示します。

- 一度差し込んだページ（自分自身を含む）をもう一度差し込もうとした
  （無限ループを防ぐため）
- 指定したページを閲覧する権限が無い
- 指定したページが存在しない
- 1ページあたりに差し込めるページ数（12）を超えた
"""

""" 技術資料
本家PukiWikiは `static $included` / `static $count` （PHPのstatic変数、
1リクエスト内で状態を持ち越す）で「差し込み済みのページ」と「差し込んだ
件数」を管理し、`convert_html()` を再帰呼び出しすることで入れ子の
`#include` にも対応している。

この移植先では `build_markdown_renderer` を呼ぶたびに（`plugin/ls.py` の
`_action` と同様）プラグインファイルが `importlib` で毎回読み直され、
モジュール直下のグローバル変数は次の呼び出しまで残らない
（`Tech/PluginGuide#_setupの呼ばれかた` 参照）。そのため static 変数の
代わりに、**PluginContext に state（{"included": set, "count": int}）を
乗せて手渡しする**ことで、入れ子の `#include` をまたいで状態を共有する。

- 一番外側の呼び出し（`context` にまだ state が無い）で state を作り、
  自分自身のページ名を `included` に入れておく（自己再帰の防止。本家の
  `$included[$root] = TRUE` に相当）。
- 差し込む先のページを描画するための `PluginContext`（`sub`）を作るとき、
  同じ state オブジェクト（参照）を `sub._include_state` に乗せる。
  `sub` の中でさらに `#include` が呼ばれれば、そちらも同じ state を見つけて
  使い回す（新しく作り直さない）。

本家の `$menubar`（サイドメニューは差し込み対象から除外・特別な見た目にする
特殊扱い）は移植していない。このシステムのメニュー（mainmenu/submenu）は
`wikilib.themes` が本文とは別経路でレンダリングしており、ページ本文の
`#include` 処理と交わることが無いため。

2026-09-25、`pagediv` を作るときに、差し込み先を描く部分（下の`sub`の作りかた・
表示を止めたページ・リンクの付け替え・資材の合流）と見出しを兄弟の共有モジュール
`_embedpage.py` に切り出した（件数の上限`MAX_INCLUDES`はinclude固有の決まりなので
ここに残した。`pagediv`には件数の上限が無い）。以下の説明の実装はそちらにある。

## 件数の上限（2026-09-25、4 → 12）

本家の `PLUGIN_INCLUDE_MAX` の既定値4を引き継いでいたが、Wiki設計者の指示で12に
広げた。数えかたは変えていない——入れ子の先で差し込んだ分も含めて、1回の描画で
差し込んだページの合計（`_include_state["count"]`）。この上限は、差し込みが
連鎖して描画が重くなりすぎるのを抑えるためのもので、無限ループは件数ではなく
「差し込み済み」の記録で止めている。4では、目次ページに章をまとめて差し込む
ような使いかたですぐに足りなくなる一方、12でも1ページの描画が1回あたり高々
12ページ分増えるだけなので、安全側の目的は保てると考える。

本家の `check_readable`（読み取り制限）に当たるものは、`published_ref` が返す
`ref.privilege` で見る（下の「閲覧の権限が無いページ」参照）。

差し込んだページの見出し（`first_h1_as_title` によるタイトル抽出）・
添付ファイルの裸のファイル名（`rewrite_content_links`）・使われた
プラグインのCSS/JS読み込み（`context.used_plugins`）は、差し込み先の
ページ自身の subpath を基準に解決する必要がある。`plugin/ls.py` の
`_action`（ajax読み込み）が同じ問題を解いているので、その実装をそのまま
下敷きにした（`sub.used_plugins` を最後に `context.used_plugins` へ
合流させる一手間だけが `ls.py` には無い。あちらは非同期の別レスポンス
として返すので、埋め込み先の本文が使うプラグイン資材と混ざる必要が無い）。

「差し込み済み」「そのページは無い」「上限超過」は、本家PukiWikiでも
例外ではなく通常の戻り値（プラグインの正常な出力）として扱われている。
これに倣い、`PluginArgumentError` は使わず（使い方の誤りではないため）、
そのまま案内文のHTMLを返す。

## 差し込み先が表示を止めている場合（2026-09-05、wikiPluginの誤りを訂正）

`#viewable_period` のように `wikilib.plugins.PluginContext.block_view` で
表示を止めているページを `#include` すると、当初は**制限が効かないまま
本文がそのまま取り込み元に出てしまっていた**（`sub._convert` 側は
`block_view` を呼んでも戻り値は空文字列のままで、`render_source` が返す
`html` には制限前の本文がそのまま入るため。Wiki設計者に指摘され、
`_convert` の実装を読み直して発見した）。

`html, _, _ = render_source(...)` の直後に `sub.view_block` を見て、立って
いれば `html` を `sub.view_block["message"]`（差し込み先ページ自身が書いた
期間外メッセージ）に差し替えるだけで直る。**取り込み元のページ全体を
止める必要は無く**（`context.view_block` には触れない。取り込み元は普通に
表示され、差し込まれた場所にだけ「表示できません」が出る）、`sub` を作る
側から見て**別の `PluginContext`（`sub`）が既に `view_block` を立てて
くれている**ので、`include` 側は読むだけでよい（Wiki設計者の方針、2026-09-05）。

差し替えた `html`（差し込み先が組み立てた固定のHTML）には
`rewrite_content_links` を通さない。差し込み先ページの添付ファイルへの
相対リンクを含む前提が無い案内文に対して機械的なリンク書き換えをかける
理由が無いため。

`title` 見出し（ページ名＋編集リンク）はこの制限と無関係にそのまま出す
（Wiki設計者の方針: 見出しはDBのタイトルで本文由来ではないため、基本的に本文が
見えなければ十分という判断）。

## 閲覧の権限が無いページ（2026-09-15、Wiki設計者の指示）

`published_ref` は、いまの閲覧者のアクセス権を `ref.privilege`（`W`/`R`/`-`）に
入れて返す。**`-` でも `ref.body` には本文が入っている**ので、変換する前に見て、
`-` なら本文の代わりに「このページを閲覧する権限がありません: ページ名」を出す。
見出し（ページ名＋編集リンク）も付けない。

在るかどうかより先に見る（ページの表示 `views.render_page` と同じ順）。差し込み
件数にも数えない（本文を差し込んでいないため）。取り込み元のページ全体は止めない
——`block_view` のときと同じく、差し込んだ場所にだけ案内が出る。
"""
import importlib.util
import os
from html import escape

from wikilib.paths import full_pagepath
from wikilib.plugins import PluginArgumentError

# 本家PukiWikiの PLUGIN_INCLUDE_MAX（既定4）から、Wiki設計者の指示で12に広げた（2026-09-25）
MAX_INCLUDES = 12

PLUGIN_INFO = {
    "help": "#include(page,title)",
    "args": [
        {"name": "page", "link": True},
        {"name": "title", "default": "title"},
    ],
}


def _load_embed():
    """兄弟の`_embedpage.py`（`pagediv`と共有）を読み込む（呼び出しごと。
    理由は`_embedpage.py`の docstring）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_embedpage.py")
    spec = importlib.util.spec_from_file_location("wikiplugin__embedpage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _strip_bracket(raw):
    """`[[ページ名]]` の外側の角括弧を外す。本家 strip_bracket() と同じ
    （必須ではないが互換のため。array_shift($args) の直後で呼ばれていた）。"""
    if raw.startswith("[[") and raw.endswith("]]"):
        return raw[2:-2]
    return raw


def _with_title(resolved):
    """選べる値（title/notitle）に無い値は、エラーにせず黙って既定（title）にする。"""
    return (resolved["title"] or "").strip().lower() != "notitle"


def _convert(resolved, body, context):
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")

    embed = _load_embed()
    state = embed.state(context)
    page = full_pagepath(context.page or "", _strip_bracket(resolved["page"]))

    if page in state["included"]:
        return f'<div class="include-notice">既に差し込み済みのページです: {embed.read_link(page)}</div>\n'

    status, ref = embed.lookup(context, page)
    if status == "forbidden":
        # 本文は ref に入っているが出さない（技術資料「閲覧の権限が無いページ」）
        return f'<div class="include-notice">このページを閲覧する権限がありません: {escape(page)}</div>\n'
    if status == "missing":
        return f'<div class="include-notice">このページはまだありません: {escape(page)}</div>\n'

    if state["count"] > MAX_INCLUDES:
        return (f'<div class="include-notice">差し込めるページ数の上限'
                f'（{MAX_INCLUDES}件）を超えました: {embed.read_link(page)}</div>\n')
    state["count"] += 1
    state["included"].add(page)

    # 差し込み先を基準にした解決・表示を止めたページ・資材の合流は
    # `_embedpage.render`（技術資料「差し込み先が表示を止めている場合」参照）
    html = embed.render(context, page, ref, state)

    if not _with_title(resolved):
        return f'{html}\n'
    return f'<h1 class="include-title">{embed.title_html(context, page)}</h1>\n{html}\n'
