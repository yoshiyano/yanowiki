"""bottle のレスポンスまわりの小さな道具。"""
import os
from html import escape

from bottle import HTTPResponse, request
from bottle import static_file as _bottle_static_file

from wikilib.paths import wiki_cookie_name


def cookie_secure():
    """いまの要求が HTTPS で届いたか。cookie に `Secure` を付けるかの判定に使う。

    `Secure` を常に付けると、HTTP で開いたとき（`./wiki.py` を LAN の IP で
    開くなど）にブラウザが cookie を送らなくなり、ログインできなくなる。
    そのため HTTPS のときだけ付ける。

    判定は bottle の `urlparts.scheme` に任せる。Apache・nginx の後ろでは
    `X-Forwarded-Proto` を、直に受けたときは `wsgi.url_scheme` を見る。
    ヘッダーは偽装できるが、偽れるのは送った本人の cookie に `Secure` が
    付くかどうかだけなので害はない。要求の外（テストなど）では付けない。"""
    try:
        scheme = request.urlparts.scheme
    except (RuntimeError, KeyError, AttributeError):
        return False
    # プロキシを重ねると "https, http" のように並ぶことがある。先頭が閲覧者側
    return (scheme or "").split(",")[0].strip().lower() == "https"


# ---- 別のサイトから送られた POST を断る（CSRF） ----------------------------------
#
# 書き換えの POST は、`Origin`（無ければ `Referer`）の宛先が、この要求の宛先（`Host`、
# プロキシ越しなら `X-Forwarded-Host` も）と同じときだけ受ける。入口（`wiki.py` の
# `dispatch`）で全部の POST に当てるので、本体の画面もプラグインの `_action` も
# 個別に書かなくてよい。設計者の決定（2026-10-23）: フォームごとのトークンではなく、
# `Origin` の照合で守る。以下はクロコの実装例（設計者は未確認）:
#
# - 比べるのはホストとポート番号だけ。スキームは見ない（TLS を終えるプロキシの
#   後ろでは、ブラウザの https とサーバの http が食い違うため）
# - `Origin` も `Referer` も無い POST は通す。今のブラウザは別のサイトからの POST に
#   必ず `Origin` を付けるので、両方が無いのはブラウザ以外（curl・スクリプト）から
#   送ったもの。CSRF はブラウザに送らせる攻撃なので、これを断っても守りは増えない
# - `Origin: null`（サンドボックスの iframe・file: のページなど）は断る
# - ヘッダーは別のサイトのフォームからは書き替えられないので、`Host`・
#   `X-Forwarded-Host` を信用してよい（偽れるのは送った本人だけ）

_DEFAULT_PORTS = {"http": "80", "https": "443"}


def _netloc(value, scheme=""):
    """`host[:port]` を小文字にし、スキームの既定のポート番号を外す。"""
    value = (value or "").split(",")[0].strip().lower()
    port = _DEFAULT_PORTS.get(scheme)
    if port and value.endswith(":" + port):
        value = value[: -len(port) - 1]
    return value


def cross_site_reason():
    """いまの POST が別のサイトから送られたものなら、その理由（文字列）。同じサイト・
    判断の材料が無い・要求の外なら None。"""
    from urllib.parse import urlsplit
    try:
        env = request.environ
    except RuntimeError:
        return None
    source = env.get("HTTP_ORIGIN")
    if source is None:
        source = env.get("HTTP_REFERER")
        if not source:
            return None
    if source.strip().lower() == "null":
        return "Origin: null"
    try:
        parts = urlsplit(source.strip())
    except ValueError:
        return f"読めない送り元: {source[:200]}"
    scheme = (parts.scheme or "").lower()
    sent_from = _netloc(parts.netloc, scheme)
    if not sent_from:
        return f"読めない送り元: {source[:200]}"
    own = {_netloc(env.get(key), scheme) for key in ("HTTP_HOST", "HTTP_X_FORWARDED_HOST")}
    own.discard("")
    if sent_from in own:
        return None
    return f"送り元 {sent_from} が宛先 {', '.join(sorted(own)) or '(不明)'} と違う"


def reject_cross_site():
    """別のサイトから送られた POST への 403。"""
    return HTTPResponse(
        body=("<!doctype html><meta charset=\"utf-8\"><title>受け付けません</title>"
              "<h1>受け付けません</h1><p>別のサイトのページから送られた要求なので、"
              "受け付けませんでした。</p><p>この Wiki の画面から操作した場合は、"
              "ページを開き直してから、もう一度お試しください。</p>"),
        status=403, content_type="text/html; charset=utf-8")


# ---- Wikiごとのcookie ---------------------------------------------------------
#
# cookieは読む・置く・消すをこの3つに集める。決まりは次のとおりで、
# 個々の画面で書き分けない。
#
#   名前      `wiki_cookie_name(base, farm)` でWikiごとに分ける（経緯は同関数）
#   Path      そのWikiの入口。空（既定のWikiをサブパス無しで使う）なら "/"
#             ——空にするとブラウザが「いまのURLのディレクトリ」を使い、
#             ページによって届いたり届かなかったりする
#   SameSite  Lax
#   Secure    HTTPS で届いたときだけ（`cookie_secure`）
#
# **置く・消すは「返すHTTPResponse自身」（`out`）に対して行う。** bottleは、
# ハンドラがHTTPResponseを返すと、スレッドローカルの `response` ではなく
# 返されたほうを使う。`bottle.response.set_cookie(...)` だとSet-Cookieが落ちる。
# **消すときは、置いたときと同じPathにする。** cookieは名前とPathの組で
# 決まるので、違うPathで消しにいっても残る。


def get_wiki_cookie(base, farm):
    """そのWikiのcookieの値。無ければ空文字列。"""
    return request.get_cookie(wiki_cookie_name(base, farm)) or ""


def set_wiki_cookie(out, base, farm, value, path, max_age, httponly=False):
    """そのWikiのcookieを `out` に置く。`httponly` は画面のJavaScriptから
    読む用が無いものに付ける（ログイン状態のcookieなど）。"""
    out.set_cookie(wiki_cookie_name(base, farm), value, path=path or "/",
                   max_age=max_age, samesite="lax", httponly=httponly,
                   secure=cookie_secure())


def delete_wiki_cookie(out, base, farm, path):
    """そのWikiのcookieを `out` で消す。`path` は置いたときと同じものを渡す。"""
    out.delete_cookie(wiki_cookie_name(base, farm), path=path or "/",
                      samesite="lax", secure=cookie_secure())

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
    `ChangeLogTech/System/todo.md` に記録されていた。

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
