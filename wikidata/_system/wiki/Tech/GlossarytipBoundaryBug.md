# glossarytip.jsが日本語のみの用語をtooltip化しない不具合（報告）

wikiSystem 本体から wikiPlugin への不具合報告です。**2026-08-25に、下の修正案で
対応済みです**。

## 現象

「ページパス」のようにASCII文字を含まない用語を[定義リスト](/Syntax/Markdown/Block#定義リスト)で
定義しても、本文の該当箇所が `#glossarytip()` でtooltip化されませんでした
（`wiki_dir` のようなASCII名の用語は動いていました）。

## 原因

`plugin/glossarytip.js` が単語境界に `\b` を使っていました。`\b` は `[A-Za-z0-9_]` の
内外が切り替わる所でしか成立しないため、両側が日本語だと一致しません。

```js
new RegExp("\\b(?:ページパス)\\b").test("URLのページパスを求める")   // => false
```

## 修正

`\b…\b` を、ASCII語の文字を明示的に除く lookaround に置き換えました。ASCII語との
誤結合は防いだまま、日本語だけの用語にも一致します。

```js
new RegExp("(?<![A-Za-z0-9_])(?:ページパス)(?![A-Za-z0-9_])")
  .test("URLのページパスを求める")     // => true
new RegExp("(?<![A-Za-z0-9_])(?:ページパス)(?![A-Za-z0-9_])")
  .test("subpathのページパスXです")     // => false
```
