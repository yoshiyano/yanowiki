# よくある使いかた

引数と中身だけでは完結しないプラグインが `context` を使う、同梱プラグインでの4つの型です。

## ページ・添付ファイルへの参照を解決する

```python
ref = resolve_page_ref(context.wiki_dir, context.page or "")
kind, target = resolve_link(ref.subpath, src, context.wiki_dir)
```

呼んでいるページから見て、相対的に書かれたファイル名がどこを指すかを解決します（`img`/`ref`/`ls`）。

## ページ全体・DB由来の情報を取得する（`need_outer_info`と組み合わせ）

```python
entries = context.page_headings(max_depth=resolved["depth"])
```

`contents` の例です。ページ全体の見出しのような外部の情報は `context` から取り、
[`need_outer_info`](/Tech/dev_plugin/plugin_info) を宣言します。

## 子ページを丸ごとレンダリングして埋め込む

```python
sub = PluginContext(config=context.config, farm=context.farm, wiki_dir=context.wiki_dir,
                     page=page, base_url=context.base_url, ext=ref.ext)
engine = build_markdown_renderer(context.config, farm_plugin_dir(context.wiki_dir), sub)
```

`include` や `ls` の折りたたみプレビューの例です。`page` を差し替えた別の `context` を作って渡すので、
埋め込まれたページの相対リンクは、そのページ自身を起点に解決されます。

描画したあとは `context.used_plugins |= sub.used_plugins` で合流させます。忘れると、埋め込まれたページで
使われたプラグインのCSS/JSが読み込まれません。

## 呼ばれたことそのものを記録に使う

```python
def _convert(resolved, body, context):
    return ""
```

`glossarytip` の例です。`_convert` は空文字列を返すだけで、目的は呼ばれた記録（`context.used_plugins`）です。
これで `plugin/glossarytip.js`/`.css` がそのページに読み込まれ、処理はブラウザ側が行います。呼ばなければ
資材ごと読み込まれないので、ページごとに機能をON/OFFできます。

`plugin_debug` も、`context` を書き換えるだけで何も表示しない使いかたです。1回の描画で同じ `context` が
使い回されることを利用して、後ろに書かれたプラグインの動作を変えます
（[ページの中だけ一時的に有効にする](/Tech/dev_plugin/spec/errors#ページの中だけ一時的に有効にするplugin_debug)）。
