"""ruby — 文字にふりがな（ルビ）を振る、インライン専用のプラグイン。

    &ruby(reading){text};

 1. **reading** … ふりがな（省略不可）

`text`（中身）にふりがなを振ります。ルビ表示に対応していないブラウザ・
読み上げでも`text（reading）`のように読めるフォールバック
（`<rp>`の丸括弧）が入ります。
"""

""" 技術資料
本家PukiWikiの`ruby.inc.php`を移植した。

本家はインライン専用（`plugin_ruby_inline()`のみ、`_convert`は無い）。
`func_get_args()`で受け取った「引数（ふりがな）＋中身」を合わせて
ちょうど2個であることを見て検証していたが、このシステムでは引数
（`resolved["reading"]`、`default`なし＝必須）と中身（`body`）が最初から
分かれているため、その検証を素直に「`reading`は必須引数」「`body`は
`_inline`内で非空を確認」の2つに素直に対応させた。

本家は検証に失敗すると`PLUGIN_RUBY_USAGE`（書きかたの説明文字列）を
**エラー表示ではなく通常の出力としてそのまま返す**、当時のPukiWiki
プラグインによくあった簡易な流儀だった。このシステムの他の移植プラグイン
（`color`/`size`/`note`等）はすべて`PluginArgumentError`による通常の
エラー表示（赤枠）に統一されているため、`ruby`もそれに揃えた
（見た目のページを壊さない・書いた側に何が悪いか伝わる、という目的自体は
変わらない。実現手段だけをこのシステムの標準的なエラー表示に揃えた
という位置づけ）。

## `<rb>`/`<rp>`をそのまま残した理由

本家の出力形式（`<ruby><rb>本文</rb><rp>(</rp><rt>ふりがな</rt><rp>)</rp>
</ruby>`）をそのまま踏襲した。`<rb>`はHTML5のルビ関連要素として現在も
有効なタグで、廃止・非推奨ではない。`<rp>`の丸括弧はルビ表示に対応して
いないブラウザ・読み上げソフトでの読みやすさ（フォールバック）を担って
おり、単なる見た目の飾りではなく機能なので削らずに残した。

## 中身（body）・引数（reading）の扱い（本家に合わせる）

本家は、中身をほかのインラインプラグインの中身と同じく展開（`make_link`）
してから、`strip_htmltag()` でHTMLタグだけを取り除いて使う。展開のときに
`&amp;` のような文字参照は文字参照のまま保たれるので、`&ruby(あ){X&amp;Y};`
は「X&Y」と表示される。このシステムでも同じにする（Wiki設計者の指示）:
`expand_inline`・`expand_plugin` を宣言して中身を展開させ、返ってきたHTMLから
タグだけを除く。タグを除いても文字参照（`&lt;` など）はエスケープされた
ままなので、生の `<` が出ることは無い。

以前は中身を展開せず `html.escape()` していたため、`&amp;` が `&amp;amp;` と
二重にエスケープされ、「&amp;」とそのまま表示されていた。

`reading` は本家の `htmlsc($ruby)` と同じくエスケープする（こちらは展開しない）。
"""

import re
from html import escape

from wikilib.plugins import PluginArgumentError

# 本家の strip_htmltag() と同じく、タグだけを取り除く
TAG_RE = re.compile(r"<[^>]+>")

PLUGIN_INFO = {
    "help": "&ruby(reading){text};",
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "reading", "label": "ふりがな"},
    ],
}


def _inline(resolved, body, context):
    text = TAG_RE.sub("", body or "").strip()
    if not text:
        raise PluginArgumentError(
            "ふりがなを振る文字を指定してください: &ruby(reading){text};"
        )

    reading = resolved["reading"]
    return (
        f'<ruby><rb>{text}</rb><rp>(</rp>'
        f'<rt>{escape(reading)}</rt><rp>)</rp></ruby>'
    )
