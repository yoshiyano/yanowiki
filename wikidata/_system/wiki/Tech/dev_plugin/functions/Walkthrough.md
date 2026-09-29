# 実例: PukiWiki記法のテキストがHTMLになるまで

リクエスト1回分の流れです。記法で分岐するのはトークン列を作るところだけで、その先は共通です。

## 1. ページ取得（`views.render_page`）

```python
ref = pagedb.published_ref(wiki_dir, pagepath)   # 公開済みの本文(ref.body)と拡張子(ref.ext)
return themes.render_with_theme(
    wiki_dir, config, farm, pagepath, ref.body, explicit_farm, ref.subpath, ref.ext,
    source_path=ref.path)
```

`published_ref`が返す`ref.ext`が`.txt`なら、これ以降ずっとPukiWiki記法として扱われます。

## 2. レンダラーの用意とparse_source（`themes.render_with_theme`）

```python
engine = plugins.build_markdown_renderer(config, farm_plugin_dir, context)
content, title, toc = render.render_source(
    engine, body, ext, first_h1_as_title, context, toc_depth=3)
```

`render_source`の中身は`parse_source` → `split_title` → `build_toc` →
`engine.renderer.render`の4段です。**`parse_source`だけが記法で分岐**します。

```python
# render.parse_source(engine, text, ext, env)
if is_pukiwiki(ext):      # ext == ".txt"
    return pukiwiki.parse(text, extra_rules, interwiki, wikiname, allow_html)
else:
    return engine.parse(text, env)   # Markdown側はengineがそのまま処理
```

## 3. 具体的なデータで見る

次のPukiWiki記法のテキストを例にします。

```pukiwiki
* サンプル

これは ''強調'' を含む本文です。

#glossarytip()
```

`pukiwiki.parse()` は `parse_blocks(lines, 0)` で行を1行ずつ振り分け（見出しは `append_heading`、地の文は
`append_tight_paragraph` → `inline_token` → `parse_inline`、リストは `_ListContainerNode`/`_ListElementNode`、
プラグインは `append_plugin_block`）、最後に `assign_heading_ids` で見出しにidを振り、`append_annotations` で
`((…))` を脚注にします。

`parse_source(engine, text, ".txt", env)`が返すトークン列（実際の出力。
`t.type`・`t.tag`・`t.meta`のみ抜粋）:

```
heading_open  'h2'                                                map=[0, 1]
inline        children=[text]                                     （見出しの中身）
heading_close 'h2'
paragraph_open 'p'                                                 map=[2, 3]
inline        children=[text, strong_open, text, strong_close, text]
paragraph_close 'p'
plugin_block  'div'  meta={'name': 'glossarytip', 'args': '', 'body': None}
```

`*` は h2（`**` は h3、`***` は h4。h1 はページタイトル用）です。`#glossarytip()` は、Markdown側の
`plugin_block_rule` が作るのと同じ形の `plugin_block` トークンになります。

`engine.renderer.render(tokens, engine.options, env)`が返すHTML:

```html
<h2 id="サンプル">サンプル</h2>
<p>これは <strong>強調</strong> を含む本文です。</p>
```

`plugin_block` トークンでは、`plugins.register_plugin_rules` が登録した描画規則（`call_plugin`）が
`glossarytip` の `_convert` を呼びます。出力は空なのでHTMLに跡は残らず、`context.used_plugins` に記録されます。

`render_source`全体の戻り値（`(html, title, toc)`）はこうなります。

```python
title == None    # PukiWikiは先頭h1をタイトル抽出しない（ページ名がタイトルのため）
toc == [{"level": 1, "id": "サンプル", "title": "サンプル"}]
html == '<h2 id="サンプル">サンプル</h2>\n<p>これは <strong>強調</strong> を含む本文です。</p>\n'
```

## 4. テーマへの組み込みと応答（`themes.render_with_theme` → `render_theme`）

```python
return themes.render_theme(engine, wiki_dir, config, farm, pagepath, title, content, ...)
# content（HTML文字列）は Markup() 済みで Jinja2 テンプレートの {{ content }} にそのまま入る
```

ここから先はHTTPレスポンスとして返されるだけです。

## 5. 呼び出し木で俯瞰する

呼び出し関係の木です。子を持つ関数はクリックで開閉できます。`>>` の色は階層の深さ（奇数が赤、偶数が緑）です。

#html(all){{
<style>
.callflow {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  overflow-x: auto;
  font-family: ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--fg);
}
.callflow pre { margin: 0; white-space: pre; }
.callflow details { margin: 0; }
.callflow summary {
  cursor: pointer;
  color: var(--fg);
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  white-space: pre;
  list-style: none;
}
.callflow summary::-webkit-details-marker { display: none; }
.callflow summary::after { content: " \25B6"; color: var(--accent); font-weight: 600; }
.callflow details[open] > summary::after { content: " \25BC"; }
.callflow summary:hover { background: var(--code-bg); }
.callflow .d-red { color: #b3413f; font-weight: 700; }
.callflow .d-green { color: #3f6e5c; font-weight: 700; }
@media (prefers-color-scheme: dark) {
  .callflow .d-red { color: #e08585; }
  .callflow .d-green { color: #6fb79b; }
}
</style>
<div class="callflow">
<pre><span class="d-red">&gt;&gt;</span> views.render_page(wiki_dir, pagepath) → HTTPレスポンス
   リクエスト1回分のエントリ</pre>
<details class="ascii-details">
<summary>... 3件の呼び出しを見る ...</summary>
<pre>  <span class="d-green">&gt;&gt;</span> pagedb.published_ref(wiki_dir, pagepath) → ref (.body, .ext)
     DBから公開済みの本文を取得
  <span class="d-green">&gt;&gt;</span> themes.render_with_theme(body, ext, ...) → HTTPレスポンス
     レンダラーの用意〜応答までをまとめて行う</pre>
<details class="ascii-details">
<summary>  ... 2件の呼び出しを見る ...</summary>
<pre>    <span class="d-red">&gt;&gt;</span> plugins.build_markdown_renderer(config, ...) → engine
       MarkdownItを組み立てる（両記法で共有）
    <span class="d-red">&gt;&gt;</span> render.render_source(engine, body, ext, ...) → (html, title, toc)
       parse → タイトル抽出 → 目次 → HTML化をまとめて行う</pre>
<details class="ascii-details">
<summary>    ... 4件の呼び出しを見る ...</summary>
<pre>      <span class="d-green">&gt;&gt;</span> render.parse_source(engine, text, ext, env) → tokens
         拡張子で記法ごとのparserに振り分ける</pre>
<details class="ascii-details">
<summary>      ... 2件の呼び出しを見る ...</summary>
<pre>        <span class="d-red">&gt;&gt;</span> [.txt] pukiwiki.parse(text, extra_rules, ...) → tokens
           PukiWiki文法の処理</pre>
<details class="ascii-details">
<summary>        ... 3件の呼び出しを見る ...</summary>
<pre>          <span class="d-green">&gt;&gt;</span> parse_blocks(lines, 0) → tokens
             行を1行ずつ「挿入カーソル」方式で振り分ける</pre>
<details class="ascii-details">
<summary>          ... 4件の呼び出しを見る ...</summary>
<pre>            <span class="d-red">&gt;&gt;</span> append_heading → なし
               見出し行（"* 見出し"）をtokensに追記
            <span class="d-red">&gt;&gt;</span> append_tight_paragraph → なし
               地の文（&amp;name(); も検出）をtokensに追記</pre>
<details class="ascii-details">
<summary>            ... 1件の呼び出しを見る ...</summary>
<pre>              <span class="d-green">&gt;&gt;</span> inline_token → inlineトークン
                 内部でparse_inlineを呼ぶ。強調・リンク・プラグイン呼び出しを検出</pre>
</details>
<pre>            <span class="d-red">&gt;&gt;</span> append_plugin_block → なし
               "#name(...)" をtokensに追記
            <span class="d-red">&gt;&gt;</span> _ListContainerNode / _ListElementNode → なし
               箇条書きの入れ子をtokensに追記</pre>
</details>
<pre>          <span class="d-green">&gt;&gt;</span> assign_heading_ids(tokens) → なし
             見出しにidを振る（tokensを書き換え）
          <span class="d-green">&gt;&gt;</span> append_annotations(tokens) → なし
             "((...))" を脚注トークンに変換（tokensを書き換え）</pre>
</details>
<pre>        <span class="d-red">&gt;&gt;</span> [else] engine.parse(text, env) → tokens
           Markdown文法の処理</pre>
</details>
<pre>      <span class="d-green">&gt;&gt;</span> render.split_title(tokens, ...) → (title, tokens)
         先頭h1をタイトルとして抜き出す
      <span class="d-green">&gt;&gt;</span> render.build_toc(tokens, toc_depth) → toc
         見出しトークンから目次データを組み立てる
      <span class="d-green">&gt;&gt;</span> engine.renderer.render(tokens, ...) → html
         トークン列をHTML文字列にする</pre>
<details class="ascii-details">
<summary>      ... 1件の呼び出しを見る ...</summary>
<pre>        <span class="d-red">&gt;&gt;</span> plugins.call_plugin(context, name, args, ...) → HTML文字列
           plugin_block/plugin_inlineトークンでプラグインを実行</pre>
</details>
</details>
</details>
<pre>  <span class="d-green">&gt;&gt;</span> themes.render_theme(engine, ..., content=html) → HTTPレスポンス
     HTML文字列をテーマのテンプレートに差し込む</pre>
</details>
</div>
}}
