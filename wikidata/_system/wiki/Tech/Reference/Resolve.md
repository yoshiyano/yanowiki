# 対象ページの特定と index の決まり

URLからページの実体を決める手順と、`index` の決まりを持っている場所です。

## 対象ページの特定

上の表の解決（`index` へのフォールバック、`.txt`→`.md`、配下チェック）は
**`resolve_page_ref(wiki_dir, pagepath)` の1か所**で行い、表示・編集・保存・
プレビュー・セクション取得・プラグインのすべてが同じ答えを使います。

戻り値の `PageRef` は、ページがまだ無くても次を持ちます（wiki配下から外れるパスの場合のみ `None`）。

| 属性 | 意味 |
|---|---|
| `pagepath` | URL上のページパス（`""` ならそのWikiのトップ） |
| `subpath` | 実体のwiki相対パス（拡張子抜き、`index` 解決済み） |
| `ext` | 拡張子。実在すればそのファイルのもの、無ければ既定の書式（`DEFAULT_MARKUP`、いまは `.txt`） |
| `path` | 実ファイルの絶対パス（実在しない場合は「保存するならここ」） |
| `body` | 内容（実在しなければ空文字列） |
| `exists` | 実在するか |
| `privilege` | いまの閲覧者のアクセス権（`W`/`R`/`-`）。**`pagedb.published_ref()` が作ったものだけ**が持ち、ここで作ったものは `None`（[ページごとの権限](/Tech/PagePermissions)） |

`subpath` は添付ファイルとバックアップの置き場所にもそのまま使います。

```
pagepath ""      → subpath "index"       （そのWikiのトップ）
pagepath "Tech"  → subpath "Tech/index"  （ディレクトリの場合）
pagepath "Tech/DesignPolicy" → subpath "Tech/DesignPolicy"
```

URL（`pagepath`）と実体（`subpath`）はずれます。取り違えると、`/Tech` の編集が `Tech.md` を
作る、トップページの添付が引けない、といった `index` の取りこぼしが起きるので、両方をここで
一度に決めて持ち回ります。存在しないページでも `None` を返さないのは、新規作成やプレビューでも
同じ判断で足り、呼び出し側に独自のフォールバックを書かせないためです。

逆向き（ファイルからURLを求める）は `pagepath_of_subpath()` です。

## `index` の決まりを持っている場所

`X.txt` とフォルダ `X/` は同居できません（`resolve_page_ref` はフォルダがあれば中の
`index` を読むので、`X.txt` が読めなくなる。`pagedb.shadowed_pages` が拾う状態）。
この決まりに触る処理は次の4つに集めてあります。

| 何を | どこが |
|---|---|
| 名前（`"index"`）そのもの | `paths.INDEX_NAME` |
| その実体パスは入口か | `paths.is_folder_entry(subpath)` |
| 実体パス → ページパス | `paths.pagepath_of_subpath(subpath)` |
| フォルダ → 入口の実体パス | `paths.entry_subpath_of(folder)` |

URLから実体を求める向きは `resolve_page_ref` の担当です（フォルダが実在するかを
ファイルシステムに聞く必要があるため）。

実体を `X` と `X/index` の間で動かすのは [`wikilib.pagemove`](/Tech/RenamePage) だけです。
本文・添付・変更の記録・書きかけ（`.draft` と `.draft.origin`）・DBの行をまとめて付け替えます
（`move_page_records`）。
