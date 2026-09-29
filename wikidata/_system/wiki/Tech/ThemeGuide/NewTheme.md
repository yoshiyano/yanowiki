# 新しいテーマを追加する

`theme/` にファイルを追加し、設定で名前を指定するだけです。

```
theme/dark.html
theme/dark.css
theme/dark.js    （テーマ独自の動きがあるときだけ）
```

```yaml
theme:
  name: dark
```

CSS・JSを `{{ themefile }}.css` のように参照しておくと、名前を変えても一式が追従します。
必ず埋め込むもの（`common.css`/`common.js` の読み込み、`{{ version }}` の表示など）は
[ファイル構成](/Tech/ThemeGuide/Files)にあります。
