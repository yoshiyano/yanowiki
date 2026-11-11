"""icd — 文の中にコード（inline code）を書く、インライン専用のプラグイン。

    &icd{wiki.py};

中身を `<code>` で囲んで表示します。Markdownの `` `wiki.py` `` と同じ表示です。
PukiWiki記法のページで使います。Markdown記法のページでは `` `wiki.py` `` と書きます。

中身の書きかたやプラグインは展開しません（`''a''` は `''a''` のまま出ます）。
周りの書きかたに読まれる文字は、前に `\\` を付けます。

    \\{  \\}    対になっていない波括弧
    \\'        強調の中の `''`（`\\'\\'`）
    \\%        打ち消しの中の `%%`（`\\%\\%`）
    \\|        表のセルの中の `|`（付けなくても書けます）
    \\\\        上の文字の前と中身の末尾の `\\`（`&icd{C:\\\\};`）

ほかの `\\` はそのまま表示します（`C:\\Users`、`\\d+`）。
"""

""" 技術資料
PukiWiki記法には文中のコードの書きかたが無い。編集画面で書きかたを切り替える
ときに本文も変換する検討の中で、Markdownの `` `code` `` の対応先が無いことが
分かり（`_system` 以外の実ページで19,280か所）、設計者が専用のプラグインを
用意することにした。「&icd{}; と表現したものは逆変換で inline code に対応させます」
（2026-11-07）。書きかたを切り替える変換器はまだ無い。

## 中身を展開しない

`expand_*` を宣言しない。コードの中の記号を飾りとして読むと、`` `code` `` と
同じものにならない。

## `` `code` `` との置き換え

このプラグインの目的は、`` `code` `` と機械的に置き換えられること。設計者「pukiwiki から
markdown にする際には、これも機械的な置き換えで inline code にすることを目的としています」
（2026-11-07）。エスケープはパーサーが中身の範囲を決める段階で関わるので、
置き換えの関数とともに `wikilib.icdbody` にある。
"""

from html import escape

from wikilib.icdbody import decode_body
from wikilib.plugins import PluginArgumentError

PLUGIN_INFO = {
    "help": "&icd{コード};（Markdown記法のページでは &icd(){コード};）",
    "args": [],
}


def _inline(resolved, body, context):
    if not body:
        raise PluginArgumentError("中身（{コード}）を書いてください。")
    # `"` は &quot; に、`'` はそのままに。Markdownの `code` と同じ文字列にする
    return "<code>" + escape(decode_body(body), quote=False).replace('"', "&quot;") + "</code>"
