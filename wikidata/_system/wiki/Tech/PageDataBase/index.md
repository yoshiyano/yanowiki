# ページのデータベース

`pageinfo/wikiall.db`（SQLite、`_sys/wikilib/pagedb.py`）は、平文ファイルと同じ内容を
DBにも持たせたものです。次に使います。

- 全文検索（SQLで絞ってから読む）
- 更新順の一覧（`recent`）
- ページ一覧やプラグインからの参照（タイトル・目次）
- ページ間のリンクと逆リンク
- **保存時の差分の基準**（システムが最後に知っていた内容）

最後のものが無いと、システムを通さずに書き換えられたページの差分が取れません
（平文だけを見ると、直接編集した内容が「元の内容」に見えてしまうため）。

どの場面でDBを読み、どの場面で平文を読むかは
[リファレンス](/Tech/Reference/DataSource#どこがdbを読みどこが平文を読むか)にあります。

## DBが公開済み、平文は作業中

DBに入っているものが公開されたページです。平文ファイルは、その書き出しと、まだ
取り込んでいない作業中の内容が混ざったものです。表示・検索・差分の基準はDBを見ます。

**編集画面だけは平文を読みます。** DBを読むと、直接編集した分が画面に出ないまま
上書き保存され、消えてしまうためです。

DBが壊れても平文から作り直せます（[壊れたとき](#壊れたとき)）。

## スキーマ

テーブルは `pages` と `links` の2つだけです（Wikiごとの `pageinfo/wikiall.db`）。定義は
`pagedb.SCHEMA` で、DBを開くたびに `CREATE … IF NOT EXISTS` でそろえます（`pagedb.connect()`）。
全文検索用のテーブル（FTS）は持ちません。

### pages（本文とその派生情報）

| 列 | 型 | 制約 | 内容 |
|---|---|---|---|
| `subpath` | TEXT | 主キー | `wiki/` からのパス（拡張子抜き）。ページの識別子（例 `Tech/PageDataBase/index`） |
| `path` | TEXT | NOT NULL | ファイル名（`wiki/` からのパス、拡張子込み。`.md` か `.txt`） |
| `body` | TEXT | NOT NULL | 平文 |
| `created` | TEXT | NOT NULL | 初回登録日時（`YYYY-MM-DD HH:MM:SS`、サーバーのローカル時刻） |
| `updated` | TEXT | NOT NULL | 最終更新日時（同じ書式）。本文か拡張子が変わったときだけ進む |
| `size` | INTEGER | NOT NULL | ファイルの大きさ（バイト） |
| `mtime` | REAL | NOT NULL | 登録した時点のファイル更新時刻（UNIX 時刻、秒）。0 のときは、次の取り込みで必ず読み直す（DBのバックアップ `wikiall.db.zip` から戻した直後の値） |
| `bodyhash` | INTEGER | NOT NULL、既定値 0 | 本文のCRC32（符号なし）。中身が本当に変わったかを見分ける |
| `title` | TEXT | NULL可 | ページの見出し（本文から取り出したもの）。見出しが無ければ `""`。取り出す前は NULL |
| `toc` | TEXT | NULL可 | 目次（JSON。`level`・`id`・`title` を持つ要素の配列）。NULL は「まだ取り出していない」の意味で、`"[]"`（見出しが無かった）とは区別する |

1ページ1行で、履歴は持ちません（履歴は `pageinfo/backup.db`。
[バックアップ](/Tech/EditGuide/Save#バックアップ差分の記録)）。

### links（本文が指しているリンク）

| 列 | 型 | 制約 | 内容 |
|---|---|---|---|
| `source` | TEXT | 複合主キー | 本文を持つページの実体パス（`pages.subpath` と同じ形） |
| `href` | TEXT | 複合主キー | 本文に書かれたままのリンク先の文字列（`source` との組で主キー） |
| `kind` | TEXT | NOT NULL | `"page"` か `"attach"` |
| `owner` | TEXT | NOT NULL | 指している先の持ち主。先頭が `/` の絶対のページパス（例 `/Tech/Groups`）。ページならその先そのもの、添付ファイルならそれを持つページ |
| `filename` | TEXT | NULL可 | 添付ファイルなら名前。ページなら NULL |

- `href` は書かれたままの文字列で、位置は持ちません。位置は本文に `pagelinks.link_spans` を
  かければ毎回見つかるので、ここは「その文字列が何を指すか」の解決結果のキャッシュです。
- `owner`・`filename` はURLに書くときの形にそろえます（アンカーを落とし、`X/index` は `X` に、
  パーセントエンコードは戻す）。2通りに分かれると突き合わせで取りこぼすためです。

拾うのは、本文の書きかたとして書かれたリンク（`pagelinks.link_spans`）と、プラグインの引数のうち
`"link": True` と宣言されたもの（`wikilib.links.plugin_arg_links`。[リネームの仕組み](/Tech/RenamePage)）
です。ページか添付かは `pagelinks.resolve_href` が決め、InterWiki・外部URL・別Wiki・
ページ内アンカーはそこで除きます。読みかたは表示のとき（`resolve_link()`）と同じなので、
押したときの行き先と記録が食い違いません。

### 索引

| 名前 | 対象 | 使う問い合わせ |
|---|---|---|
| （主キー） | `pages (subpath)` | 1ページの本文・情報の取り出し（`load_page`）、`subpath` 順の一覧（`page_entries`） |
| （主キー） | `links (source, href)` | そのページから出ているリンクの取り出し（`links_of`・`link_rows_of`） |
| `links_owner` | `links (owner)` | 逆リンク。`owner` を引く1回の問い合わせで求まる（`backlinks_of`） |
| `pages_updated` | `pages (updated DESC)` | 更新の新しい順の取り出し（`recent_pages`） |

`#recent`・`#ls` は `page_entries()` で `subpath` 順に読み、並べ替えは Python 側で行うので、
`pages_updated` は通りません。本文・タイトルの検索（`subpaths_containing`）は `LIKE` で全行を
読み、専用の索引は持ちません。

## title・toc・linksを本文と同じDBに入れている理由

本文から一意に決まる値なので、同じDBに一度に書けば食い違いません（別ファイルだと、
途中で落ちたときに「本文は新しいが目次は古い」状態になり、安く見つける方法がない）。

取り出しは本文の登録より5倍以上遅い（1万ページで本文7秒、取り出し37秒）ので、
作り直しでは本文だけを先に戻し、取り出しは次で埋めます。

- ページを開いたとき（`links.ensure_page_info()`。1ページ数ミリ秒）
- `./wiki.py updatepage`（逆リンクは全ページが揃わないと数えられないので、開かれていない
  ページも埋める）

## 書き込まれる手順

保存・リネーム・直接編集の取り込みで、DBに何がどの順で書き込まれるかは
[書き込まれる手順](/Tech/PageDataBase/Writes) にあります。

## 壊れたとき

開けない・読めない場合は作り直します（`pagedb.ensure_db()`）。平文が正本なので中身は戻ります。
`created` はバックアップのいちばん古い日時、無ければファイルの更新時刻で代えます。

スキーマを変えたとき（列を増やした、`links` の形を変えたなど）は `ALTER TABLE` で移行しません。
`wikiall.db` を削除して `./wiki.py updatepage --force` を実行し、
[本文だけを先に戻して](#titletoclinksを本文と同じdbに入れている理由)、取り出しは開いたときと
`updatepage` で埋め直します。
