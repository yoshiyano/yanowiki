"""別のページの本文を描いて差し込む処理（`include`・`pagediv` の共有モジュール）。

`_` で始まるのでプラグインとしては読み込まれない。使う側は自分の `__file__` の
隣を `importlib.util.spec_from_file_location` で呼び出しのたびに読み込む
（`readauth.py` の `_load_common` と同じ。`sys.modules` に置かないのは、置くと
このファイルを直してもサーバーを再起動するまで反映されないため）。

    lookup(context, page)            → (状態, ref)。状態は "ok" / "forbidden" / "missing"
    render(context, page, ref, ...)  → 差し込むHTML（本文のみ。見出しは付けない）
    state(context)                   → 差し込み済みのページの記録（無ければ作る）
    title_html(context, page)        → ページ名の見出し（編集できれば編集ボタン）

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

from wikilib.auth import PAGE_NONE, PAGE_WRITE
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
    return f'<a href="/{escape(page)}">{escape(page)}</a>'


def title_html(context, page, ref=None):
    """ページ名の見出しの中身。閲覧者がそのページを編集できるなら、そのページへ
    `cmd=edit` をPOSTする `<form>`＋`<button>`（GETのリンクにしないのは、URLだけで
    編集画面を開けないようにするため）、そうでなければ閲覧のリンク。

    編集できるかは、`ref` を渡せばその `privilege`、渡さなければ（`include`）
    `context.privilege.check(page)` で見る（入口は権限で出し分ける）。

    **フォームの `action` には自分で `context.base_url`（`/=Wiki名` や設置場所の
    接頭辞）を付ける。** ページの `href`・`src` は描画の後段
    （`render.rewrite_content_links`）が入口を補うが、`action` は補わない。
    付け忘れると、既定のWiki以外で見出しを押したとき、既定のWikiの同じ名前の
    ページへ送られていた（2026-09-25、`pagediv` で発覚。`include` も同じ）。"""
    if ref is not None:
        editable = getattr(ref, "privilege", PAGE_WRITE) == PAGE_WRITE
    else:
        editable = context.privilege.check(page.strip("/")) == PAGE_WRITE
    if editable:
        return (
            f'<form method="post" action="{escape(f"{context.base_url}/{urlquote(page)}")}">'
            '<input type="hidden" name="cmd" value="edit">'
            f'<button type="submit">{escape(page)}</button>'
            "</form>"
        )
    return read_link(page)
