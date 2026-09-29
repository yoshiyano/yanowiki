# ページ内の用語をtooltipで参照するプラグイン（要望）

#code()

wikiSystem 本体から wikiPlugin への実装依頼です。**2026-08-24に `glossarytip` プラグインとして
実装されました。** 使いかたは [glossarytipプラグイン](/Syntax/Plugin/glossarytip)、使用例は
[プラグイン開発で使える汎用関数](/Tech/dev_plugin/functions#共通する引数戻り値) にあります。

## 背景・動機

Markdown に[定義リスト](/Syntax/Markdown/Block#定義リスト)（`mdit_py_plugins.deflist`）を足したので、
`wiki_dir` のような用語を `<dl><dt>用語</dt><dd>説明</dd></dl>` として1か所で定義できます。
残っていたのは、その用語が本文の他の場所（関数シグネチャの中など）に出てきたとき、
マウスを乗せて説明を読めるようにすることです。

全ページに一律で効かせると、用語が一般的な単語と重なるページで誤爆します。使いたいページだけで
有効にしたいので、書けば効き、書かなければ何もしないプラグインの形にしました。

## 仕様

`#glossarytip()`（ブロック、引数なし）を書いたページだけで働きます。Python側は資材（JS・CSS）を
読み込ませるきっかけを作るだけで、処理はすべて `plugin/glossarytip.js` が行います。

1. 本文の `<dl>` から `<dt>`（用語）と `<dd>`（説明）の対応表を作る
2. `<dl>` 自身を除いた本文を走査し、用語と一致する語を tooltip にする
3. `<code>` の中も対象にする（`resolve_page_ref(wiki_dir, pagepath)` の `wiki_dir` を読めるようにするのが、もともとのきっかけ）

- 単語の境界を見て一致させる（`subpath` が `subpaths` の一部に一致しない）
- `<dt>`・`<dd>` の中や、すでに包んだ部分は対象外
- 大文字小文字は区別する（識別子のような語を想定しているため）

```pukiwiki
#glossarytip()

wiki_dir
: そのWikiの実体ディレクトリ（絶対パス）

`resolve_page_ref(wiki_dir, pagepath)` は、wiki_dirを受け取ります。
```
