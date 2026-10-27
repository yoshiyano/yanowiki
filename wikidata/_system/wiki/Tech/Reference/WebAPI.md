# WebAPI

画面から呼ばれる、HTMLではなくデータ（JSON・断片）を受け渡すHTTPのエンドポイントと、操作を受けるPOSTの一覧です。
どのエンドポイントにも専用のトークンや鍵はなく、画面と同じ cookie（`wikiuser_<Wiki名>`・`wikiauth_<Wiki名>`。
[ログイン](/Tech/Accounts/Login)）で呼び出す人を判断し、画面と同じ権限を確かめます
（[ページごとの権限](/Tech/PagePermissions)）。画面からだけ使う前提で、**外から使う安定した仕様としては約束していません**。

管理者が画面から使うツールは [管理者権限でできること](/AdminGuide) にあります。URLと配信するファイルの対応は
[URLルーティング](/Tech/Reference/Routing) にあります。

## 共通のきまり

- エンドポイントはWikiごとです。`/=<Wiki名>/…` を付けたURLは、そのWikiに対する操作になります。**起点Wikiでしか開けない画面**（`/.newwiki`・`/.delwiki`・`/.allwiki`・`/.restart`）は、Wiki名付きのURLを403にします
- 管理系のJSONのエンドポイント（`…/api`）は、断るときもJSONで返します（`{"ok": false, "message": …}`。権限が無いと403、知らない操作は400）。読むのは画面のJavaScriptで、断られたときも文言をその場に出せるようにするためです
- 管理系のJSONのエンドポイントは、`Content-Type: application/json` の本文（POST）で受けます。成功は `{"ok": true, "message": …}` に、操作ごとの結果を加えます
- 助手が行った操作は、エンドポイントの側で記録します（[助手の操作の記録](/Tech/StaffLog)）

## ページに対する操作

どれも**そのページ自身の通常URLへ POST** します。編集の入口があると、URLを見ただけでは分からないようにするためです
（[編集機能の仕組み](/Tech/EditGuide)）。**そのページの編集の権限（`W`）が無いと、どれも403です。**

| `cmd` | 動き | 主な送るもの | 戻り |
|---|---|---|---|
| `edit` | 編集画面を開く | `tab`（`diff`・`attach`・`history`） | 編集画面のHTML |
| `save` | 保存する。本文が空なら削除 | `source`（本文）・`origin`（開いたときのハッシュ）・`markup`・`from_draft=1`（預かった書きかけをそのまま保存） | 成功は303でページへ。競合は[統合する画面](/Tech/ConflictMerge)へ |
| `draft` | 書きかけを預ける | 本文 | 204 |
| `pause`・`discard` | 預けて戻る／預かりを消して戻る | | 303 |
| `attach` | 添付の追加・削除・移動・名前の変更 | `upload`（複数可）・`overwrite=1`・`delete`・`move`と`move_to`・`rename`と`rename_to`・`pasted=1` | [添付ファイルの管理](/Tech/EditGuide/Attach) |
| `preview` | 生テキストを描いたHTMLの断片を返す | 本文を本体に載せる。**`cmd` はクエリ（`?cmd=preview`）**。`?markup=` で書きかたを指定できる | HTMLの断片 |
| `diff` | 送った本文と保存されている内容の差分を返す | 同上（`?cmd=diff`） | HTML |
| `history` | 履歴タブの中身。履歴の取得と復元 | 値なしで表示、`data=history`・`data=version` でJSON、`do=restore`・`do=merge-restore` で復元 | [変更履歴の仕組み](/Tech/BackupUI#受け付ける要求) |

- **GETでは `cmd` は効かず、常に閲覧画面が返ります**
- 大きなPOST（本文・添付）は `chunk_id`・`chunk_index`・`chunk_total` を付けて分けて送れます。そろうまでは 204 を返します（[何回かに分けて送る](/Tech/EditGuide/ChunkedUpload)）
- 旧URL `/.editwikipage/<ページパス>` は、メソッドを問わずこの名前を除いたURLへ303で送り返すだけです

## 編集を助けるエンドポイント

| URL | 動き | 権限 |
|---|---|---|
| `GET /.section/<ページパス>?heading=<id>&scope=header\|body` | その節の生テキストを返す。`parts=1` で `{"before","section","after","origin"}` のJSON | `W` |
| `POST /.section/<ページパス>` | `source`（ページ全体）と `origin` を送って保存する。`{"ok","changed","url"}`、競合は `{"ok":false,"conflict":true,"url"}` | `W` |
| `GET /.pagetree` | ページの木のJSON（ページ選択ダイアログ・サイドバーの一覧が読む） | 読める権限のあるページだけ |
| `GET /.attach/<ページの実体パス>/<ファイル名>` | 添付ファイルを返す | 持ち主のページの閲覧権限。無いときも無いときと同じ404 |

詳しくは [セクション編集](/Tech/SectionEditing#保存のやりとり)・[ページの一覧を作る](/Tech/PageList)。

## 検索

`GET /.search?q=…`。`mode`（and/or）・`target`（all/name/body）・`path`・`page` で絞れ、`fragment=1` を付けると結果の部分だけを返します
（ページ送りのAJAX用）。閲覧の権限が無いページは結果から除きます（[検索・一覧の画面](/Tech/Reference/Views)）。

## ファイル一覧

`/.files/` は、同梱の webFileDir の画面とそのAPI（`/.files/api/v1/…`）です。ログインは要りませんが、**見えるのは読む権限のあるページだけで、操作ごとに権限を確かめます**。
名前の変更・移動・コピー・削除・新規作成などを、webFileDir のコマンドとして受けます
（[ファイル一覧の仕組み](/Tech/FilesUI)）。テーマのファイル（`/.admin/themes/`）も同じ仕組みです。

## アカウントとログイン

| URL | 動き | 権限 |
|---|---|---|
| `POST /.plugin/login` | `cmd` でログイン（省略時）・`logout`・`revoke`（他端末の認証の解除）・`signup`（アカウント作成） | だれでも |
| `POST /.passwd` | 自分のパスワードを変える（ID・いまのパスワード・新しいパスワード） | だれでも |
| `/.pwhash` | ID・パスワードからハッシュ値を作る。何も記録しない | だれでも |
| `POST /.admin/accounts/api` | `{"cmd":"update","uidnum","uid","name","pw"}`・`{"cmd":"delete","uidnum"}` | **既定は管理者だけ**。助手には操作ごとに許せる（`accounts.rename`・`.password`・`.delete`。管理者のアカウントは助手には触れない） |
| `POST /.admin/staffperms` | フォームの `shown`（表示した助手の番号）と `perm.<番号>`（許す権限の名前）で、助手の権限を保存して303で戻る | **管理者だけ** |
| `POST /.admin/approvals` | フォームの `op`（`approve`・`reject`）と `uidnum` | 管理者・助手 |
| `POST /.groups/api` | `{"cmd":"add","group","uids":[…]}`・`{"cmd":"remove","group","uidnums":[…]}` | そのグループの編集権（`g:<名前>`・`admin`・`g:staff`） |

詳しくは [アカウントの仕組み](/Tech/Accounts)・[グループ管理](/Tech/Groups)。

## 管理ツールのJSON

| URL | 動き |
|---|---|
| `POST /.admin/configwiki/api` | `op` が `set`（既定。`path`・`use`・`value`・`ack` で1項目を書く）・`rename`（Wiki名の変更）・`rx_…`（定義ルールの操作）。権限は管理者・助手。応答は `{"ok","message","value","own","state","backups"}` |
| `POST /.admin/privileges/api` | `op` が `add`・`set`・`delete`・`evaluate`（記録は変えず、ページの評価を返す）。どの書き込みも、更新後の一覧 `rows` を返す。`set`・`delete` は行を開いたときの `version` を添える。権限は管理者・助手 |
| `POST /.admin/stafflog` | フォームの `id` で、その記録を元に戻す。権限は、既定では**管理者だけ**（助手には `stafflog.undo` を許せる） |

詳しくは [Wikiの設定を画面から変える](/Tech/ConfigWiki)・[ページごとの権限](/Tech/PagePermissions/Privileges#編集画面adminprivileges)・[助手の操作の記録](/Tech/StaffLog)。

## 画面の確認を経てPOSTで実行するもの

GETで確認の画面を出し、POSTで実行する操作です（全Wikiの一覧 `/.allwiki` はGETだけで、URLの名前は設定 `farm.allwiki` で決まり、空なら出しません）。

| URL | 動き | 権限 |
|---|---|---|
| `/.restart` | サービスの再起動。`POST /.restart?now=1` で、画面を介さずその場で再起動する（スクリプトから呼ぶ用。cookie が要る。GET では確認の画面だけ） | 起点Wikiの管理者・助手 |
| `/.newwiki` | 新しいWikiを作る | 起点Wikiの管理者・助手 |
| `/.delwiki` | Wikiを消す。段ごとに署名付きの合札を持ち回る | 起点Wikiの管理者・助手 |
| `/.garbagecollect` | 持ち主のページが無い添付を `/trashbox` へ集める | 管理者・助手 |
| `/.admin/operations` | 中断した名前の変更・移動を続ける（POSTのフォームの `id`） | 管理者・助手 |
| `/.solveDupPage/<ページ名>` | 同じ名前の `.txt` と `.md` の整理。GETで2つのプレビューと添付・アクセス制限の状態、POSTでフォームの `keep`（採用する拡張子 `.txt`／`.md`）・`hash.txt`／`hash.md`（開いたときの本文のハッシュ）・`dest:<ファイル名>`（添付ごとの移動先）を受けて整理する。整理できなかったとき（開いてから本文が変わっていた、など）は、理由を添えた画面を409で返す | そのページの編集の権限（`W`） |
| `/.updatePageAuth` | 機能していない `#readauth`・`#writeauth` の記録を消す。同じ人が1時間に10回まで（429）。結果は件数だけ | だれでも |

[サービスの再起動の仕組み](/Tech/Restart)・[新しいWikiを作る仕組み](/Tech/NewWiki)・[Wikiを消す仕組み](/Tech/DelWiki)・[削除したページの添付を集める仕組み](/Tech/GarbageCollect)・[リネームの仕組み](/Tech/RenamePage#止めて続きから再開する)・[重複の整理の仕組み](/Tech/SolveDupPage)。

## プラグインのエンドポイント

`/.plugin/<プラグイン名>` は、プラグインの `_action` を呼びます（`#comment` の書き込み、`#vote` の投票、`/.plugin/updateDB` など）。
権限・応答の形はプラグインごとです（[プラグインの開発](/Tech/dev_plugin)）。`/.plugin/<名前>.css` のような名前は、プラグインの資材を返します。

## そのほか

| URL | 動き |
|---|---|
| `POST /.themeselect` | 閲覧者が選んだテーマを cookie（`wikitheme_<Wiki名>`、1日）に覚え、元のページへ戻す。フォームの `theme`（空で既定に戻す）・`reset`・`page`（このWiki内のページパスだけ） |
| `GET /.conflict/<ページパス>` | 編集の競合を統合する画面（`W` が要る）。[統合する画面](/Tech/ConflictMerge) |

資材の配信（`/.theme/…`・`/.slottheme/…`・`/.vendor/…`・`/.editor.js` など `.` で始まる名前）は、操作ではないのでここには載せていません
（[URLルーティング](/Tech/Reference/Routing)）。
