# code — Markdownのコードフェンスと同じHTMLで表示する

| 使える記法 | |
|---|---|
| ブロック `#code()` | ○ |
| インライン `&code();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

中身を、Markdownのコードフェンス（バッククォート3つ）と同じHTMLで表示し、Prism.jsで色付けします。
ページの記法に関わらず出力は同じなので、PukiWiki記法のページで言語つきの色付きコードを載せるときにも使えます。
このシステム独自のプラグインです。

### 書きかた

```pukiwiki
#code(python){{
def hello():
    print("hello")
}}
```

| 引数 | 値 | 既定 | 意味 |
|---|---|---|---|
| `lang` | 言語名 | 指定なし | コードの言語（`class="language-{lang}"`）。[使える言語](#使っているprismjsの構成)に無い名前は、色が付かないだけ |
| `nonum` | 単語を書くだけ | 表示する | 行番号を出さない（`<pre>` に `class="no-line-numbers"`） |
| `nocopy` | 単語を書くだけ | 表示する | コピー用ボタンを出さない |

`lang` を省略して `nonum`/`nocopy` だけ書くときは、先頭にカンマが要ります（`#code(, nonum)`）。`#code(nonum)` だと `nonum` が言語名になります。

### 表示例

#code(python){{
def hello():
    print("hello")
}}

- 中身は展開されず、書いたとおりに出ます
- 2行以下のコードは、`nonum` が無くても行番号の数字が消えます。余白は残るので、長いコードと左端が揃います（余白ごと消すなら `nonum`）
- 中身にバッククォート3つが含まれていても正しく処理されます

### `pukiwiki`・`markdown` の色付け

`lang` を `pukiwiki` にすると、このWikiのPukiWiki記法に合わせて色分けします（npmのPrism.jsには無い、このシステム独自の言語定義）。
複数行のプラグインの中身（`{{ … }}` の中）は対象外です。

#code(pukiwiki){{
* 見出し
- 箇条書き
#contents(depth=2)
&size(150%){強調したい文};
''太字''、'''斜体'''
[[表示名>PageName]]
}}

`markdown` でも、`#name(` のように丸括弧が直後に続くプラグイン呼び出しは、見出しと別の色になります。

#code(markdown){{
# 本物の見出し
#note(type=tip){中身};
}}

### 中身を省略すると、Prism.jsを読み込むだけの合図になる

中身を省略した `#code()` は何も表示せず、そのページの素のコードフェンス（前にあるものも含む）を色付けする合図になります。書いていないページの素のフェンスは色が付きません。

`nonum`/`nocopy` を付けると、それより下の素のフェンスの既定が変わります。上から順に効き、何度でも切り替えられます。
中身のある `#code(lang){{…}}` と、ほかのプラグインの中身に書いたフェンスには効きません。PukiWiki記法のページには素のフェンスが無いので、実質働きません。

````pukiwiki
#code(, nonum)

```python
これ以降の素のフェンスは行番号なしになります
```

#code()

```python
これで既定（行番号あり）に戻ります
```
````

### エラーになる書きかた

`#code(py thon){中身}` のように、`lang` に空白・バッククォートが含まれるとエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
`#code(python)` のように中身だけを省略するのはエラーではありません（上の合図になります）。

### 使っているPrism.jsの構成

Prism.js本体は、`theme/prism.build.py` で作ったものを `plugin/code.css`・`plugin/code.js` に同梱しています。行番号欄の幅は本来の70%です。

- **バージョン**: 1.30.0
- **テーマ**: `coy`
- **言語**（47種）: markup, css, clike, javascript, apacheconf, arduino, bash, basic, c, csharp, cpp, cmake, csv, diff, django, dns-zone-file, docker, gcode, git, go, ignore, java, json, json5, jsonp, latex, lisp, lua, markdown, markup-templating, matlab, nasm, nginx, perl, php, python, ruby, rust, scss, sql, typescript, vbnet, verilog, vhdl, vim, wiki, yaml（と、独自の pukiwiki）
- **プラグイン**（11種）: line-highlight, line-numbers, show-invisibles, file-highlight, show-language, highlight-keywords, autoloader, keep-markup, command-line, toolbar, copy-to-clipboard

言語・プラグインを増やすときは、`theme/prism.build.py` の `LANGS`/`PLUGINS` を編集して実行し直します。
