# 今ある土台と、閲覧を止める経路

権限の仕組みを載せる前からあった土台と、どの画面が何を見ているか、閲覧を止めるときに塞ぐ経路です。

## すでにある土台

ページの権限は、`auth.py`（認証・認可）と `sysui.py`（画面の土台）に乗せています。

| もの | どこ | 何ができるか |
|---|---|---|
| ログイン状態の取得 | `auth.current_user(wiki_dir, farm)` | cookie 2枚（`wikiuser_<Wiki名>`/`wikiauth_<Wiki名>`）を突き合わせて、いま誰が入っているかを返す |
| 権限の判定 | `auth.allows(wiki_dir, farm, principals)` | 画面単位の判定はここ1つに集約 |
| プリンシパルの展開 | `auth.expand_principal(s)` | `admin` / `g:<グループ名>` を uidnum の集合に展開する |
| 決まった組み合わせ | `auth.ADMIN_ONLY` / `STAFF` / `ANY_USER` | 画面はこれを渡すだけでよい |
| 画面を開ける人の判定 | `sysui.require(...)` | 通らなければ中身を組み立てずに403を返す |
| サービス全体に効く画面の判定 | `sysui.require_on_default_farm(...)` | 既定Wikiのアカウントで判定する（`/.restart`・`/.newwiki`・`/.allwiki`・`/.delwiki`） |
| グループ | `group_members`表（`config/users.db`） | 誰でも作れる汎用グループ。助手（`staff`）も同じ表 |
| 本文の差し替え | `plugins.PluginContext.block_view` | プラグインが「このページの本文を出さない」と決めるメソッド |
| 書き込みの合流点 | `pagesave.save_page` | 編集画面・セクション保存・`#comment`・`#vote`・`#tasklist` が最後に通る |

ページの権限の判定（`auth.page_privilege`）も `auth.allows` の隣に置きました。

## いま、どの画面が何を見ているか

| 経路 | いまの判定 |
|---|---|
| `/.admin/accounts` | 管理者だけ（`auth.ADMIN_ONLY`） |
| `/.admin`・`/.admin/configwiki`・`/.admin/privileges`・`/.admin/approvals` | 管理者と助手（`auth.STAFF`） |
| `/.groups` | ログインしていれば誰でも（`auth.ANY_USER`） |
| `/.login` | 誰でも（閉じると誰もログインできないため、ページごとの権限の対象外） |
| `/.restart`・`/.newwiki`・`/.allwiki` | 既定Wikiの管理者と助手。Wiki名付きのURLは403 |
| `/.delwiki` | 同じ。さらに消される側のWikiの管理者のパスワードを確かめる（[Wikiを消す仕組み](/Tech/DelWiki)） |
| ページの表示（`views.render_page`） | 閲覧の権限（`published_ref` が返す `ref.privilege`）。`-` なら403「閲覧する権限がありません」。本文は描かない（データの読み出しはする） |
| 編集・保存（`editor.render_edit`） | 編集の権限。`W` でなければ403「編集する権限がありません」。一時保存・添付・保存も同じ関数を通る |
| セクション編集（`/.section`） | 編集の権限。`W` でなければ取り出し（GET）も保存（POST）も403。`block_view` のときも403 |
| 添付の配信（`/.attach/…`） | 持ち主のページの閲覧権限。`-` なら 404 `File not found`（ファイルは探さない） |
| `#include`・`#ls` の読み込み表示・目次・メニュー | 閲覧の権限。`-` なら本文を出さない |
| `#comment`・`#vote` の書き込み | 閲覧の権限。`-` なら403。`R` は通す |
| `#tasklist` のチェックの切り替え | 編集の権限。`W` でなければ403。`W` が無い人にはチェックボックスを押せない形で出す |
| 検索（`/.search`） | 閲覧の権限。`-` なら本文を見る前に検索結果から省く |
| ページ一覧JSON（`/.pagetree`） | 編集画面・ページ選択ダイアログ用（[ページの一覧を作る](/Tech/PageList)） |
| 履歴・復元（ページのURLへ `?cmd=history`） | 編集の権限。`W` でなければ403。編集画面の「履歴」タブが使う（[変更履歴の仕組み](/Tech/BackupUI#受け付ける要求)） |
| 名前の変更・移動（ファイル一覧） | 編集の権限。一緒に動くページすべてに `W` が要る（1枚でも欠ければ断る） |
| 競合の統合（`/.conflict`） | 編集の権限。`W` でなければ画面を描く前に403 |
| プレビュー・差分（`?cmd=preview`・`?cmd=diff`） | 編集の権限。`W` でなければ403 |

## 閲覧を止めるなら、塞ぐ経路（漏れる経路の全数）

本文が読めてしまう経路は表示だけではありません。調査の時点で挙げた全数です。
それぞれのいまの判定は上の表にあります。

### 本文そのものが出る

- ページの表示（`views.render_page`）
- 編集画面（`editor.render_edit`。本文が編集欄に入る）
- セクションの取り出し（`/.section`）
- 一時保存の読み戻し（`draft`）
- 履歴と復元（`?cmd=history`。過去の版の本文と差分）
- 競合の統合（`/.conflict`）
- プレビュー・差分（差分は保存されている本文も読む）
- 他ページからの取り込み（`#include`）

### 本文の一部・存在が出る

- 検索（本文の抜粋）
- `#ls` / `#recent` / `#popular` / `#contents`（ページ名・タイトル・更新順）
- `/.pagetree`（全ページ名のJSON）
- ファイル一覧（`/.files/`）
- テーマのメニューとTopicPath
- リンク元（`pagedb` の backlinks を使う表示）
- 添付ファイル（`/.attach/…`。ページとは別のURL）

**閲覧の権限の無いページの名前（ページがあること）を出さないのは、努力目標であって義務では
ありません**（Wiki設計者、2026-09-29）。利便性のための努力目標で、漏洩対策としての義務では
ないので、避けにくい場面では名前が見えてもかまいません。漏洩対策として出してはいけないのは
本文と、検索の抜粋などの本文の一部です。

### 書き込み側

- 編集画面からの保存（`pagesave.save_page`）
- セクション保存（`editor.save_section`）
- `#comment` / `#vote` / `#tasklist`（プラグインによる書き換え。記録は `system`）
- 添付の追加・削除
- 名前の変更・移動（ファイル一覧）、競合の統合（`/.conflict`）、履歴からの復元（`?cmd=history`）

書き込みは `pagesave.save_page` に合流しているので、最後の判定を1か所に置けます。
