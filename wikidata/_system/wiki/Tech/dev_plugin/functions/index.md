# プラグインで使う汎用関数

#code()

ページ名とファイルパスの変換・本文の解釈・保存・一覧取得など、プラグインが使う `_sys/wikilib/` の関数の
早見表です。正確な仕様は各関数のdocstringにあります（このページは追随が遅れることがあります）。

#note(type=warn){{
**ページの読み書きに `open()` や `os.listdir()` を使わないでください。** ページはOSのファイルと1対1ではありません
（`X.txt` にも `X/index.txt` にもなり、同じ名前がページでもフォルダでもある）。
[ページを扱うインターフェイス](/Tech/PageFileSystem) に理由と代わりの関数があります。
}}

`context`（`PluginContext`）のメソッドとして呼べるものが少しあり、ほかは `wikilib.*` から直接 `import` します。
`_sys/wikilib/` を直したときはサーバーの再起動が要ります
（[実行時の呼ばれかた](/Tech/dev_plugin/spec/lifecycle#_syswikilib-を直したときは再起動が要ります)）。

#glossarytip()

## 共通する引数・戻り値

繰り返し出てくる語をここで定義し、以下の表では説明を省きます（ページ内の他の場所でマウスを乗せても読めます。
[`glossarytip`](/Syntax/Plugin/glossarytip)）。

「パス」を含む語が3つあるので、どの世界を指すかを先に整理します。

- **URL世界** — ブラウザがこのページを開くときのアドレス。`pagepath`
- **内部識別子** — システム内部だけの識別子（DBの主キー・添付の置き場所など）。`subpath`
- **実ファイル世界** — ディスク上のファイル・ディレクトリ（`_dir` と `_path`）。`絶対パス`

`wiki_dir`
: そのWikiの実体ディレクトリ（絶対パス）

`pagepath`
: **URL世界。** URL上のページパス（先頭にスラッシュは付かない。空文字列はそのWikiのトップ）

`subpath` / `subpaths`
: **内部識別子。** `wiki_dir` 相対・拡張子抜きで、フォルダの実体は `…/index`。DBの主キー・添付の置き場所・
  バックアップの記録に使う。フォルダのページでは `pagepath` と食い違う（`/Tech` なら `"Tech"` と `"Tech/index"`）。
  複数形はその集合・リスト

`ext`
: 拡張子。`.txt`はPukiWiki記法、`.md`はMarkdown

`engine`
: `MarkdownIt` のレンダラーインスタンス（Markdown/PukiWiki両記法で共有）

`context`
: `PluginContext`。実行時の設定・Wikiの場所・いま開いているページなどをまとめて持つ

`config`
: Wikiの設定（`default.yaml`相当のdict）

`text` / `body`
: ページ本文の生テキスト（`body`はDB上のカラム名としての同じ内容）

`title` / `toc` / `links`
: 本文から取り出したタイトル・目次・リンクの3点セット（`extract_page_info`が返す形）

`tokens`
: 本文をparseして得られるトークン列（markdown-it-py互換）

`PageRef`
: `pagepath`/`subpath`/`ext`/`path`（実在しなければ「保存するならここ」）/`body`/`exists`/`privilege`
  （閲覧者のアクセス権。`published_ref` が作ったものだけ）を持つオブジェクト。3つの世界の値が揃っているので、
  どれを見ているかを意識すること

`ページパス`
: URL世界。URL上のページパス（`pagepath`と同じ意味。関数の戻り値として書くときの表記）

`絶対パス`
: 実ファイル世界の絶対パス。関数名の末尾が `_path` なら1ファイル（`page_file_path`）、`_dir`/`_dir_for` なら
  ディレクトリ（`attach_dir_for`）。`farm_pageinfo_dir` のような `_dir` 系は、名前を渡すとその中のファイルのパスも作れる

## 下位のページ

| ページ | 内容 |
|---|---|
| [関数の早見表](/Tech/dev_plugin/functions/Reference) | `wikilib.paths`・`render`・`pagesave`・`pagedb`・`links`・`attach` の関数 |
| [実例: PukiWiki記法のテキストがHTMLになるまで](/Tech/dev_plugin/functions/Walkthrough) | ページの取得から応答までを、具体的なデータと呼び出し木で追う |

## 実例（同梱プラグインのimport）

```python
# plugin/ls.py — 一覧を組み立てる（閲覧の権限は pagelist の中で見る）
from wikilib import pagelist
from wikilib.pagedb import published_ref
from wikilib.paths import resolve_page_ref

# plugin/recent.py — 最近更新されたページを名前で絞り込む
from wikilib import pagelist
from wikilib.search import name_matches, split_filters

# plugin/img.py / plugin/ref.py — リンク先の解決
from wikilib.attach import attach_dir_for, attach_kind, format_bytes
from wikilib.paths import resolve_link, resolve_page_ref
```

`context.page_headings()`（`plugin/contents.py`）のように `context` だけで済むなら、import は要りません。

## 関連ページ

- [プラグインの開発方法](..) … `PLUGIN_INFO`・引数の宣言・入れ子の扱いなど、プラグインの構成そのものについて
- [ページのデータベース](/Tech/PageDataBase) … ここで挙げた関数が読み書きする`pageinfo/wikiall.db`のスキーマ
- [リネームの仕組み](/Tech/RenamePage) … `page_file_path`/`pagedb`のリネーム時の使われかた
