# 全体の構成

リクエストが応答になるまでの流れと、ディレクトリ・モジュールの構成です。

## 全体像

```
リクエスト
  ↓ URL接頭辞(server.prefix)を除去
  ↓ アクセス先のWikiを決定（"=Wiki名" があればそれ、無ければ既定のWiki）
  ↓ ページファイルを探す（.txt を優先、無ければ .md）
  ↓ 本文をHTMLにする（.txt は PukiWiki記法、.md は Markdown として）
  ↓ メニューと目次を組み立てる
  ↓ テーマ（Jinja2テンプレート）で全体を組み上げる
レスポンス
```

## ディレクトリ構成

```
/
 + wiki.py          起動とURLの振り分けだけ
 + wiki.wsgi        WSGIサーバ（uWSGI・Apache）から使うときの入口
 + _sys/            アプリケーション本体と、外部から持ち込んだもの
      + bottle.py     bottle本体（ベンダリング）
      + wikilib/      実装のモジュール群（下記）
      + editor/       編集画面のCSS/JS（ほかの画面の資材も、画面ごとのフォルダに置く）
      + vendor/       第三者ライブラリの資材
      + webfiledir/   ファイル一覧の部品 webFileDir（同梱。由来と更新は WIKISYSTEM.txt）
 + plugin/          全wiki共通のプラグイン
 + theme/            全wiki共通のテーマ
 + config/          設定（server.yaml と、既定値の雛形 *.example.yaml）
 + wikidata/
      + wiki/       個別Wiki
           + wiki/    ページ本文
           + attach/  添付ファイル
           + plugin/  このwiki固有のプラグイン
           + theme/    このwiki固有のテーマ
           + config/  このwiki固有の設定と、アカウント（users.db）・アクセス制限（privileges）
           + log/     アクセス・認証・管理操作の記録（*.log.db）
           + pageinfo/  ページに付随する記録（システムが書く）
                + draft/   編集中の書きかけ（一時保存）
                + backup.db   編集バックアップ（差分）
                + upload/  分けて送られているファイルの、継ぎ足しの途中
                + wikiall.db  ページ本文と、そこから取り出した情報のDB
```

`wikidata/` の下にフォルダを追加すれば、Wikiをいくつでも増やせます。

## モジュール構成

`wiki.py` は**起動とURLの振り分けだけ**を受け持ち、実際の処理は
`_sys/wikilib/` の各モジュールが持ちます。

**表示と記法**

| モジュール | 受け持ち |
|---|---|
| `paths.py` | 定数と、URLのページパス↔実ファイルの対応づけ（`resolve_page_ref` ほか） |
| `wikiconfig.py` | 設定の読み込み（共通→個別Wikiの重ね）と、そこから決まる値 |
| `plugins.py` | プラグインの読み込み・記法の登録・呼び出し |
| `render.py` | 本文のレンダリング、目次・見出し位置、本文リンクの書き換え |
| `pukiwiki.py` | PukiWiki記法のパーサー |
| `extrarules.py` | PukiWiki記法の「ユーザ定義ルール」「フェイスマーク定義ルール」 |
| `interwiki.py` | PukiWiki記法の InterWiki（`[[登録名:ページ名]]`） |
| `subst.py` | プラグインではない、単純な置換系コマンド（PukiWikiの「置換文字」） |
| `cjkemphasis.py` | 日本語の中の `**強調**` が効くようにする（[日本語の強調](/Tech/Emphasis)） |
| `htmlpolicy.py` | 本文に書かれた生HTMLをどこまで通すか（`allow_html`） |
| `markers.py` | マーカーシステム |
| `themes.py` | Jinja2でページ全体を組み立てる |
| `views.py` | ページ表示と、ページ／Wikiが無いときの画面 |
| `search.py` | 検索 |
| `web.py` | レスポンスまわりの小さな道具 |
| `vendor.py` | 第三者ライブラリ（`_sys/vendor/`）の資材の配信 |

**編集と保存**

| モジュール | 受け持ち |
|---|---|
| `editor.py` | 編集画面・保存・削除・添付タブ・ページ一覧 |
| `draft.py` | 編集中の書きかけの一時保存（`pageinfo/draft/`） |
| `editdiff.py` | 「更新状況」に出す差分のHTML化（行ごとの対応見出し付き） |
| `conflict.py` | 編集が競合したときに統合する画面（`/.conflict/<ページパス>`） |
| `attach.py` | 添付ファイルの配信と管理 |
| `imagesize.py` | 画像の幅・高さを、ヘッダだけ読んで求める |
| `chunked.py` | 大きなものを何回かに分けて受け取る（`pageinfo/upload/`） |
| `backup.py` | 保存時の差分バックアップ（`pageinfo/backup.db`） |
| `backupmerge.py` | バックアップからの部分復元 |
| `backupui.py` | 編集画面の「履歴」タブの中身（ページのURLへ `?cmd=history`） |
| `snapshot.py` | ある時点のページ本文・フォルダ直下の一覧を、差分と改名の記録から組み立てる（内部処理のみ） |
| `pagesave.py` | ページ1枚を「保存した」ことにする後始末（差分・平文・DB）を1つにまとめたもの |
| `pagesync.py` | 平文の直接編集の取り込み（起動時・1時間ごと・`updatepage`） |
| `pagemove.py` | ページとフォルダの行き来（展開・集約と、それに伴う付け替え） |
| `pagerename.py` | ページ・フォルダの名前と置き場所を変える（ファイル一覧から呼ぶ）。指していたリンクも直す |
| `filesui.py` | ファイル一覧（`/.files/`）。webFileDir を組み込み、閲覧できるページをエクスプローラーの形で見せる。ページの参照・編集・名前の変更・移動・削除・フォルダとページの新規作成ができる |
| `pagelinks.py` | 本文に書かれたリンク先を、書かれたままの位置で書き換える |
| `pluginlinks.py` | プラグインの引数に書いたページ名を、名前の変更に合わせて書き換える |

**ページの記録と一覧**

| モジュール | 受け持ち |
|---|---|
| `pagedb.py` | ページ本文と派生情報のDB（`pageinfo/wikiall.db`） |
| `dbbackup.py` | `wikiall.db` の控えを1日1回とる |
| `links.py` | 本文から取り出すもの（タイトル・目次・リンク）と逆リンク |
| `pagelist.py` | 読み手に見せるページの一覧（閲覧の権限を見る。[ページの一覧を作る](/Tech/PageList)） |
| `pagetree.py` | ページ一覧のツリー（ページ選択ダイアログ用） |
| `treeview.py` | ページ一覧のTreeViewが持つCSS/JS（`/.treeview.css`, `/.treeview.js`） |
| `accesslog.py` | ページ・添付ファイルへのアクセスログ（`log/access.log.db`） |
| `diskusage.py` | そのWikiが使っている場所（ページと添付ファイル） |

**アカウントと権限**

| モジュール | 受け持ち |
|---|---|
| `userdb.py` | アカウントの記録（`config/users.db`） |
| `groups.py` | グループの記録（`users.db` の `group_members` 表） |
| `auth.py` | いま誰がログインしていて、その人が何をしてよいか（画面は作らない） |
| `authlog.py` | 認証の履歴（`log/auth.log.db`） |
| `privilege_records.py` | ページごとのアクセス制限の記録（`config/privileges`） |
| `accounts.py` | アカウントまわりの画面（一覧と編集・自分のパスワード・ハッシュ値づくり） |
| `approvalsui.py` | 承認待ちのアカウントを承認する・断る画面（`/.admin/approvals`） |
| `groupsui.py` | グループの画面（`/.groups`） |
| `privilegesui.py` | アクセス制限を編集する画面（`/.admin/privileges`） |

**Wikiの管理**

| モジュール | 受け持ち |
|---|---|
| `sysui.py` | システムの画面（`/.admin/…`・`/.groups` ほか）が共通で使う土台（外枠・権限の関門） |
| `adminui.py` | 管理の道具の一覧（`/.admin`） |
| `adminlog.py` | 管理操作の履歴（`log/admin.log.db`） |
| `configui.py` | Wikiの設定を画面から書き換える（`/.admin/configwiki`） |
| `extrarulesui.py` | PukiWiki記法の定義ルールを設定画面から書き換える |
| `restart.py` | サービスの再起動（`/.restart`）。動かしかたを見分けて方法を変える |
| `newwiki.py` | 新しいWikiを作る（`/.newwiki`） |
| `delwiki.py` | Wikiを消す（`/.delwiki`） |
| `farmrename.py` | Wikiの名前を変える（設定画面の「Wiki名」） |
| `wikimark.py` | そのWikiを取り違えていないかを確かめる目印 |
| `convwiki.py` | PukiWikiのデータを写して新しいWikiを作る（`./wiki.py convwiki`） |
| `allwiki.py` | このサーバーの全Wikiの一覧（`/.allwiki`。URL名は設定で決まる。既定Wikiの管理者と助手だけ） |

依存はおおよそ **`paths`/`wikiconfig` → `plugins` → `render` → `themes` →
各機能 → `editor`/`views`** の向きで、循環しないようにしてあります。

逆向きになる少数の呼び出し（`PluginContext.page_headings` が `render` を使うなど）は、関数の中で `import` しています。

### なぜ `_sys/` の下のパッケージにしたか

`_sys/` は `sys.path` の先頭に入るので、`render.py` のようなありふれた名前をそのまま置くと、
標準ライブラリや依存パッケージと衝突しかねません。`wikilib` パッケージにまとめて避けています。

`wiki.py` の先頭の `_venv` での再実行は、依存パッケージの `import` より前に要るので、そのまま置いてあります。
