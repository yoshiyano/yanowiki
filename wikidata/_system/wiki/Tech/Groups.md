# ユーザーが自分で作れるグループ（`/.groups`）

ログインしていれば誰でも作れる・入れるグループの管理画面です。
[助手グループ](/Tech/AdminPages#助手グループ)（`staff`）も専用の画面・表を持たず、
`staff` という名前のグループとしてこの仕組みで扱います。

## 画面

ログインしていないと開けません（`sysui.require` に `auth.ANY_USER` を渡し、
ほかの管理ページと同じ403を返します）。画面は管理ページ共通の外枠
（[管理の画面](/Tech/AdminPages)）で出ます。

「グループ作成」「グループ編集」の2つのタブがあり、最初に見せるタブはサーバーが
クエリ（`tab=`）で決め、あとは `groups.js` が切り替えます。

    /.groups                        既定は「グループ作成」タブ
    /.groups?tab=create             グループ作成タブ
    /.groups?tab=edit&group=<名前>  グループ編集タブ。<名前>を開いた状態

**所属グループの一覧は出しません**（Wiki設計者の判断、2026-09-12）。編集タブは
開きたいグループの名前を自分で入れる作りです。

## グループ作成

#img(グループ作成のタブ>groups-create.png)

フォームに入れた名前で新規に作ります（POST。JSは使いません）。

- 使える文字は半角の小文字・数字・`-`・`_` だけ（`wikilib.groups.GNAME_RE` =
  `^[a-z0-9_-]+$`）。URLの一部になるので、大小文字の違いで迷わないよう大文字を
  許しません（ログインIDの決まり `userdb.UID_RE` とは別）
- すでにあるグループ名は使えません（`wikilib.groups.exists`。メンバーが1人以上いれば「ある」）
- **`all`・`any` は作れません。** 権限の許可者で `g:all`・`g:any` として使う、記録に
  持たない特別なグループの名前だからです。作れてしまうと、`g:all` と書いた権限が
  そのグループのメンバーだけに効くようになります
- 作成した人をメンバーに加えて始めます
- 作れたら、そのグループの編集タブへ303で送ります

## グループ編集

編集できる人だけが中身（一覧・追加フォーム）を見られます。編集できない相手や
存在しないグループ名には、案内だけを返します（200のまま。「グループ作成」タブは
誰でも使えるので、`/.groups` 全体は403にしません）。

**`foo` グループの編集権は `g:foo`・`admin`・`g:staff` の誰か**です（Wiki設計者の
指示、2026-09-12）。管理者と助手は、自分が入っていないグループも見渡して手直し
できます（下の「権限は『プリンシパル』のリストで表す」）。

- メンバーの一覧にはユーザー名・表示名・登録日時を出し、ユーザー名と登録日時は
  見出しのクリックで並べ替えられます（`groups.js` がクライアント側でソート）
- 削除は、左のチェックボックスで選んで「削除」ボタン（1つ以上選んだときだけ押せる）
- 追加は、ユーザー名をスペースかカンマで区切って入れる
- 追加・削除はAjaxで、まとめて1回のAPI呼び出しで送り、ページを読み直さずに反映します
  （失敗した分は理由つきで表示）

自分自身を外すこともできます。全員が抜けるとグループは消えます（メンバー0人＝
存在しない扱い。「最後の1人は外せない」という保護はありません）。例外は `staff` で、
`admin` だけの状態に戻ります（下の「`staff`の特別さは…」）。

## API（`/.groups/api`）

`groups.js` が使う、1つのグループへの操作を受けるJSONのAPIです。ログイン状態は
画面と同じcookie（`wikiuser_<Wiki名>`・`wikiauth_<Wiki名>`）で見ます。

    POST /.groups/api
    {"cmd": "add", "group": "…", "uids": ["a", "b"]}
    {"cmd": "remove", "group": "…", "uidnums": [2, 5]}

`add` は、追加できたメンバーの詳細と、できなかった分の `[uid, 理由]` を返します。

    {"ok": true,
     "added": [{"uid": "b", "name": "…", "uidnum": 3, "joined_at": 1234567890,
                "joined_label": "2026-09-12 12:00"}],
     "failed": [["c", "そのIDは登録されていません。"]]}

`remove` は `{"ok": true, "removed": 1}`（実際に外れた件数）を返します。
編集権（`wikilib.auth.can_edit_group`）が無い相手には、どちらも403で断ります。

## 権限は「プリンシパル」のリストで表す

「誰が対象か」を表すときは、次の書きかたを使います。

    admin       管理者（uidnum=1）そのひと1人
    g:<gname>   <gname>グループのメンバー全員
    g:all       登録ユーザ全員（承認待ちを除く）
    g:any       誰でも。未ログインも含む

[ページごとの権限](/Tech/PagePermissions)の許可者も同じ書きかたなので、展開する部分は
`wikilib.auth.expand_principal`/`expand_principals` として独立させてあります。
`g:any` は、uidnumの集合には未ログインを入れられないので、展開すると `g:all` と
同じ集合になります（未ログインを含めた判定は `PagePrivilege` が行います）。

    expand_principal(wiki_dir, "admin")        → {1}
    expand_principal(wiki_dir, "g:foo")        → fooグループのuidnum集合
    expand_principals(wiki_dir, ["admin", "g:staff"])
                                                → 両方の和集合

- `"admin"` は `uid` の文字列ではなく `userdb.ADMIN_UIDNUM`（番号）を返します。
  `uid` は書き換えられる名前なので、それに頼ると権限の対象がずれるためです
- どちらの形にも当たらない文字列は空集合です（書き間違いを誰にでも当てはまるものとして扱わない）

`can_edit_group(wiki_dir, gname, uidnum)` は、`[f"g:{gname}", "admin", "g:staff"]` を
展開した集合に `uidnum` が入っているかを見るだけです。`gname` が `staff` のときも
同じ式で、結局 `admin` と `g:staff` の合併になります。

## `staff`の特別さは「削除時の挙動」だけ

`staff` は他のグループと同じ `group_members` 表に入り、`create_group` に `staff` 専用の
分岐はありません。**ふつうのグループと違うのは、削除時の挙動だけです**（Wiki設計者の
指示、2026-09-12）。

- **事前に作っておきます。** Wiki作成時（`newwiki.create_wiki`）と `./wiki.py initusers`
  実行時に、`ensure_staff_group` で `admin` を1人だけ加えた状態を用意します。
  「すでにある名前は作れない」という通常の決まりで作り直せなくなります（事前に
  作っていなければ、`staff` もただのグループとして作れてしまいます。その保証は
  Wikiを作る側の責務です）
- **全員が抜けたときだけ、特別に扱います。** `remove_members` がその場で
  `ensure_staff_group` を呼び、`admin` だけの状態に戻します
- `ensure_staff_group` を呼ぶのは、事前に作る2か所と、この削除の1か所だけです
  （読み取りのついでに確かめると、どこが効いているのか追えなくなるため）

## 記録の形

`config/users.db`（アカウントの記録と同じDB）に表を1つ持ちます。

```sql
CREATE TABLE group_members (
    gname     TEXT    NOT NULL,   -- グループ名（助手グループなら"staff"）
    uidnum    INTEGER NOT NULL,   -- メンバーのアカウント番号
    joined_at INTEGER NOT NULL,   -- 加わった時刻（UNIX時刻）
    PRIMARY KEY (gname, uidnum)
);
```

- 表は開くたびに `CREATE TABLE IF NOT EXISTS` を通るので、古い `config/users.db` にも足されます
- 「グループ一覧」の表は持ちません。どんなグループがあるかは `gname` の種類を見るしかなく、
  それを見せる画面もありません。`staff` だけは名前（`wikilib.groups.STAFF_GROUP`）を
  知っているので、`/.admin` の一覧から直接リンクできます
- `config/users.db` が無いWikiでは、`/.groups` は「アカウントの記録がまだありません」と
  いう案内だけを出します（`/.admin/accounts` と同じ）

## 実装の置き場所

| 何を | どこが |
|---|---|
| グループの記録（存在・メンバー判定・作成・追加・削除） | `_sys/wikilib/groups.py` |
| 助手グループの削除時の挙動（`STAFF_GROUP`/`ensure_staff_group`） | `_sys/wikilib/groups.py` |
| `staff`を事前に作る呼び出し | `wikilib.newwiki.create_wiki`・`wiki.py`の`run_initusers` |
| 権限展開・編集権の判定（`expand_principal`/`can_edit_group`） | `_sys/wikilib/auth.py` |
| 画面の組み立てとAPI（`render_groups`/`render_groups_api`） | `_sys/wikilib/groupsui.py` |
| 開ける人の判定（`require`。`auth.ANY_USER`を渡す） | `_sys/wikilib/sysui.py` |
| 画面のJavaScript（タブ・ソート・追加削除のAjax） | `_sys/groups/groups.js`（`/.groups.js`） |
| 画面のCSS | `_sys/groups/groups.css`（`/.groups.css`） |
| 表の置き場所 | `wikilib.userdb.SCHEMA`（`group_members`） |

自動テストは `tests/test_groups.py`（名前の検証・作成・追加・削除、`staff`の特別扱い、
権限展開、`can_edit_group`）と `tests/test_groupsui.py`（ログイン必須、編集権の無い
相手には見えないこと、管理者と助手の例外、API）です。
