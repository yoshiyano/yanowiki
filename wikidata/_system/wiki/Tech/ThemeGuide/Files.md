# ファイル構成

テーマは同じ名前の3点セットで扱います。`theme.name` に `base` を指定した場合は次のとおりです。

| ファイル | 役割 |
|---|---|
| `base.html` | ページ全体のレイアウト（Jinja2テンプレート） |
| `base.css` | このテーマのページ構造（ヘッダ・menu1/本文/目次+menu2の3コラム）の配色と組版 |
| `base.js` | このテーマだけの動き（menu1の階層の開閉）。検索などテーマによらない動きは `common.js` が持つ |

`.js` は、テーマ独自の動きが無ければ要りません（`fresh` は持っていません）。

これとは別に、**どのテーマも `common.css` と `common.js` を読み込みます。**

```html
<link rel="stylesheet" href="{{ theme_url }}/common.css">
<script src="{{ theme_url }}/common.js"></script>
```

`common.*` は、テーマの作りに関わらず働くものを持ちます。目印にするのは次の2種類です。

**(1) サーバーがどのテーマにも同じ形で渡すもの**

| 機能 | 目印 |
|---|---|
| セクション編集 | `.content[data-editable]` |
| 別で編集中 | `.content[data-draft]` |
| 目次の現在位置ハイライト | `.toc a[href^="#"]` |
| 共通メニューの編集（Alt+E） | `[data-hotkey="edit"]` |
| 共通メニューの「新規」 | `[data-new-page-open]` `.new-page-dialog` |

後の2つは、本体が組み立てる共通メニュー（`{{ common_menu }}`。
[テンプレートで使える変数](/Tech/ThemeGuide/Variables#共通メニューcommon_menu)）に含まれています。

**(2) テーマがHTMLで用意する、決まったクラス名**

| 機能 | 目印 |
|---|---|
| 検索 | `.search` `.search-word` `.search-scope` `.search-submit` |
| 検索条件パネル | `.search-options` |
| ページ内検索のナビ | `.page-search-nav` とその子 |
| 一致箇所の一覧 | `.page-search-panel` とその子 |
| 検索を独立したモーダルにする（任意） | `.search-modal-open` `.search-modal` とその子 |
| 狭い画面でのサイドバーの開閉 | `.subbar` `.mainbar` |
| 表示の拡大縮小 | `.zoom-in` `.zoom-out` `.zoom-value` |

(2) は、テーマが置いた部品に `common.js` が振る舞いを付けます。クラス名を合わせれば、一から書いた
テーマでも検索などがそのまま使え、置かなかった部品は何もしません。目印の一覧は `theme/common.js` の
冒頭にあります。`base.css` は `base.html` のページ構造の見た目なので、`base.html` を継承しないテーマでは
読み込みません。

`common.css` の色は `var(--名前, 既定値)` の形で、テーマが変数を定義していなくても既定値で描けます。
テーマ自身のCSSより前に読み込むので、同名セレクタをテーマ側に書けば上書きできます
（`bloom.css` はセクション編集の差分だけを書いています）。

#note(type=warn){{
`common.css` と `common.js` の読み込みを忘れると、そのテーマでだけセクション編集が使えず（JS）、
枠も色も付かない素のままの表示になります（CSS）。
}}

## 置き場所

同名ファイルは個別Wiki固有のものが優先されます。

| 対象 | ディレクトリ |
|---|---|
| 全wiki共通 | トップレベルの `theme/` |
| 個別Wiki固有 | `wikidata/<Wiki名>/theme/` |

CSS・JSは `/.theme/base.css`（別のWikiなら `/=sandbox/.theme/base.css`）で配信され、
このURLも個別Wiki固有→共通の順に探すので、片方だけ差し替えられます。

## バージョン表示（テーマ作成時の必須埋め込み）

**どのテーマも、フッタなど目立たない場所に版とリビジョン（`{{ version }}`）を出します。**
障害対応や動作報告のとき、動いている版を画面から確かめるためです（同梱のテーマはすべて対応済み）。

```html
<span class="site-version">{{ version }}</span>
```

見た目は `common.css` の `.site-version` にあるので、クラス名を合わせるだけで済みます。
