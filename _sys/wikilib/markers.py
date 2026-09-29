"""マーカーシステム。複数の用語を色分けしてページをまたいで追跡する。

**本体（`_sys/markers/markers.js`/`markers.css`）は全ページに自動で差し込む**
（`wikilib.themes.render_theme` が本文へ `<link>`/`<script>` を足す）ため、
どのテーマを選んでいても同じように使え、テーマ側の変更は要らない
（`_sys/editor/` と同じ考えかた）。

状態（用語・色・用語セット・最後に使った時刻）は**ブラウザのlocalStorageだけ**
に持つ。サーバー側はページを配るだけで、状態そのものは一切扱わない
（wikiSystemにはログイン・アカウントの仕組みが無く、「誰の」状態かをサーバー側
で紐づける手段が無いため）。

操作用の画面（用語の追加・色・用語セットの切り替え・一致数などの表示）は、
本体とは別ウィンドウ（`/.markers-panel`、`window.open`）として持つ。本文の
中に置くと、テーマのレイアウト崩れやスクロールの奪い合いを気にしなければ
ならなくなるため。本体（page側）と操作画面（panel側）は同じオリジンの
`BroadcastChannel`（`wikisys-markers`）で状態の変化だけを伝え合い、実際の
値はどちらも同じlocalStorageを読み直す（片方が持ちきりにしない）。
"""
import os

from wikilib.paths import MARKERS_DIR
from wikilib.web import plain, serve_asset, static_file


def serve_markers_asset(name):
    """全ページに差し込む本体のCSS/JSを配信する（/.markers.css, /.markers.js）。"""
    return serve_asset(MARKERS_DIR, "markers", name)


def serve_markers_panel_asset(name):
    """操作用の別ウィンドウが持つCSS/JSを配信する（/.markers-panel.css, .js）。"""
    return serve_asset(MARKERS_DIR, "panel", name)


def render_markers_panel():
    """操作用の別ウィンドウそのもの（/.markers-panel）。

    特定のWiki・farmに紐づかない（状態はlocalStorageに置き、オリジン全体で
    共有する）ので、テーマは通さず素のHTMLをそのまま返す。"""
    if not os.path.isfile(os.path.join(MARKERS_DIR, "panel.html")):
        return plain("no page", status=404)
    return static_file("panel.html", root=MARKERS_DIR)
