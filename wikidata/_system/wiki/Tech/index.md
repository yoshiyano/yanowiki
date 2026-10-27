# 技術ドキュメント

このWikiシステムの仕組みと、カスタマイズ・開発のための資料です。使いかたは
[使ってみよう](/UsageGuide)、書きかたは [書きかた](/Syntax) にあります。

## 目次

### 全体

- [全体の構成](/Tech/Architecture) … 処理の流れと、ディレクトリ・モジュールの構成
- [設計方針](/Tech/DesignPolicy) … なぜこの構造にしたのか
- [リファレンス](/Tech/Reference) … URLルーティング表・config全項目
- [ロードマップ](/Tech/Roadmap) … これから作る予定

### 編集

- [編集機能の仕組み](/Tech/EditGuide) … 編集画面・書式の差し替え・保存とバックアップ
- [セクション編集](/Tech/SectionEditing) … 見出し単位の生テキスト編集・プレビュー・保存
- [変更履歴（履歴タブ）の仕組み](/Tech/BackupUI) … 編集画面の「履歴」タブ。履歴の見せかたと復元
- [編集の競合を統合する画面の仕組み](/Tech/ConflictMerge) … 3文書マージでの統合
- [外部エディタ連動](/Tech/EditorSync) … 編集画面と手元のエディタ（VS Code・Emacs・Neovim）の同期。ブラウザ側・拡張機能・プラグインの作りとプロトコル
- [本文に書くHTMLの扱い](/Tech/HtmlPolicy) … allow_html の3段階と、何を落とすか
- [日本語の `**強調**`](/Tech/Emphasis) … 空白で区切らない日本語でも強調が効くようにした判定のゆるめかた

### ページとデータ

- [ページのデータベース](/Tech/PageDataBase) … `pageinfo/wikiall.db` のスキーマと、記録される手順
- [ページの一覧を作る](/Tech/PageList) … 一覧を得る4つの道（`pagelist`）と、そこで見る閲覧の権限
- [ページを扱うインターフェイス](/Tech/PageFileSystem) … OSのファイル操作との食い違いと、代わりに使う関数の一覧
- [リネームの仕組み](/Tech/RenamePage) … リンク元DBを使った名前変更の流れと、現状の課題
- [ファイル一覧の仕組み](/Tech/FilesUI) … `/.files/`。webFileDir の組み込みと、各操作が呼ぶ処理・権限の当てはめ
- [マーカーシステム](/Tech/MarkerSystem) … 用語を色分けしてページをまたいで追跡する仕組み
- [平文ファイルの取り込みをHTTPから実行する仕組み](/Tech/UpdateDB) … `/.plugin/updateDB`、自動取り込みとの違い

### アカウントと権限

- [アカウントの仕組み](/Tech/Accounts) … `config/users.db` と、ログイン・一覧・ハッシュ生成の3画面
- [ページの中でログインする](/Tech/LoginPlugin) … `#login` プラグインから届くログイン・パスワード変更・アカウント作成を、システム側で受ける仕組み
- [ページごとの権限](/Tech/PagePermissions) … 閲覧・編集の権限の決めかた。調査の結果と、決まったこと・まだ決まっていないこと
- [ユーザーが自分で作れるグループ](/Tech/Groups) … `/.groups`。ログインしていれば誰でも作れる、権限とは無関係なグループ

### 管理・運用

- [管理の画面](/Tech/AdminPages) … `/.admin` の下にまとめた管理ツールと、開ける人
- [助手の操作の記録](/Tech/StaffLog) … `/.admin/stafflog`。助手の操作を記録し、管理者が確かめて元に戻す
- [Wikiの設定を画面から変える](/Tech/ConfigWiki) … `/.admin/configwiki`
- [新しいWikiを作る仕組み](/Tech/NewWiki) … `/.newwiki` でWikiを増やす
- [Wikiを消す仕組み](/Tech/DelWiki) … `/.delwiki`。7zへ固めてから消すので、展開すれば戻せる
- [PukiWikiのデータを移す仕組み](/Tech/ConvWiki) … `./wiki.py convwiki` で手元のPukiWikiを新しいWikiとして作り直す
- [削除したページの添付を集める仕組み](/Tech/GarbageCollect) … `/.garbagecollect`。持ち主の無い添付を `/trashbox` へ
- [サービスの再起動の仕組み](/Tech/Restart) … `/.restart` と、動かしかた別の再起動
- [公開版からの更新の仕組み](/Tech/Update) … `/.admin/update`。新しいバージョンを info で知らせ、取り込んで再起動する
- [同じ名前の .txt と .md を整理する仕組み](/Tech/SolveDupPage) … `/.solveDupPage/<ページ名>`。片方を `_bak` のページへ残す
- [タイトル右端の info に出す知らせ](/Tech/PageNotice) … 本体から読み手に知らせる枠（`page_info`）と、知らせの足しかた

### 文書の書きかた

- [AI をつかったプロジェクト管理方法](/PageEdit/AI_Collabo) … GitHub と Wiki を AI に管理させる準備（鍵・clone・Wiki 作成・指示）
  - [AI エージェントに Wiki ページを書かせる](/PageEdit/AI_Collabo/howto4ai) … 置き場所・PukiWiki と Markdown の書きかた・書くときの原則・リンク検査。`checklinks.py` を添付

### 拡張の開発

- [テーマの開発方法](/Tech/ThemeGuide) … テンプレートを書き換えてレイアウトを変える
- [プラグインの開発方法](/Tech/dev_plugin) … Markdownの書きかたを増やす（仕様・PLUGIN_INFO・contextは配下に分けてあります）
- [プラグイン開発で使える汎用関数](/Tech/dev_plugin/functions) … ページ名変換・parse・保存・一覧取得の早見表

## プロジェクト間の申し送り（対応済み）

wikiSystem・wikiPlugin間の実装依頼・不具合報告です。いずれも対応済みです。

- [プラグイン引数の自由順序化](/Tech/PluginArgsFreeOrder)
- [プラグインのwhole_page改名・dynamic_output追加](/Tech/PluginContextFlags)
- [candidateの旧機能の削除](/Tech/PluginCandidateReCleanup)
- [ブロックプラグインの丸括弧の対応を数える](/Tech/PluginBlockParenFix)
- [ページ内の用語をtooltipで参照するプラグイン](/Tech/GlossaryTooltip)
- [glossarytip.jsが日本語のみの用語をtooltip化しない不具合](/Tech/GlossarytipBoundaryBug)

## 全体の構成

リクエストが応答になるまでの流れと、ディレクトリ・モジュールの構成は
[全体の構成](/Tech/Architecture) にあります。
