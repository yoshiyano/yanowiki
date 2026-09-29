"""katex — LaTeX形式の数式をKaTeXで組版して表示する、ブロック・
インライン両対応のプラグイン。

    #katex(){{
    E = mc^2
    }}
    &katex(){x^2 + y^2 = z^2};

中身にLaTeX形式の数式をそのまま書きます。ブロック（`#katex()`）は
独立した数式として中央に、インライン（`&katex();`）は文中に組み込んで
表示されます。

このプラグイン自身は数式を組版しません。ページを開いたブラウザ側で
KaTeX（ローカル同梱の資材を読み込みます）が実際の組版を行います。
組版できない場合（JavaScriptが無効・KaTeX本体の読み込みに失敗、
いずれも）は、書いたとおりのLaTeX原文がそのまま表示され、なぜ数式に
なっていないかの注記が添えられます。
"""

""" 技術資料
KaTeXでLaTeX数式を表示する、このシステム独自のプラグインです。KaTeXの
PukiWiki向け実装（各種コミュニティ製プラグインがある）を参考にしたが、
本家PukiWiki公式のプラグインではなく（`../CLAUDE.md`の後方互換方針は
本家公式プラグインの移植が対象）、正確な仕様を確認できる一次情報源が
手元に無いため、書きかた自体は本項独自に設計した。

KaTeX本体の配布方式は、当初「CDN（jsDelivr）から都度読み込む」で
作ったが（Wiki設計者の指示）、後日「ローカルに置いてほしい」と指示が変わり、
`_sys/vendor/`（`diffmerge`と同じ、バンドラ不要の第三者ライブラリを
そのまま置く仕組み）へ同梱し直した。CDN取得結果をサーバー側で
キャッシュする方式（都度キャッシュ・数式ごとのSVG事前レンダリング＋
キャッシュ、いずれも）は、CDN到達性への依存が完全には消えないことや、
実装の複雑さに見合わないと判断し採用しなかった（検討の経緯はWiki設計者との
やり取りを参照。まとめると: 事前レンダリングはKaTeX自体がSVG単体出力を
持たずMathJax等への切り替えが要ること、ローカル同梱は`diffmerge`の
前例がありコード追加ゼロで実現できたこと、が決め手）。

## サーバー側では数式を一切解釈しない

`_convert`/`_inline`は、中身のLaTeX原文をエスケープしただけの文字列を
`<div>`/`<span>`に入れて返すだけで、組版はすべてブラウザ側（KaTeX）に
任せる。サーバー側でLaTeXを解釈・検証する処理は持たない（Node.js等を
サーバー側で動かさない限りPythonだけでKaTeX相当の組版はできないため。
JavaScriptが無効な環境でも、少なくとも書いたとおりの原文は読める
形で残る、という考えかたは`code.py`の「中身は展開されない」と同じ）。

`expand_block`/`expand_inline`/`expand_plugin`はいずれも宣言しない
（`code.py`と同じ理由。中身はLaTeXの生テキストであり、Markdown/PukiWiki
記法・他のプラグインとして展開されては困る）。

## ブロック/インラインの区別（`data-katex-display`）

`_convert`（ブロック）は`<div class="katex-source" data-katex-display>`、
`_inline`（インライン）は`<span class="katex-source">`（`data-katex-display`
無し）を返す。`plugin/katex.js`はこの属性の有無で、KaTeXの
`displayMode`（true＝独立した大きな数式、false＝行内の小さな数式）を
決める。要素の種類（div/span）そのものではなく明示的な属性で判定する
ことで、JS側の意図が読み取りやすいようにした（`prism`関連の`data-*`
属性の流儀に揃えている）。

## KaTeX本体は`_sys/vendor/`にローカル同梱（`plugin/katex.js`）

KaTeX本体（CSS/JS/フォント）は`_sys/vendor/katex/`に同梱してあり、
`/.vendor/katex/`から配信される（`_sys/wikilib/vendor.py`の
`serve_vendor_asset`。path-traversal対策済みの単純な静的配信）。
`plugin/katex.js`が、ページに`.katex-source`が1つ以上あるときだけ、
`<link>`（KaTeXのCSS）と`<script>`（KaTeXの本体JS）を`/.vendor/katex/`
から動的に`<head>`へ追加する。バージョンは同梱物そのもので固定される
（現在0.16.11）。上げるときは`_sys/vendor/README.txt`の`## katex`節に
ある手順（新しいtarballを取得し`dist/`を丸ごと置き換える）に従う。

`serve_plugin_asset`（プラグイン単体のCSS/JS配信の仕組み）はファイル
1つしか配信できず、KaTeXが必要とする`fonts/`以下（複数のwoff2/woff/ttf）
を配信できないため使えない。`_sys/vendor/`（`diffmerge`が確立した、
複数ファイルからなる第三者ライブラリをそのまま置く仕組み）が適していた。

`katex.min.css`内の`url(fonts/…)`という相対参照はそのまま
`/.vendor/katex/fonts/…`に解決されるため、CSS自体への手当ては不要
だった。

**根からの絶対パス（`/.vendor/katex/`）を決め打ちにはできない。**
サイト全体をサブパス配下に置く設定（`server.prefix`）があり、これが
空でない場合`/.vendor/…`は存在しないパスになってしまう。
`plugin/katex.js`は、自分自身の`<script>`のURL
（`document.currentScript.src`。`/.plugin/katex.js`として配信される）
から接頭辞込みの根を逆算して`BASE`を組み立てる（`serve_plugin_asset`が
`{base_url}/.plugin/<name>.js`という形でURLを渡してくるため、逆算元として
使える。読み込みは`defer`だが、`defer`スクリプトの実行中も
`document.currentScript`は有効）。

KaTeXの自動検出用の拡張（`auto-render`、ページ全体を`$…$`のような区切り
記号でスキャンする仕組み）は使っていない。**`.katex-source`という
決まったクラスの要素だけを対象に`katex.render()`を個別に呼ぶ**ほうが、
ページ中の無関係な`$`記号を誤って数式と解釈する事故が無く、確実だと
判断した。

CSSの読み込みが完了する前にJSでの組版が先に走っても見た目が崩れる
（フォントが読み込めていない状態で組版される）恐れがあるため、
CSSは`<link>`を先に挿し込み、JSの`<script>`の`onload`を待ってから
`katex.render()`をまとめて呼ぶ（CSS自体の読み込み完了は待たない。
KaTeXの組版そのものはCSSに依存しないためで、フォントは通常の
Webフォント読み込みと同じくCSSが後から効いても見た目が整う）。

## 編集画面のライブプレビューへの対応（`window.KatexPlugin.renderAllUnder`）

`plugin/katex.js`は、ページ読み込み時に一度`document`全体を走査して
組版するだけの単純なIIFEではなく、**任意の要素配下を後から組版し直せる
`window.KatexPlugin.renderAllUnder(scope)`を公開している**（`Prism`の
`Prism.highlightAllUnder(scope)`と同じ考えかた。読み込み時は
`renderAllUnder(document)`を1回呼ぶだけ）。KaTeX本体（CSS/JS）の
読み込みは`ensureLoaded()`が1回だけ行い、以後の呼び出しは同じ
Promiseを使い回す（プレビュー更新のたびに`<script>`を重複挿入しない
ため）。

これは、編集画面のライブプレビュー（`_sys/editor/editor.js`の
`updatePreview()`、節編集の`theme/common.js`の`renderPreview()`）が
`preview.innerHTML = html`でプレビュー領域を丸ごと差し替えたあと、
差し込んだ分の`.katex-source`を**これらのファイル側から
`window.KatexPlugin.renderAllUnder(preview)`を呼んで拾い直す**ことを
前提にした設計。**この呼び出し自体は`editor.js`/`common.js`（wikiSystem
本体側のファイルで`wikiPlugin`の編集範囲外）に追加してもらう必要があり、
`Prism.highlightAllUnder(preview)`の呼び出しのすぐ近くに同様の1行を
足す形になる**（両ファイルとも既にPrism向けに同じ理由のコメントが
ある。「プレビューに数式が出ない」という報告を機に発見・対応した
経緯は`Tech/ChangeLog/plugin/`参照）。

編集画面自体は登録済み全プラグインの資材を無条件で読み込んでいる
（`build_edit_page_html`）ため、`plugin/katex.js`（このファイル）は
編集画面でも必ず読み込まれる。ただし**KaTeX本体（CSS/JS）の読み込みは
それとは別**で、`ensureLoaded()`が実際に`.katex-source`を検出した
タイミング（＝プレビューに初めて数式が現れたタイミング）まで遅延する
ため、数式を含まないページの編集では無駄な読み込みが発生しない。

節編集はページの上で開くので、**そのページが元々katexを使っていなければ
`plugin/katex.js`自体が無い**。プレビューの応答ヘッダー（`X-Wiki-Plugin-Scripts`・
`X-Wiki-Plugin-Styles`。`editor.render_preview`）に、描いた断片が使った
プラグインの資材が載り、`common.js`がまだ無いものだけを後から足す
（2026-09-25）。足した`katex.js`は読み込み時の`renderAllUnder(document)`で
差し込み済みのプレビューを組版し、2回目からは上の呼び出しが拾う。

## 組版が有効化できない場合の合図（Wiki設計者の指示）

「組版できていないことを初回表示で分かるようにできないか」という
Wiki設計者の要望を受け、2つの経路それぞれに手当てした。**どちらも組版が
できていないこと自体は元から分かる（LaTeX原文が数式化されずそのまま
出るため）が、それが「壊れている」のか「意図してLaTeX原文を見せている」
のか、読み手には区別が付かなかった**（katexプラグインを知らない読み手
だと特に）。

### JavaScriptが無効な場合（`<noscript>`）

`_convert`/`_inline`はどちらも、`.katex-source`本体の直前に
`<noscript><span class="katex-noscript-notice">…</span></noscript>`を
必ず添える。`<noscript>`の中身はJavaScriptが有効なブラウザでは一切
描画されず（DOMにすら現れない）、無効なブラウザでのみ通常の要素として
表示される、という標準のHTML仕様をそのまま使っている。サーバー側では
JavaScriptの有効/無効を知りようがないため、**両方の場合の出力を常に
埋め込んでおき、ブラウザ側の解釈に委ねる**しかない（JSでの後付け検出は
不可能——JS自体が無効なら検出コードも動かないため）。

### KaTeX本体の読み込みに失敗した場合（`script.onerror`）

`plugin/katex.js`の`ensureLoaded()`は、`<script>`タグに`onload`しか
設定していなかったため、**読み込み失敗時（`_sys/vendor/katex/`の資材が
何らかの理由で404になる等）は`resolve()`が永遠に呼ばれず、`.then()`も
一切実行されない**まま静かに止まっていた（エラー表示もされない）。
`script.onerror`でこの失敗を捕まえ、`Promise`を`reject`するように直した。
`renderAllUnder()`側は`.catch()`を追加し、対象の`.katex-source`要素
すべてに、個々の数式のLaTeX構文エラー（`throwOnError: false`）と同じ
`katex-source-error`クラスを付けて視覚的に揃える（メッセージだけ
「KaTeX本体の読み込みに失敗しました」で区別する）。

## エラーの扱い（`throwOnError: false`）

書いたLaTeXの構文が誤っている場合、KaTeXは既定で例外を投げてページの
組版を止めてしまう。`throwOnError: false`を指定し、誤りがあっても
その数式の位置にエラーメッセージを赤字で表示するだけにとどめ、
ページの他の部分（他の数式を含む）の表示を妨げないようにした。

## 中身にバッククォート等ではなく`{{ }}`の波括弧が必要な場合の注意

複数行のLaTeX（`\\begin{matrix}...\\end{matrix}`等）を書くと、閉じ括弧
`}`だけの行が偶然できることがある（フレームワークの複数行本体
`{{ ... }}`は、開いた個数と同じかそれ以上の`}`だけの行が来ると閉じたと
みなす）。その場合は`#katex(){{{ ... }}}`のように波括弧を3つ以上にして
書けば回避できる（`plugin/pre.py`等、他のプラグインの複数行本体と
共通の仕組み・共通の回避方法）。
"""

from html import escape

from wikilib.plugins import PluginArgumentError

PLUGIN_INFO = {
    "help": "#katex(){{数式}} / &katex(){数式};",
}


_NOSCRIPT_NOTICE = (
    '<noscript><span class="katex-noscript-notice">'
    '⚠ JavaScriptが無効なため、この数式は組版されず原文がそのまま表示されています'
    '</span></noscript>'
)


def _convert(resolved, body, context):
    if not (body or "").strip():
        raise PluginArgumentError("数式を指定してください: #katex(){{ 数式 }}")
    return (
        f'{_NOSCRIPT_NOTICE}'
        f'<div class="katex-source" data-katex-display>{escape(body)}</div>'
    )


def _inline(resolved, body, context):
    if not (body or "").strip():
        raise PluginArgumentError("数式を指定してください: &katex(){数式};")
    return f'{_NOSCRIPT_NOTICE}<span class="katex-source">{escape(body)}</span>'
