# ブロック

標準テーマは次のブロックに分かれています。必要な部分だけを差し替えられます。

`title` / `styles` / `head` / `header` / `commands` / `marker_controls` / `search_form` / `search_options` / `page_header` / `breadcrumb` / `page_heading` / `menu1_sidebar` / `main` / `content` / `sidebar` / `toc` / `page_search_panel` / `footer` / `scripts`

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
