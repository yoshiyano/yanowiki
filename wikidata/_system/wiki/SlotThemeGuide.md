# スロット型のテーマでデザインを変える

スロット型のテーマは、**HTML と CSS だけで書く**テーマです。配色・配置・ロゴの差し替えのような、
簡単なデザイン変更におすすめです。テーマを作って置くのは、そのWikiの管理者と助手です。

テーマに書くのは、目印を付けたふつうの HTML です。ページの本文・メニュー・検索窓などは、
目印の場所に本体が埋めます。テーマにはプログラムもスクリプトも書けないので、テーマから
サーバのプログラムが動いたり、閲覧者のブラウザでスクリプトが動いたりすることはありません。

構造から作り直すような複雑なテーマは、Jinja2 のテーマ（[テーマの開発](/Tech/ThemeGuide)）で作ります。
違いは [テーマと見た目](/AdminGuide/Themes#2種類のテーマ) にまとめてあります。

## はじめかた

管理者メニューの「テーマのファイル」の画面で作ります（画面の使いかたは [テーマと見た目](/AdminGuide/Themes#テーマのファイルの画面)）。

1. `slotcommon`（共通のスロット型のテーマ）のテーマを選び、右クリックの「slottheme へコピー」で写して、
   名前を変えます（例: `mine.html`）
2. 同じフォルダに CSS（例: `mine.css`）を置き（新しいファイルを作るか、アップロード）、HTML の `<head>` から読みます

   ```html
   <link rel="stylesheet" data-asset="mine.css">
   ```

3. そのテーマを選びます

   ```yaml
   theme:
     name: mine
   ```

   テーマを選ぶ欄（`theme.selector: true`）にも出ます。

フォルダ形式（`mine/mine.html` と、その中の CSS・画像）でも置けます。

HTML と CSS は、画面の右クリックの「テキストを編集」で直せます。下の「書けないもの」が含まれていると、
理由が出て保存されません（直してから保存します）。

## 目印

| 目印 | 意味 |
|---|---|
| `data-text="値"` | 要素の中身を、その値の文字列にする |
| `data-href="home"` | `href` を、そのWikiのトップページの URL にする |
| `data-if="名前"` | 値（またはスロットの中身）が空なら、要素ごと消す |
| `data-unless="名前"` | 値（またはスロットの中身）が空でなければ、要素ごと消す |
| `data-slot="名前"` | 要素はそのまま残し、中身を本体の部品にする |
| `<wiki-slot name="名前">` | 要素ごと、本体の部品に置き換える |
| `data-asset="名前"` | `<link>` の `href`・`<img>` の `src` を、テーマの資材の URL にする |
| `<meta name="wiki-slot" content="名前">` | `<head>` の中に本体の部品を置く |
| `<meta name="wiki-behaviors" content="名前">` | 本体が用意した動きを選ぶ（いまは `menu1-fold`。menu1 の階層の開け閉め） |

目印の中に書いた見本の文字（「サイト名」など）は、本体が置き換えます。HTML のファイルを
ブラウザで直接開くと、見本の姿で確かめられます。

### 値（`data-text`・`data-if`）

| 名前 | 中身 |
|---|---|
| `site_title` | サイト名 |
| `page_title` | ページのタイトル |
| `head_title` | 「ページのタイトル - サイト名」（`<title>` 向け） |
| `login_as` | ログインしている人（していなければ空） |
| `render_ms` | 本文の描画にかかった時間 |
| `source_mtime` | 本文の最終更新日時 |
| `disk_usage` | そのWikiが使っている容量 |
| `version` | wikiSystem のバージョン |
| `copyright_year` | 今年 |

### スロット（`data-slot`・`<wiki-slot>`）

| 名前 | 中身 |
|---|---|
| `plugin-assets` | そのページで使うプラグインの CSS・JS（`<head>` に置く） |
| `common-menu` | ログイン・トップ・編集・新規 |
| `zoom-controls` | 表示倍率の操作 |
| `marker-controls` | マーカーの操作 |
| `search-form` | 検索窓 |
| `search-options` | サイト全体を検索するときの条件 |
| `title-note` | タイトルの脇の注記（編集中など） |
| `page-info` | info の知らせ（重複の警告など）。知らせが無ければ空 |
| `topic-path` | TopicPath のリンク |
| `menu1` / `menu2` | メニューのページ |
| `content` | 本文 |
| `toc` | 目次の項目（`<li>` の並び。見出しが1つ以下なら空） |
| `page-search-panel` | ページ内検索の結果 |
| `scripts` | 本体の JavaScript（`</body>` の前に置く） |

## 書けないもの

次のものは、描くときに本体が取り除きます。

- `<script>`・`<style>`・`<form>`・`<input>`・`<button>`・`<iframe>`・`<svg>` など、構造と飾り以外の要素
- `style` 属性と、`onclick` などの `on…` 属性
- 外へのリンク（`<a>` の `href` は `#…` だけ。トップページは `data-href="home"`）
- `theme-` で始まらない `id`、目印と `data-theme-…` 以外の `data-…` 属性
- 本体の部品の class（`search`・`search-…`・`page-search-…`・`marker-…`・`zoom-…`・`new-page-…`・`section-editor`）。
  部品はスロットで置きます。`content` の class は `data-slot="content"` の要素にだけ付けられます

見た目は CSS で付けます。CSS では、次のものが使えません。

- `@import`（ほかの CSS を読み込む）
- 外への `url()`（行き先は、テーマと同じフォルダの資材の名前か、`data:` の画像だけ）
- `expression()`・`behavior`・`-moz-binding`

## 資材（CSS・画像・フォント）

テーマと同じフォルダに置いた CSS・画像（png・jpg・jpeg・gif・webp・avif・ico）・フォント（woff・woff2）を、
`data-asset` で指します。`common:` で始めると、全Wiki共通の `theme/` の資材を指します。

```html
<link rel="stylesheet" data-asset="common:common.css">
<link rel="stylesheet" data-asset="mine.css">
<img data-asset="logo.png" alt="ロゴ">
```

`common.css` は検索窓・ページ内検索・マーカー・表示倍率の操作など、本体の部品の見た目を持っているので、読んでおくのがおすすめです。

## 小さな例

```html
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title data-text="head_title">ページ - サイト名</title>
<meta name="wiki-slot" content="plugin-assets">
<link rel="stylesheet" data-asset="common:common.css">
<link rel="stylesheet" data-asset="mine.css">
</head>
<body>
<header class="site-header">
  <a data-href="home" data-text="site_title">サイト名</a>
  <wiki-slot name="common-menu"></wiki-slot>
  <wiki-slot name="search-form"></wiki-slot>
</header>
<h1 data-text="page_title">ページのタイトル</h1>
<main class="content" data-slot="content"><p>本文の見本</p></main>
<nav class="toc" data-if="toc"><ul data-slot="toc"></ul></nav>
<aside data-if="menu1" data-slot="menu1"></aside>
<wiki-slot name="page-search-panel"></wiki-slot>
<wiki-slot name="scripts"></wiki-slot>
</body>
</html>
```

## 補足

- 検索結果のページは、Jinja2 のテーマで描きます（`theme.name` が Jinja2 のテーマならそれ、そうでなければ `base`）
- 同じ名前の Jinja2 のテーマがあると、そちらが使われます
- 仕組みは [スロットHTML のテーマ](/Tech/ThemeGuide/SlotTheme) にあります
