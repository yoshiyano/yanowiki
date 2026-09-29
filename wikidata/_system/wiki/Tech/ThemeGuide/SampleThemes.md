# 同梱しているサンプルテーマ

書きかたの違う2つのサンプルです。`theme.name` を `fresh` / `bloom` にすると切り替わります。

| | fresh（薄緑） | bloom（薄オレンジ） |
|---|---|---|
| 雰囲気 | 爽やかで、すっきり整理された感じ | ゆったりと余白をとった、やわらかい感じ |
| HTML | `{% extends "common/base.html" %}` で**差分だけ**書く（短い） | 継承せず**一から**書く（自由度が高い） |
| CSS | `@import url("base.css")` で共通CSSを土台にする | 独立。細かい部品の見た目も自前で用意する |
| JS | `common.js` だけ（独自JSなし） | `common.js` + 独自の `bloom.js`（「上に戻る」ボタン） |
| サイドバー | 右。囲みを外し、余白と細線で区切る | 左。カードとして分離し、影で浮かせる |
| TopicPath | ヘッダ内に小さく置く | タイトルの上に中央寄せで置く |
| 目次 | サイドバーの先頭 | カードにして画面に貼り付ける（sticky） |

## fresh: 継承して差分だけ書く

`theme/fresh.html` は数十行で、共通テーマの大枠を使い、変えたいブロックだけを上書きしています。

```jinja
{% extends "common/base.html" %}

{# scripts は継承元のまま（common.js だけ）。fresh 独自の動きは無い #}

{# TopicPathはヘッダへ移したので、ここは空にする #}
{% block breadcrumb %}{% endblock %}
```

CSSも、共通CSSを読み込んでから色と一部のレイアウトだけを差し替えます。

```css
@import url("base.css");

:root {
  --accent: #2f8f5b;
  --panel-bg: #f4faf6;
}
```

共通テーマの改良はこちらにも反映されますが、共通テーマの構造に依存します。

## bloom: 一から書く

`theme/bloom.html` は継承せず、`<!doctype html>` から書いています。要素の順番や入れ子を自由に
決められる代わりに、共通テーマの改良は反映されません。

一から書く場合も、`common.css` / `common.js` が使う目印は残します。

- `.content[data-editable]` … セクション編集
- `.content[data-draft]` … 別で編集中（一時保存を預かっているページ）の印
- `.toc a[href^="#"]` … 目次の現在位置ハイライト

**`data-editable` は必ず `{% if editable %}` で囲みます。** `editable` には、見ている人の編集の権限が
集約されているので（[編集の入口は権限で出し分ける](/Tech/Reference/EditEntry#編集の入口は権限で出し分ける)）、
直接出すとそのテーマでだけ権限が効かなくなります。

編集リンクは、共通メニュー（`{{ common_menu }}`）を置けば本体が出し分けます
（[テンプレートで使える変数](/Tech/ThemeGuide/Variables#共通メニューcommon_menu)）。自分で書く場合
（`bloom.html` はまだこの形）は、同じく `{% if editable %}` で囲みます。

タイトルの脇には `{{ title_note }}` を置きます。一時保存を預かっているページで **（編集中）** と出ます
（[セクション編集](/Tech/SectionEditing#別で編集中のときも保存できます)）。

```jinja
<h1 class="page-title">{{ page_title }}{{ title_note }}</h1>
```

検索を使うなら、検索フォームの部品も同じ名前で用意します。

- `.search` / `.search-word` / `.search-scope` / `.search-submit` … 検索フォーム
- `.search-options` … 検索条件パネル
- `.page-search-nav` とその子 … ページ内検索の前へ/次へ
- `.page-search-panel` とその子 … 一致箇所の一覧

開閉する部品（`.search-options` `.page-search-nav` `.page-search-panel`）には `display` を
無条件に書いてかまいません。`common.css` の `[hidden] { display: none !important; }` が閉じるほうを
担保しています（ブラウザ既定の `[hidden]` は作者スタイルに負けるため、これが無いと閉じられなくなります）。

### テーマ独自のJavaScriptを足す

`bloom.html` は `common.js` を読み込んだうえで、独自の `bloom.js` を足しています。

```html
<link rel="stylesheet" href="{{ theme_url }}/common.css">
<link rel="stylesheet" href="{{ theme_url }}/bloom.css">
...
<script src="{{ theme_url }}/common.js"></script>
<script src="{{ theme_url }}/bloom.js"></script>
```

そのテーマにだけ必要な動き（bloomでは「上に戻る」ボタン）を、別のファイルに書けます。

## 検索結果ページとの関係

`theme/search.html` は `{% extends themefile + ".html" %}` なので、どちらのテーマでも検索結果は
そのデザインになります。一から書くテーマでも、`breadcrumb` と `content` のブロックを定義しておけば
`search.html` がそこへ結果を流し込みます。
