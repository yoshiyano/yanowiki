# 検索とページ内検索

検索結果は `theme/search.html` が描画します。設定中のテーマを継承しているので、検索結果もそのデザインになります。

```jinja
{% extends themefile + ".html" %}
```

`search.html` が受け持つのは検索フォームの体裁だけです。結果の一覧とページ送りは検索機能が組み立てて
`results_block`（HTML）で渡し、見た目と動きも `/.search.css`・`/.search.js` が持ちます
（[リファレンス](/Tech/Reference/Views#見た目は検索自身が持つ)）。一致部分は `<mark>` で囲まれています。

結果のリンクには検索語を `?q=` で付けます。移動先で `common.js` がその語を本文から探して
`<mark class="search-hit">` で囲み、最初の箇所（`current` 付き）までスクロールします。
一致箇所はHTMLの構造と無関係な位置になりうるので、サーバーでアンカーを埋めずに描画後のDOMから探しています。

## 検索フォームの見た目

`search_form` ブロックは「検索語 → 範囲 → 検索ボタン」の順に並べ、`.search` に1本の枠線・角丸・
`overflow: hidden` を掛けて1つのフォームに見せています。内側は `border-left` だけで区切ります。

## ページ内検索

検索窓の中の範囲ボタン（`.search-scope`、`data-scope` 属性に `site`/`page` を持つ）で動きが変わります。

| 範囲 | 動き |
|---|---|
| サイト全体 | 通常のフォーム送信で検索ページへ移動する |
| このページ内 | `common.js` が送信を止め、本文の一致箇所を強調して前へ/次へで辿れるようにする |

範囲ボタンは `<select>` ではなくボタン要素です。クリックでその場で切り替わり、押したまま動かすと
選択メニューが出て、離した位置の項目が選ばれます（ポインタの移動量が6px未満ならクリック）。
メニューは `common.js` が `SCOPE_LABEL` から組み立てます。

サイト全体のときは、検索窓を選ぶと条件（AND/OR・対象・絞り込み）のパネルがフロートインします
（`search_options` ブロック）。

## フロートするパネルは `.search` の外に置く

`.search` には `overflow: hidden` が掛かっているので、中に置くとフロート表示が切り取られます。
そこで範囲の選択メニューと条件パネルは `.search` の外（`<form>` の外）に置き、`position: fixed` で
`common.js` が座標を計算して配置します。

- 範囲の選択メニュー（`.search-scope-menu`）は `common.js` が `document.body` 直下に組み立てて配置する
- 条件パネル（`.search-options`）はテンプレートの時点で `<form>` の外にあり、表示のたびに
  `document.body` へ移動して位置を計算する

条件パネルの中身（`select#so-mode` など）は、`form="site-search-form"` 属性で
`<form id="site-search-form">` に結び付けてあるので、フォームの外にあっても一緒に送信されます。
`focusout` の判定は、フォームとパネルの両方を検索UIの内側として扱います（Tab移動で閉じないように）。

一致箇所の一覧は、`page_search_panel` ブロックの器に `common.js` が中身を流し込みます。
位置や見た目はCSSだけで変えられます。目印は次のクラスです。

- `.page-search-panel` … パネル本体（既定では右上に固定）
- `.page-search-list` / `.page-search-item` … 一致箇所の一覧と各項目
- `.page-search-nav` … 検索窓の横の前へ/次へと件数表示
- `.search-hit` / `.search-hit.current` … 本文中の一致箇所と、いま辿っている箇所

ヘッダは、本文をたどる間も前へ/次へを押せるように固定（`position: sticky`）しています。
固定を外すなら、見出しの `scroll-margin-top` も合わせて調整します。
