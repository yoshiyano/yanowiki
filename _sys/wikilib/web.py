"""bottle のレスポンスまわりの小さな道具。"""
import os
from html import escape

from bottle import HTTPResponse
from bottle import static_file as _bottle_static_file

def html_page(title, body_html):
    """テーマのテンプレートが見つからない場合に使う最低限のHTML。"""
    return (
        "<!doctype html>\n"
        '<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{escape(title)}</title>\n</head>\n<body>\n{body_html}\n</body>\n</html>\n"
    )


def plain(body, status=200):
    return HTTPResponse(body=body, status=status, content_type="text/plain; charset=utf-8")


def static_file(filename, root):
    """静的資材（テーマ・編集画面・検索など、bottleが配信するCSS/JS等）を
    `Cache-Control: no-cache` 付きで返す（`bottle.static_file` のラッパー）。

    既定（ヘッダ無し）だと、ブラウザは仕様上のヒューリスティックキャッシュ
    （更新日時からの経過時間の一定割合を「新鮮」とみなす）に従うため、
    **ふつうのナビゲーション（リロードではない）ではサーバーに一切
    問い合わせずキャッシュから返してしまう。** テーマ・編集画面のCSS/JSを
    更新しても、ハードリロードしないと反映されない不具合として
    `Tech/ChangeLog/todo.md` に記録されていた。

    `no-cache` は「キャッシュ禁止」ではなく「使う前に必ず再検証」の意味。
    ETag/Last-Modified による条件付きGETはそのまま効くので、実際に変わって
    いなければ304で済み、帯域は増えない。"""
    response = _bottle_static_file(filename, root=root)
    response.set_header("Cache-Control", "no-cache")
    return response


def serve_asset(directory, basename, name, kinds=("css", "js")):
    """画面が自前で持つ資材（CSS/JS）を配信する。無ければ404。

    URLに現れるのは拡張子だけ（`/.groups.css` なら `name="css"`）で、実際の
    ファイル名は `<basename>.<name>`。

    **同じ処理を各画面が自前で持っていたのを1つにまとめたもの**（Wiki設計者の指示、
    2026-09-13。「同じようなことをさせているのに別のコードを使っている事例
    などがあれば共通化する」）。13か所が1行ずつの呼び出しになった。

    `kinds` は受け付ける拡張子。CSSだけの画面は `("css",)` を渡す。"""
    if name not in kinds:
        return plain("no page", status=404)
    filename = f"{basename}.{name}"
    if not os.path.isfile(os.path.join(directory, filename)):
        return plain("no page", status=404)
    return static_file(filename, root=directory)
