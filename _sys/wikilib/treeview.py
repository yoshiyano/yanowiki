"""ページ一覧のTreeViewが持つCSS/JS（/.treeview.css, /.treeview.js）。

ページ選択ダイアログ・名前を変える画面・バックアップ管理画面が同じものを使う。
3か所に同じ木を別々に持っていたので、1つにまとめてある。**同じ見た目のものが
場所によって違う動きをする**のがいちばん困るため。

木の中身（何を出すか・選ぶと何が起きるか）は使う側が決め、ここは
「並べかた・開閉・キーボードでの動かしかた」だけを受け持つ。
"""

from wikilib.paths import TREEVIEW_DIR
from wikilib.web import serve_asset


def serve_treeview_asset(name):
    """TreeViewが自前で持つCSS/JS。渡ってくるのは拡張子だけ。"""
    return serve_asset(TREEVIEW_DIR, "treeview", name)
