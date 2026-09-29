"""code — 中身を、Markdownのコードフェンス（```lang ... ```）と
同じHTMLに、Prism.jsで色付けできる状態にして表示する、ブロック専用の
プラグイン。

    #code()
    #code(lang){{
    中身
    }}
    #code(lang, nonum, nocopy){{
    中身
    }}
    #code(, nonum)

 1. lang   … 言語名 (default: 指定なし。`#code(){{ … }}`のように省略できます)
 2. nonum  … 単語を書くと、行番号を表示しない (default: 表示する)
 3. nocopy … 単語を書くと、コピー用ボタンを表示しない (default: 表示する)

**2行以下のコードは、`nonum`を書かなくても行番号の数字が自動で消えます**
（`nonum`とは違い、行番号の余白そのものは残ります。詳しくは「2行以下は
行番号の数字だけを自動で消す」参照）。`nonum`を書けば、2行以下でも
1行でも常に余白ごと消せます。

`#code(python){{ 中身 }}`は、Markdown記法で言語名`python`のコード
フェンス（バッククォート3つで中身を挟む書きかた）を書いたときに
生成されるコード部分（`<code class="language-python">…</code>`）と
同じHTMLになります。`<pre>`要素には行番号・コピーボタンの制御用の
クラス・属性が付くため、`<pre>`まで含めた完全一致は保証しません
（詳しくは`nonum`/`nocopy`の説明）。

**Markdown記法のページで色付けが効くのは、そのページで`#code`を
一度でも呼んだ場合だけです。** 一度も呼んでいないページでは、素の
コードフェンス（バッククォート3つ）は色の付かない標準的な表示に
なります。

**中身（`{{ }}`）を省略した`#code(...)`は、それより下にある素の
コードフェンス（バッククォート3つ）の`nonum`/`nocopy`の既定値を
切り替えます。** ページの上から順に効き、同じページで何度でも
切り替えられます。`#code(lang){{ 中身 }}`のように中身のある呼びかた
（このプラグイン自身が中身を組版する場合）には影響しません。

````markdown
#code(, nonum)

```python
これ以降のフェンスは行番号なしになります
```

#code()

```python
これで既定（行番号あり）に戻ります
```
````

**`lang`を省略して`nonum`/`nocopy`だけ書くときは、先頭にカンマが
必要です**（`#code(, nonum)`。`#code(nonum)`と書くと`nonum`が言語名
として扱われてしまいます。`#code(lang){{ 中身 }}`の中身ありの書きかたと
同じ決まりです）。

**PukiWiki記法のページに書いても、Markdown記法のコードフェンスと同じ
HTMLになります**（記法によらず常に同じ出力）。中身は展開されません
（`**太字**`のような記法・`&note();`のようなプラグインもそのままの
文字として表示されます）。PukiWiki記法には素のコードフェンスに相当する
書きかたが無いため、既定値の切り替えは実質Markdown記法のページ向けです。
"""

r""" 技術資料
このシステム独自のプラグインです（本家PukiWikiには同名のプラグインは
ありません）。Wiki設計者の指示: 「#code(lang){{ code }}の中身を、Markdownの
```lang ... ```が生成するのとまったく同じHTMLにしたい」に始まり、
Prism.jsでの色付け（wikiSystem側でtheme全体に導入済み）・行番号や
コピーボタンの個別停止（`nonum`/`nocopy`）・中身無しでの資材読み込み
合図、という3段階で拡張してきた。

## 自前でエスケープを組み立てず、実際にmarkdown-itへ描かせる理由

最初は`pre.py`のverb=false側（`html.escape(body)`を自前で組み立てる形）
を真似ようとしたが、**`html.escape()`の既定（`quote=True`）はシングル
クォート（`'`）も`&#x27;`にエスケープするのに対し、markdown-itの
コードフェンスの既定エスケープはシングルクォートを一切エスケープ
しない**という食い違いを実際に検証して見つけた（`it's` → markdown-it
はそのまま`it's`、`html.escape()`は`it&#x27;s`）。「まったく同じHTML」を
名言している以上、この食い違いは看過できないため、自前でエスケープ
規則を再実装するのではなく、**実際にmarkdown-itのレンダラーへ
描かせて、その結果をそのまま使う**方式にした。

`_sys/wikilib/plugins.py`の`build_markdown_renderer`（プラグインの読み込み
まで含むフルセット）ではなく、**素の`MarkdownIt(preset)`**を都度組み立てる
（`markdown_it`パッケージから直接importする。フェンスの描画は
markdown-it本体の既定動作で、プラグイン拡張・目次アンカー・脚注などの
追加ルールは一切関与しないため、それらを読み込む必要がない。プラグイン
ディレクトリを毎回走査する重い初期化を避けられる副次効果もある）。
`preset`は`context.config`の`markdown.preset`（既定`"gfm-like"`。
`wikilib.plugins.build_markdown_renderer`と同じ既定値）を読む。

## フェンスの記号（バッククォート）の個数

中身に```（3連続のバッククォート）が含まれていると、素朴に3個で
組み立てたフェンスがそこで閉じたと誤認されてしまう。中身に含まれる
最長のバッククォート連続より1個多い個数（最低3個。CommonMarkの
「ネストしたコードフェンス」と同じ考えかた）を`_pick_fence()`で選ぶ。

## `lang`の検証

`lang`は自分で組み立てる`` ```{lang}\n ``という行（フェンスの情報文字列）
にそのまま差し込むため、改行・空白・バッククォートを含む値を許すと
フェンスの構造そのものを壊しかねない。`LANG_RE`でこれらを含まない
ことだけを確かめる（言語名の綴りそのもの—例えば実在する言語かどうか—は
検証しない。表示用の`class="language-{lang}"`にそのまま使われるだけの
自由な文字列として扱う）。

## `expand_*`を一切宣言しない理由

中身はあくまで「表示したいコードそのもの」であり、Markdown/PukiWiki
記法・他のプラグインとして展開されては困る（`#code(){{ #ls() }}`と
書いても、本当に`#ls()`という文字列がそのまま表示されてほしい）。
そのため`expand_block`/`expand_inline`/`expand_plugin`はいずれも
宣言しない（既定でFalse）。`body`はフレームワークが再展開しない、
このプラグインの中だけで完結した生テキストとして扱われる。

## 記法（PukiWiki/Markdown）によらず同じ出力になる理由

`_convert`が返すのは、すでに完成した`<pre><code>...</code></pre>`という
生HTMLの文字列そのもの（フレームワークによる再展開を経ない）なので、
呼び出し元のページがPukiWiki記法（`.txt`）でもMarkdown記法（`.md`）でも
関係なく、常に同じHTMLになる。

## nonum・nocopy（Prismの機能を`<pre>`の属性で制御する）

wikiSystem側のPrism導入は、`<pre>`のクラス名・`data-*`属性でON/OFFする
という、Prism自身の規約にそのまま従う設計になっている
（`line-numbers`クラス／`show-invisibles`クラス／`data-line`／
`command-line`関連の`data-*`など。中間層を新設せず二重定義を避けるため、
wikiSystem側の判断）。`#code`もこれに乗せる。

- **行番号は既定で表示**。`<html>`要素に`class="line-numbers"`が付いて
  おり（wikiSystem側の対応、2026-08-29）、`Prism.util.isActive()`が
  祖先を遡って有効/無効を判定するPrism本体の仕組みにより、サイト全体の
  既定でONになっている。**`nonum`は`class="line-numbers"`を省略する
  のではなく、既定を打ち消す`class="no-line-numbers"`を明示的に付ける**
  （祖先を遡る途中で見つかった`no-line-numbers`が`<html>`側の既定より
  優先されるため。技術資料参照）
- **コピーボタンは既定で表示**（Prismのtoolbar/copy-to-clipboardが
  全ブロックに自動で付けるため、`#code`側は何もしなくても出る）。
  `nocopy`を指定すると`<pre data-no-copy>`を付けて個別に止める。
  **この`data-no-copy`はPrism標準の属性ではなく、wikiSystem側が
  `theme/prism.js`にブロック単位の抑制フックとして追加した独自の
  仕組み**（Prismのcopy-to-clipboardプラグインには元々ブロック単位で
  ボタンを止める仕組みが無いため。属性名`data-no-copy`はwikiPlugin側の
  提案をそのまま採用してもらった）

`<pre>`タグへのクラス・属性の付与は、`engine.render()`が返す文字列の先頭
（`<pre>`は必ずこの1箇所にしか現れない。1回の呼び出しは常に1つの
フェンスしか描かないため）を`str.replace(..., count=1)`で置き換える、
文字列操作で行っている（HTMLパーサを介さない簡便な実装。`<pre>`という
固定の3文字列だけを対象にしているため誤爆の心配はない）。

## 中身を省略すると何も表示しない理由（Wiki設計者の指示、2026-08-29）

もともとは、「素のMarkdownコードフェンス（```lang）を使うだけの
ページでは`#code`プラグインが一度も呼ばれないため、`context.used_plugins`
ベースの資材読み込み（`plugin/code.css`・`plugin/code.js`）が働かず、
そのページでPrism.js/CSSを読み込む機会が無い」という課題への対処
だった。`#code()`を中身無しで書くと**表示は何も生成しないが、呼び出され
たこと自体は`_sys/wikilib/plugins.py`の`call_plugin`が
`context.used_plugins.add("code")`で記録する**（プラグインの通常の
仕組みで、`_convert`側で特別なことをする必要はない）ことを利用し、
「ページのどこかに`#code()`と書いておくと、そのページでPrism資材が
読み込まれる」という合図として使えるようにした。

**2026-08-29〜2026-09-03の間、wikiSystem側で`_sys/wikilib/themes.py`の
`render_with_theme`がMarkdown記法（`.md`）のページでは`"code"`を
`context.used_plugins`へ無条件に足す時期があった**（Markdownページなら
`#code`を一度も使っていなくても常にPrism資材が読み込まれる、という
挙動）。**2026-09-03、この無条件化は撤回された**（Wiki設計者の判断。素の
コードフェンスしか無い既存81ページの色は消えたままにする、という
判断込み）。現在は記法（Markdown/PukiWiki）によらず、**`#code`を
一度でも呼んだページだけ**Prism資材が読み込まれる、という素直な挙動に
戻っている。この中身無し呼び出しの合図としての役割は、Markdownページ
でも再び意味を持つようになった。

## 素のコードフェンスの既定値を切り替える（`register(engine)`、2026-09-03）

Wiki設計者の指示: 「`#code(...)`の引数で、それ以降の素のコードフェンス
（バッククォート3つ）の既定値（`nonum`/`nocopy`相当）を変えられるように
したい」。中身のある`#code(lang){{ }}`はこのプラグイン自身が完成した
HTMLを組み立てて返すので影響を受けないが、**素のフェンスの描画は
markdown-it本体の既定規則（`fence`）が行っており、このプラグインの
`_convert`は一切関与していない**。そこを差し替える必要がある。

wikiSystem側が下調べした`_sys/wikilib/plugins.py`の`build_markdown_renderer`
（登録した各プラグインモジュールの`register(engine)`という関数を、
`PLUGIN_INFO`方式とは別に、旧来のmarkdown-it-py直接拡張の窓口として
呼ぶ仕組み）を使い、`code.py`に`register(engine)`を追加して
`engine.add_render_rule("fence", ...)`でフェンスの描画規則を差し替える
（wikiSystem側が最初に試作し、その後「Prismに依存する指定はPrismを
管理するcode側に閉じるべき」とのWiki設計者の判断で撤回した`_sys/wikilib/
plugins.py`側の実装（コミット`df8e413`）を参考に、こちらへ移した）。

描画そのものはmarkdown-it本体の既定（`from markdown_it.renderer import
RendererHTML`の`RendererHTML.fence`）にそのまま任せ、返ってきたHTMLの
`<pre>`へ属性を足すだけにする（`_convert`が今までやっているのと同じ
`str.replace(..., count=1)`の手当て。エスケープやクラス名の組み立てを
ここで再実装すると、素のフェンスと`#code`の出力が食い違う余地ができる
ため避けた）。

### 既定値の持たせかた（`context`に直接乗せる）

「それ以降のフェンス」に効かせる既定値は、ページを上から描く間だけ
有効ならよい状態（1回のページ描画の間だけ持てばよく、複数ページを
またいで持ち越す必要は無い）。`include.py`が差し込み先ページ用に
**別の`PluginContext`（`sub`）を都度new**しているのと同じ理由で、
`context`オブジェクト自体がすでに「1回のページ描画」の単位になって
いる。そのため`context._comment_counters`のようなページパスキーの
辞書は不要で、`context`に直接属性（`_code_fence_default`）を乗せる
だけでよい（初期値は未設定＝既定どおり`nonum`/`nocopy`とも`False`
として扱う）。

**プラグインの中身に書いたフェンス（`#note(){{ ```py``` }}`等）は対象外**
（Wiki設計者の判断、実装の単純さ優先）。これは意図して何もしていない結果で
はなく、**`wikilib.plugins.build_expand_renderer`（プラグインの中身を
展開する専用の軽量なMarkdownItインスタンス）が、`build_markdown_renderer`
のような「登録済みモジュールの`register(engine)`を呼ぶ」処理を
そもそも持たない**ため、この`code.py`の`register(engine)`で差し替えた
`fence`規則は、プラグインの中身の展開には最初から効かない。何も
特別な除外処理を書かずに、自然とスコープが絞られている。

### `#code(nonum)`ではなく`#code(, nonum)`と書く必要がある理由

`lang`が`num_order: 1`の位置引数のため、`#code(nonum)`は`nonum`という
語を`lang`（1番目の位置引数）として束ねてしまい、`nonum=True`には
ならない（`lang="nonum"`という、実在しない言語名として扱われるだけで
エラーにはならない）。中身ありの`#code(lang){{ }}`側も元から同じ決まり
（`#code(, nonum){{ }}`のように`lang`をカンマで飛ばす必要がある）なので、
中身無しの既定値切り替えだけ特別扱いして`#code(nonum)`を`nonum=True`と
解釈する変更は行わなかった（wikiSystemから実装の可否を委ねられたが、
書きかたの決まりをプラグイン全体で統一する方を優先した判断）。

## 2行以下は行番号の数字だけを自動で消す（2026-09-04）

Wiki設計者の依頼:「2行までのコードには行番号は不要。nonumでなくても2行以下の
場合は付けないようにしたい。ただし、通常のnonumとは異なり、番号だけ
消すということをしたい。」

`nonum`は`class="no-line-numbers"`でPrismの行番号機能そのものを止める
ため、行番号の余白（`padding-left`等）ごと無くなる。短いコードだけ
自動で余白まで詰めると、長いコードと並んだときに**左端が行ごとに
ずれて見える**。Wiki設計者が求めたのは「数字だけ見えなくする」（余白は
他のコードブロックと揃えたまま）という、`nonum`とは別の見た目のため、
別のクラス（`no-line-number-text`）を新設した。

### 余白を残したまま数字だけ消す仕組み（CSS）

Prism.jsの行番号は、`<pre>`に`class="line-numbers"`が効いている（既定で
ON。技術資料「nonum・nocopy」参照）とき、**クライアント側のJavaScript**
（`theme/prism.js`の行番号プラグイン）が`.line-numbers-rows`という要素を
実行時に組み立てて挿し込む（サーバー側が返すHTMLには最初から含まれない）。
数字そのものは`.line-numbers-rows>span:before{content:counter(linenumber)}`
というCSSカウンタで描かれる（`plugin/code.css`。Prism公式の仕組み）。

`no-line-numbers`を付けずに（＝行番号機能自体は有効なまま）、
`.line-numbers-rows>span::before`の`content`だけを`visibility:hidden`で
見えなくすれば、余白（`padding-left:3.8em`等）はそのまま保たれ、数字
だけが消える。この上書きCSSは`_HIDE_NUMBER_TEXT_CSS`という小さな
`<style>`片として持たせた。

### なぜ`plugin/code.css`に足さなかったか（wikiSystemを変更しない設計）

`plugin/code.css`は**`theme/prism.build.py`（wikiSystem/wikiThemes管理）
が自動生成するファイル**で、`DARK_MODE_CSS`/`NO_COPY_CSS`のような
「末尾に付け足す定数」以外の箇所を手で足しても、次の再生成で消える
（`code.css`冒頭のコメント「このブロックはprism.build.pyが自動で
付け直す」参照）。新しいCSSクラスを足すには、本来なら
`theme/prism.build.py`へ新しい定数を追加してもらう（wikiSystem/
wikiThemesへの依頼）必要がある。

代わりに、**`_convert`/`_render_fence`が返すHTML文字列自身に、`<pre>`の
直前へ小さな`<style>`タグを埋め込む**方式にした（`_style_once()`。以下の
「行番号表示欄の幅を70%に縮める」でも同じ関数を使い回す）。`_convert`の
戻り値は`allow_html`のフィルタを経由しない生HTMLとしてそのまま使われる
（技術資料「記法によらず同じ出力になる理由」と同じ経路）ため、`<style>`を
その場に書いても問題なく効く。HTML5は`<style>`を`<body>`内に書くことを
許しており、主要ブラウザもそのまま解釈する。これにより**wikiSystem/
wikiThemesを一切変更せずに完結した**（`plugin/code.py`単体の変更のみ）。

同じ`<style>`を短いコードブロックごとに繰り返し出すと冗長なため、
`_style_once(context, flag_name, css)`が`context`に`flag_name`という印を
立てて**そのページで最初の1回だけ**出す（`_code_fence_default`と同じ
「1回のページ描画の間だけ持てばよい」考えかた。`flag_name`を変えれば
複数の独立した`<style>`を、それぞれ1回ずつ出せる）。CSSセレクタの詳細度は
`pre.no-line-number-text .line-numbers-rows>span::before`（クラス2つ・
要素/擬似要素2つ）が`plugin/code.css`側の`.line-numbers-rows>span:before`
（クラス1つ・要素/擬似要素2つ）より高いため、`!important`無しで確実に
上書きできる。

### 判定基準（`SHORT_BLOCK_MAX_LINES`）

`len(body.splitlines())`（`_convert`）・`len(tokens[idx].content.
splitlines())`（`_render_fence`）で行数を数え、`2`以下なら対象にする。
`splitlines()`は末尾の改行1つを余分な行として数えない（`"a\nb\n"` →
`["a", "b"]`）ため、中身の末尾に改行が付いているかどうかに影響されない。
`nonum`が指定されている場合はそちらが優先され（自動での`no-line-number-
text`付与はしない）、`nonum`本来の「余白ごと消す」動作が保たれる。

## 行番号表示欄の幅を70%に縮める（2026-09-05）

Wiki設計者の依頼:「3桁行を表示することはほとんど無い。行番号表示欄の幅を
70%に縮めてください。」`plugin/code.css`（Prism.js既定）の行番号関連の
値をすべて0.7倍した`_NARROW_GUTTER_CSS`を、上と同じ`_style_once()`の
仕組みで**そのページで最初の1回だけ**埋め込む（`plugin/code.css`を直接
変更しない理由は上の節と同じ。wikiSystem/wikiThemesへの依頼は不要）。

対象は3つの値（いずれも元の値×0.7）:

    .line-numbers.line-numbers code の padding-left … 3.8em → 2.66em
    .line-numbers-rows の width                      …   3em → 2.1em
    .line-numbers-rows>span:before の padding-right   … .8em → .56em

セレクタは`plugin/code.css`の元のものと**まったく同じ**にした（詳細度を
上げる小細工はしていない）。詳細度が同じ場合、CSSは**あとに出てきた方が
勝つ**というカスケードの基本規則により、`<head>`側の`code.css`より後ろ
（`<body>`内の`_convert`/`_render_fence`の出力）にある`<style>`が確実に
勝つ。数字を消す`no-line-number-text`（クラス2つで詳細度を上げている）とは
異なる考えかただが、こちらはページ内の**全ての**行番号付きブロックに
効かせたい（`no-line-number-text`は特定のブロックだけを狙い撃つ必要が
あった）ため、素直に同じセレクタで上書きする方が意図が伝わりやすいと
判断した。

`nonum`が指定されたブロック自体には効果が無い（そのブロックには元々
行番号欄が無いため）が、害も無い。同じページの**他の**行番号付き
ブロックには変わらず効く。`_convert`/`_render_fence`のどちらが先に
呼ばれても`_style_once`が1回だけに絞るので、この2つの`<style>`
（`_NARROW_GUTTER_CSS`と`_HIDE_NUMBER_TEXT_CSS`）が二重に出ることも無い。
"""

import re

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML

from wikilib.plugins import PluginArgumentError

LANG_RE = re.compile(r"^[^\s`]*$")

PLUGIN_INFO = {
    "help": "#code(lang,nonum,nocopy){{中身}}",
    "args": [
        {"name": "lang", "num_order": 1, "default": "", "label": "言語名"},
        {"name": "nonum", "flag": True, "default": False, "label": "行番号を隠す"},
        {"name": "nocopy", "flag": True, "default": False, "label": "コピーボタンを隠す"},
    ],
}

# これ以下の行数のコードは、nonumが無くても行番号の数字だけを自動で消す
# （技術資料「2行以下は行番号の数字だけを自動で消す」参照）
SHORT_BLOCK_MAX_LINES = 2

# 行番号の余白（padding-left等）は残したまま、数字（Prismがcounter()で
# 描く.line-numbers-rows>span::beforeのcontent）だけを見えなくする。
# plugin/code.css（theme/prism.build.pyが自動生成）は手で足しても消えて
# しまうため、ここでは足さず、_convert/_render_fenceの返すHTML自身に
# 小さな<style>として埋め込む（技術資料参照）。
_HIDE_NUMBER_TEXT_CSS = (
    "<style>pre.no-line-number-text .line-numbers-rows>span::before"
    "{visibility:hidden}</style>"
)

# 行番号表示欄の幅を、plugin/code.css（Prism.js既定）の70%に縮める
# （技術資料「行番号表示欄の幅を70%に縮める」参照）。3桁行を表示することが
# ほとんど無いための調整（Wiki設計者の指示、2026-09-05）。対象の3つの値は
# すべてplugin/code.cssの元の値×0.7:
#   .line-numbers.line-numbers code の padding-left … 3.8em → 2.66em
#   .line-numbers-rows の width                      …   3em → 2.1em
#   .line-numbers-rows>span:before の padding-right   … .8em → .56em
# セレクタは元のCSS（plugin/code.css）とまったく同じものを使う。詳細度が
# 同じなら、あとから出てくる（本文中の<style>は<head>のリンクより後ろ）
# 側が勝つため、詳細度を上げる小細工は不要（技術資料参照）。
_NARROW_GUTTER_CSS = (
    "<style>"
    'pre[class*="language-"][class*="language-"].line-numbers.line-numbers code'
    "{padding-left:2.66em}"
    ".line-numbers .line-numbers-rows{width:2.1em}"
    ".line-numbers-rows>span:before{padding-right:.56em}"
    "</style>"
)


def _pick_fence(body):
    """`body`に含まれる最長のバッククォート連続より1個多い個数の
    バッククォートを返す（最低3個）。中身にコードフェンスの例が
    そのまま書かれていても、フェンスが早期に閉じないようにする。"""
    longest = 0
    run = 0
    for ch in body:
        if ch == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return "`" * max(3, longest + 1)


def _pre_attrs(nonum, nocopy, line_count):
    """`<pre>`に足す、行番号・コピーボタン制御用のクラス・属性を組み立てる
    （技術資料「nonum・nocopy」「2行以下は行番号の数字だけを自動で消す」
    参照）。戻り値は`(attrs文字列, 数字だけを消すCSSが要るか)`。"""
    auto_hide_number_text = not nonum and line_count <= SHORT_BLOCK_MAX_LINES
    classes = []
    if nonum:
        classes.append("no-line-numbers")
    elif auto_hide_number_text:
        classes.append("no-line-number-text")
    attrs = f' class="{" ".join(classes)}"' if classes else ""
    if nocopy:
        attrs += " data-no-copy"
    return attrs, auto_hide_number_text


def _style_once(context, flag_name, css):
    """`css`を、そのページで最初の1回だけ返す（`flag_name`という印を
    `context`に立てて判定する。技術資料「同じ<style>を...最初の1回だけ
    出す」参照）。`_HIDE_NUMBER_TEXT_CSS`・`_NARROW_GUTTER_CSS`で使う。"""
    if context is None:
        return css
    if getattr(context, flag_name, False):
        return ""
    setattr(context, flag_name, True)
    return css


def _convert(resolved, body, context):
    if body is None:
        # 中身無しの呼び出し。表示は何も生成しない。呼ばれたこと自体は
        # フレームワークがcontext.used_pluginsへ記録するので、それを
        # 「このページでPrism資材を読み込む」合図として使う（技術資料参照）。
        # 同時に、この呼び出しの引数を「それより下の素のフェンスの既定値」
        # として持たせる（技術資料「素のコードフェンスの既定値を切り替える」
        # 参照）。
        if context is not None:
            context._code_fence_default = {
                "nonum": resolved["nonum"], "nocopy": resolved["nocopy"],
            }
        return ""

    lang = resolved["lang"] or ""
    if not LANG_RE.fullmatch(lang):
        raise PluginArgumentError(f"言語名の指定が正しくありません: {lang}")

    nonum = resolved["nonum"]
    nocopy = resolved["nocopy"]

    md_conf = (context.config or {}).get("markdown") or {}
    engine = MarkdownIt(md_conf.get("preset", "gfm-like"))

    fence = _pick_fence(body)
    source = f"{fence}{lang}\n{body}\n{fence}\n"
    html = engine.render(source)

    # 行番号はPrism側で<html>にclass="line-numbers"を付けて既定ONに
    # なっている（Prism.util.isActiveが祖先を遡ってon/offを見る仕組み。
    # wikiSystem側の対応）。nonumは「line-numbersを省略する」のではなく、
    # 既定を打ち消す"no-line-numbers"を明示的に付けないと効かない
    # （技術資料参照）。
    pre_attrs, auto_hide = _pre_attrs(nonum, nocopy, len(body.splitlines()))
    if pre_attrs:
        html = html.replace("<pre>", f"<pre{pre_attrs}>", 1)
    style = _style_once(context, "_code_narrow_gutter_style_emitted", _NARROW_GUTTER_CSS)
    if auto_hide:
        style += _style_once(context, "_code_hide_number_style_emitted", _HIDE_NUMBER_TEXT_CSS)
    return style + html


def _render_fence(self, tokens, idx, options, env):
    """素のコードフェンス（```lang）の描画規則。既定の描画（markdown-it
    本体の`RendererHTML.fence`）にそのまま任せ、`_code_fence_default`
    （`#code(...)`の中身無し呼び出しで設定される、そのページの現在の
    既定値）に従って`<pre>`へ属性を足すだけにする（技術資料参照）。"""
    context = (env or {}).get("wiki")
    default = getattr(context, "_code_fence_default", None) or {
        "nonum": False, "nocopy": False,
    }
    html = RendererHTML.fence(self, tokens, idx, options, env)
    attrs, auto_hide = _pre_attrs(
        default["nonum"], default["nocopy"], len(tokens[idx].content.splitlines()))
    if attrs:
        html = html.replace("<pre>", f"<pre{attrs}>", 1)
    style = _style_once(context, "_code_narrow_gutter_style_emitted", _NARROW_GUTTER_CSS)
    if auto_hide:
        style += _style_once(context, "_code_hide_number_style_emitted", _HIDE_NUMBER_TEXT_CSS)
    return style + html


def register(engine):
    """素のコードフェンスの描画規則を差し替える（`PLUGIN_INFO`方式とは別の、
    markdown-it-py本体を直接拡張する旧来の窓口。技術資料参照）。"""
    engine.add_render_rule("fence", _render_fence)
