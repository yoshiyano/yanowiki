この wiki（wiki farm インスタンス）固有のテーマを配置するディレクトリです。
全 wiki 共通のテーマはトップレベルの theme/ に配置します。

ここに base.html / base.css / base.js を置くと、同名の共通テーマより優先され、
このwikiだけレイアウトやデザインを差し替えられます。

一部だけ変えたい場合は、共通テーマを継承して必要なブロックだけを書くのが手軽です。

    {% extends "common/base.html" %}
    {% block commands %}...{% endblock %}

共通テーマは "common/" を付けた名前で参照してください（"base.html" と書くと
このファイル自身を継承することになり、無限再帰でエラーになります）。

詳しい説明は wiki ページ /ThemeGuide（一般向け）と /Tech/ThemeGuide（開発者向け）を参照してください。
