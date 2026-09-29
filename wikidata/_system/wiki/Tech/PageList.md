# ページの一覧を作る（`wikilib.pagelist`）

**読み手に見せるページの一覧は、すべてこの層を通します**（Wiki設計者の指示、2026-09-17）。
一覧を得る関数を4つに絞り、その中で必ず閲覧の権限を見ます。

以前は `#ls`・`#recent`・検索・`/.pagetree` がそれぞれ自前で一覧を作っていました。
[ページごとの権限](/Tech/PagePermissions) の判定を各所に書くと、書き漏らしが穴になり、
書いても食い違うため、1か所にまとめました。

## 4つの関数

```python
from wikilib import pagelist

pagelist.scandir(wiki_dir, under="Tech")     # 1階層ぶん（os.scandir にあたる）
pagelist.glob(wiki_dir, "Tech/*")            # パターンに当たるもの
pagelist.walk(wiki_dir, under="Tech")        # その下のページ全部
pagelist.filter(wiki_dir, names)             # 手元にある名前の並びを絞る
```

更新順（`#recent`）・アクセスの多い順（`#popular`）・検索の候補のように、ディレクトリの
列挙ではない一覧は、自分で並びを作ってから `filter` に通します。並び順は渡したままです。
名前は既定でページパスとして読み、`by="subpath"` なら実体パスとして読みます。

## 返す項目（`PageItem`）

名前だけでなく、一覧に出す値をまとめて返します（`pagedb.page_entries` が1回のSQLで
揃えた値を、使う側で引き直さずに済むように）。

| 属性 | 意味 |
|---|---|
| `name` | 直下の名前（`scandir` のときに意味を持つ） |
| `pagepath` | URL上のページパス（`""` はそのWikiのトップ） |
| `subpath` | 実体のwiki相対パス（拡張子抜き、`index` 解決済み） |
| `title` | 見出し。無ければ空文字列 |
| `created` / `updated` / `size` | DBの値 |
| `exists` | ページの実体があるか（`scandir` が返す、通り道でしかないフォルダだけ偽） |
| `has_children` | その下にページがあるか |
| `privilege` | いまの閲覧者のアクセス権（`W`/`R`/`-`） |

名前は [`PageRef`](/Tech/Reference/Resolve#対象ページの特定) に揃えてあります。

並びはページパスの順です（DBの実体パス順のままだと、`Tech/index` が `Tech/Secret` の
後ろに来てしまうため）。

## `need`（どこまで要るか）

| 値 | 残るもの |
|---|---|
| `PAGE_READ`（既定） | 読めるページ（`R` と `W`） |
| `PAGE_WRITE` | 編集できるページだけ（編集画面の一覧・移し先の選択） |
| `None` | 絞らない。`privilege` は入れて返す |

既定を「読めるもの」にしてあるので、指定を忘れても安全な側に倒れます。

## `source`（どこから採るか）

| 値 | 採る先 |
|---|---|
| `"published"`（既定） | DB。表示・検索・一覧 |
| `"files"` | 平文ファイル。取り込む前のページも出す必要がある、編集の道具だけ |

## 判定器の使い回し

閲覧者は `auth.current_uid` から取り、判定器はその場で作ります（1ms程度）。1回の要求で
何度も一覧を作るなら、`privilege=` に判定器を渡します（プラグインなら `context.privilege`）。

## 使わない場所

取り込み（`pagesync`）・名前の変更（`pagerename`）・日次の控え（`dbbackup`）・DBの
作り直しは、権限と関係なく全ページを見るので `pagedb` を直接使います。`pagelist` に
替えると、権限のせいで取り込みが漏れます。`auth.act_as(auth.SYSTEM_UID)` で包む形も
使えます。

    pagedb・backup・accesslog   記録をそのまま読む層（権限を見ない）
    pagelist                    読み手に見せる一覧を作る層（必ず権限を見る）

## 載せ替えの状況

| 呼ぶ側 | 状態 |
|---|---|
| `#recent`・`#popular`・`#ls`・`#navi` | 載せ替え済み |
| 検索（`/.search`） | 権限の判定は入っている。ただし `pagelist` は通さず、`search.search_matches` が候補を決めた直後に `privilege.check` で落としている |
| `/.pagetree`・編集画面の一覧 | 載せ替えない（全ページを出す。編集の権限は、開いたときに編集画面が見る） |
| 編集画面の「履歴」タブ（`?cmd=history`） | 載せ替えない（ページの一覧を返さない。1ページずつ見る。[変更履歴の仕組み](/Tech/BackupUI)） |

木に組む処理（`#ls` と `/.pagetree`）は、見せかた（折りたたみ・書きかけの印）が違うので、
当面それぞれに残します。
