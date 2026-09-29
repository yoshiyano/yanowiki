# 設定ファイル

設定は、どのWikiを開くかが決まる前に要るかどうかで2つに分けています。

| 設定 | 既定値を書いてあるファイル | 上書きする場所 |
|---|---|---|
| `server` / `farm` / `debug` | `config/server.example.yaml` | `config/server.yaml`（インスタンスに1つ） |
| `page` / `markdown` / `theme` | `config/default.example.yaml` | 各Wikiの `config/default.yaml` |
| PukiWiki記法のユーザ定義ルール・フェイスマーク定義ルール | `config/pukiwiki.extrarules.example.yaml` | 各Wikiの `config/pukiwiki.extrarules.yaml` |
| InterWiki登録表 | `config/pukiwiki.interwiki.example.yaml` | 各Wikiの `config/pukiwiki.interwiki.yaml` |

## 共通の config/ には雛形しか置かない

`config/` に実ファイルとして置くのは `server.yaml` だけです。個別Wikiの設定は雛形
（`config/*.example.yaml`）をそのまま既定値として読み、共通の `config/default.yaml` は
作りません。雛形を直せば、その項目を自分で書いていない全Wikiに届きます
（以前は各Wikiへ写していたため、写したあとに共通側を直しても届かなかった）。

`config/server.yaml` と各Wikiの `config/*.yaml`（`README.txt` は除く）はGit管理対象外です。
`config/server.yaml` は無ければ `./wiki.py` の起動時に雛形から作られます。**雛形
（`config/*.example.yaml`）はGit管理対象なので、書き換えても更新（`git reset --hard`）で
戻ります。** 手元の値は各Wikiの `config/` に書いてください（[入れかた・動かしかた](/InstallGuide)）。

## 読み込む順番

1. 共通の `config/default.example.yaml` を読む
2. その上に `wikidata/<Wiki名>/config/default.yaml` を重ね、書かれた項目だけを上書きする

辞書の中まで降りて重ねるので、`markdown.toc_depth` だけを書いても `markdown.linkify` は
消えません。個別Wiki側には変えたい項目だけを書けば足ります。

```yaml
# wikidata/blog/config/default.yaml … サイト名だけを変える例
theme:
  site_title: 日記
```

`/.newwiki` で「Wiki設定を独立させる」（既定で入っている）にチェックを入れて作ったWikiには、
雛形がまるごと写されます。要らない行は消してかまいません（消せば既定値に従う）。チェックを
外せばファイルは作られず、既定値の変更に追随し続けます。

## PukiWiki関連の設定は重ねずローカル優先

`pukiwiki.extrarules.yaml`・`pukiwiki.interwiki.yaml` は、個別Wiki側にファイルがあれば
それだけを読みます（共通側は読まない。`wikilib.wikiconfig.read_yaml_local_or_common`）。
ルールを配列でしか書けず、項目単位で重ねると共通のどの行が生きているかが見えなくなるためです。

個別Wiki側のファイルは自動では作られません。置かないかぎり雛形を読み、置いたWikiは
それ以降、雛形を直しても追随しません。

## サービスの起動に関わる設定は別

`server` / `farm` / `debug` は `server.yaml` にだけ置きます。どのWikiを開くかが決まる前に
要る値なので、個別Wikiの `default.yaml` に書いても効きません。

```yaml
# config/server.yaml
debug: false         # プラグインのエラー詳細を表示するか（--debug 起動でも有効）

server:
  host: 127.0.0.1   # 待受ホスト。コマンドライン引数 --host が優先される
  port: 8619         # 待受ポート。コマンドライン引数 --port が優先される
  prefix: ""         # サイトのルート以外に設置する場合のURL接頭辞（例: /abcd/efgh）

farm:
  default: wiki      # / へ直接アクセスした際に表示するデフォルトのWiki名
```

## 個別Wikiの設定 全項目

```yaml
# config/default.example.yaml（既定値。Wikiごとに変えるときは
#   wikidata/<Wiki名>/config/default.yaml に、変えたい項目だけを書く）
edit:
  defaultwiki: pukiwiki  # 新しく作るページの記法（pukiwiki / markdown）
  title_length: 24   # サイドバーのページ一覧でタイトルを打ち切る幅（全角は2文字ぶん）
  custom_colors:     # ツールバーの文字色・背景色に足すこのWiki固有の16色（#rrggbb。PukiWiki記法のみ）
    - "#e74c3c"
    # …（16個）

account:
  policy: open  # ユーザ登録の受け入れかた（open / approval）
  pw_salt: ""    # パスワードのハッシュに混ぜる塩。空ならWiki名。変えると全員のパスワードが通らなくなる

attach:
  max_size: 20MB     # 添付ファイル1つあたりの大きさの上限

plugin:
  debug: false       # 実行できなかったプラグインに、その説明（_help）を折りたたみで添えるか

markdown:
  preset: gfm-like          # markdown-it-pyのプリセット
  linkify: true             # 裸のURLを自動リンク化するか
  linkify_fuzzy: true       # "http://"の無い裸の語もドメインらしければリンク化するか
  allow_html: false         # 本文の生HTMLをどこまで通すか（false / true / all）
  anchors: true             # 見出しにidを振る（h1〜h6すべて。off にすると振らない）
  toc_depth: 3              # 目次に出す深さ（idを振る範囲とは別）
  first_h1_as_title: true   # 1行目のh1をページタイトルとして扱うか
  listname: title           # ページの一覧に出す名前（fname＝ファイル名 / title＝見出し）

pukiwiki:
  allow_html: false         # 生HTMLの扱い（markdown.allow_html と同じ意味）
  facemark: true            # フェイスマーク定義ルールを使うか
  wikiname: true            # WikiName（例: PukiWiki）を自動リンクにするか
  listname: fname           # ページの一覧に出す名前（既定は markdown と逆）

theme:
  name: base               # 使用するテーマ名（base なら base.html/css/js）
  site_title: wikiSystem   # ヘッダに表示するサイト名
  show_index: false        # ページ一覧に index を出すか（下の「ページ一覧のTreeView」）
  selector: false          # テーマを選ぶセレクタを menu1 の先頭に出すか
  menu1_page: mainmenu     # サイドバー上段のメニューページ
  menu2_page: submenu      # サイドバー下段のメニューページ
  # menu1_mode:             # ページごとのmenu1開閉モード（省略時は全ページ auto）
  #   - "FrontPage,fix"       # 狭い画面でも常に開いたままにする
  # menu2_mode:             # menu2も同様（menu1とは別に指定する）
```

メニュー枠は `menu1`/`menu2` の2つが既定ですが、`menu3_page` のように番号を増やして書けば、
その枠のHTML・開閉モードがテーマへ渡ります（`themes.menu_slot_numbers()` がキー名から
見つける。テンプレート側の記述は別に要る）。

各項目の詳しい説明:

- `debug`（`server.yaml`）・`plugin.debug` … [エラーの扱い](/Tech/dev_plugin/spec/errors)
- `server.prefix` … [設計方針](/Tech/DesignPolicy) の「サブパスへの設置」
- `edit.defaultwiki` … [PukiWiki記法](/Syntax/PukiWiki#editnotation) の「この記法で書くには」
- `edit.title_length` … [編集機能の仕組み](/Tech/EditGuide/Sidebar)
- `account.policy`・`account.pw_salt` … [アカウントの仕組み](/Tech/Accounts)
- `attach.max_size` … 下の「添付ファイルの大きさの上限」
- `markdown.*` … [プラグインの開発方法](/Tech/dev_plugin) の「レンダリングの設定」
- `markdown.allow_html`・`pukiwiki.allow_html` … [本文のHTMLの扱い](/Tech/HtmlPolicy)
- `pukiwiki.*` … [PukiWiki記法](/Syntax/PukiWiki)
- `markdown.listname`・`pukiwiki.listname` … [ls プラグイン](/Syntax/Plugin/ls)
- `theme.*` … [見た目を変えよう](/ThemeGuide)、[テーマの開発方法](/Tech/ThemeGuide)
