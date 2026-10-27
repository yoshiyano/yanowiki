# ブロック

標準テーマは次のブロックに分かれています。必要な部分だけを差し替えられます。

`title` / `styles` / `head` / `header` / `commands` / `marker_controls` / `search_form` / `search_options` / `page_header` / `breadcrumb` / `page_heading` / `page_title_tools` / `page_info` / `page_width_toggle` / `menu1_sidebar` / `main` / `content` / `sidebar` / `toc` / `page_search_panel` / `footer` / `scripts`

`page_info` は `page_heading`（タイトルの `<h1>`）の中、右端の道具置き場にある「info の場所」です。
本体が変数 `page_info`（`<a ...>...</a>` のHTML。`Markup`。[変数の一覧](/Tech/ThemeGuide/Variables) 参照）を渡すと、それを描きます。
知らせが複数あれば `<a>` が並んで渡ります。入れ物の `.page-info-slot` が、間を `gap: 0.3em` で空けます（`common.css`）。
知らせがないページでは空で、幅を取りません。本体が何を・誰に出すかは [タイトル右端の info に出す知らせ](/Tech/PageNotice) にあります。
`page_width_toggle` はその右にある「本文の幅の上限を外す／戻す」ボタンです。
このブロックを空に上書きすると、そのテーマにはボタンが出ません。
`page_title_tools` は、この2つを包む道具置き場の全体です。空に上書きすると見出しの中から両方が無くなるので、
ほかの場所へ置きたいテーマが使います（`pukiwiki_default` は、ヘッダのコマンド群の末尾に置いています）。

`menu1_sidebar` は3コラムレイアウトの左カラム（menu1）です。空にすると左カラムごと
無くなり、`.layout` 側のCSSが自動で2コラムに詰めます（`fresh` がこの例。
[同梱しているサンプルテーマ](/Tech/ThemeGuide/SampleThemes) 参照）。

## 一部のブロックだけ差し替える

あるwikiだけヘッダのコマンド欄を変えたい、といった場合は、共通テーマを丸ごとコピーする必要はありません。
`wikidata/<Wiki名>/theme/base.html` を作り、共通テーマを継承して必要なブロックだけを書きます。

```jinja
{% extends "common/base.html" %}

{% block commands %}
<nav class="commands"><span class="command">このwiki専用のメニュー</span></nav>
{% endblock %}
```

**共通テーマは `common/` を付けた名前で参照します。** `{% extends "base.html" %}` と書くと
自分自身を継承して、無限再帰でエラーになります。

テンプレートの編集は、再起動しなくてもすぐに反映されます（Jinja2の自動リロード）。
