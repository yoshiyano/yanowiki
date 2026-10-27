# ようこそ

![wikiSystemのロゴ](logo.png)

PythonとbottleでつくられたちいさなWikiシステムのサンプルサイトです。

## はじめての方へ

- [インストールと起動](/InstallGuide) … 自分のパソコンで動かすまでの手順：**ダウンロードして起動だけでは途中状態です**
- [使ってみよう](/UsageGuide) … ページの閲覧・編集のしかた
- [書きかた](/Syntax) … PukiWiki記法・Markdown記法と[プラグイン](/Syntax/Plugin)の書きかたと表示例
- [管理者権限でできること](/AdminGuide) … ログイン後の管理ツールの使いかた
- [技術ドキュメント](/Tech) … 設計方針、テーマやプラグインのつくりかた
- [更新履歴](/ChangeLog) … バージョンごとの変更点

## このWikiシステムについて

### Wikiとして当たり前にできること

- Webブラウザから**編集**・ファイルを**添付**できます。誰でも編集できるWikiにも、
  ログインした人だけが編集できるWikiにもできます（[編集する](/UsageGuide/Edit)）
- サイト全体・ページ内を**検索**できます（[検索・マーカー](/SearchMarkerGuide)）

### wikiSystem独自の特徴

- **PukiWiki記法とMarkdown記法**をページごとに選べます（[書きかた](/Syntax)）
- 1つのサーバーで**複数のWiki**を動かせます（[Wiki Farm](/FarmGuide)）
- 見た目（テーマ）を**自分でデザイン**できます（[見た目を変えよう](/ThemeGuide)）。HTML に差し込む場所を書くだけの
  **スロット型のテーマ**も作れます（[スロット型のテーマでデザインを変える](/SlotThemeGuide)）
- **プラグイン**で機能を拡張できます（[プラグイン](/Syntax/Plugin)）
- 登録した用語を、開いたどのページでも色付きで光らせる**マーカー**があります
  （[検索・マーカー](/SearchMarkerGuide)）
- 保存のたびに**差分で記録**され、見比べたり戻したりできます（[変更履歴](/BackupGuide)）
- **見出しごとに、その場で編集**できます（[セクション編集](/UsageGuide/Edit/SectionEdit)）
- **手元のエディタ**（VS Code・Emacs・Neovim）で書いて、ブラウザでプレビューを見られます
  （[外部エディタ連動の編集](/PageEdit/EditorSyncGuide)）
- ページとフォルダを**ファイル一覧**で見て、名前の変更・移動・コピー・削除ができます（[ファイル操作](/FilesGuide)）
- **アカウントとアクセス制限**で、閲覧・編集できる人をページごとに決められます（[アクセス権とログイン](/AccessGuide)）
- 新しいバージョンが出ると管理者に知らせ、**画面から更新**できます（[公開版から更新する](/AdminGuide/Maintenance#公開版から更新する)）
- **Linux**でも**Windows**でも動きます（常時公開するならLinux）。
  インストールは数コマンドで済みます（[インストールと起動](/InstallGuide)）

ソースコードは [GitHub](https://github.com/yoshiyano/yanowiki) で公開しています。

#note(type=warn){{
**この `_system` は配布元が管理するサンプルWikiです。** 直接編集しても、
更新（[`git pull` など](/InstallGuide#更新する)）で配布元の内容に戻ります。
自分のページは、管理者メニューの「新しいWikiを作る」で**別のWikiを作って**書いてください（[手順](/InstallGuide)の8）。
}}
