# プラグインの開発方法

ページの中に機能を差し込むプラグインのつくりかたです。呼びかたは
[共通の書きかた](/Syntax/Common#プラグインの呼びかた)、同梱プラグインの仕様は [プラグイン](/Syntax/Plugin) にあります。

**プラグインを追加したら、`/Syntax/Plugin/<名前>` に仕様と使用例のページを作ります。** 一覧は `ls` が
自動で作ります。1行目を `# <名前> — <ひとことの説明>` にし、引数・既定値・表示例・入れ子の可否をそろえて書きます。

## 早見: 1つのURLが指す実体

`/=_system/Tech/dev_plugin` を開いたときの値です（[用語の3つの世界](./functions#共通する引数戻り値)）。

| 変数 | 世界 | この例での値 |
|---|---|---|
| `farm` | — | `"_system"` |
| `explicit_farm` | — | `True`（`=Wiki名`で明示されたアクセスのため） |
| `pagepath` | URL世界 | `"Tech/dev_plugin"` |
| `wiki_dir` | 実ファイル世界（ディレクトリ） | `wikidata/_system/wiki`（絶対パス） |
| `subpath` | 内部識別子 | `"Tech/dev_plugin/index"`（フォルダなので`index`が補われる） |
| `ext` | — | `".md"` |
| `path`（`PageRef.path`） | 実ファイル世界（ファイル） | `wikidata/_system/wiki/Tech/dev_plugin/index.md`（絶対パス） |
| `title` | — | `"プラグインの開発方法"`（`index.md`の1行目`# `から抽出） |

`Tech/dev_plugin` はフォルダなので、`pagepath` と `subpath` がずれます。`subpath` を素朴に組み立てると
別のファイルを指してしまいます。

### URLから実ファイル・タイトルを得る手順

1. `resolve_page_ref(wiki_dir, pagepath)`（`wikilib.paths`）で `subpath` と実ファイルを決める。
   フォルダなら `index` を補い、`wiki_dir` の外なら `None`。`PAGE_EXTS`（`.txt`→`.md`）を試し、
   `PageRef`（`pagepath`/`subpath`/`ext`/`path`/`body`/`exists`）を返す
2. `render.render_source(engine, body, ext, ...)` に本文を渡すと、1行目の `# 見出し` をタイトルとして返す
   （PukiWiki記法では抜き出さない。[タイトルの扱い](./spec/title)）

**表示用には `pagedb.published_ref(wiki_dir, pagepath)` を使います。** 未取り込みの平文ファイルを
その場で取り込んでから返すので、必ず公開された内容になります（[ページのデータベース](/Tech/PageDataBase)）。

返る `PageRef` の `privilege` には、いまの閲覧者のアクセス権（`W`/`R`/`-`）が入っています。
**`-` でも `body` は入っているので、本文を出す前に確かめます**（[ページごとの権限](/Tech/PagePermissions)）。

## 詳細ページ

| ページ | 内容 |
|---|---|
| [プラグイン仕様](./spec) | 呼び出しの記法、引数の宣言（`args`） |
| └ [エラーの扱い](./spec/errors) | 引数の検証・画面での表示・`_help()` |
| └ [実行時の呼ばれかた](./spec/lifecycle) | `_action`・`_setup`が呼ばれるタイミング |
| └ [タイトルの扱い](./spec/title) | 1行目のh1をページタイトルにする仕組み |
| [PLUGIN_INFO](./plugin_info) | 宣言できる特徴（入れ子・`need_outer_info`・`dynamic_output`） |
| [context](./context) | `_setup`/`_convert`/`_inline`/`_action`に渡される情報 |
| [プラグイン開発で使える汎用関数](./functions) | ページ名変換・parse・保存・一覧取得の早見表 |

## 置き場所と優先順位

| 対象 | ディレクトリ |
|---|---|
| 全wiki共通 | トップレベルの `plugin/` |
| 個別Wiki固有 | `wikidata/<Wiki名>/plugin/` |

同じ名前が両方にあれば、個別Wiki固有のものが優先されます（テーマと同じ）。
`.` や `_` で始まるファイルは読み込まれないので、一時ファイルや共有モジュールの置き場所に使えます。

## プラグインの構成

1つのPythonファイルが1つのプラグインで、ファイル名がプラグイン名です。必要な関数だけを定義します。

| 関数 | 呼ばれるタイミング |
|---|---|
| `_setup(context)` | HTTPリクエストごとに1回、最初に呼ばれる |
| `_convert(resolved, body, context)` | ブロック記法 `#name(...)` から呼ばれる |
| `_inline(resolved, body, context)` | インライン記法 `&name(...);` から呼ばれる |
| `_action(context)` | `/.plugin/<name>` へのアクセスで呼ばれる |
| `_help()` | 実行できなかったとき（詳しくは[エラーの扱い](./spec/errors#_help-で詳しい説明を添える)） |

`_convert` と `_inline` は **HTML文字列を返します。**
`_action` は文字列（HTMLとして返される）か、bottleの `HTTPResponse` を返します。

`resolved` は、引数を `PLUGIN_INFO["args"]` の宣言に沿って束ねた `{名前: 値}` です（宣言が無ければ空）。

`body` は `{中身}` の生文字列です。中身を書かなければ `None`、`{}` なら `""` で区別されます。
中身の記法は既定では展開されません（展開は [PLUGIN_INFOの入れ子（`expand_*`）](./plugin_info#入れ子expand_)）。

`PLUGIN_INFO` はモジュール直下の辞書で、プラグインの特徴を宣言します（[PLUGIN_INFO](./plugin_info)）。

```python
PLUGIN_INFO = {
    "help": "書きかた: #hello(name=世界)",
    "args": [{"name": "name", "default": "世界"}],
}

def _convert(resolved, body, context):
    return f"<p>こんにちは、{resolved['name']}さん</p>"
```

## CSSは基本的にプラグイン自身が持つ

プラグインの見た目に要るCSSは、テーマではなくプラグイン自身が持ちます。プラグインを追加するときに
テーマを直さずに済み、テーマを乗り換えても崩れにくいためです。

`plugin/name.css` を置くと、そのページで `_convert`/`_inline` が実際に呼ばれたときだけ `/.plugin/name.css` として
読み込まれます（記録は [`context.used_plugins`](./context/Recipes#呼ばれたことそのものを記録に使う)）。
`plugin/name.js` も同じで、`defer` 付きで読み込まれます。置き場所の優先順位はPythonファイルと同じです。

```
plugin/ls.py
plugin/ls.css   ← 同じ名前で置くだけ。特別な登録は不要
plugin/ls.js
```

オプションによって動きが要らなくても読み込まれるので、JavaScript側で出番があるかを確かめてから
動きます（`ls.js` は `.ls-ajax` が無ければ何もしません）。

読み込み順は「プラグインのCSS → テーマのCSS」なので、テーマ側で同じセレクタを書けば上書きできます。
プラグイン側は、どのテーマでも崩れない最低限の見た目を用意します。

```css
/* theme/bloom.css 側での上書き例 */
.recent-title {
  color: var(--accent);
  border-bottom: 1px dashed var(--border);
}
```

テーマによって変数が違う（`--radius` は `bloom` にあるが `base` に無い、など）ので、
`var(--radius, 6px)` のようにフォールバックを添えます。

## 同梱しているサンプル

| ファイル | 内容 |
|---|---|
| `plugin/note.py` | ブロック・インライン両対応。`expand_*` で入れ子を受け入れる例 |
| `plugin/contents.py` | `need_outer_info` を宣言し、`context.page_headings()` を使う例 |
| `plugin/recent.py` | `pagelist.walk()`（ページの一覧）を使う例。専用CSS（`plugin/recent.css`）を持つ例でもある |
| `plugin/ls.py` | 引数を5つ宣言し、宣言だけでは表せない指定（選べる値の一覧・フォルダとして解決できるか）は**`PluginArgumentError` を `raise` する**例。折りたたみを `<details>` で実現する例、`_action` で自分あてのAJAXを受ける例、専用のCSSとJavaScriptを持つ例でもある |
| `plugin/tasklist.py` | 旧来の `register(md)` 形式（markdown-it-pyを直接拡張する）。`_convert`・`_action` と併せて使う例でもある |

### 旧来の register(md) 形式

markdown-it-py のレンダリング自体を拡張したい場合は、いまも `register(md)` が使えます。

```python
from mdit_py_plugins.tasklists import tasklists_plugin

def register(md):
    md.use(tasklists_plugin, enabled=True)
```

`md` は `markdown_it.MarkdownIt` のインスタンスです。記法そのものを増やすならこちら、ページに機能を
差し込むなら `_convert` / `_inline` を使います。

## レンダリングの設定

プラグインを書かずに変えられる項目は、設定の `markdown` セクション
（既定値は `config/default.example.yaml`、Wikiごとの上書きは
`wikidata/<Wiki名>/config/default.yaml`）にあります。

```yaml
markdown:
  preset: gfm-like        # markdown-it-pyのプリセット
  linkify: true            # 裸のURLを自動リンク化する
  allow_html: false        # 本文に書かれた生HTMLをどこまで通すか（false / true / all）
  anchors: true            # 見出しにidを振る（h1〜h6すべて）
  toc_depth: 3             # サイドバーの目次に出す深さ（idを振る範囲とは別）
  first_h1_as_title: true  # 1行目のh1をページタイトルとして扱う（詳しくは[タイトルの扱い](./spec/title)）
```

`allow_html` の3段階は [本文に書くHTMLの扱い](/Tech/HtmlPolicy) にあります。
