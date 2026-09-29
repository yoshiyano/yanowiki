# PukiWikiのデータを移す仕組み

手元のPukiWikiのページと添付ファイルから、このシステムの新しいWikiを作る道具です
（`./wiki.py convwiki`、実装は `_sys/wikilib/convwiki.py`）。

```
./wiki.py convwiki 1ev-c Prog1
```

これで `~/syncthing/pukiwiki/1ev-c/` をもとに `wikidata/Prog1/` ができ、`/=Prog1/` で開けます。

## 使いかた

| 書きかた | 何をするか |
|---|---|
| `convwiki <元> <Wiki名>` | 写して新しいWikiを作る（管理者の最初のパスワードを聞きます） |
| `--dry-run` | 何も書かずに、何をどこへ写すかだけを出す |
| `--title` | トップページの見出し（省略するとWiki名） |
| `--password` | 管理者の最初のパスワード（省略すると聞きます） |
| `--src-root` | 変換元の置き場所（既定は `~/syncthing/pukiwiki`） |
| `--include-system` | PukiWikiの設定ページ（`:config` など）も写す |
| `--include-stock` | PukiWiki付属のページも写す |
| `--toppage` | `index` にするページ（省略するとPukiWikiの `$defaultpage`） |
| `--theme` | 写したWikiで使うテーマ（既定は `pukiwiki_default`） |

変換元は、名前だけ（`1ev-c`）なら既定の置き場所の下、`/` を含むならパスとして扱います。
まず `--dry-run` で確かめてから実行します。

**既にあるWikiには書き込みません。** 入れ直すときは `wikidata/<Wiki名>/` を消してから実行します。

## 本文はそのまま写す

PukiWiki記法はこのシステムがそのまま読める（[記法](/Syntax/PukiWiki)）ので、文面は書き換えません。
落とすのは、PukiWikiが本文の先頭に書き足す2行だけです（先頭にある分だけで、本文の途中は触りません）。

| 落とすもの | なぜ |
|---|---|
| `#author("2026-04-10T10:11:18+09:00","","")` | PukiWikiの管理行。同名のプラグインが無く、残すとエラーになる。時刻は更新日時に使う |
| `#freeze` | 凍結の印。このシステムに凍結は無い（権限で行う） |

PukiWikiの設定ページ（`:config/…`。`--include-system` で写せる）、履歴（`backup/` `diff/` `counter/`
`cache/`）、添付の旧版（`…_ファイル名.1`）、syncthingの競合ファイル（`*.sync-conflict-*`）も写しません。
履歴は形式が違うので移せません。元のPukiWikiを残しておけば、そちらで読めます。

### PukiWiki付属のページは写しません

どのWikiにも入っている、書いた人の中身ではないページは写しません（`--include-stock` で写せます）。

- 次の15枚（`STOCK_PAGES`、完全一致）

  ```
  AutoTicketLinkName  BracketName   FormattingRules  Help        InterWiki
  InterWikiName       InterWikiSandBox  PHP          RecentChanges
  RecentDeleted       SandBox       WikiEngines      WikiName
  WikiWikiWeb         YukiWiki
  ```

- 説明書の `PukiWiki` とその配下（`PukiWiki/1.4/Manual/Plugin/A-D` など。`STOCK_FOLDERS`、前方一致）

増やすときは、ページ1つずつなら `STOCK_PAGES`、フォルダ丸ごとなら `STOCK_FOLDERS` に足します。

## プラグイン呼び出しの手当て

次の3つは、書き換えないとエラーになる、またはプラグインが展開されないので書き換えます。

### 非標準プラグインを標準プラグインへ

`attachref` → `ref`、`ls2` → `ls` へ、名前だけを機械的に置き換えます（`rewrite_plugin_aliases`）。
役割も引数の並びも同じです。

空引数（`&attachref();`）や本家固有のオプション（`#ls2(,title)` の `title`）は置き換えた先でも動きませんが、
置き換えずに残すと常にエラーになるもの（実データで840件超）に比べて1割未満なので、
機械的に置き換えます（Wiki設計者の指示、2026-09-18）。

ブロック・インラインのどちらも対象です。名前の直後が `(` か `;` かを確かめるので、
`#ls2を使うと一覧になります` のような地の文は巻き込みません。

### ブロックプラグインの誤ったセミコロン

`#navi(データ型);` のように、ブロックプラグインの後ろに `;` が付いていると、プラグインとして展開されず
文字列のまま出ます（`pukiwiki.PLUGIN_BLOCK_RE` は末尾の `;` を許さない）。この `;` を落とします
（`strip_block_semicolons`）。対象は `#name(args);` の単純形だけで、本体つきの形は実データに例が無いので
扱いません。

### `#navi` を `#navi(..)` に

`#navi(..)` と書くべきところに、親のページ名を絶対パスで書いている本文を、**直接の親と同じ名前のときだけ**
`#navi(..)` に直します（`rewrite_navi_home`）。相対で書かれたものや、親と違う場所を指すものは触りません。

    演習/第01回/p1-1.c に書かれた #navi(演習/第01回)  → #navi(..)
    講義/第01回        に書かれた #navi(講義)          → #navi(..)
    どこかに書かれた   #navi(../)（すでに相対）         → 触らない

子を持つページ（実体が `<名前>/index`）でも、`pagepath_of_subpath` で `/index` を剥がしてから親を数えるので、
`演習/第01回` に書かれた `#navi(演習)` は `#navi(..)` になります。

## 更新日時は `#author` の時刻を使う

写した先のファイルの更新日時には、`#author` の時刻を入れます（無ければ元ファイルの更新日時）。
PukiWikiのファイルはコピーや同期でまとめて新しくなっていることがあるためで、`#recent` の並びが
PukiWikiでの見えかたと揃います。

## 名前の付け替え

PukiWikiのページ名は、ほぼそのままページパスになります。手を入れるのは次の2つだけです。

| 元の名前 | 写した先 | なぜ |
|---|---|---|
| `$defaultpage` のページ | `index` | このシステムのトップページは `index`。どのページがトップかは `pukiwiki.ini.php` から読む（`TopPage` も `FrontPage` もありうる） |
| 子を持つページ `A` | `A/index` | `A.txt` とフォルダ `A/` は同居できない（[ページを扱うインターフェイス](/Tech/PageFileSystem)） |

メニューのページ（`MenuBar`・`RightBar`）は名前を変えず、設定（`theme.menu1_page` / `menu2_page`）を
そちらへ合わせます。本文の `[[MenuBar]]` のような参照がそのまま生きます。

写した先に `index` が既にあるときは付け替えず、報告に出します。ページ名に使えない文字（先頭の `.` と `=`）は
直しますが、直すと別のページと同じ名前になるなら、直さずに写します（「演習」と「演習.」が並んでいる例がありました）。

### トップページを指していたリンクは直します

`index` への改名で壊れるリンクだけは直します。

| 元の書きかた | 写した先 |
|---|---|
| `[[TopPage]]` | `[[TopPage>/]]`（見える文字はそのまま、指し先だけトップへ） |
| `[[トップ>TopPage]]` | `[[トップ>/]]`（[リネーム](/Tech/RenamePage)と同じ書き換え） |

後者は取り込みのあとに `pagerename.fix_links`（ページの名前の変更と同じ道具）で直すので、整形済みやコードの中の
`[[…]]` は触りません。プラグインの引数に書かれたページ名（`&pageaction("TopPage",…);` など）は直りません。

## PukiWikiの設定を引き継ぐ

`pukiwiki.ini.php` と `default.ini.php` から、同じ意味の項目だけを `wikidata/<Wiki名>/config/default.yaml` へ
書きます（各項目に由来のコメントを添えます）。書かない項目は共通の既定値が効きます。

| PukiWiki | このシステム | 補足 |
|---|---|---|
| `$page_title` | `theme.site_title` | 配布時のまま（`PukiWiki`）ならWiki名を入れる |
| `$menubar` | `theme.menu1_page` | サイドバー上段（左） |
| `$rightbar_name` | `theme.menu2_page` | 右のカラム（目次の下） |
| `$nowikiname` | `pukiwiki.wikiname` | 真偽が逆 |
| `$usefacemark` | `pukiwiki.facemark` | |
| スキン | `theme.name` | `pukiwiki_default`。`--theme` で変えられる |
| （写したページ） | `edit.defaultwiki: pukiwiki` | 写したページはすべてPukiWiki記法 |

`$read_auth`・`$edit_auth` のように、このシステムでは別の仕組み（[ページごとの権限](/Tech/PagePermissions)）で
決めるものは設定に書かず、報告と `default.yaml` のコメントに回します。

読むのは上の表の変数だけです（同じファイルに平文の `$adminpass` があるため）。InterWiki（`$interwiki`）や
追加ルール（`$line_rules`・`$facemark_rules`）は、形式の違う別ファイル
（`config/pukiwiki.interwiki.yaml`・`pukiwiki.extrarules.yaml`）に書くものなので引き継ぎません。
追加ルールは、移したあとで設定画面から書き足せます。

## 添付ファイル

PukiWikiの添付 `attach/<ページ名のhex>_<ファイル名のhex>` を、ページのパスをミラーしたフォルダ
（[添付ファイルの管理](/Tech/EditGuide/Attach)）へ写します。`A/index` の形にしたページの添付は
`attach/A/index/` です。持ち主のページを写していない添付は写さず、報告に出します。

## 最後にDBへ取り込む

写し終えたら `pagesync.sync_wiki(force=True)` で、[平文ファイルの取り込み](/Tech/UpdateDB)と同じことを済ませます。
全ページを1回ずつ描くので、描けないページはこの時点で分かります。

## 移したあとに残る仕事

このシステムに無いプラグイン（`attachref`・`ls2` 以外）は、ページの中にエラーとして出ます。どれがいくつ
使われているかは実行時の報告（`--dry-run` でも）に出ます。プラグインを増やすかどうかは
[プラグインの開発方法](/Tech/dev_plugin) の話です（`plugin/` は wikiPlugin の持ち物）。

## 確かめたこと（2026-09-18）

`1ev-c`（291ページ）から、252ページ・添付161個ができること（付属15枚・説明書11枚・設定ページ13枚・
syncthingの競合1枚が減る）と、`_sys/_tools/check_pages.py` で全ページが200で開けること。
トップの付け替え、メニューの左右、`[[TopPage]]` の書き換え、`attachref`・`ls2` の置き換え、
`#navi` の280箇所の書き換え、`;` の除去（12箇所）も画面で確かめました。
他の変換元（`mypkwk` 835ページなど）でも試算が通ります。テストは `tests/test_convwiki.py` にあります。
