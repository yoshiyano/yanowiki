# タイトルの描画

1行目のh1はページタイトルとして本文から取り出されるので（[タイトルの扱い](/Tech/dev_plugin/spec/title)）、
`content` にタイトルの見出しは入っていません。テンプレート側で `page_title` を描画します。

標準テーマでは、3コラム（menu1／本文／目次+menu2）の外側に専用の枠を置き、タイトル、TopicPath（現在地）の
順に並べています。3コラムぶんの幅いっぱいにタイトルを置けるようにするためです。

```jinja
{% block page_header %}
<div class="page-header">
  {% block page_heading %}<h1 class="page-title">{{ page_title }}</h1>{% endblock %}
  {% block breadcrumb %}
  <div class="page-path">TopicPath :
    <a href="{{ base_url }}/">/</a>{% for item in topic_path %}{% if item.url %}<a href="{{ item.url }}">{{ item.label }}</a>{% else %}{{ item.label }}{% endif %}{% if not loop.last %}/{% endif %}{% endfor %}
  </div>
  {% endblock %}
</div>
{% endblock %}
```

`topic_path` はページパスの各階層を `{label, url}` で持ちます。末尾（現在のページ）だけ `url` が
`None` で、リンクにしません。`/Tech/ThemeGuide` なら、`Tech` は `Tech/index` へのリンク、
`ThemeGuide` はリンクなしの現在地です。

タイトルを本文の中に出すには、`page_header` ブロックを空にして、`content` の前で `page_heading` を描画します。

```jinja
{% block page_header %}{% endblock %}

{% block main %}
<main class="content">
  {{ self.page_heading() }}
  {{ content }}
</main>
{% endblock %}
```

`page_heading` ブロックを空にすればタイトルを出さないテーマにもできますが、`<h1>` が1つも無いと
スクリーンリーダーで読む閲覧者がページの題を掴めなくなります。
