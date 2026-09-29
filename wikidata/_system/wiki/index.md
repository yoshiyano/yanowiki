# ようこそ

![wikiSystemのロゴ](logo.png)

PythonとbottleでつくられたちいさなWikiシステムのサンプルサイトです。

## はじめての方へ

- [入れかた・動かしかた](/InstallGuide) … 自分のパソコンで動かすまでの手順
- [使ってみよう](/UsageGuide) … ページの見かた、書きかた、名前のつけかた
- [書ける記法](/Syntax) … PukiWiki記法・Markdown記法と[プラグイン](/Syntax/Plugin)の書きかたと表示例
- [技術ドキュメント](/Tech) … 設計方針、テーマやプラグインのつくりかた、更新履歴

## このWikiシステムについて

### Wikiとして当たり前にできること

- Webブラウザから**編集**・ファイルを**添付**できます。誰でも編集できるWikiにも、
  ログインした人だけが編集できるWikiにもできます（[使ってみよう](/UsageGuide#ページを編集する)）
- サイト全体・ページ内を**検索**できます（[検索・マーカー](/SearchMarkerGuide)）

### wikiSystem独自の特徴

- **PukiWiki記法とMarkdown記法**をページごとに選べます（[書ける記法](/Syntax)）
- 1つのサーバーで**複数のWiki**を動かせます（[新しいWikiを作る](/NewWikiGuide)）
- 見た目（テーマ）を**自分でデザイン**できます（[見た目を変えよう](/ThemeGuide)）
- **プラグイン**で機能を拡張できます（[プラグイン](/Syntax/Plugin)）
- 登録した用語を、開いたどのページでも色付きで光らせる**マーカー**があります
  （[検索・マーカー](/SearchMarkerGuide)）
- 保存のたびに**差分で記録**され、見比べたり戻したりできます（[変更履歴](/BackupGuide)）
- **Linux**でも**Windows**でも動きます（常時公開するならLinux）。
  インストールは数コマンドで済みます（[入れかた・動かしかた](/InstallGuide)）

ソースコードは [GitHub](https://github.com/yoshiyano/yanowiki) で公開しています。

#note(type=warn){{
**この `_system` は配布元が管理するサンプルWikiです。** 直接編集しても、
更新（[`git pull` など](/InstallGuide#更新する)）で配布元の内容に戻ります。
自分のページは、`/.newwiki` で**別のWikiを作って**書いてください。
}}
