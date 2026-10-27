"""別のページの本文を描いて差し込む処理（`include`・`pagediv` の共有モジュール）。

`PLUGIN_INFO` を持たないので、プラグインとしては登録されない（`#include_` とは書けない）。
`pagediv` は `include` から分かれたものなので、名前は `include` の塊に揃えた。
使う側は自分の `__file__` の
隣を `importlib.util.spec_from_file_location` で呼び出しのたびに読み込む
（`readauth.py` の `_load_common` と同じ。`sys.modules` に置かないのは、置くと
このファイルを直してもサーバーを再起動するまで反映されないため）。

    lookup(context, page)            → (状態, ref)。状態は "ok" / "forbidden" / "missing"
    render(context, page, ref, ...)  → 差し込むHTML（本文のみ。見出しは付けない）
    state(context)                   → 差し込み済みのページの記録（無ければ作る）
    read_link(page)                  → ページ名の閲覧リンク（見出し・案内文）

**差し込める件数の上限や入れ子の深さといった決まりは持たない**（`include` は
12件まで、`pagediv` は件数を問わず入れ子3段まで、と決まりがプラグインごとに違う
ため）。持つのは、どのプラグインから差し込んでも同じでなければならない部分——
閲覧の権限・表示を止めたページ・添付ファイルへのリンク・資材の合流——だけ。
2026-09-25、`pagediv` を作るときに `include.py` から切り出した（`include` の
出力は切り出しの前後で変わらないことを確かめた）。

差し込み済みのページの記録（`context._include_state`）は `include` と `pagediv` で
**同じもの**を使う。`#pagediv` のセルに置いたページが `#include` で元のページを
取り込み返す、のような、2つのプラグインをまたぐ無限ループも止めるため。
"""

from html import escape
from urllib.parse import quote as urlquote

from wikilib.auth import PAGE_NONE
from wikilib.pagedb import published_ref
from wikilib.paths import farm_plugin_dir
from wikilib.plugins import PluginContext, build_markdown_renderer
from wikilib.render import render_source, rewrite_content_links


def state(context):
    """差し込み済みのページと件数の記録。一番外側の呼び出しで作り、自分自身の
    ページ名を入れておく（自己再帰の防止。本家 include の `$included[$root]`）。
    差し込み先を描く `sub` には同じもの（参照）を渡すので、入れ子をまたいで共有される。"""
    st = getattr(context, "_include_state", None)
    if st is None:
        st = {"included": {context.page or ""}, "count": 1}
        context._include_state = st
    return st


def lookup(context, page):
    """差し込むページを探す。(状態, ref) を返す。

    閲覧の権限は在るかどうかより先に見る（ページの表示 `views.render_page` と同じ順。
    `-` でも `ref.body` には本文が入っているので、呼ぶ側は "forbidden" なら出さない）。"""
    ref = published_ref(context.wiki_dir, page)
    if ref is not None and ref.privilege == PAGE_NONE:
        return "forbidden", ref
    if ref is None or not ref.exists:
        return "missing", ref
    return "ok", ref


def render(context, page, ref, st, sub_attrs=None):
    """ページ `page`（`lookup` が "ok" を返したもの）の本文をHTMLにする。

    `sub_attrs` は差し込み先を描く `PluginContext`（`sub`）に乗せたい属性
    （`pagediv` の入れ子の深さなど）。`st` は `state()` の記録で、`sub` へ渡す。

    - 見出し・添付ファイルの裸の名前・プラグインの資材は、差し込み先のページ
      自身を基準に解決する（`page` だけ差し替えた別の `PluginContext` で描く）
    - 差し込み先が `block_view`（`#viewable_period` 等）で表示を止めていたら、
      本文の代わりに差し込み先自身が書いた案内文を出す（案内文には
      `rewrite_content_links` を通さない）
    - `sub.used_plugins` を `context.used_plugins` へ合流させる（忘れると
      差し込んだページのプラグインのCSS/JSが読み込まれない）"""
    sub = PluginContext(config=context.config, farm=context.farm, wiki_dir=context.wiki_dir,
                        page=page, base_url=context.base_url, ext=ref.ext)
    sub._include_state = st
    for key, value in (sub_attrs or {}).items():
        setattr(sub, key, value)
    engine = build_markdown_renderer(context.config, farm_plugin_dir(context.wiki_dir), sub)
    md_conf = (context.config or {}).get("markdown") or {}
    html, _, _ = render_source(engine, ref.body, ref.ext,
                               md_conf.get("first_h1_as_title", True), sub)
    if sub.view_block:
        html = sub.view_block["message"]
    else:
        html = rewrite_content_links(html, context.base_url, ref.subpath, context.wiki_dir)
    context.used_plugins |= sub.used_plugins
    return html


def read_link(page):
    """ページ `page` を開く閲覧のリンク（`include`・`pagediv` の見出しと、案内文）。

    見出しに編集ボタンは持たない（編集の入口はページ自身のヘッダにある。
    2026-10-12、Wiki設計者の指示で `include`・`pagediv` とも閲覧のリンクだけにした。
    それまでの編集ボタン `title_html` は、呼び出し元がなくなったので削除した）。

    **`href` はURLエンコードする。** ページ名には `#`・`?`・`%` や空白が使える
    ため、そのまま書くと `C#入門` が `C` のページ（`#入門` は断片）、`Q?A` が
    クエリ、`100%` が不正なエスケープになる。入口（`/=Wiki名`）は描画の後段
    （`render.rewrite_content_links`）が補う。エンコード済みでも補われることは
    確かめてある（2026-10-12）。"""
    return f'<a href="/{escape(urlquote(page))}">{escape(page)}</a>'
