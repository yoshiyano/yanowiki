# Wiki Farm とURLの設計

1つのサーバーで複数のWikiを動かす構成と、URLの名前空間・既定のWiki・設置場所についての方針です。

## Wiki Farm構成

1つのサーバーで複数のWikiを扱えるよう、`wikidata/` の下に個別Wikiのフォルダを作ります。
全Wiki共通のリソース（`plugin/`, `theme/`, `config/`）をトップレベルに、個別Wikiの専用リソースを
`wikidata/<Wiki名>/` の下に置く2階層で、共通化と個別カスタマイズを両立させています。

## URLの名前空間

URLは原則としてデフォルトのWikiのページパスとして解決し、別のWikiへは `=` を前置した名前（例: `/=sandbox/`）で
アクセスします。Wiki名とページ名が同じ名前空間にあると、先頭のパスがどちらか判別できないためです。
デフォルトのWikiではWiki名を書かずに済み、相対リンクもそのまま働きます。

システムが使う `*.js` や `*.css` などの資材へのアクセスには同様に `.` を割り当てています（例: `/.theme/base.css`）。そのため、`=` と `.` で始まる
ページ名は使えません。

### デフォルトのWikiを明示した場合の扱い

デフォルトのWiki( 例えば defwiki とする)も `/=defwiki/UsageGuide` のように明示して開けます。明示していた場合（`explicit_farm`）は
`base_url` に `=defwiki` を含め、以後のリンクでも `=defwiki/` が保たれます。明示して開いたのに、リンクの先で
暗黙のデフォルトへ引き戻されると、どのWikiを見ているか見失うためです。

### 本文・メニュー中のリンクの書き換え

本文やメニューは `/UsageGuide` のようなルート相対パスで書きます。`base_url` が空でないとき
（`=Wiki名` の明示、`server.prefix` でのサブパス設置）はそのままだとリンクが切れるので、描画後のHTMLの
`href="/..."`・`src="/..."` に `base_url` を補います（`rewrite_content_links`）。添付（`/.attach/...`）も
同じ扱いです。`=Wiki名` を指すリンク・外部URL・`#anchor` はそのまま残します。
`/.admin/configwiki`・`/.search` のようなシステムのURLにも補います（既定以外のWikiで、既定のWikiの画面が
開かないように）。既定のWikiでしか開けない `/.newwiki`・`/.delwiki`・`/.restart`・`/.allwiki` と、別のWikiを指す
`/=Wiki名/…` には、Wiki名の無いサイトの根（`server.prefix` の分）だけを補います。プロキシが入口を伝えているとき
（`X-Forwarded-Prefix`）は根が分からないので、この2つは書かれたまま残します。

同じ関数が、`/` で始まらず拡張子の付いた名前（`logo.png` など）を、そのページの添付
`/.attach/<attach_subpath>/logo.png` に解決します（拡張子の無い裸の名前はトップからのページパス。
[共通の書きかた](/Syntax/Common#リンクとファイルの指しかた)）。`attach_subpath` は実際に解決された
ファイルのパスなので、`/Tech`（実体は `Tech/index.md`）の添付は `attach/Tech/index/` です。

## デフォルトのWikiの役割

デフォルトのWiki（`config/server.yaml` の `farm.default`。以下、既定Wiki）は、URLでWiki名を省けるだけでなく、
**サービス全体の管理を預かるWiki**でもあります。

| 特徴 | 中身 | 詳しく |
|---|---|---|
| サービス全体の操作は既定Wikiの管理者と助手だけ | 再起動（`/.restart`）・Wikiの作成（`/.newwiki`）・削除（`/.delwiki`）・一覧（`/.allwiki`）。判定はいま開いているWikiではなく、既定Wikiの `admin` と `g:staff` で行う（`sysui.require_on_default_farm`）。ほかのWikiの管理者が管理できるのは、自分のWikiの中だけ | [ページごとの権限](/Tech/PagePermissions#restartnewwikiallwiki-は既定wikiの-admin-と-gstaff-だけ) |
| Wiki名を含むURLでは受け付けない | `/=<Wiki名>/.newwiki` などは、既定Wikiの名前でも403。ログインのcookieはWikiごとの `Path` にあり、既定Wikiのものだけが `Path=/` なので、素のURLに絞れば判定に使うcookieが既定Wikiのものひとつに決まる | [再起動の仕組み](/Tech/Restart#誰が実行できるか)・[アカウントの仕組み](/Tech/Accounts) |
| Wikiを消すときは、消される側の管理者のパスワードも要る | 既定Wikiの管理者であることは画面を開いてよい証しで、ほかのWikiを消してよい証しではない。既定Wikiそのものは消せない | [Wikiを消す仕組み](/Tech/DelWiki#誰が消せるか) |
| 既定Wikiを移すと、権限も移る | `/.newwiki` の「既定のWikiにする」や `farm.default` の書き換えで既定Wikiが替わると、元のWikiの管理者は上の操作ができなくなる | [新しいWikiを作る仕組み](/Tech/NewWiki) |
| `_` で始まるWikiは既定にしない予定（**未実装**） | 設置直後の既定Wikiは `_system`。`_` 付きはシステムの見本・説明用なので、`config/server.yaml` を直接編集しない限り既定にできないようにし、新規設置では起動時に用意した新しいWikiを既定にする | [新しいWikiを作る仕組み](/Tech/NewWiki) |

## ページ解決とindex規約

Wikiのトップ（`/=Wiki名/`）も通常のディレクトリ（`Tech/`）も同じ規約で、配下の `index.txt`（無ければ
`index.md`）を表示します。拡張子は `.txt`（PukiWiki記法）を優先し、無ければ `.md`（Markdown）を探します。
新しいページの既定はPukiWiki記法で、編集画面で選び直せます。

## サブパスへの設置

リバースプロキシ配下のサブパスに置くための `server.prefix` があります。接頭辞は「付いていればはずす」ので、
プロキシが接頭辞を落として転送しても、そのまま転送しても動きます。

Wikiごとに外向きの名前を変える場合（外向きの `/sandbox/` を内側の `/=sandbox/` へ中継するなど）は、
プロキシが `X-Forwarded-Prefix` ヘッダで外向きのURLを伝え、システムはその値でリンクを組み立てます
（`wikiconfig.farm_base_url`。組み立てはこの1か所）。設定手順は [インストール](/InstallGuide) の
「Wikiを外向きの別名で公開する」にあります。
