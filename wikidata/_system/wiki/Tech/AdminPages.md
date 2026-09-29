# 管理の画面

管理の道具は **`/.admin`**（道具の一覧の画面）から開き、新しい道具もその下に
つなぎます。一覧の中身（`adminui.TOOLS`）は、`#login` プラグインの「管理者メニュー」
タブにも出ます。

#img(道具の一覧の画面（/.admin）>admin-tools.png)

| 画面 | 開ける人 | 理由・中身 |
|---|---|---|
| `/.admin` | 管理者と助手 | 道具を並べるだけ |
| `/.admin/accounts` | **管理者だけ** | 他人のパスワードを書き換えられる＝そこから管理者になれてしまう（[アカウントの仕組み](/Tech/Accounts)） |
| `/.admin/approvals` | 管理者と助手 | 承認待ちのアカウントを承認する・断る（[アカウントの仕組み](/Tech/Accounts) の「承認制の動き」） |
| `/.groups?tab=edit&group=staff` | 管理者と助手 | 助手グループの出し入れ（下の「助手グループ」） |
| `/.admin/configwiki` | 管理者と助手 | 設定を変えられるが、管理者にはなれない（[Wikiの設定](/Tech/ConfigWiki)） |
| `/.admin/privileges` | 管理者と助手 | ページごとのアクセス制限（[ページごとの権限](/Tech/PagePermissions)） |
| `/.updatePageAuth` | 誰でも（1時間に10回まで。管理者と助手は除く） | 機能していない `#readauth`・`#writeauth` の記録を消す（[ページごとの権限](/Tech/PagePermissions/Privileges#機能していない記録の後始末updatepageauth)） |
| `/.admin/stafflog` | **管理者だけ** | 助手の操作の記録を見る・元に戻す（[助手の操作の記録](/Tech/StaffLog)） |
| `/.garbagecollect` | 管理者と助手 | 削除したページの添付を `/trashbox` へ集める。GETで確認、POSTで実行（[削除したページの添付を集める仕組み](/Tech/GarbageCollect)） |

**線引きは「そこから管理者になれてしまうか」です。** 新しい道具もこの基準で
振り分けます。判定する関数は `sysui.require` 1つで、その画面に必要なプリンシパル
（`auth.ADMIN_ONLY`／`auth.STAFF`／`auth.ANY_USER`）を渡します。

通れないときの断りの画面（403）には、ログインの入口（`/.login`）とトップページへのリンクを出します。
「ログインしていない」と「権限がない」を分けて伝えないため、文言とリンクはログインの状態に
かかわらず同じです。ログインのあとは、そのWikiのトップへ戻ります（システムの画面は戻り先にしません）。

`/.admin` の一覧では、開けない道具も隠さず「管理者だけ」と印を付けて並べます
（隠すと「無い」のか「開けない」のかが分からないため）。

アカウントと設定の画面の旧URL（`/.accounts`・`/.configwiki`）、助手グループの旧画面
（`/.admin/staff`）は残していません。

## 助手グループ

助手は、管理者の権限が要る画面を代わりに使えます。ただし「管理者だけ」の画面は
使えません。

助手グループの名前は **`staff`** で、[ユーザーが自分で作れるグループ](/Tech/Groups)
そのものです（専用の画面・表は持ちません）。出し入れは `/.admin` の一覧の
「助手グループ」から `/.groups?tab=edit&group=staff` を開いて行います。

    そのグループの編集権 … g:<グループ名>, admin, g:staff の誰か
    staffグループの編集権 … 結局 admin, g:staff の合併（管理者と助手だけ）

**`staff` がふつうのグループと違うのは、削除時の挙動だけです**（Wiki設計者の指示、
2026-09-12）。

- Wiki作成時・`initusers` 実行時に、`admin` を1人加えた状態であらかじめ作ります。
  「すでにある名前は作れない」という通常の決まりで、作り直せなくなります
- 全員が抜けたときは、次に参照されたときに `admin` だけを含む状態へ自動で戻します

`g:XXXX` という書きかたと、それを展開する `wikilib.auth.expand_principal` は
[権限は「プリンシパル」のリストで表す](/Tech/Groups#権限はプリンシパルのリストで表す)
にまとめてあります（[ページごとの権限](/Tech/PagePermissions)の許可者も同じ書きかた）。

## 見た目は共通の外枠（テーマの影響を受けない）

管理ページ（道具の一覧・アカウント・承認・グループ・設定・Wikiの一覧・新規作成・
削除・名前変更・再起動、権限が無いときの断りの画面）は、テーマを通さず、
編集画面と同じヘッダ＋全幅の本文の外枠（`sysui.page`）で描きます。

- ページ一覧は付けません
- 色は外枠が持ち、明暗はOSの設定（`prefers-color-scheme`）に従います
- 狭くしたい画面は、その画面のCSSで `max-width` を持ちます

アクセス制限（`/.admin/privileges`）・編集画面の「履歴」タブ・競合の統合の画面は、
それぞれ独自の外枠で、`sysui.page` は使っていません（共通化は今後の課題）。

## 実装の置き場所

| 何を | どこが |
|---|---|
| 道具の一覧の画面（`/.admin`） | `_sys/wikilib/adminui.py` |
| 道具の一覧（中身のHTML。`#login` のタブにも差し込む） | `adminui.admin_tools_html`（並びは `adminui.TOOLS`） |
| アクセス制限の画面・API | `_sys/wikilib/privilegesui.py`（資材は `_sys/privilegesui/`） |
| アクセス制限の記録（`config/privileges`） | `_sys/wikilib/privilege_records.py` |
| 助手グループ（`staff`）の判断・データ | `_sys/wikilib/groups.py`（[グループ管理](/Tech/Groups)参照） |
| 開ける人の判定（`require`。プリンシパルを渡す） | `_sys/wikilib/sysui.py` |
| 共通の外枠（`page`） | `_sys/wikilib/sysui.py`・`_sys/sysui/shell.css` |
| 権限の判断（`allows`／`is_staff`／プリンシパル展開） | `_sys/wikilib/auth.py` |
| 画面のCSS | `_sys/accounts/accounts.css`（アカウントの画面と共有） |
| 自動テスト | `tests/test_adminui.py`・`tests/test_groups.py`・`tests/test_privilege_records.py` |
