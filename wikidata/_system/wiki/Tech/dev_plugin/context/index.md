# context（実行時の情報）

`_setup`/`_convert`/`_inline`/`_action` に渡される `context` から、次のものが参照できます。

| 属性 | 内容 |
|---|---|
| `context.config` | そのWikiに効いている設定（共通の既定値 `config/default.example.yaml` に個別Wikiのものを重ねたもの） |
| `context.farm` | Wiki名 |
| `context.page` | ページパス |
| `context.base_url` | URL接頭辞（`=Wiki名/` の明示・`server.prefix` を含む） |
| `context.explicit_farm` | URLで `=Wiki名` が明示されていたか |
| `context.ext` | いま描いているページの拡張子（`.md` / `.txt`）。記法の見分けに使う |
| `context.wiki_dir` | そのWikiのページ置き場の絶対パス |
| `context.partial` | 部分プレビュー中か |
| `context.debug` | エラー詳細を表示する設定か |
| `context.plugins` | 他のプラグインのレジストリ |
| `context.page_headings(max_depth)` | このページの見出し一覧 |
| （ページの一覧） | `context` ではなく [`wikilib.pagelist`](/Tech/PageList) から取る（閲覧の権限はそこで見る） |
| `context.used_plugins` | このリクエストで呼び出されたプラグイン名の集合。専用のCSS/JSを読み込むかの判定に使う |
| `context.block_view(message, by, status)` | このページの本文を出さないよう頼む（下記） |
| `context.deny_view(by)` | 標準の「閲覧する権限がありません」の画面（403）で止める（下記） |
| `context.privilege` | いまの閲覧者のアクセス権の判定器。`context.privilege.check(ページ名)` で `W`/`R`/`-` を返す（下記「閲覧者のアクセス権に従う」） |
| `context.view_block` | `block_view` で本文を止める印が立っていれば、その内容（`message`・`by`・`status`）。立っていなければ `None` |
| `context.theme_override` | そのページで使うテーマの指定（`#wikitheme` が立てる）。閲覧者がcookieで選んだテーマのほうが優先される |
| `context.plugin_debug_override` | ページ内で `#plugin_debug(true)` が使われたか（既定 `False`）。`plugin.debug` とORで合わさるだけで、無効化はできない |

プラグインが返したHTML中の `/` で始まるリンクには、本文と同じく `base_url` が自動で補われます
（[設計方針](/Tech/DesignPolicy)）。JavaScriptから呼ぶAPIのURLのように、HTMLのリンクとして書かない文字列は、
自分で `context.base_url` を前置します（`ls` の `_action` 宛てURLがこの例）。

## 標準の「閲覧する権限がありません」で止める（`context.deny_view`）

権限が無いために本文を出さないプラグインは、自分で文言を作らずにこれを呼びます（`#readauth` が使う）。

    if not 許可されている:
        context.deny_view(by="myplugin")
        return ""

- ページの権限で断られたときと同じ本文・案内になり（`wikilib.views.no_view_body_html`）、未ログインには
  ログインのリンク（戻り先つき）が付く。ステータスは403
- 中身は `block_view` なので、下の決まり（先に立てたものが効く、「見せない」であって「読ませない」ではない、
  別のページを変換するプラグインは `view_block` を自分で見る）も同じ
- 自分の文言を出したいとき（閲覧期間の案内など）は `block_view` を使う

## ページを出さないよう頼む（`context.block_view`）

閲覧期間の外、役目を終えた、のように、認証とは別の理由でページの表示を止めたいときに呼びます。

```python
def _convert(resolved, body, context):
    if 期間外:
        context.block_view(期間外に出すHTML, by="viewable_period")
    return ""
```

| 引数 | 意味 |
|---|---|
| `message` | 本文の代わりに出すHTML。Wikiテキストで受け取りたいなら、渡す前に `expand_body` などで展開しておく |
| `by` | 止めたプラグインの名前。追いかけるときの手がかり |
| `status` | 返すHTTPステータス。既定は200 |

止まったページは、本文が `message` に差し替わり、目次が消え、題名はページ名になります
（本文の見出しが題名として漏れないように）。

**編集リンクはそのまま残ります**（Wiki設計者の指示、2026-09-05）。閲覧を止めるプラグインが編集まで
止める理由は無く、消すと期間を書き間違えたページを画面から直せなくなるためです。

先に立てたものが効きます（同じページに2つあれば上のほう）。`block_view` は受け付けたかどうかを真偽で返します。

#note(type=warn){{
**これは「見せない」であって「読ませない」ではありません。** 止まるのはページを開いたときの本文の描画だけで、
本文は次のどれからも読めます。

- 編集画面（そのページのURLへ `cmd=edit` をPOST）
- 見出し単位の取り出し（`/.section/<ページ名>`）
- 編集画面の「履歴」タブ（ページのURLへ `?cmd=history`）
- 検索の結果に出る抜粋、`#ls` や `#recent` に出るタイトル

秘密を守る用途には使えません。読ませたくないものは、置かないか、前段のWebサーバーなどで止めます。
}}

### 別のページの本文を変換するプラグインは、自分で見に行くこと

印が立つのは、その変換に渡した `context` だけです。[`#include`](/Syntax/Plugin/include) のように別のページを
別の `context`（`sub`）で変換するプラグインは、変換後に `sub.view_block` を見て、あれば `message` に差し替えます。

```python
html, _, _ = render_source(engine, ref.body, ref.ext, ..., sub)
if sub.view_block:
    html = sub.view_block["message"]
```

見に行かないと、止めたはずの本文がそのまま取り込み先に出ます。止まるのは差し込まれた場所だけで、
取り込み元のページは普通に表示します。同じことをするプラグインを作るときは、`plugin/include.py` を手本にします。

## 閲覧者のアクセス権に従う（`context.privilege`・`ref.privilege`）

[ページごとの権限](/Tech/PagePermissions)に従うための値です。`W`（閲覧・編集）・`R`（閲覧だけ）・`-`（不可）の3つで、
比べるときは `wikilib.auth` の `PAGE_WRITE`/`PAGE_READ`/`PAGE_NONE` を使います。

別のページの本文を読むときは、`published_ref` の戻り値の `ref.privilege` を見ます。
**`-` でも `ref.body` には本文が入っている**ので、出す前に必ず見ます。

```python
from wikilib.auth import PAGE_NONE
from wikilib.pagedb import published_ref

ref = published_ref(context.wiki_dir, page)
if ref is not None and ref.privilege == PAGE_NONE:
    return '<div>このページを閲覧する権限がありません</div>'
```

ページの一覧は [`wikilib.pagelist`](/Tech/PageList) の `scandir`（1階層）・`glob`（パターン）・`walk`（下位すべて）・
`filter`（手元の並びを絞る）で作ります。閲覧の権限はその中で見ます。`privilege=context.privilege` を渡すと、
判定器の準備が1回で済みます。

```python
from wikilib import pagelist

items = pagelist.walk(context.wiki_dir, under="Tech", privilege=context.privilege)
for item in items:          # item.pagepath / title / updated / size / privilege
    ...
```

平文を読み書きするとき（`resolve_page_ref` の戻り値は `privilege` を持たない）や、ページ名だけで判定したいときは
`context.privilege` を使います（判定器は最初に聞かれたときに作り、その `context` のあいだ使い回します）。

```python
if context.privilege.check(pagepath) == PAGE_NONE:
    return plain("このページを閲覧する権限がありません。", status=403)
```

同梱のプラグインと本体は、次のように扱っています。

| 場面 | `-` のとき |
|---|---|
| [`#include`](/Syntax/Plugin/include) | 本文の代わりに「このページを閲覧する権限がありません: ページ名」 |
| [`#ls`](/Syntax/Plugin/ls) の読み込み表示（ajaxview） | 「このページを閲覧する権限がありません。」 |
| `context.page_headings`（[`#contents`](/Syntax/Plugin/contents)） | 空の一覧 |
| テーマのメニュー（`themes.render_menu`） | 出さない |
| `#comment`・`#vote` の書き込み（`_action`） | 403で断る。`R` は通す（プラグインによる書き換えは編集とは別に数える） |
| `#tasklist` のチェックの切り替え（`_action`） | `W` でなければ403（`context.privilege.check(page) != PAGE_WRITE`） |
| `#recent`・`#popular` の一覧 | 並ばない |
| `#ls` の一覧 | 並ばない（中身が全部隠れたフォルダも出ない） |

## よくある使いかた

参照の解決、DB由来の情報の取得、子ページの埋め込み、呼ばれたことの記録といった使いかたの例は
[よくある使いかた](/Tech/dev_plugin/context/Recipes) にあります。
