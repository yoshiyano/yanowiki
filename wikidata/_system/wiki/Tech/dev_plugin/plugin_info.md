# PLUGIN_INFO で宣言する動作仕様

モジュール直下に `PLUGIN_INFO` という辞書を置くと、プラグインの特徴を宣言できます。省略した項目は
安全側の既定値になります。引数（`args`）の書きかたは [プラグイン仕様](/Tech/dev_plugin/spec/args#引数の宣言args) にあります。

| 項目 | 既定 | 意味 |
|---|---|---|
| `help` | `""` | エラー時に**常に**表示する一言ヘルプ（詳しい説明は[`_help()`](/Tech/dev_plugin/spec/errors#_help-で詳しい説明を添える)） |
| `need_outer_info` | `False` | 引数・中身だけでは完結せず外部情報が必要か |
| `dynamic_output` | `False` | 同じ引数・中身でも出力が時間とともに変わりうるか（予約項目。まだ何も参照しない） |
| `expand_plugin` | `False` | 出力に含まれるプラグイン記法を展開するか |
| `expand_block` | `False` | 出力をブロック要素として展開するか |
| `expand_inline` | `False` | 出力をインライン要素として展開するか |
| `args` | `()` | 引数の宣言（[プラグイン仕様](/Tech/dev_plugin/spec/args#引数の宣言args)） |
| `body_html` | `None` | 中身を展開するときに生HTMLをどこまで通すか（`None`＝ページの設定に従う／`False`／`True`／`"all"`）。下記 |

## 中身のHTMLをどこまで通すか（`body_html`）

`expand_*` で中身を展開するとき、中身の生HTMLをどう扱うかをプラグインが決められます。

```python
PLUGIN_INFO = {
    "expand_inline": True,
    "body_html": False,      # 中身のHTMLは一切通さない
}
```

| 値 | 中身のHTML |
|---|---|
| `None`（既定） | **そのページの設定**（`allow_html`）に従う |
| `False` | 一切通さない。文字として出る |
| `True` | 許可したタグ・属性だけ通す |
| `"all"` | すべて通す |

ページの設定より緩くも厳しくもできます（`allow_html` がプラグインを縛らない理由は
[本文に書くHTMLの扱い](/Tech/HtmlPolicy#プラグインは自分が渡すテキストの水準を決められる)）。
`build_expand_renderer` や `build_markdown_renderer` を直に使うプラグインは、`policy` 引数へ同じ値を渡せます。
`expand_*` を宣言していなければ、この項目は働きません。

## 入れ子（`expand_*`）

既定では、中身に書かれたプラグインやWiki記法は展開されず、ただの文字列です。入れ子の扱いはプラグインごとに
違うので、受け入れるものだけを宣言します。

```python
PLUGIN_INFO = {
    "expand_block": True,    # 中身のブロック要素(段落・リスト・見出し)を展開する
    "expand_inline": True,   # 中身のインライン要素(強調・リンクなど)を展開する
    "expand_plugin": True,   # 中身のプラグインを展開する
}
```

3つとも既定は `False` です。`_convert`（`#`）と `_inline`（`&`）の両方を持つ場合は、呼ばれかたごとに判定されます。

| オプション | ブロック呼び出し `#plugin(...)` での効果 | インライン呼び出し `&plugin(){...};` での効果 |
|---|---|---|
| `expand_block` | 中身をブロック要素（段落・リスト・見出しなど）として再解釈する | 常に無効（`<p>` で包まれるのを避けるため） |
| `expand_inline` | 中身の強調・リンクなどのインライン記法を展開する | 同左 |
| `expand_plugin` | `expand_block` と併用したときに限り、中身の**ブロックプラグイン記法**（`#name(...)`）を展開する | `expand_inline` と併用したときに限り、中身の**インラインプラグイン記法**（`&name();`）を展開する |

`expand_plugin` は単独では働かず、再解釈の対象にプラグイン記法も含めるかを決めるだけです。
ブロックプラグイン（`#name(...)`）は `expand_block`、インラインプラグイン（`&name();`）は `expand_inline` が
効いているときに限り展開されます。標準のインライン記法は `expand_inline` だけで展開されます。

互いを呼び合っても止まるよう、展開の深さには上限があり、達するとその箇所に断り書きが出ます。

展開は中身をプラグインへ渡す前に、ページの記法に合わせて行います（PukiWiki記法のページなら
`''強調''`・`[[リンク>ページ名]]` など）。中身が空白だけなら展開しません。

戻り値は再パースされないので、生のタグ（`<div class="...">` など）を含めてもそのまま出ます
（[本文に書くHTMLの扱い](/Tech/HtmlPolicy#プラグインの出力はこの決まりの外です)）。

## 引数・中身だけでは完結しない場合（need_outer_info）

目次のように、引数・中身のほかに外部の情報（ページ全体・他のページ・DBの状態など）が要るプラグインは
`need_outer_info` を宣言します。

```python
PLUGIN_INFO = {"need_outer_info": True}

def _convert(resolved, body, context):
    for item in context.page_headings(max_depth=2):
        ...
```

宣言すると、[セクション編集](/Tech/SectionEditing)の部分プレビューでは処理されず、
「`#contents` は部分プレビューでは処理されません」という断り書きが出ます（断片から誤った結果を出さないため）。

## 出力が時間とともに変わりうる場合（dynamic_output）

同じ引数・中身でも、DBの更新状況などで出力が変わりうるプラグイン（`ls`/`recent` など）が宣言します。

```python
PLUGIN_INFO = {"dynamic_output": True}
```

`need_outer_info` とは別の軸です（[経緯](/Tech/PluginContextFlags)）。まだ参照する処理は無く、
将来プラグインの出力をキャッシュするときに、宣言したものを毎回作り直すために使う予定です。
