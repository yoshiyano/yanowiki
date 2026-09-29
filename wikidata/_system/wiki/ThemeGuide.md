# 見た目を変えよう

見た目のひとそろいを「テーマ」と呼びます。テンプレートから作り直すときは [テーマの開発](/Tech/ThemeGuide) をご覧ください。

このページの設定は、そのWikiの設定ファイル `wikidata/<Wiki名>/config/default.yaml` に書きます。
管理者と助手は [Wikiの設定画面](/.admin/configwiki) からも変えられます。

## メニューを編集する

サイドバーのメニューは普通のWikiページです。

| メニュー | ページ名 |
|---|---|
| 上のメニュー | `mainmenu` |
| 下のメニュー | `submenu` |

たとえば `mainmenu` をこう書けば、そのままメニューになります。

```markdown
## メニュー

- [ようこそ](/)
- [使ってみよう](/UsageGuide)
```

- リンクは `/` から始まる形で書くと、どのページから見ても正しく飛べます
- メニューのページが無いときは、その枠ごと表示されません

どのページをメニューにするかは、設定で変えられます。

```yaml
theme:
  menu1_page: mainmenu
  menu2_page: submenu
```

## 目次について

ページの見出しから目次が自動でつくられます（見出しが1つしかないページでは出ません）。
目次に入る見出しの深さは設定で変えられます。

```yaml
markdown:
  toc_depth: 3   # 見出し3段目まで目次に入れる
```

## サイト名を変える


```yaml
theme:
  site_title: わたしのWiki
```

## 色を変える

標準のテーマ（`base`）の配色は、`theme/base.css` の先頭にまとまっています。

```css
:root {
  --bg: #ffffff;      /* 背景の色 */
  --fg: #1f2328;      /* 文字の色 */
  --accent: #0969da;  /* リンクの色 */
  --panel-bg: #f6f8fa;/* サイドバーの色 */
}
```

`base`・`fresh`・`bloom`・`pukiwiki_default` は、端末がダークモードのとき自動で暗い配色になります。

## テーマを丸ごと切り替える


```yaml
theme:
  name: base
```

`base` と書くと、`theme/` の `base.html` `base.css` `base.js` が使われます（`.js` は無くても
かまいません。どのテーマにも `common.css` と `common.js` が加わります）。

`theme.selector: true` にすると、メニューにテーマを選ぶ欄が出ます（選んだテーマは、そのブラウザで1日だけ効きます）。

## 用意されているテーマ


| 名前 | 雰囲気 |
|---|---|
| `base` | 標準。青系で、機能がひととおり見える形。menu1が左・本文が中央・目次とmenu2が右の3コラム（画面が狭いときは自動で2コラム→1コラムに詰まる） |
| `fresh` | 薄緑系。爽やかで、すっきり整理された見た目。サイドバーは右 |
| `bloom` | 薄オレンジ系。余白をゆったりとった、やわらかい見た目 |
| `pukiwiki_default` | PukiWiki 1.5系の既定の見た目（薄青）を、`base` を土台に再現したもの |
| `post_it_1` | PukiWikiの配色をもとにした、付箋風の見た目 |
| `pkwk` | `post_it_1` を土台に、PukiWiki標準の配色（薄青）へ寄せたもの |

| | |
|---|---|
| **`base`** | **`fresh`** |
| &img(base>theme-base.png, w100%); | &img(fresh>theme-fresh.png, w100%); |
| **`bloom`** | **`pukiwiki_default`** |
| &img(bloom>theme-bloom.png, w100%); | &img(pukiwiki_default>theme-pukiwiki_default.png, w100%); |
| **`post_it_1`** | **`pkwk`** |
| &img(post_it_1>theme-post_it_1.png, w100%); | &img(pkwk>theme-pkwk.png, w100%); |
