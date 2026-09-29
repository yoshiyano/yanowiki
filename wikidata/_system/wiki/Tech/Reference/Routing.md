# URLルーティング

| アクセスURL | 参照するファイル |
|---|---|
| `/` | `wikidata/_system/wiki/index.txt`（優先）、無ければ `index.md` |
| `/UsageGuide` | `wikidata/_system/wiki/UsageGuide.txt`。無ければ `.md`。どちらも無ければ「このページはまだありません」をテーマ付きで表示（HTTP 404） |
| `/Tech`, `/Tech/dev_plugin` | ディレクトリの場合、配下の `index.txt`（無ければ`index.md`）にフォールバック（階層は何段でも可） |
| `/=team/`, `/=team/UsageGuide` | `team` という個別Wiki（`wikidata/team/wiki/` 配下）のページ |
| `/=_system/UsageGuide` | デフォルトのWikiの明示指定（`/UsageGuide` と同じページを表示するが、`=_system/` を明示した状態はそのページ以降のリンクにも引き継がれる） |
| `/.theme/base.css` | テーマ資材。個別Wiki固有の `wikidata/<Wiki名>/theme/` を優先し、無ければ共通の `theme/` から配信 |
| `/.attach/index/logo.png` | 添付ファイル。`wikidata/<Wiki名>/attach/` 配下、ページのパスをそのままミラーした場所から配信（全Wiki共通の置き場所は無い） |
| `/.search?q=...` | 検索。`mode`（and/or）、`target`（all/name/body）、`path`（ページ名の絞り込み、ワイルドカード可）、`page`（ページ送り）を指定できる。`fragment=1` で結果の部分だけを返す（ページ送りのAJAX用）。閲覧の権限が無いページは結果から除く |
| `/.search.css`, `/.search.js` | 検索結果の資材（`_sys/search/`） |
| `<ページパス>`（POST, `cmd=edit`） | 編集画面を返す（GETでは常に閲覧画面。`?tab=attach` で添付タブを開く）。[編集機能の仕組み](/Tech/EditGuide)参照 |
| `<ページパス>`（POST, `cmd=save`, 本文が空） | そのページを削除する（ファイルごと）。添付ファイルが残っている場合は削除せず警告を出す |
| `<ページパス>`（POST, `cmd=attach`） | 添付ファイルの追加（`upload`、複数可・`overwrite`）・削除（`delete`）・移動（`move` と移動先の `move_to`） |
| `/.admin` | 管理の道具を並べた画面。**管理者と助手**。[管理の画面](/Tech/AdminPages)参照 |
| `/.admin/accounts` | 登録されているアカウントを見る・直す・増やす・消す。**管理者だけ**。[アカウント](/Tech/Accounts)参照 |
| `/.admin/configwiki` | Wikiの設定（`config/default.yaml`）を書き換える画面。**管理者と助手**。[Wikiの設定を画面から変える](/Tech/ConfigWiki)参照 |
| `/.admin/privileges`, `/.admin/approvals` | ページごとのアクセス制限を決める画面・承認待ちのアカウントを承認する画面。どちらも**管理者と助手**。[管理の画面](/Tech/AdminPages)参照 |
| `/.login`, `/.passwd`, `/.pwhash` | ログイン・自分のパスワードの変更・パスワードからハッシュ値を作る道具。[アカウントの仕組み](/Tech/Accounts)参照 |
| `/.groups` | ユーザーが自分で作れる汎用グループの管理画面（助手グループの管理も含む）。**ログインしていれば誰でも開ける**。`?group=<グループ名>` でそのグループの編集タブを開く（中身が見えるのは g:<グループ名>・admin・g:staff の誰か）。資材は `/.groups.css`・`/.groups.js`。[グループ管理](/Tech/Groups)参照 |
| `/.groups/api` | `/.groups` の一覧の追加・削除を受けるJSON API（POST）。**そのグループの編集権がある人だけ**（g:<グループ名>・admin・g:staffの誰か） |
| `/.editwikipage/<ページパス>` | 旧URL。メソッドを問わず、この名前を除いた通常URLへ303で送り返すだけ。さらに古い `/.edit/…` は送り返さない |
| `/.pagetree` | ページ一覧を階層構造のJSONで返す。ページ選択ダイアログが読む（[ページの一覧を作る](/Tech/PageList)） |
| `<ページパス>?cmd=history`（POST） | 編集画面の「履歴」タブの中身。値なしで埋め込みの表示、`data=history\|version` でJSON、`do=restore\|merge-restore` で復元。どれもそのページの編集の権限が要る。[変更履歴の仕組み](/Tech/BackupUI#受け付ける要求)参照 |
| `/.history.css`, `/.history.js` | 「履歴」タブの資材（`_sys/backupui/`） |
| `/.restart` | サービスの再起動。GETで確認画面、POSTで実行。`?now=1` で画面を介さず受け付ける（こちらもログインが要る）。**既定Wikiの管理者と助手だけ**。[サービスの再起動の仕組み](/Tech/Restart)参照 |
| `/.admin/stafflog` | 助手の操作の記録。一覧・詳細（`?id=`）・元に戻す（POST）。**管理者だけ**（[助手の操作の記録](/Tech/StaffLog)） |
| `/.garbagecollect` | 削除したページ（持ち主のページが無い）の添付を `/trashbox` へ集める。GETで確認画面、POSTで実行。**管理者と助手だけ**。1時間ごとにも全Wikiで行う（[削除したページの添付を集める仕組み](/Tech/GarbageCollect)） |
| `/.newwiki` | 新しいWikiを作る。GETで入力画面、POSTで作成。**既定Wikiの管理者と助手だけ**。[新しいWikiを作る仕組み](/Tech/NewWiki)参照 |
| `/.delwiki` | いまあるWikiを消す。**既定Wikiの管理者と助手だけ**（Wiki名付きのURLは403）。名前・そのWikiの管理者のパスワード・いまの様子・最後の確認の4段。消す前に `wikidata/<Wiki名>.<yymmdd_hhmmss>.7z` へ固める。資材は `/.delwiki.css`。[Wikiを消す仕組み](/Tech/DelWiki)参照 |
| `/.allwiki` | このサーバーの全Wikiの一覧。**既定Wikiの管理者と助手だけ**（Wiki名付きのURLは403）。URL名は `server.yaml` の `farm.allwiki` で決まり、空にすると出さない。資材は `/.allwiki.css`。下の「[Wikiの一覧](/Tech/Reference/Views#wikiの一覧)」参照 |
| `/.editor.css`, `/.editor.js` | 編集画面の資材（`_sys/editor/`） |
| `/.section/<ページパス>?heading=<id>&scope=header\|body` | セクション単位の生テキストの取り出し（GET）と、ページ全体での保存（POST）。**編集の権限（`W`）が要る**。[セクション編集](/Tech/SectionEditing)参照 |
| `/.conflict/<ページパス>` | 編集の競合を統合する画面。**編集の権限（`W`）が要る**。資材は `/.conflict.css`・`/.conflict.js`。[編集の競合を統合する画面の仕組み](/Tech/ConflictMerge)参照 |
| `/.plugin/<プラグイン名>` | プラグインの `_action` を呼ぶ（`#comment` の書き込み、`#vote` の投票、`/.plugin/updateDB` など）。`/.plugin/<名前>.css` のような名前はプラグインの資材を返す。[プラグインの開発方法](/Tech/dev_plugin)参照 |
| `<ページパス>?cmd=preview`（POST） | 送信した生テキストをレンダリングしたHTML断片を返す。**編集の権限（`W`）が要る**。[セクション編集](/Tech/SectionEditing)参照 |
| `<ページパス>?cmd=diff`（POST） | 送信した生テキストと、保存されている内容の差分をHTMLで返す。**編集の権限（`W`）が要る**。[編集機能の仕組み](/Tech/EditGuide/Diff)参照 |

- `.txt` を優先し、無い場合のみ `.md` にフォールバックする。
- 該当ファイルが無い場合は、テーマを適用して「このページはまだありません」を表示し、HTTP 404 を返す。あわせて `cmd=edit` を送る「このページを作る」を出す（`=` や `.` で始まる作れない名前では出さない）。
- 存在しないWikiへのアクセスは、テーマも設定も辿れないので、どのテーマにも依存しないHTMLで「アクセスしたWikiは存在しません」を表示する（HTTP 404）。
- テーマ資材・添付ファイル・`/.section`・`/.plugin` など、ページではないURLは `no page`（text/plain、HTTP 404）を返す。
- **編集に連なる操作は、ページ自身の通常URLへ POST する**（`cmd=edit`・`save`・`draft`・`attach`・`preview`・`diff`）。URLを見ただけでは編集の入口があると分からないようにするため。`preview` と `diff` だけは本文を生テキストのまま本体に載せるので、`cmd` をクエリで受ける。
- 本文中のリンク・画像参照（`href="..."` / `src="..."`）の意味づけは **`resolve_link(page_subpath, href)`（`paths.py`）の1か所**で決まる。記法によらず、表示（`rewrite_content_links()`）と[リンクの記録](/Tech/PageDataBase#links本文が指しているリンク)が同じ答えを使う。戻り値は3種類。

  | 種類 | 対象 | 解決先 |
  |---|---|---|
  | `page` | `/` で始まるもの、および拡張子の付かないもの | `base_url` を補ったページのURL |
  | `attach` | 拡張子（`.` ＋英数字1〜6文字）で終わるもの | `/.attach/<持ち主の実体パス>/<ファイル名>` |
  | `keep` | 外部URL・`#anchor`・`mailto:`・`tel:`・`=Wiki名` を指すもの・`/.` で始まるシステムのURL | そのまま |

- **相対になるのは `./` `../` で始めたときだけ**で、起点はそのページ自身（親フォルダではない）。裸の名前は**トップからの絶対**になる（本家PukiWikiの `get_fullname()` と同じ決まり）。`/foo/bar` に書いた場合、`moge` は `/moge`、`./uha` は `/foo/bar/uha`、`../piyo` は `/foo/piyo`。`..` がトップを越える場合はトップで止める。
- **添付は、ページ名の部分を書かなければ「そのページ」のもの**。書いた場合はページと同じ決まりで読む。`/foo/bar` に書いた場合、`img.jpg`・`./img.jpg` は `/foo/bar` の添付、`../img.jpg` は `/foo` の添付、`../bbb/img.jpg` は `/foo/bbb` の添付、`bbb/img.jpg`・`/bbb/img.jpg` は `/bbb` の添付、`/img.jpg` はトップページの添付。持ち主の実体が `…/index` の場合を見分けるため、`resolve_link()` には `wiki_dir` を渡す（渡さないと `…/index` の解決だけが省かれる）。
- ページの実在は見ない。まだ無いページへのリンクもページとして扱う（「このページを作る」へ進めるため）。
- `attach_subpath` は実際に解決されたファイル（拡張子抜き）のパスで、`/Tech` は `Tech/index` になる。
- **ページ名のルール**: 次の名前は使えない。該当するURLはページが存在しない扱いになる。
  - `=`（Wiki指定）と `.`（システム資材）で始まる名前（パス途中の階層名も同様）
  - 拡張子の形（`PAGE_NAME_EXT_RE` = `\.[A-Za-z0-9]{1,6}$`）で終わる名前。リンクに書いたとき添付ファイルと見分けが付かなくなるため
- 添付ファイルを返せない場合は、**ファイルが無いときも閲覧の権限が無いときも**テキストの404 `File not found`（`attach.attach_not_found()`）を返す。表示が違うと、見比べるだけでページに制限がかかっていると分かってしまうため。
- `.txt` は[PukiWiki記法](/Syntax/PukiWiki)（`wikilib.pukiwiki`）、`.md` は [markdown-it-py](https://github.com/executablebooks/markdown-it-py) の `gfm-like` プリセットでHTMLへレンダリングし、どちらもテーマを通して `text/html; charset=utf-8` で返す。
- パストラバーサル対策済み（Wiki名の検証、`realpath` による `wikidata/<Wiki名>/wiki/` 配下チェック）。
