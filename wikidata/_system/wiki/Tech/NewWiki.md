# 新しいWikiを作る仕組み

`/.newwiki` から、新しいWiki（個別Wiki）を作れます。使いかたは
[新しいWikiを作る](/NewWikiGuide) にあります。このページは実装の仕組みです。

## 誰が作れるか

既定Wiki（`config/server.yaml` の `farm.default`）の管理者と助手だけです。Wikiを
増やすのはサービス全体に効く操作なので、[再起動](/Tech/Restart) と同じ判定
（`wikilib.sysui.require_on_default_farm`）を、画面を組み立てる前・POSTを処理する前に
通します。

- 見るのは、いま開いているWikiではなく既定Wikiのアカウントです
- Wiki名を含むURL（`/=<Wiki名>/.newwiki`）は、既定Wikiのものでも403です

権限の全体像は [ページごとの権限](/Tech/PagePermissions)、既定Wikiが持つ役割のまとめは
[設計方針](/Tech/DesignPolicy/Farm#デフォルトのwikiの役割) にあります。

## 何をするか

`wikidata/<名前>/` の下に、フォルダ一式と説明ファイル、最初のページ、管理者の
アカウントを用意します。

```
wikidata/<名前>/
  wiki/       index（トップ）と mainmenu（メニュー）※既定の記法で作る
  attach/     README.txt
  plugin/     README.txt
  theme/      README.txt
  config/     README.txt・users.db（アカウントの記録）
              ・privileges（利用形態が free 以外のとき）
              ・default.yaml（「Wiki設定を独立させる」を選んだとき、または
                利用形態が account.policy を書くとき）
  log/        README.txt
  pageinfo/   README.txt
    draft/    README.txt
    backup/   README.txt
    upload/   README.txt
```

`pageinfo/` にはシステムが自動で書く記録を、それ以外には管理者や編集者が書き換える
ものを置きます。

- 最初のページはトップ画面だと分かる程度の短いものです。メニューも作るので、
  作った直後からサイドバーが使えます
- 書式は既定の記法（`DEFAULT_MARKUP`、いまは [PukiWiki記法](/Syntax/PukiWiki)）です
- 説明ページ（`/Syntax` など）へのリンクは置きません（新しいWikiの中には無いため）

作ったWikiは `/=<名前>/` で開け、作成後はそのトップページへ移ります。

### 管理者のアカウント

`config/users.db` は、Wikiを作るときにここで用意します（作る場所はここと
`./wiki.py initusers` だけ）。**`admin` の最初のパスワードは作成画面で必ず入れて
もらいます**（Wiki設計者の指示、2026-09-08）。既定値のままだと、誰でも知っている値で
管理者に入れる状態から始まるためです。あわせて、助手グループ（`staff`）を `admin`
だけが入った状態で作ります（[グループ](/Tech/Groups)）。

### Wiki設定を独立させる

作成画面の「Wiki設定を独立させる」にチェックを入れると、雛形
（`config/default.example.yaml`）をまるごと写した `config/default.yaml` を用意します。
何が設定できるかをその場で見られるようにするためで、要らない行は消してかまいません。
書かなかった項目は既定値が使われます（[設定ファイル](/Tech/Reference/Config)）。

**チェックは既定で入れてあります**（Wiki設計者の指示、2026-09-15）。引き換えに、
写した項目は作った時点の値で固定され、あとで既定値を直してもそのWikiには届きません
（[設定ファイル](/Tech/Reference/Config#共通の-config-には雛形しか置かない)）。既定値の変更に
追従させたいWikiは、チェックを外して作ります。あとから独立させたくなったら、
そのとき `wikidata/<名前>/config/default.yaml` を作ります。

各Wikiの `config/*.yaml` はGit管理の対象外です。消すと、そのWikiは既定値をそのまま
使う状態に戻ります。

## 利用形態を選ぶ

作るときに「利用形態」を選び、それに応じた権限の既定値とユーザ登録の受け入れかたを
最初から与えます（`newwiki.USAGES`）。形態は [アカウントの仕組み](/Tech/Accounts) の
「想定している5つの使いかた」のうち、権限の行として同じになる1・2をまとめた4つです。

| キー | 使いかた | 置くもの | `account.policy` |
|---|---|---|---|
| `free`（初期値） | 1・2 自分だけ／LAN内で自由 | 何も置かない（未ログインも読み書きできる） | 書かない |
| `named` | 3 LAN内で文責を残す | `*:R:g:any`・`*:W:g:all` | `open` |
| `public` | 4 外部公開 | `*:R:g:any`・`*:W:g:all` | `approval` |
| `members` | 5 閲覧にもログイン | `*:R:g:all`・`*:W:admin,g:staff` | `approval` |

- 初期値を変えるなら `USAGE_DEFAULT` です
- 権限は既定の行（ページ名が `*` だけの行。[ページごとの権限](/Tech/PagePermissions)）として
  `config/privileges` に置きます。許可者を確かめるため、`users.db` と助手グループを
  作ったあとに置きます
- `account.policy` は `config/default.yaml` に書きます。雛形を写したときは写しの1行だけを
  置き換え（コメントは残る）、独立させないときは `account.policy` だけの設定ファイルを作ります
- `members` の「特定のユーザ」は、最初は管理者と助手だけです（増やすときは `/.admin/privileges`）
- 知らない形態が渡されたときは、何も作らずに断ります
- 形態1と2の違いは「ログインの入口を出すか」だけで、そこはまだ分けていません
- `convwiki`（PukiWikiからの取り込み）と、`create_wiki` を引数なしで呼ぶ場合は `free` です

## 名前の決まり

使えるのは半角英数字と `-` `_` で、先頭は英数字です（64文字まで）。URLの一部になり、
そのままフォルダ名にもなるためです。

| 入力 | 断る理由 |
|---|---|
| 空 | 名前が要る |
| すでにある名前 | 上書きしない |
| `=` や `.` で始まる | [予約プレフィックス](/Syntax/Common#ページの名前のルール) |
| `/` を含む・日本語・記号 | 使える文字の範囲外 |

名前を組み立てたあとも、実パスが `wikidata/` の直下になるかを確かめてから作ります。

## 既定のWikiにする（チェックボックス）

チェックを入れて作ると、`config/server.yaml` の `farm.default` もそのWiki名へ
書き換えます（`set_default_farm`）。`/` を開いたときに出るWikiが変わります。

チェックの初期状態は、既存のWikiが `_system` だけかどうかで決まります。

- `_system` しか無い: チェック入り（作った直後に自分のWikiへ入れるように）
- 他に1つでもWikiがある: チェックなし（使い分けている人の設定を勝手に変えないように）

#note(type=warn){{
**既定Wikiを移すと、`/.restart`・`/.newwiki`・`/.allwiki`・`/.delwiki` を使える相手も
移ります。** 元のWikiの管理者は、そのままでは再起動・Wikiの作成と削除・Wikiの一覧の
どれもできなくなります。
}}

あとから変えるときは、設定を直接書き換えても構いません。

```yaml
farm:
  default: sandbox
```

`farm.default` の書き換えは、`default:` の行だけをその場で置き換えます（YAMLとして
読み直して書き出すと、手で付けたコメントが消えるため）。

**`_` で始まるWiki（`_system` など）は、`config/server.yaml` を直接編集しない限り
既定Wikiにできないようにする予定です**（Wiki設計者の指示、2026-09-13。未実装）。
あわせて、新しく設置したときは起動時に用意させた新規Wikiを既定にします。`_` 付きは
システムの見本・説明用なので、そこへ権限が乗らないようにするためです。

## Gitとの関係

`wikidata/` 以下は `.gitignore` で `_system` だけを対象にしているため、ここで作った
Wikiは自動的にGit管理の外になります。

```
/wikidata/*
!/wikidata/_system/
```
