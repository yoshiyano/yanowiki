# blockdiv — 枠つきの箱を作り、段組みや回り込みに使う

| 使える記法 | |
|---|---|
| ブロック `#blockdiv()` | ○ |
| インライン `&blockdiv();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

#code()

幅・回り込み・枠線・背景などを指定した箱（`<div>`）で中身を囲みます。箱を左右に回り込ませれば、ページを2段・3段に組めます。
PukiWikiで使っていた `blockdiv` の移植で、**PukiWikiで書いた `#blockdiv(名前:値,…)` 〜 `#blockdiv(end)` はそのまま動きます。**
そのうえで、`名前=値` の書きかた・`{{ }}` で中身を囲む書きかた・文字色や角の丸みなどの指定を足してあります。

## 書きかた

### 2段に組む（PukiWikiでの書きかた）

`#blockdiv(...)` で箱を開き、`#blockdiv(end)` で閉じます。並べた箱の後ろには [clear](/Syntax/Plugin/clear) を置いて回り込みを止めます。

```pukiwiki
#blockdiv(float:left,bordercolor:transparent,width:48%,margin:2px)
左の段の中身
#blockdiv(end)
#blockdiv(float:right,bordercolor:transparent,width:48%,margin:2px)
右の段の中身
#blockdiv(end)
#clear()
```

#blockdiv(float:left,bordercolor:transparent,width:48%,margin:2px)
左の段の中身
#blockdiv(end)
#blockdiv(float:right,bordercolor:transparent,width:48%,margin:2px)
右の段の中身
#blockdiv(end)
#clear()

生成されるHTML:

```html
<div class="blockdiv" style="float:left; width:48%; text-align:left; border-style:solid; border-width:1px; border-color:transparent; background-color:inherit; margin:2px; padding:0px;">
<p>左の段の中身</p>
</div>
<div class="blockdiv" style="float:right; width:48%; text-align:left; border-style:solid; border-width:1px; border-color:transparent; background-color:inherit; margin:2px; padding:0px;">
<p>右の段の中身</p>
</div>
<div class="clear"></div>
```

指定しなかった項目も既定値で `style` に書き出されます（PukiWikiと同じ）。

### 中身を `{{ }}` で囲む（新しい書きかた）

中身を `{{ }}` で囲むと、その場で箱が閉じるので `#blockdiv(end)` は要りません。**閉じ忘れが起きないので、新しく書くときはこちらをおすすめします。**
中身にはMarkdown・PukiWiki記法や他のプラグイン（`#blockdiv` の入れ子も）をそのまま書けます。

```pukiwiki
#blockdiv(width=48%, bordercolor=transparent, margin=2px){{
- **左**の段
- 箇条書きも書けます
}}
#blockdiv(float=right, width=48%, bordercolor=transparent, margin=2px){{
右の段
}}
#clear()
```

#blockdiv(width=48%, bordercolor=transparent, margin=2px){{
- **左**の段
- 箇条書きも書けます
}}
#blockdiv(float=right, width=48%, bordercolor=transparent, margin=2px){{
右の段
}}
#clear()

生成されるHTML（左の箱）:

```html
<div class="blockdiv" style="float:left; width:48%; text-align:left; border-style:solid; border-width:1px; border-color:transparent; background-color:inherit; margin:2px; padding:0px;">
<ul>
<li><strong>左</strong>の段</li>
<li>箇条書きも書けます</li>
</ul>
</div>
```

### 飾りの箱

回り込ませない（`float=none`）箱に、枠線・角の丸み・余白・文字色を付けた例です。
`rgb(…)` のように値に `,` を含むときは、引用符で囲みます。

```pukiwiki
#blockdiv(float=none, border="dashed 2px #0064c8", radius=8px, padding=1em, color="rgb(0,100,200)"){{
回り込ませない、角の丸い点線の箱
}}
```

#blockdiv(float=none, border="dashed 2px #0064c8", radius=8px, padding=1em, color="rgb(0,100,200)"){{
回り込ませない、角の丸い点線の箱
}}

生成されるHTML:

```html
<div class="blockdiv" style="float:none; width:auto; text-align:left; border-style:dashed; border-width:2px; border-color:#0064c8; background-color:inherit; margin:0px; padding:1em; color:rgb(0,100,200); border-radius:8px;">
<p>回り込ませない、角の丸い点線の箱</p>
</div>
```

### 用意されていないCSSを足す（`css`）

`css="プロパティ:値; プロパティ:値"` で、ほかのCSSをそのまま足せます。

```pukiwiki
#blockdiv(float=none, bordercolor=transparent, css="display:flex; gap:1em"){{
#note(){中身A}
#note(type=tip){中身B}
}}
```

生成されるHTML（開きタグ）:

```html
<div class="blockdiv" style="float:none; width:auto; text-align:left; border-style:solid; border-width:1px; border-color:transparent; background-color:inherit; margin:0px; padding:0px; display:flex; gap:1em;">
```

## 指定できるもの

`名前=値`（新しい書きかた）でも `名前:値`（PukiWikiでの書きかた）でも書けます。どちらも順番は自由で、書きたいものだけ書けます（両方で同じ名前を書いたら `名前=値` が優先）。名前の大文字小文字は区別しません。

| 名前 | 意味 | 既定 |
|---|---|---|
| `end` | 単語だけで書く。前の `#blockdiv(...)` で開いた箱を閉じる | — |
| `float` | 回り込み。`left` / `right` / `none` | `left` |
| `clear` | 回り込みを止める。`left` / `right` / `both` / `none`。**書くとほかの指定は使われず、回り込みを止めるだけの箱になる** | 止めない |
| `width` | 幅 | `auto`（中身に合わせる） |
| `align` | 文字の寄せ。`left` / `center` / `right` / `justify` | `left` |
| `border` | 枠線を「種類 太さ 色」の順にまとめて。書いた部分だけが下の3つを上書きする | — |
| `borderstyle` | 枠線の種類（`solid` / `dashed` / `dotted` / `double` / `none` など） | `solid` |
| `borderwidth` | 枠線の太さ | `1px` |
| `bordercolor` | 枠線の色 | `inherit`（外側から引き継ぐ） |
| `backcolor` | 背景色 | `inherit` |
| `margin` | 箱の外側の余白 | `0px` |
| `padding` | 箱の内側の余白 | `0px` |
| `class` | 箱に付けるclass名（PukiWikiでの書きかたでは `style:名前`） | `blockdiv` |
| `color` | 文字の色（新しく足した指定） | 指定しない |
| `radius` | 角の丸み（新しく足した指定） | 丸めない |
| `css` | そのほかのCSS（新しく足した指定） | 足さない |
| `start` | 書いても何も変わらない（PukiWikiの書きかたとの互換のため） | — |

**何も指定しないと、文字色の細い枠が付きます**（枠の色の既定 `inherit` が、外側の文字色を引き継ぐため）。段組みに使うときは `bordercolor:transparent` のように枠を消してください。

## 注意

- `#blockdiv(...)` だけの書きかたで **`#blockdiv(end)` を書き忘れると**、箱がページの残り全体に広がり、レイアウトが崩れることがあります（PukiWikiと同じ）。`{{ }}` の書きかたならこの心配はありません。
- 開いていないのに `#blockdiv(end)` を書くと、エラーになります（外側の枠を閉じてページを壊さないよう、何も閉じません）。
  見出し単位の編集のプレビューでは、開きが別の見出しにあるのが普通なので、エラーにせず何も出しません。
- 並べた箱の後ろには [clear](/Syntax/Plugin/clear) を置いてください。置かないと、後ろの文章が箱の横へ回り込みます。

## エラーについて

このプラグイン固有のエラーです。

| 書きかた | エラーの内容 |
|---|---|
| `#blockdiv(foo:1)` / `#blockdiv(left)` | 知らない指定です（名前の間違い。PukiWikiでは黙って無視されていました） |
| `#blockdiv(width:48%;color:red)` | 値に使えない文字が含まれています（`;` `:` `"` `<` `>` `{` `}` `\` などは値に書けません） |
| `#blockdiv(float:up)` / `#blockdiv(float=up)` | `float`（`clear`・`align` も同様）に選べない値を書いた |
| `#blockdiv(css="background:url(x.png)")` | `css` に使えない書きかたが含まれています（`url(` `\` `@` `/*` などは書けません） |
| `#blockdiv(end){x}` | `end` と中身（`{{ }}`）は同時に書けません |
| 開いていないのに `#blockdiv(end)` | 閉じる箱がありません |

```pukiwiki
#blockdiv(foo:1)
```

#blockdiv(foo:1)

書きかた自体が壊れている場合は、共通のエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
