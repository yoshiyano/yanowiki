# 関数の早見表

ページ名の変換・解釈・保存・一覧・リンク・添付ファイルの関数です。引数と戻り値の決まりは [プラグインで使う汎用関数](/Tech/dev_plugin/functions#共通する引数戻り値) にあります。

## ページ名 ⇔ ファイルパスの相互変換（`wikilib.paths`）

| 関数 | 役割 |
|---|---|
| `resolve_page_ref(wiki_dir, pagepath)` → `PageRef` | URLのページパスから対象ページを特定する。実在しなくても`PageRef`を返す（`exists=False`）。フォルダを指していれば配下の`index`に解決する。`wiki_dir`の外を指すときだけ`None` |
| `pagedb.published_ref(wiki_dir, pagepath)` → `PageRef` | 表示用。**DBに公開された内容**を運ぶ`PageRef`を返す（未取り込みの平文ファイルがあれば、その場で取り込んでから返す）。いまの閲覧者のアクセス権を`privilege`（`W`/`R`/`-`）に入れる。**`-`でも本文は入っている**ので、出す前に`privilege`を見ること。公開されていなければ`exists=False` |
| `pagepath_of_subpath(subpath)` → ページパス | `resolve_page_ref`の逆。実体パス（拡張子抜き、`index`込み）からURLのページパスを求める。ファイル側から辿る一覧処理で使う |
| `full_pagepath(base_pagepath, name)` → ページパス | リンク先に書かれた相対記法（`./abc`・`../abc`・裸の`abc`）を解決する。`base_pagepath`はいま開いているページ（解決の基点）、`name`はリンク先として書かれた文字列 |
| `resolve_link(page_subpath, href, wiki_dir=None)` → `(kind, value)` | 書かれたリンク先文字列の意味を決める。`page_subpath`は基点となるいま開いているページの実体パス、`href`は書かれたリンク先文字列。`kind`は`"page"`/`"attach"`/`"keep"`のいずれか、`value`は種別に応じた値（ページパス、または実体パス+ファイル名） |
| `page_file_path(wiki_dir, pagepath, ext)` → 絶対パス | ページの保存先を決める。`wiki_dir`の外へ出るパスは`None` |
| `page_ext_of_subpath(wiki_dir, subpath)` → 拡張子 | 実体パス（拡張子抜き）から、そのページの記法（`.txt`/`.md`）を決める |
| `is_valid_pagepath(pagepath)` → bool | `=`（Wiki指定）・`.`（システム資材）で始まる名前を弾く |

## ページのparse処理（`wikilib.render` / `wikilib.links`）

| 関数 | 役割 |
|---|---|
| `render.parse_source(engine, text, ext, env=None)` → tokens | 生テキストをその拡張子の記法（Markdown/PukiWiki記法）でトークン列にする。`env`は`{"wiki": context}`の形（markdown-itのレンダリング環境）。PukiWiki記法もmarkdown-it-py互換のトークン形になるため、この表の関数はどちらの記法でも共通で使える |
| `render.render_source(engine, text, ext, first_h1_as_title, context=None, toc_depth=None)` → `(html, title, toc)` | 生テキストを丸ごとHTML化する（parse + タイトル抽出 + 目次組み立て + レンダリングをまとめて行う）。`first_h1_as_title`は先頭のh1見出しをタイトルとして抜き出すか、`toc_depth`は目次に含める見出しの深さの上限、`html`はレンダリングされた本文HTML |
| `render.build_toc(tokens, max_level=None)` → toc | 見出しトークンから目次データを組み立てる。`max_level`は`toc_depth`と同じ意味（引数名が関数ごとに違う） |
| `render.heading_positions(tokens)` → positions | 見出しごとの生ソース上の行範囲一覧（`positions`。セクション編集で使う。目次には使わない） |
| `links.extract_page_info(engine, text, ext, subpath, first_h1_as_title=True, wiki_dir=None, interwiki=None)` → `(title, toc, links)` | 本文から3点セットを取り出す。保存前後の差し替え・取り込みで使う。`interwiki`はInterWikiの登録表 |
| `context.page_headings(max_depth=6)` → toc | このページの見出し一覧を返すプラグイン向けショートカット（`max_depth`は目次に含める深さの上限）。**DBに取り出し済みの目次を読む**（全文をパースし直さない）。使用例: `plugin/contents.py` |

## ファイルの保存（DB登録を含む）（`wikilib.pagesave`）

**本文を保存するときは、DBを個別に触らず `save_page` を使います。** バックアップ・平文の書き出し・DB登録の3つを
正しい順番で揃えて行います（一部だけだと差分や検索・一覧が壊れます）。

| 関数 | 役割 |
|---|---|
| `pagesave.save_page(wiki_dir, config, subpath, ext, text, engine=None, path=None, known=None, merge=True, write=True, created=None)` → bool | ページ1枚分を保存したことにする。バックアップ→平文ファイル書き出し→DB登録までをまとめて行う。`path`は書き出す先（省略時は`subpath`+`ext`から決める）、`known`は差分の基準にする「変更前」の内容（省略時はDBの内容）、`merge`は直前の差分と統合してよいか、`write`は平文ファイルを書き出すか、`created`は新規登録時の初回登録日時 |
| `pagesave.remove_page(wiki_dir, subpath, known=None)` → bool | ページが消えたことを記録する（消える前の内容をバックアップに残してからDBの行を消す）。`known`は`save_page`と同じ意味 |

`pagedb.record_page`/`record_page_info` は `save_page` の内部で使う関数で、取り込み処理のような特殊な場面のほかは
直接呼びません。

## ファイルの一覧取得（`wikilib.pagedb` / `wikilib.paths`）

一覧は平文ファイルではなくDBから組み立てます（公開済みの内容に揃い、タイトル・更新日時・大きさも揃っている）。

#note(type=warn){{
**画面に出す一覧は [`wikilib.pagelist`](/Tech/PageList) から取ります。** `pagedb` は閲覧の権限を見ないので、
直接使うのは全ページを見る必要があるシステム側の処理だけです。
}}

| 関数 | 役割 |
|---|---|
| `pagedb.page_entries(wiki_dir, prefix="")` → `[{subpath, path, title, created, updated, size}, ...]` | **本文を除いた**一覧。ページ一覧やフォルダツリーを作るならこれで足りる。`prefix`（`"Tech/"`のように末尾`/`込み）でその下だけに絞れる。`created`/`updated`は登録日時・最終更新日時、`size`はファイルサイズ（バイト） |
| `pagedb.all_pages(wiki_dir)` → `[{...}, ...]` | 本文込みの全件（`page_entries`と違い重い。本文自体が要る場合のみ） |
| `pagedb.all_subpaths(wiki_dir)` → `[subpath, ...]` | 登録されている全ページの実体パスだけ |
| `pagedb.iter_page_texts(wiki_dir)` / `iter_page_texts_of(wiki_dir, subpaths)` / `page_texts_of(wiki_dir, subpaths)` → `(subpath, title, body)`の並び | 1件ずつ、または指定したページだけ返す。全件を一度にメモリへ載せない`iter_*`と、リストで受け取る`*_of` |
| `pagedb.recent_pages(wiki_dir, limit=None)` → `[{...}, ...]` | 更新の新しい順。全ページ対象、`limit`（返す件数の上限）省略で無制限 |
| `pagelist.walk(wiki_dir, under="", need, source, privilege)` → `[PageItem, ...]` | **画面に出す一覧はここから取る**（[ページの一覧を作る](/Tech/PageList)）。`scandir`・`glob`・`filter` も同じ形で、閲覧の権限はこの中で見る。使用例: `plugin/recent.py`・`plugin/popular.py` |
| `pagedb.subpaths_containing(wiki_dir, term)` → `{subpath, ...}` | 本文かタイトルにその語（`term`）を含むページの実体パス集合（絞り込みをSQLite側に任せる） |
| `paths.iter_pages(wiki_dir)` → `(ページパス, 本文)`の列 | **DBを経由せずファイルシステムを直接走査**する。DB再構築（`pagedb.rebuild`）など特殊な場面向けで、通常の一覧・検索には同じ表の`pagedb.*`（DB版）を使う |

## リンク・バックリンク（`wikilib.pagedb` / `wikilib.links`）

| 関数 | 役割 |
|---|---|
| `pagedb.links_of(wiki_dir, subpath)` → `[ページパス, ...]` | そのページが参照している先（先頭に`/`が付いた形、名前順） |
| `pagedb.backlinks_of(wiki_dir, owner)` → `[ページパス, ...]` | そのページ（または配下の添付ファイル）を指しているページ（名前順、索引ずみで1クエリ）。`owner`はリンクされている側（持ち主）のページパス |
| `pagedb.link_rows_of(wiki_dir, subpath)` → `{書かれた文字列: (種別, 持ち主, ファイル名)}` | リンクの解決結果 |

`PLUGIN_INFO["args"]` の項目に `"link": True` を宣言すると、その値は自動でリンク元DBに記録され、`backlinks_of` から
見つかります（[プラグイン仕様](/Tech/dev_plugin/spec/args#引数の宣言args)）。

## 添付ファイル（`wikilib.attach`）

| 関数 | 役割 |
|---|---|
| `attach.attach_dir_for(wiki_dir, subpath)` → 絶対パス | そのページの添付ファイル置き場（ディレクトリ）を返す |
| `attach.list_attachments(wiki_dir, subpath, base_url)` → `[{name, size, mtime, url, kind, ...}, ...]` | そのページの添付ファイル一覧を返す。`base_url`はサイトのベースURL |
| `attach.attach_kind(name)` → `(種別id, 表示名)` | 拡張子から種別を判定する（画像/文書/その他等）。`name`は添付ファイルのファイル名 |
| `attach.format_bytes(size)` → 文字列 | ファイルサイズを読みやすい単位（`"512 B"`・`"12.3 KB"`のような文字列）にする。`size`はバイト数 |
