# ls — ページの一覧（リンク付き）を差し込む

| 使える書きかた | |
|---|---|
| ブロック `#ls()` | ○ |
| インライン `&ls();` | — |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

#code()

フォルダの中のページの一覧を作り、それぞれへのリンクを並べます。フォルダの入口ページに置くと便利です。

### 書きかた

```pukiwiki
#ls()
#ls(Tech)
#ls(Tech, recursive, MTIME_REV)
#ls(Tech, ajaxview, sort=TITLE, natural)
#ls(Tech, exclude=old, format_md=TITLE, format_pk=FILE)
```

| 名前 | 既定 | 意味 |
|---|---|---|
| `folder` | 自分の下 | 対象のフォルダ（**常に1番目**） |
| `recursive` | （なし） | 単語を書くと下の階層まで辿る |
| `sort` | `FNAME` | 並び順 |
| `ajaxview` | （なし） | 単語を書くと、その場でページの中身を開ける |
| `natural` | （なし） | 単語を書くと、数字を数値として比べる |
| `exclude` | （なし） | 除外する名前（**名前付きでだけ書ける**） |
| `format_md` | 設定 `markdown.listname`（既定 `TITLE`） | Markdownのページの見せかた（**名前付きでだけ書ける**） |
| `format_pk` | 設定 `pukiwiki.listname`（既定 `FILE`） | PukiWiki記法のページの見せかた（**名前付きでだけ書ける**） |

`recursive`・`sort`・`ajaxview`・`natural` は好きな順で書けます。`folder` を省いてこれらだけ書くときは、1番目を空けます（`#ls(, recursive)`）。
`#ls(recursive)` と書くと `recursive` という名前のフォルダを探し、`#ls(Tech, old)` と書くと `old` はフォルダ名として読まれます。

#### folder（対象のフォルダ）

省略すると、自分の下のフォルダが対象です。`/Tech` のような入口ページに置けば、その中の一覧になります。
下にフォルダが無い単独のページに置くと、エラーにはならず何も表示しません。

指しかたは本文のリンクと同じです。`#ls(Tech)` も `#ls(/Tech)` も、どのページに置いても（サイドバーでも）`/Tech` を指します。
`./Plugin` はいまのページの下、`../Tech` は1つ上からです。存在しないフォルダを指定するとエラーです。

#### sort（並び順）と natural

| 指定 | 並び |
|---|---|
| `FNAME` | ファイル名順（既定） |
| `MTIME` | 更新が古い順 |
| `TITLE` | タイトル順 |
| `SIZE` | ファイルが小さい順 |

`_REV` を付けると逆順です（新しい順は `MTIME_REV`）。`MTIME`・`SIZE` は、公開された（取り込まれた）時点の日時と大きさです。

`natural` を付けると、`FNAME`・`TITLE` で数字のかたまりを数値として比べ、`page2, page10` の順になります（全角数字も同じ）。
付けないと文字として比べるので、`page10` が `page2` より前に来ます。

#### format_md / format_pk（見せかた）

| 指定 | 出るもの |
|---|---|
| `BOTH` | ファイル名とタイトルの両方 |
| `FILE` | ファイル名だけ |
| `TITLE` | タイトルだけ（無ければファイル名） |

`format_md` はMarkdownのページに、`format_pk` はPukiWiki記法のページに効き、混ざっていてもそれぞれで決まります。フォルダは入口ページの書きかたで決まります。
省略時の既定は設定 `markdown.listname`／`pukiwiki.listname`（`title`→`TITLE`、`fname`→`FILE`）で、管理者がWikiの設定ファイルで変えられます。`BOTH` は `#ls()` 側でだけ指定できます。

#### ajaxview（その場で開く）

各項目の左に **▸** が付き、押すと**そのページの中身**をその場に開きます（もう一度押すと閉じます）。目次から順に読んでいくのに使います。
中身はふつうに開いたときと同じ処理で作られ、1行目のタイトルは省かれます。一度読んだ中身は覚えておきます。JavaScriptが無効なら ▸ は働きませんが、ページ名のリンクは使えます。

開いた中身は読むためのものです。`#comment`・`#vote` の欄は表示されますが、書き込むにはページを開きます。プラグインのCSS・JavaScriptは読み込まないので、見た目や動きがふつうに開いたときと違うことがあります。`#viewable_period` で表示を止めたページは、`#include` と同じく案内文になります。

#### 複数の列に並べる表示

`recursive` も `ajaxview` も書かない一覧は、表示幅に合わせて複数の列に並びます。上から下へ並べて、次の列へ続きます。列の幅はすべて同じで、幅の狭い場所では1列になります。

列に収まらない名前があるときは、一覧の右上の1項目分の場所に **ファイル名の部分省略** のチェックボックスが出ます。最初はオンで、名前を `…` で省略し、マウスを載せると全体が見えます。オフにすると、折り返して全体を見せます。タイトルを見せる一覧でも同じように働きます。
ページを開き直すとオンに戻ります。JavaScriptが無効なときは、チェックボックスは出ず、折り返して全体を見せます。

#### フォルダの "/"

下にページを持つフォルダは、名前の最後に `/` が付きます（`Tech/`）。タイトルを見せるときはタイトルの後ろに付きます。`recursive` で `<details>` に畳まれるフォルダには付きません。入口ページだけで、下にページの無いフォルダにも付きません。

#### exclude（除外）

`folder` からの相対パスで照合します。`*` や `?` を含めばワイルドカード、含まなければ部分一致で、大文字小文字は区別しません。
照合の規則は [recent](/Syntax/Plugin/recent) の `exclude` と同じです（recent はWikiの先頭からのパスで照合します）。

```pukiwiki
#ls(Tech, exclude=old)              old を含む名前を除外
#ls(Tech, exclude=*.bak)            .bak で終わる名前を除外
#ls(Tech, exclude=old;draft)        ; で区切って複数（; そのものは \;）
#ls(Tech, recursive, exclude=ChangeLog/plugin)
```

除外したフォルダは中身ごと除外されます。`;` の前後が空（`a;;b`・末尾の `;`）だとエラーです。

### 表示例

このWikiの `Tech/dev_plugin` の一覧:

#ls(/Tech/dev_plugin, recursive, format_md=BOTH)

`recursive` のときフォルダは `<details>` になり、名前をクリックすると畳めます（JavaScriptは要りません）。
フォルダもページと同じ並び順に混ざります。出力は `<nav class="ls">` の中の `ul.ls-list` で、ページは `li.ls-page`、フォルダは `li.ls-folder`、タイトルの添え書きは `span.ls-title` です。

複数の列に並ぶ一覧の書きかたと、生成されるHTML（ページの構成は架空の例です。チェックボックスはブラウザ側で足されます）:

```pukiwiki
#ls(Tech)
```

```html
<nav class="ls ls-columns ls-clip" data-ls-api="/.plugin/ls"><ul class="ls-list">
<li class="ls-page"><a href="/Tech/Plugin/index">Plugin/</a></li>
<li class="ls-page"><a href="/Tech/Setup">Setup</a></li>
</ul></nav>
```

### エラーになる書きかた

| 書きかた | 理由 |
|---|---|
| `#ls(NoSuchFolder)` | フォルダが存在しない（公開されたページを1枚も持たない） |
| `#ls(./Tech)` | `./` はいまのページの下を探す（`/Tech` なら `#ls(Tech)`） |
| `#ls(=other/Tech)` | `=`（Wiki指定）・`.` で始まる名前は使えない |
| `#ls(Tech, BADSORT)` | どの引数の値としても解釈できない |
| `#ls(Tech, format_pk=BADFORMAT)` | `BOTH`/`FILE`/`TITLE` のどれでもない |
| `#ls(Tech, format=TITLE)` | `format` という引数は無い |
| `#ls(Tech, exclude=a;;b)` | `;` の前後が空 |

詳しくは [共通の書きかた](/Syntax/Common#うまく動かないとき) を参照してください。

### 性質

- 並ぶのは公開されたページだけです。ファイルを直接置いただけのページは、取り込む（`./wiki.py updatepage`）まで出ません。ページを1枚も持たないフォルダも出ません
- 入口ページ（`index`）は項目として並ばず、フォルダ名がそのページへのリンクになります。中身が入口ページだけのフォルダは1件として並びます。入口ページを持たないフォルダは出ません
- 閲覧する権限の無いページは並びません。中身が全部そうなったフォルダも出ません（[ページごとの権限](/Tech/PagePermissions)）
- 同じ名前の `.txt` と `.md` は1つのページです。`=` や `.` で始まる名前は対象外です（[ページの名前のルール](/Syntax/Common#ページの名前のルール)）
- `exclude` の指定は、リンク元のデータベースには記録されません（ページへの参照ではないため）
