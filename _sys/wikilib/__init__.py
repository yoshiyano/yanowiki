"""wikiSystem の実装をまとめたパッケージ。

wiki.py は起動とURLの振り分けだけを担い、実際の処理はこの下のモジュールが持つ。
`_sys/` を sys.path に入れているため、`from wikilib import ...` で読み込める
（パッケージにしてあるのは、`render` や `search` のような一般的な名前が
標準ライブラリや依存パッケージと衝突しないようにするため）。

モジュールの依存はおおよそ次の向きで、循環しないようにしてある。

    paths / wikiconfig          … 定数・設定・ページの場所の解決（土台）
      ↓
    plugins → render → themes    … 本文の組み立て
      ↓
    backup / pagedb / pagesave / pagesync / attach / pagetree / search
      ↓
    editor / views              … 画面
"""
