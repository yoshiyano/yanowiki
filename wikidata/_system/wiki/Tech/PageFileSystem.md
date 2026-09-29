# ページを扱うインターフェイス

ページの読み書きは、呼ぶ側が `open()` や `os.makedirs()` を書かずに済む関数に
まとめてあります。このページはシステム側（`_sys/wikilib/`）の一覧と決まりです。
プラグインから使う早見表は [プラグイン開発で使える汎用関数](/Tech/dev_plugin/functions) にあります。

## 気をつけること

- **ページかフォルダかを二択で判定しない。** 両方真がありえます
- **`open` / `os.makedirs` / `os.remove` を自分で書かない。** 下の表の関数を使います
- **「ある」がどの意味かを決めてから関数を選ぶ。** 平文・公開・書きかけは食い違います
- **実体を動かす処理を自分で書かない。** 随伴物の一覧は `move_page_records` だけが持っています

どれも、取り違えるとエラーが出ないまま静かにページが失われる種類のものです。

## OSの世界とwikiの世界の違い

### 1枚のページが、3つの形をとる

`/Tech` の実体は次のどれかで、時間とともに変わります。

```
Tech.txt          PukiWiki記法のページ
Tech.md           Markdown記法のページ
Tech/index.txt    下位ページを持つページ（フォルダの入口）
```

下位ページを作れば `Tech.txt` は `Tech/index.txt` になり、下位を全部消せば戻ります。

### 同じ名前が、ページでもフォルダでもある

`/講義/第07回` は開けるページであると同時に、`演習課題1` を含むフォルダでもあります。
「ページか」「フォルダか」は別々に見ます。

### ページを作ると、別のページが動く

`A` があるところへ `A/B` を作るとき、`os.makedirs("A")` してから `A/B.txt` を書くと、
OSとしては成功しますが `A` が読めなくなります。`resolve_page_ref` はフォルダがあれば
中の `index` を読むので、`A.txt` は誰からも辿れなくなります（`pagedb.shadowed_pages` が
拾う状態）。

正しくは、先に `A.txt` を `A/index.txt` へ移し、添付・変更の記録・書きかけ・DBの行も
付け替えます。これを呼ぶ側に覚えさせないのが、このインターフェイスの目的です。

### 「ある」に3つの意味がある

| 意味 | 見る先 | 使う場面 |
|---|---|---|
| 平文ファイルがある | `resolve_page_ref(...).exists` | 編集・保存 |
| 公開されている | `pagedb.published_ref` / `load_page_body` | 表示・一覧 |
| 書きかけを預かっている | `draft.has_draft` | 一覧での目印 |

平文だけ置いて取り込んでいなければ「ファイルはあるが公開されていない」、書きかけだけ
あれば「まだどこにも無いが作りかけ」です（ページ選択ダイアログは `has_file`、
編集画面の「履歴」タブは `published` を見ています）。

### ページには、本文以外の随伴物がある

実体パス（subpath）が変わると、次のすべてを一緒に動かします。

```
本文          wiki/<subpath>.<ext>
添付          attach/<subpath>/
変更の記録    pageinfo/backup.db
書きかけ      pageinfo/draft/（.draft と .draft.origin）
DBの行        pageinfo/wikiall.db（本文・タイトル・目次・リンク）
```

この一覧は `pagemove.move_page_records` の1か所にしかありません。

## OSの何にあたるか

| OSでの書きかた | wikiでの相当 | 置き場所 |
|---|---|---|
| `os.listdir(d)` | `page_children(wiki_dir, prefix)` | `pagedb` |
| `os.stat(f)` | `page_entries(wiki_dir, prefix)` の1行 | `pagedb` |
| `open(f)` （表示） | `published_ref(wiki_dir, pagepath)` | `pagedb` |
| `open(f)` （編集） | `resolve_page_ref(wiki_dir, pagepath)` | `paths` |
| `open(f, "w")` | `save_page(wiki_dir, config, subpath, ext, text)` | `pagesave` |
| `os.makedirs(d)` | 要らない（`save_page` が途中の階層を入口へ移す） | — |
| `os.remove(f)` | `delete_page(wiki_dir, config, ref)` | `editor` |
| `os.replace(a, b)` | `move_page(wiki_dir, config, 旧subpath, 新subpath)` | `pagemove` |
| （名前の変更、リンクの直しつき） | `rename_page(wiki_dir, config, subpath, 名前, 置き場所)` | `pagerename` |
| `os.path.isfile(f)` | `resolve_page_ref(...).exists` | `paths` |
| `os.path.isdir(d)` | `page_children(...)` が空でないか | `pagedb` |
| `os.walk(d)` | `page_entries(wiki_dir, prefix)`（その下を平坦に全部） | `pagedb` |
| `glob` | `pagelist.glob(wiki_dir, "Tech/*")`（権限で絞った一覧） | `pagelist` |
| `os.path.join` の安全版 | `safe_join(base, *parts)`（境界の外へ出たらNone） | `paths` |

この表の関数（`pagelist` 以外）はシステム用で、権限を見ません。読み手に見せる一覧は
`pagelist`（`scandir`・`glob`・`walk`・`filter`）から取ります（[ページの一覧を作る](/Tech/PageList)）。
名前とパスの読み替えは `paths` にあります（[リファレンス](/Tech/Reference/Resolve#index-の決まりを持っている場所)）。

## 決まり

### 書くときは `save_page` を使う

`pagesave.save_page` は次の順で行います。

1. 途中の階層にページがあれば入口へ移す（`pagemove.ensure_folder_path`）
2. 変更前との差分を記録する（書き換える前でないと取れない）
3. 平文ファイルを書き出す
4. DBに本文・タイトル・目次・リンクを入れ直す

`write=False` は、置かれているファイルを後から記録するとき（取り込み）だけ使います。
3を飛ばし、1も行いません（平文の置きかたは、置いた人が決めたものなので動かさない）。

### ページの名前は pagepath で受ける

外から受け取る名前（URL・プラグインの引数・フォームの値）はページパス
（`Tech/dev_plugin`）です。実体パス（`Tech/dev_plugin/index`）や拡張子は外に出しません。
読み替えは `resolve_page_ref` が行い、`PageRef` が `pagepath` / `subpath` / `ext` / `path` を
まとめて運びます。取り違えると `index` を取りこぼします（`/Tech` の編集が `Tech.md` を作る、
トップページの添付が引けない、など）。

### 消したあとは、階層を畳む

`editor.delete_page` は、本文を消したあと空のフォルダを片付け（`remove_empty_dirs`）、
入口だけになったフォルダをページに戻します（`pagemove.convert_folder_to_page`）。
添付ファイルが残っているページは削除しません。
それ以外の経緯で残った空のフォルダは、取り込みが片付けます（`pagesync.prune_empty_folders`、
[書き込まれる手順](/Tech/PageDataBase/Writes#空のフォルダを片付ける)）。

## まだ揃っていないもの

必要になった時点で足します。

| 欲しくなりそうなもの | いまの代わり | 備考 |
|---|---|---|
| `page_state(wiki_dir, pagepath)` | `resolve_page_ref` と `page_children` を別々に呼ぶ | 「ページか」「フォルダか」を1回で返す |
| システム用の `walk`・`glob` | `page_entries(wiki_dir, prefix)` | 階層のまま辿る形・パターンで選ぶ形は、読み手向けの `pagelist` にだけある |
| `delete_page` の置き場所 | `editor` にある | ページパスで受ける形にして `pagemove` 側へ移すのが筋 |
