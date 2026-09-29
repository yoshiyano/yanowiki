# アカウントの仕組み

ページごとの認証の土台です。このページで扱うのは、アカウントを持つことと、
送られてきたIDとパスワードを確かめてログイン状態を持ち回ることです。
どのページを誰が読めて書けるかは [ページごとの権限](/Tech/PagePermissions) にあります。

## 画面

ログインの入口は `/.login` です。ページごとの権限の対象ではないので、閲覧にも
ログインを求めるWikiでも開きます。中身は `#login` プラグイン
（[ページの中でログインする](/Tech/LoginPlugin)）と同じフォームで、`/.plugin/login` へ送ります。

| URL | 何をするか | 開ける人 |
|---|---|---|
| `/.login` | ログインの入口（`#login` と同じフォーム） | 誰でも |
| `/.plugin/login` | `#login` のフォームを受ける（照合・ログアウト・他端末からの認証の解除・アカウント作成） | 誰でも |
| `/.admin/accounts` | 登録されているアカウントを見る・直す・増やす・消す | **管理者だけ** |
| `/.admin` | 管理の道具の一覧（[管理の画面](/Tech/AdminPages)） | 管理者と助手 |
| `/.admin/approvals` | 承認待ちのアカウントを承認する・断る（`account.policy` が `approval` のWiki） | 管理者と助手 |
| `/.groups?tab=edit&group=staff` | 助手グループの出入り（[グループ管理](/Tech/Groups)） | 管理者と助手 |
| `/.passwd` | **自分の**パスワードを変える（いまのパスワードが要る） | 誰でも |
| `/.pwhash` | パスワードからハッシュ値を作るだけの道具 | 誰でも |

どれも `/=<Wiki名>/.admin/accounts` のようにWikiごとに開き、管理ページ共通の外枠で
出ます（[管理の画面](/Tech/AdminPages)）。

## 下位のページ

| ページ | 内容 |
|---|---|
| [照合の記録とロック](/Tech/Accounts/AuthLog) | 照合の記録（`auth.log.db`）、5回まちがえたときのロック |
| [ログイン（`#login` プラグイン経由）](/Tech/Accounts/Login) | ログインのフォームと、そのやりとり |
| [アカウントの一覧とパスワードの変更](/Tech/Accounts/AccountList) | `/.admin/accounts`・`/.passwd`・`/.pwhash` |
| [ユーザ登録の受け入れかた（`account.policy`）](/Tech/Accounts/Policy) | 誰でも・承認制・受け付けない、の設定と動き |
| [記録の形とパスワードの持ちかた](/Tech/Accounts/Records) | アカウントの記録の形、ID・番号の決めかた、パスワードの持ちかた |

## 実装の置き場所

記録・認証と認可・画面の3層に分け、依存は下から上への一方向です。

| 層 | 何を | どこが |
|---|---|---|
| 記録 | アカウントのDBの読み書き・照合・ハッシュ | `_sys/wikilib/userdb.py` |
| 記録 | グループの記録 | `_sys/wikilib/groups.py` |
| 記録 | 認証の履歴／管理操作の履歴 | `_sys/wikilib/authlog.py`／`adminlog.py` |
| 認証・認可 | cookieと合言葉（`current_user`／`session_token`ほか） | `_sys/wikilib/auth.py` |
| 認証・認可 | ログイン・ログアウト・他端末からの認証の解除・アカウント作成（`do_login`等） | `_sys/wikilib/auth.py` |
| 認証・認可 | 権限の判断（プリンシパル展開・`allows`・`is_staff`） | `_sys/wikilib/auth.py` |
| 画面の土台 | 外枠・知らせ・JSON・開ける人の判定（`page`／`notice`／`json_out`／`require`） | `_sys/wikilib/sysui.py`・`_sys/sysui/shell.css` |
| 画面 | `/.admin/accounts`・`/.passwd`・`/.pwhash` | `_sys/wikilib/accounts.py` |
| 画面 | 一覧の更新・削除を1件ずつ受けるAPI（`render_accounts_api`） | `_sys/wikilib/accounts.py`（`/.admin/accounts/api`） |
| 画面 | 一覧のJavaScript | `_sys/accounts/accounts.js`（`/.admin/accounts.js`） |
| 画面 | それらの画面で共有するCSS | `_sys/accounts/accounts.css`（`/.admin/accounts.css`） |
| — | `#login` プラグイン本体（画面・`_action`） | `plugin/login.py`・`plugin/login.css` |
| — | DBの置き場所 | `wikilib.paths.farm_users_db_path()` |
| — | 設置ごとの合言葉 | `config/secret.txt`（`wikilib.paths.SECRET_PATH`） |

自動テストは `tests/test_userdb.py`（記録・照合・合言葉）と `tests/test_accounts.py`
（cookieの置きかたと読み戻し・`render_accounts_api` の認証・1件ずつの操作・記録）です。
照合の可否と、合言葉の材料を1つ取り違えたときに通らないことを固定してあります。

## 管理者は1人のまま

**管理者は `uidnum = 1` の1人のままで、複数持てるようにはしません**（Wiki設計者の判断、
2026-09-21）。管理の道具を使う人は助手グループ（`staff`）で増やします
（[管理の画面](/Tech/AdminPages)）。特定の処理は admin に集約し、最悪の場合はローカルの
コマンド（`./wiki.py resetpw` など）で対応するので、管理者の権限はこれ以上増やしません。

これから作るものは[ロードマップ](/Tech/Roadmap)にあります。
