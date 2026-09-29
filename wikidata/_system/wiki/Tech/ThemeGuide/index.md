# テーマの開発方法

テーマのテンプレートを書き換えて、ページ全体の構造そのものを変える方法です。
設定でできる範囲の変更は [見た目を変えよう](/ThemeGuide) をご覧ください。

テーマは [Jinja2](https://jinja.palletsprojects.com/) のテンプレートです。上から順に読むと全体像がつかめます。

1. [ファイル構成](/Tech/ThemeGuide/Files) — 3点セットと `common.css` / `common.js` の関係
2. [テンプレートで使える変数](/Tech/ThemeGuide/Variables)
3. [タイトルの描画](/Tech/ThemeGuide/Title)
4. [検索とページ内検索](/Tech/ThemeGuide/Search)
5. [ブロック](/Tech/ThemeGuide/Blocks) — 一部だけ差し替える方法
6. [新しいテーマを追加する](/Tech/ThemeGuide/NewTheme)
7. [同梱しているサンプルテーマ](/Tech/ThemeGuide/SampleThemes) — fresh・bloomの書きかたの違い
8. [自動エスケープについて](/Tech/ThemeGuide/Escaping)

## ページ一覧

#ls(sort=FNAME, format_md=TITLE)
