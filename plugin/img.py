"""img — 画像を差し込む、ブロック／インライン両対応のプラグイン。

    #img(src)                              ブロック
    #img(src, right)                       右寄せ（回り込み）
    #img(src, clear)                       回り込みを止める線を引く
    #img(タイトル>src)                       図の下にタイトルを表示
    #img(src, right){回り込ませたい文章}      文章を画像の横に回り込ませる
    &img(src);                             文中に差し込む
    &img(src, w50%);                       表示幅の半分にする（レスポンシブ）
    #img(src, [200;100%;600])              200px〜600pxの範囲でレスポンシブ
    &img(src, false);                      クリックしても拡大表示しない
    #img(, clear)                          画像を出さず、回り込みを止める線だけを引く

`src`は常に1番目です。それ以外（`float`/`zoom`/`makelink`）はsrcより
後ろなら好きな順で書けます。

 1. **src** … 画像（URLか、添付ファイル名。常に1番目）
       `タイトル>src` の形で書くと、図の下にタイトルを表示します
       （例: `#img(夕焼け>sunset.jpg)`）。**`float`に`clear`/`c`を指定する
       場合に限り省略できます**（`#img(, clear)`。下記参照。それ以外の
       場合は省略できません）
 2. float … 回り込み（**ブロックでのみ効果があります**。インラインでも
       構文上は書けますが、書いても効きません） (default: 指定なし)
       `right`/`r`（右寄せ＋回り込み）、`left`/`l`（左寄せ＋回り込み）、
       `clear`/`c`（回り込みを止める線だけを引く）

`float`が`right`/`r`/`left`/`l`のとき、中身（`{…}`／`{{…}}`）に文章を
書くと、その文章を画像の横に回り込ませます。中身には見出し・段落・
リストなどのブロック記法、太字・リンクなどのインライン記法、他の
プラグインが使えます。回り込みは中身の範囲だけで閉じるので、続く
`#img(,clear)`のような回り込み解除は要りません
（`#img(src, right){回り込ませたい文章}` だけで完結します）。

`#img(, clear)`のように**srcを省略して`float`に`clear`/`c`だけを指定**
すると、画像を何も出さず、回り込みを止める線（`<div style="clear:both">`）
だけを引きます。既存の`#img(src, right)`等（floatはさせるが、途中で
明示的に止めたい）と組み合わせて使う書きかたです。

 3. zoom … 大きさ (default: 指定なし＝元の大きさ)
       これまでの書式（`300x200`/`300px`/`300x`/`x200`/`300w`/`200h`/`50%`）に加え、
       `w50%`（表示幅に対する割合。レスポンシブ）、
       `[200;100%;600]`（幅200px〜600pxの範囲でレスポンシブ。詳しくは技術資料）
       が使えます
 4. makelink … `true`/`false`/`nolink`（`nolink`は`false`と同じ）
       (default: true＝クリックで拡大表示する)。`false`/`nolink`で、
       クリックしても拡大表示しません

`makelink`が`true`（既定）のとき、画像をクリックすると、ページを
移動せずにその場のダイアログで拡大表示します。画面のどこかをクリック
するか、Escキーで閉じます。拡大表示中にダブルクリックすると、画像を
別タブで開きます（ページ上の画像をCtrl+クリック・中クリックしたときも、
ブラウザの通常どおり別タブで開けます）。

`zoom`の`[MIN;VALUE%;MAX]`はインラインでも書けます
（`&img(src, [200;100%;600]);` のように）。丸括弧`()`ではなく角括弧`[]`
にしているのはこのため（詳しくは技術資料）。
"""

r""" 技術資料
本家PukiWikiのimg.inc.phpを土台にしつつ、このシステム向けに再設計した
（ユーザーからの個別の指示による。オプションの種類・組み合わせを一部
本家から変更している点で、他のPukiWiki移植プラグインの「完全互換」方針とは
別枠）。

## src の "タイトル>リンク" 記法

PukiWikiのブラケットリンク `[[タイトル>リンク先]]` と同じ書きかたを
`src`引数に採用した。`>` があれば手前をタイトル、後ろを実際のsrcとして
分ける（`_split_title()`）。

**`"link": True` はsrc全体（タイトルを含む生の文字列）に対して働く。**
`wikilib.links.plugin_arg_links` は宣言だけを見てプラグインを実行せずに
値を取り出すため、`タイトル>src` のうち`src`だけを取り出すこの
プラグイン固有の分割ルールまでは知らない。そのため、**タイトル付きで
書いた場合、リンク元データベースにはタイトルを含む生の文字列がそのまま
記録され、正しく解決されない**（既知の制限。直すならwikilib側で
plugin_arg_linksに分割ルールを持たせる必要があり、このプラグイン単体では
直せない）。

## float・zoom・makelinkの自由順序化（num_order、2026-08-23）

`src`だけ`num_order: 1`で1番目に固定し、`float`/`zoom`/`makelink`は
`num_order`を宣言しない自由順序にした。`float`/`makelink`は`candidate`
（語の完全一致）で判定できるが、`zoom`は書式が複数あり宣言的な
`candidate`/`re`では読みにくい（下記）ため、あえて`candidate`/`re`を
宣言せず「他のどれにも当てはまらなかった残り」を受け取る項目にした
（`candidate`/`re`を書いていない自由順序の項目は「何にでもマッチする」
扱いになる）。自由順序の解決は宣言順で先勝ちのため、**`zoom`は
`float`/`makelink`より後ろに宣言する必要がある**（先に書くと、
`right`のような`float`のトークンまで`zoom`が先取りしてしまう）。
`zoom`の書式そのものの検証は、これまでどおり`_parse_zoom()`が担う
（宣言側では素通しし、実行時に`PluginArgumentError`を投げる。これにより
不正な`zoom`値のエラーメッセージも変わらず具体的なままになる）。

## float は「宣言上はどこでも書けるが、効くのはブロックだけ」

フレームワークの`block_only`宣言は廃止された（ブロック呼び出し専用の
引数という概念自体が無くなった）。そのため`float`は今はインラインでも
**構文上はエラーなく書ける**が、`_inline()`は`resolved["float"]`を
一切読まないため、**書いても効果が無い**（本家PukiWikiが未知のフラグを
「静かに無視」するのと同じ扱いにする、というユーザーの方針どおり。
警告も出さない）。

旧実装（`block_only: True`）では`&img(src, right)`は「知らない引数
です」でエラーになっていたが、今は`float`（回り込み指定）として静かに
受理され、無視される。**エラーから無視へ挙動が変わった**ことは把握
しておく（`Syntax/Plugin/img.md`にも明記）。

## 回り込みと、割合の幅（2026-09-28）

`w30%`・`[MIN;30%;MAX]` の `%` は、画像を入れている枠（containing block）の幅に
対する割合。回り込む（`float`）ときの枠（`<div class="plugin-img" style="float:…">`）は
中身に合わせて幅が決まるので、「枠の幅は画像で決まり、画像の幅は枠で決まる」という
堂々巡りになる。ブラウザは枠を画像の元の大きさ（本文の幅いっぱいまで）に広げ、その中で
画像だけを30%にするので、画像の横に大きな空きが残り、文章が回り込まなかった
（Wiki設計者の報告「`30%` と `w30%` で、幅の指定以外の挙動が異なる」。`30%` は
CSSの `zoom` で、元の大きさに対する割合なので、枠も縮んだ画像の大きさになる）。

回り込むときは、**割合の幅を画像ではなく回り込む枠に付け**（`float:right;width:30%`）、
画像は枠いっぱい（`width:100%`）にする（`_box_width`）。枠の幅は本文の幅に対する
割合になり、`w30%` の「表示幅に対する割合」という意味どおりに、文章が横に回り込む。
MIN/MAX を `%` で書いた `[…]` は、`img.js` が計算した `clamp()` を、回り込む枠の中の
画像なら枠の側に付ける。回り込まないとき（ブロック・インライン）は、これまでどおり画像に付ける。

## zoom の書式と、clampだけ角括弧にした理由

`zoom`は宣言的な`re`では検証していない（書式が複数あり正規表現1本では
読みにくいため）。`_parse_zoom()`が順に試し、`PluginArgumentError`は
どの書式にも合わなかったときだけ`_convert`/`_inline`側で投げる。

`[MIN;VALUE%;MAX]`はCSSの`clamp(MIN, VALUE%, MAX)`にそのまま対応する
（`width: clamp(200px, 100%, 600px)`のように）。VALUEは常に%（表示幅＝
containing blockに対する割合。標準のCSS%と同じ意味で、追加の計算は
不要）。MIN/MAXは数値なら px でそのままCSSにできる。

**区切りに丸括弧`()`ではなく角括弧`[]`を使っているのは、インラインでも
書けるようにするため。** `wikilib/plugins.py`の`PLUGIN_INLINE_RE`
（`&name(...)`の引数を切り出す正規表現）は`[^()]*`で**丸括弧だけを
除外**しており、角括弧は普通の文字として通る。そのため
`&img(src, [200;100%;600]);`のようにインラインでも使える
（丸括弧のままだったcolorプラグイン初期実装で最初に踏んだ制約
`&color(rgb(...))`が使えない、という同じ問題を、区切り文字の選びかたで
回避した形）。

**MIN/MAXを%（画像の実ピクセル寸法＝内在サイズに対する割合）で書いた
場合だけは、サーバー側では計算しない。** 画像を読んでサイズを調べる
処理はサーバー側でファイルを開く・パースする必要があり、**「画像はサーバー
側で編集せず、すべてJavaScript/CSSで処理する」というユーザーの方針**に
反する（Pillow等の依存を増やす／自前でPNG・JPEG等をパースするコードを
持つ、という初期実装は撤回した）。かわりに、そのケースだけ
`data-zoom-min`/`data-zoom-mid`/`data-zoom-max` 属性と
`plugin-img-zoom-js` クラスを付けて出力し、**`plugin/img.js` が
ブラウザ側で`img.naturalWidth`（画像を読み込めば分かる、ブラウザが
既に持っている実ピクセル幅）から計算し、`style.width`に
`clamp(...)`を設定する。** サーバー側では画像の中身を一切見ない。

JavaScriptが無効な環境でも崩れないよう、サーバー側でも暫定の
`width:VALUE%;height:auto;max-width:100%;`（MIN/MAXでの頭打ちは
無いが、大きく崩れはしない）をあらかじめ`style`に入れておき、
`img.js`が実行されればより正確な`clamp()`に上書きする
（プログレッシブエンハンスメント）。

## float+中身での回り込み（display: flow-root）

`float`が`right`/`left`（`r`/`l`含む）かつ中身（`body`）があるとき、
画像を包む`<div class="plugin-img" style="float:...">`をさらに
`<div class="plugin-img-wrap">`で包み、続けて中身をそのdivの中に
（フレームワークによる再展開のため生のまま）埋め込む。

```html
<div class="plugin-img-wrap">
  <div class="plugin-img" style="float:right">…img…</div>
  …中身（展開済み）…
</div>
```

`.plugin-img-wrap`には`display: flow-root`を当てる（`img.css`）。これは
「新しいブロック整形コンテキストを作り、中のfloatをそのdivの内側だけで
閉じ込める」CSSのプロパティで、昔ながらの`::after{content:"";
display:table;clear:both}`クリアフィックスと同じ効果を、擬似要素無しの
1行で実現できる（現行ブラウザはすべて対応）。これにより、
`plugin-img-wrap`の**外**では回り込みが終わっているため、続く
`#img(,clear)`のような明示的な解除が要らない。

`body`が無い場合（画像だけ、または`float`が無い/`clear`の場合）は
**この仕組みを使わない**。これまでどおり`<div class="plugin-img"
style="float:...">…</div>`（＋`clear`指定時は`clear:both`の行）を
そのまま返す。後方互換のため、既存の呼びかたの出力は変えていない。

`float`が無い（または`clear`）のに中身が書かれた場合は、回り込ませようが
無いので、画像の直後にそのまま中身を続ける（黙って消さない）。

`expand_block`/`expand_inline`/`expand_plugin`を宣言しているので、
中身には見出し・段落・リストのようなブロック記法、太字・リンクの
ようなインライン記法、他のプラグインの入れ子が使える（`note.py`と
同じ仕組み）。`body`は`_convert`/`_inline`が呼ばれる前にフレームワーク側
（`wikilib.plugins.expand_body()`）で展開済みのHTMLとして渡ってくるため、
エスケープせずそのまま埋め込むだけでよい。

### `#img(,clear)`（srcを省略してのclear単独使用）の互換（2026-09-18）

Wiki設計者の指示:「img プラグインで float を解除するため #img(,clear)
を実行する機能がある。これを認めるため、ファイルがない場合にエラーに
しないように。」

本家PukiWikiの`img.inc.php`（`plugin_img_convert`）を確認すると、この
書きかたはそもそも本家にある正当な互換動作だった。

```php
$arg = isset($args[1]) ? strtoupper($args[1]) : '';
if ($p->file_path === '' && $arg == 'CLEAR') {
    // Stop word-wrapping only (Ugly but compatible)
    // Short usage: #img(,clear)
    return PLUGIN_IMG_CLEAR;
}
```

本家自身のコメントに"Ugly but compatible"（行儀は悪いが互換性のため）と
あるとおり、`file_path`（src）が空文字列で、かつ2番目の引数が`CLEAR`の
ときだけ、「ファイルが見つかりません」を出さずに`<div style="clear:both">`
だけを返す特例。

このシステムの実装では、`src`は元々`num_order: 1`かつ`default`キーが
無い＝必須の引数だったため、`#img(,clear)`はフレームワーク側の必須引数
チェックの時点で弾かれ、`_convert`に到達する前にエラーになっていた
（本家の特例が抜け落ちていた）。`src`に`default: ""`を足して省略可能に
した上で、`_convert`側で「srcが無く、`float`が`clear`/`c`のときだけは
エラーにせず`CLEAR_DIV`を返す」という、本家と同じ絞りこみを再現した
（`float`が`clear`以外でsrcが無い場合は、これまでどおり「画像を指定
してください」のエラーのまま。本家もCLEAR以外の特例は無い）。

**bodyの扱いは本家に無い判断。** 本家には中身（`{…}`）を持つ書きかた
自体が無いため、このシステム独自の`expand_block`の仕組みと整合させる
必要がある。srcが無い場合も、既存の「floatが無い／clearのときに中身が
あれば、画像の直後にそのまま中身を続ける（黙って消さない）」という
このプラグイン内の一貫した方針をそのまま延長し、`CLEAR_DIV`の後ろに
bodyを続けるだけにした（`plugin-img-wrap`は使わない。画像自体が無い
ので回り込ませる対象が無いため）。

### 中身に`#code`のコードブロックがあると画像が隠れる問題（`img.css`、2026-09-18）

Wiki設計者からの報告（`=1ev-c/講義/第01回/C言語の基本形/4.コメント文`）:
`#img(src,right){{ #code(c){{ … }} }}`のように、floatさせた画像の横に
`#code`のコードブロックを回り込ませると、描画領域が崩れ、画像が完全に
隠れて表示されない。実機のヘッドレスブラウザでスクリーンショットを
撮って再現・確認した（サーバーを介さない`build_markdown_renderer`の
確認だけではHTML文字列しか見えず、この崩れはCSSの適用結果としてしか
現れないため）。

原因は`img`側ではなく、Prism（`plugin/code.css`、`theme/prism.build.py`が
生成）が持つ2つの性質の組み合わせ:

1. `pre[class*="language-"]`は`overflow: visible`で、新しいブロック
   整形コンテキスト（BFC）を作らない。BFCを作らないブロック要素は、
   floatの隣にあっても**ボックス自体**（背景・枠）はコンテナの全幅に
   広がる（floatを避けて幅が縮むのは中身のテキスト行だけ）。
2. `pre[class*="language-"]>code`に`position: relative; z-index: 1`が
   付いている。CSS 2.1のスタッキング順序では、z-indexを持つ
   positioned要素は、non-positionedなfloat要素より**前面**に来る
   （通常は逆で、floatの方がnon-positionedなブロックより前面に来る）。

この2つが重なると、floatした画像と重なる領域で、コードの不透明な背景
（`#fdfdfd`、ダークモードでは`var(--code-bg)`）が画像の上に描画され、
画像を完全に覆い隠してしまう。

`img.css`の`.plugin-img-wrap pre[class*="language-"][class*="language-"]`
に`overflow: auto`を足し、Pre自身にBFCを作らせて対処した。BFCを持てば
floatを避けてボックスの幅そのものが縮むため、上の2つの問題（全幅に
広がること・z-indexで前面に出ること）がまとめて解消する（floatの
回り込み本来の挙動に戻すだけで、Prism側のz-indexを直接打ち消す必要が
無い）。セレクタを`[class*="language-"]`2つ重ねにしているのは、
`plugin/code.css`本体（同じセレクタを2つ重ねている）と詳細度を揃え、
CSSの読み込み順に依存せず確実に上書きするため（`code.css`冒頭の
「wikiSystem追加分」と同じ考えかた）。

`.plugin-img-wrap`限定のセレクタにしたのは、この救済がfloatと重なる
場面だけで要る対処であり、通常の（floatを使わない）`#code`の見た目を
変えたくないため。`plugin/code.css`側（`theme/prism.build.py`の自動生成
物）を変更する案もあったが、**プラグインの処理は可能な限り単体で
完結させる**方針により、`img`プラグイン自身が作る`.plugin-img-wrap`
構造の中でだけ効く`img.css`側の救済とした（`wikiSystem`/`theme`側の
変更は無し）。この対処はPrismの`language-`クラス・DOM構造に依存する
（`img`が`code`の実装詳細を知る形になる）が、他のfloatと相性が悪い
プラグインが将来出てきた場合も、同じ考えかたで個別に追記していけば
よい。

紙めくれの影（coyテーマの`::before`/`::after`のbox-shadow）は
`overflow: auto`によりPre自身のボックス外へはみ出す部分がクリップ
されるが、影の一部が薄くなる程度の副作用で、画像が隠れる不具合に比べ
軽微と判断した。

（過去の版では、`figure_html`と`body`の間に空行（`\n\n`）を挟む必要が
あった。当時は「プラグインの返り値全体を再パースする」方式で、空行が
無いとMarkdownの「生HTMLブロック」判定が`figure_html`の続きとして`body`
の1行目まで飲み込んでしまっていたため。2026-09-02に`body`を先に展開して
返り値を再パースしない方式（`expand_body()`）へ変わり、この問題自体が
起きなくなったため空行は不要になったが、書式として残していても実害は無い）。

### （解消済み）1行の`{…}`に丸括弧を含む中身を書くと壊れていた問題

`_sys/wikilib/plugins.py`の`PLUGIN_BLOCK_RE`が引数を囲む丸括弧の対応を
貪欲マッチ（`.*`）で取っていたため、1行の`{…}`形式の中身に丸括弧が入る
書きかた（`[文字](リンク先)`のようなMarkdownリンクなど）をすると、
本体の取り出しに失敗して「本体（{…}）の書きかたが正しくありません」に
なっていた。`img`固有の不具合ではなく、ブロックプラグイン全般に共通する
フレームワーク側の挙動だった。

2026-08-25にwikiSystem本体側で修正され（丸括弧の対応を数える走査に
置き換え。詳しくは`Tech/PluginBlockParenFix.md`）、1行の`{…}`に丸括弧を
含めても正しく動くようになった。複数行の`{{ … }}`を使う回避策は、
もう必要ではないが、引き続き使っても問題無い。

## makelink

本家は`nolink`（無ければ既定でリンクあり）の1つだけだが、このシステムでは
`true`/`false`/`nolink`の3値candidateにした（`nolink`は`false`と同じ）。
ユーザーの指示による（「本システムに適した形にする」）。`type: bool`の
自動変換は使っていない（`_coerce_bool`が受け付ける語彙に`nolink`が
無いため）。値は`_makelink()`で解釈する。

## makelinkのリンクをページ内ダイアログで開く（2026-09-14）

Wiki設計者の指示で、リンクのクリックを「画像のURLへ移動する」から
「ページ内のダイアログで拡大表示する（クリック・Escで閉じ、ダブル
クリックで別タブ）」へ変えた。**サーバー側の出力はリンクのまま**
（`<a href>`にクラスを1つ足しただけ）で、クリックを横取りして
ダイアログにするのはすべて`plugin/img.js`が行う。`_sys/`の変更は無い。
本家PukiWikiの「画像へのリンク」で行けた先（画像そのもの）は、
ダブルクリック・Ctrl+クリック・中クリック、JavaScript無効時の通常の
クリックでいまも開けるので、到達手段を削ってはいない。

- **対象の見分けは`plugin-img-link`クラスで行う。** `image-link`は
  `ref.py`の画像リンクにも付いているため、これで選ぶと、同じページで
  `#img`と`#ref`を併用したときだけ`#ref`の画像までダイアログになる
  （`img.js`は`#img`を使ったページにしか読み込まれない）という
  ページ構成次第の食い違いが起きる。`image-link`はテーマ側のCSSとの
  互換のため残した。
- **ネイティブの`<dialog>`＋`showModal()`を使う。** 最前面表示
  （top layer）・背面ページの操作の遮断・Escでの`cancel`→`close`・
  閉じたあとのフォーカス復帰をブラウザに任せられ、自前のオーバーレイと
  キー処理を持たずに済む。`showModal`が無いブラウザではクリックを
  横取りせず、従来のリンクのまま動かす。
- **クリックとダブルクリックの両立。** ダブルクリックでも先に`click`が
  2回飛ぶため、1回目の`click`で即座に閉じると`dblclick`はダイアログに
  届かず、下のページに落ちる。そこで1回目の`click`ではフェードアウト
  （`is-closing`）を始めるだけにして、`CLOSE_DELAY`（300ms）後に
  閉じる。その間に`dblclick`が来たら別タブで開いて閉じる。OSの
  ダブルクリック間隔を300msより長く設定している環境では、2回目の前に
  閉じてしまうことがある。その2回目がたまたまページ上の画像リンクに
  落ちてもダイアログを開き直さないよう、クリックで閉じた直後
  `REOPEN_GUARD`（500ms）は画像リンクのクリックを無視する。
- **別タブは`window.open(url, "_blank", "noopener")`。** `dblclick`の
  直前に`mouseup`があるのでユーザー操作とみなされ、ポップアップ
  ブロックの対象にならない。
- **修飾キー付き・左ボタン以外のクリックは横取りしない**（Ctrl/⌘/
  Shift/Alt+クリック、中クリック）。ブラウザ標準の「新しいタブで開く」
  等をそのまま使えるようにするため。
- **クリック横取りは`document`へのイベント委譲。** `include`や`ls`の
  AJAXで後から差し込まれた`#img`にもそのまま効く（ただし`img.js`自体が
  読み込まれていないページに差し込まれた場合は、従来どおりのリンクと
  して動く）。
- ダイアログは初回クリック時に1つだけ作って`<body>`末尾に置き、使い
  回す。閉じるたびに`src`を外し、次に別の画像を開いたとき前の画像が
  一瞬見えないようにしている。
"""

import os
import re
from html import escape

from wikilib.attach import attach_dir_for
from wikilib.paths import resolve_link, resolve_page_ref
from wikilib.plugins import PluginArgumentError

SHOW_IMAGE = True  # 本家PLUGIN_IMG_SHOW_IMAGE相当。falseで外部/添付画像をリンクだけの表示にする
CLEAR_DIV = '<div style="clear:both"></div>'

_LEGACY_SIZE_RULES = [
    (re.compile(r"^(\d+)x(\d+)$"), lambda m: f"max-width:{m.group(1)}px;max-height:{m.group(2)}px;"),
    (re.compile(r"^(\d+)px$"), lambda m: f"max-width:{m.group(1)}px;max-height:{m.group(1)}px;"),
    (re.compile(r"^(\d+)x$"), lambda m: f"max-width:{m.group(1)}px;height:auto;"),
    (re.compile(r"^x(\d+)$"), lambda m: f"width:auto;max-height:{m.group(1)}px;"),
    (re.compile(r"^(\d+)w$"), lambda m: f"max-width:{m.group(1)}px;height:auto;"),
    (re.compile(r"^(\d+)h$"), lambda m: f"width:auto;max-height:{m.group(1)}px;"),
    (re.compile(r"^(\d+(?:\.\d+)?)%$"), lambda m: f"zoom:{m.group(1)}%;"),
]
_W_PERCENT_RE = re.compile(r"^w(\d+(?:\.\d+)?)%$")
_CLAMP_RE = re.compile(r"^\[\s*([^;]+?)\s*;\s*(\d+(?:\.\d+)?)%\s*;\s*([^;]+?)\s*\]$")
_BOUND_RE = re.compile(r"^(\d+(?:\.\d+)?)(%)?$")

FLOAT_CANDIDATES = ["right", "left", "clear", "r", "l", "c"]
FLOAT_ALIASES = {"r": "right", "l": "left", "c": "clear"}

PLUGIN_INFO = {
    "help": "#img(src,float,zoom,makelink){回り込ませる文章}",
    "expand_block": True,
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "src", "num_order": 1, "default": "", "link": True},
        {"name": "float", "candidate": FLOAT_CANDIDATES, "default": None, "label": "回り込み"},
        {"name": "makelink", "candidate": ["true", "false", "nolink"], "default": "true", "label": "リンク作成"},
        {"name": "zoom", "default": None, "label": "大きさ"},
    ],
}


def _split_title(src):
    """"タイトル>src" なら (タイトル, src) を、無ければ (None, src) を返す。"""
    if ">" in src:
        title, _, rest = src.partition(">")
        return title, rest
    return None, src


def _makelink(value):
    return value.lower() == "true"


# ---- zoom の解釈 ----

def _box_width(zoom):
    """枠の幅に対する割合で幅が決まる指定（`w30%`・`[MIN;30%;MAX]`）なら、その幅
    （CSSの値）。それ以外は None。回り込むときは、この幅を画像ではなく回り込む枠に
    付ける（技術資料「回り込みと、割合の幅」）。"""
    if not zoom:
        return None
    m = _W_PERCENT_RE.match(zoom)
    if m:
        return f"{m.group(1)}%"
    m = _CLAMP_RE.match(zoom)
    if m and _BOUND_RE.match(m.group(1)) and _BOUND_RE.match(m.group(3)):
        if "%" not in m.group(1) and "%" not in m.group(3):
            return f"clamp({m.group(1)}px, {m.group(2)}%, {m.group(3)}px)"
        return f"{m.group(2)}%"   # MIN/MAX が % のときは暫定の幅（img.js が仕上げる）
    return None


def _parse_zoom(zoom):
    """zoom文字列から (style, data属性の辞書) を返す。空なら ("", {})。

    data属性が空でなければ、そのimgに `plugin-img-zoom-js` クラスを付け、
    `plugin/img.js` がブラウザ側で仕上げる（サーバー側では画像の中身を
    一切見ない。詳しくは技術資料）。"""
    if not zoom:
        return "", {}

    m = _W_PERCENT_RE.match(zoom)
    if m:
        return f"width:{m.group(1)}%;height:auto;", {}

    m = _CLAMP_RE.match(zoom)
    if m:
        min_token, value, max_token = m.group(1), m.group(2), m.group(3)
        if not _BOUND_RE.match(min_token) or not _BOUND_RE.match(max_token):
            raise PluginArgumentError(f"zoomの指定が正しくありません: {zoom}")
        if "%" not in min_token and "%" not in max_token:
            # MIN/MAXともpxなので、その場でCSSにできる（画像を読む必要が無い）
            return f"width:clamp({min_token}px, {value}%, {max_token}px);", {}
        # MIN/MAXのどちらかが%（画像の実ピクセル寸法に対する割合）→
        # サーバー側では計算せず、img.jsに任せる。読み込み前後で見た目が
        # 大きく変わらないよう、暫定でVALUE%の幅にしておく
        fallback = f"width:{value}%;height:auto;max-width:100%;"
        data = {"data-zoom-min": min_token, "data-zoom-mid": f"{value}%", "data-zoom-max": max_token}
        return fallback, data

    for pattern, build in _LEGACY_SIZE_RULES:
        m = pattern.match(zoom)
        if m:
            return build(m), {}

    raise PluginArgumentError(f"zoomの指定が正しくありません: {zoom}")


# ---- 添付ファイル・URLの解決 ----

def _resolve(src, context):
    """(実在するか, urlとして埋め込む値) を返す。urlは書かれた値そのまま
    （/.attach/... への書き換えは rewrite_content_links に任せる）。"""
    ref = resolve_page_ref(context.wiki_dir, context.page or "")
    kind, target = resolve_link(ref.subpath, src, context.wiki_dir)
    if kind == "keep":
        return True, src

    if kind == "attach":
        owner_subpath, _, name = target.rpartition("/")
        directory = attach_dir_for(context.wiki_dir, owner_subpath)
        found = bool(directory) and os.path.isfile(os.path.join(directory, name))
        return found, src

    return False, src


def _render(src, title, zoom, makelink, is_block, context, in_box=False):
    """`in_box` が真なら、割合の幅（`_box_width`）は外側の枠が持つので、画像は
    その枠いっぱい（width:100%）にする（回り込むとき。技術資料「回り込みと、割合の幅」）。"""
    found, url = _resolve(src, context)
    if not found:
        raise PluginArgumentError(f"見つかりません: {src}")

    style, zoom_data = _parse_zoom(zoom)
    if in_box and _box_width(zoom):
        style = "width:100%;height:auto;"

    if not SHOW_IMAGE:
        h_url = escape(url, quote=True)
        warn = escape("SHOW_IMAGE が無効なため表示していません", quote=True)
        return f'<a href="{h_url}" title="{warn}">{escape(url)}</a>'

    h_url = escape(url, quote=True)
    style_attr = f' style="{escape(style, quote=True)}"' if style else ""
    css = "plugin-img-block" if is_block else "plugin-img-inline"
    if zoom_data:
        css += " plugin-img-zoom-js"
    data_attr = "".join(f' {k}="{escape(v, quote=True)}"' for k, v in zoom_data.items())
    alt = escape(title or "", quote=True)
    img = f'<img class="{css}" src="{h_url}" alt="{alt}"{style_attr}{data_attr}>'
    if makelink:
        # image-link はテーマ側の見た目との互換のため残し、img.js が拡大表示の
        # 対象を見分けるのは img 専用の plugin-img-link で行う（ref.py も
        # image-link を使うため。詳しくは技術資料）
        img = f'<a href="{h_url}" class="image-link plugin-img-link">{img}</a>'

    if is_block and title:
        return f'{img}<div class="plugin-img-title">{escape(title)}</div>'
    return img


def _inline(resolved, body, context):
    title, src = _split_title(resolved["src"] or "")
    if not src:
        raise PluginArgumentError("画像を指定してください: &img(src);")
    return _render(src, title, resolved["zoom"], _makelink(resolved["makelink"]),
                   is_block=False, context=context)


def _convert(resolved, body, context):
    title, src = _split_title(resolved["src"] or "")
    float_value = FLOAT_ALIASES.get(resolved["float"], resolved["float"])

    if not src:
        if float_value != "clear":
            raise PluginArgumentError("画像を指定してください: #img(src)")
        # 本家PukiWikiのimg.inc.php互換（"Ugly but compatible"と本家コメント
        # にある特例）。#img(,clear) は画像を指定せず、floatの回り込みを
        # 止める線だけを引ける（技術資料「#img(,clear) の互換」参照）。
        return f'{CLEAR_DIV}{body or ""}'

    wrapper_style = {"right": "float:right", "left": "float:left"}.get(float_value, "")
    clear_html = CLEAR_DIV if float_value == "clear" else ""

    box_width = _box_width(resolved["zoom"]) if wrapper_style else None
    img_html = _render(src, title, resolved["zoom"], _makelink(resolved["makelink"]),
                       is_block=True, context=context, in_box=bool(box_width))
    if box_width:
        # 割合の幅は、回り込む枠に付ける（技術資料「回り込みと、割合の幅」）
        wrapper_style += f";width:{box_width}"
    style_attr = f' style="{escape(wrapper_style, quote=True)}"' if wrapper_style else ""
    # 回り込ませるときは左右に余白を取る目印（img.css の .plugin-img-float。
    # Wiki設計者の指示、2026-09-28。回り込んだ文章が画像に詰まって見えたため）
    klass = "plugin-img plugin-img-float" if wrapper_style else "plugin-img"
    figure_html = f'<div class="{klass}"{style_attr}>{img_html}</div>'

    if not body:
        return f'{figure_html}{clear_html}'

    if wrapper_style:
        # float=right/left で回り込ませる文章がある場合。画像と文章を1つの
        # divにまとめ、display:flow-root でそのdivの中だけでfloatを閉じる。
        # 外側に clear:both を置く必要が無くなる（詳しくは技術資料）。
        return f'<div class="plugin-img-wrap">{figure_html}{body}</div>'

    # float が無い／clear のときは回り込ませようが無いので、画像の後ろに
    # そのまま続ける（本文を書いたのに黙って消えることは無いようにする）
    return f'{figure_html}{clear_html}{body}'
