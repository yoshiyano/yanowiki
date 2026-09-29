"""第三者ライブラリ（_sys/vendor/、バンドラ不要のもの）の資材を配信する。

置きかたは_sys/vendor/README.txt参照。1ライブラリ1フォルダで、配布版の
ファイルをそのままコピーしているだけなので、ここでは単純にディスクから
読んで返すだけでよい。編集画面・バックアップ画面など、複数の機能から
同じライブラリを参照できるよう、機能ごとのディレクトリ（_sys/editor/等）
とは分けてある。
"""
import os

from wikilib.paths import VENDOR_DIR, safe_join
from wikilib.web import plain, static_file


def serve_vendor_asset(relpath):
    """/.vendor/<relpath> を配信する（例: relpath="diffmerge/diffmerge.umd.js"）。

    ライブラリは複数ファイル・サブディレクトリ構成のまま置くため、
    relpathはそのまま結合する。VENDOR_DIRの外を指す場合は404にする
    （../ を使ったディレクトリ逸脱を防ぐ、wikilib.paths.safe_join参照）。"""
    if not relpath:
        return plain("no page", status=404)
    target = safe_join(VENDOR_DIR, relpath)
    if target is None or not os.path.isfile(target):
        return plain("no page", status=404)
    directory, filename = os.path.split(target)
    return static_file(filename, root=directory)
