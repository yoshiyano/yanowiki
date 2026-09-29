"""システムの画面（`/.admin/…`・`/.groups` ほか）が共通で使う土台。

各画面が自前で持っていた同じ処理を1か所にまとめたもの（Wiki設計者の指示、
2026-09-13。「同じようなことをさせているのに別のコードを使っている事例
などがあれば共通化する」）。

    page()       共通の外枠に本文を入れる  （4か所で重複していた。テーマは通さない）
    notice()     知らせの1行              （2か所）
    json_out()   JSONの応答               （3か所）
    json_body()  POSTのJSON本文の読み取り （2か所）
    require()    通してよい相手かの関門   （3種類に分かれていた）
    require_on_default_farm()
                 サービス全体に効く操作（`/.restart`・`/.newwiki`・`/.allwiki`）
                 の関門

## 関門は「必要なプリンシパルを渡す」形に揃えてある

以前は入口ごとに `require_login`・`require_staff`・`require_admin` と3つの
関数があり、それぞれ別の判定（`current_user is not None`・`is_staff`・
`is_admin`）を呼んでいた。いまは判定を`wikilib.auth.allows`1つに集約し、
ここは**断られたときの画面を作るだけ**になっている。

    denied = require(wiki_dir, config, farm, explicit_farm,
                     ACCOUNTS_URLPATH, auth.ADMIN_ONLY)
    if denied is not None:
        return denied

**断る理由は分けて伝えない。** 「ログインしていない」も「その権限がない」も
同じ文言にしてある。分けると、そのIDが登録されているかどうかを外から
確かめる手がかりになるため。

## CSSは呼ぶ側が指定する

`page()`はCSSのURLを引数で受け取るだけで、どの見た目を使うかは各画面が決める
（`/.groups`は`groups.css`、アカウントまわりと管理の窓口は`accounts.css`）。
断りの画面だけはここが組み立てるので`accounts.css`を使う——クラス名の接頭辞
（`acct-`/`grp-`）を1つに揃えるのは、CSSとHTMLの全面的な書き換えになるため
別の作業にしてある。
"""
import json
import os
from html import escape

from bottle import HTTPResponse, request

from wikilib import auth
from wikilib.paths import ACCOUNTS_URLPATH, BASE_DIR
from wikilib.themes import login_href, make_plugin_context
from wikilib.wikiconfig import load_default_farm


SHELL_CSS_PATH = os.path.join(BASE_DIR, "_sys", "sysui", "shell.css")


def _shell_css():
    """共通の外枠のCSS（`_sys/sysui/shell.css`）。読めなければ空（枠は素のまま出る）。"""
    try:
        with open(SHELL_CSS_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def page(wiki_dir, config, farm, explicit_farm, urlpath, title, body,
         css_url=None, status=200):
    """システム画面に共通の組み立て。`css_url` があれば末尾に足す。

    **テーマは通さない**（Wiki設計者の指示、2026-09-24。「管理ページや編集など幅を
    使うページは、テーマの影響なく共通のフォーマットに」）。編集画面と同じ、
    ヘッダ＋全幅の本文の外枠（`_sys/sysui/shell.css`）に、`body` を入れて返す。
    テーマを替えても、管理ページはいつも同じ見た目と幅になる。

    `css_url` はこのWikiの入口からの相対（例: `".groups.css"`）。"""
    context = make_plugin_context(config, farm, wiki_dir, urlpath, explicit_farm)
    if css_url:
        body += f'<link rel="stylesheet" href="{escape(context.base_url)}/{css_url}">'
    site_title = (config.get("theme") or {}).get("site_title", "wikiSystem")
    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} - {escape(site_title)}</title>
<style>
{_shell_css()}</style>
</head>
<body class="sys-body">
<header class="sys-head">
  <a class="sys-home" href="{escape(context.base_url)}/">{escape(site_title)}</a>
  <span class="sys-kind">{escape(title)}</span>
  <a class="sys-back" href="{escape(context.base_url)}/">ページを見る</a>
</header>
<main class="sys-main">
{body}
</main>
</body>
</html>
"""
    return HTTPResponse(html, status=status,
                        headers={"Content-Type": "text/html; charset=utf-8"})


def notice(message, bad=False, prefix="acct"):
    """画面の上に出す知らせの1行。`message` が空なら何も出さない。

    `prefix` はCSSクラスの接頭辞（`acct-notice` / `grp-notice`）。"""
    if not message:
        return ""
    cls = f"{prefix}-notice {prefix}-notice-error" if bad else f"{prefix}-notice"
    return f'<div class="{cls}" role="status">{escape(message)}</div>'


def json_out(obj, status=200):
    """JSONで応答する（画面のJSが読む窓口）。"""
    return HTTPResponse(body=json.dumps(obj, ensure_ascii=False), status=status,
                        content_type="application/json; charset=utf-8")


def json_body():
    """POSTのJSON本文を辞書で返す。読めなければ空の辞書。

    読めない本文を例外にしないのは、**受け取った側で「知らない操作です」と
    答えられるほうが扱いやすい**ため（呼ぶ側はキーの有無だけを見ればよい）。"""
    try:
        return request.json or {}
    except ValueError:
        return {}


def require(wiki_dir, config, farm, explicit_farm, urlpath, principals):
    """`principals` のどれにも当たらなければ、断りの画面（403）を返す。
    通ってよければ None。

    判定は `wikilib.auth.allows`（プリンシパルの展開）に任せる。画面は
    `auth.ADMIN_ONLY`・`auth.STAFF`・`auth.ANY_USER` のような組み合わせを
    渡すだけでよい。"""
    if auth.allows(wiki_dir, farm, principals):
        return None
    base_url = make_plugin_context(config, farm, wiki_dir, urlpath, explicit_farm).base_url
    return page(wiki_dir, config, farm, explicit_farm, urlpath,
                "権限がある人だけの画面", _denied_html(base_url),
                css_url=f"{ACCOUNTS_URLPATH}.css", status=403)


def require_on_default_farm(config, farm, wiki_dir, explicit_farm, urlpath):
    """**サービス全体に効く操作**（`/.restart`・`/.newwiki`・`/.allwiki`）の関門。
    通してよければ None、駄目なら断りの画面（403）を返す。

    判定に使うのは**既定Wikiの管理者と助手**（Wiki設計者の指示、2026-09-13。
    「`/.restart` と `/.newwiki` は default wiki の g:staff と admin による
    操作のみとします」）。再起動もWikiの作成も**サービス全体に効く**もので、
    隣のWikiの都合で起こされては困る。任せる相手を1組に揃えておけば、
    Wikiがいくつ増えても権限の持ち主は増えない。

    **全Wikiの一覧（`/.allwiki`）もここを通る**（Wiki設計者の指示、2026-09-16。
    「`.allwiki` は `.newwiki` と同様、デフォルトwikiの admin 権限を持っている
    人のみ実行可能に」）。こちらは操作ではなく読むだけだが、並ぶのは**他のWikiの
    名前＝そのままURL**で、サーバーに何が置いてあるかを明かす。見せる相手は
    Wikiを増やせる人と同じ範囲でよい（`wikilib.allwiki` の冒頭）。

    ## Wiki名を含むURLは、既定Wikiのものでも断る

    **`/=<Wiki名>/.restart` は一律403**（Wiki設計者の指示、2026-09-13。
    「`/=other/.restart` や `/=other/.newwiki` は禁止で403扱いです。
    default wiki が dwiki のとき、`/=dwiki/.restart` なども禁止扱いです」）。
    通るのは**Wiki名を含まない `/.restart`** だけになる。

    はじめは「既定Wikiの同じURLへ送り直す」形にしていたが、断る形に改めた。
    こちらのほうが**入口が1つに定まる**——ログイン状態のcookieはWikiごとの
    `Path` に置いてあるので（`auth.remember_login`）、Wiki名付きのURLでは
    どのWikiのcookieが読まれるかが状況次第になる。入口を素のURLだけに
    絞れば、**読めるcookieは既定Wikiのものひとつ**に決まる。

    既定Wikiが見つからない設定のときも、同じように断る（安全側）。"""
    if explicit_farm or farm != load_default_farm(config):
        return page(wiki_dir, config, farm, explicit_farm, urlpath,
                    "このURLでは開けません", _wrong_entrance_html(urlpath),
                    css_url=f"{ACCOUNTS_URLPATH}.css", status=403)
    return require(wiki_dir, config, farm, explicit_farm, urlpath, auth.STAFF)


def _wrong_entrance_html(urlpath):
    """Wiki名を含むURLで開かれたときの断り。

    **ここは理由をはっきり伝えてよい。** 「断る理由は分けて伝えない」という
    決まりは、アカウントの在る無しを外から確かめられないようにするためのもので、
    これはURLの形の話なので、伝えても手がかりにならない。黙って403を返すと、
    権限を持っている人が理由を掴めないまま詰まる。"""
    return f"""<div class="acct acct-denied">
  <p class="acct-notice acct-notice-error" role="status">
    この操作は、Wiki名を含まないURL（<code>/{escape(urlpath)}</code>）から
    だけ行えます。</p>
  <p class="acct-hint">サービス全体に効く操作なので、入口を既定のWikiの
    ひとつに絞ってあります。</p>
</div>
"""


def _denied_html(base_url):
    # **ログインの入口（`/.login`）へのリンクを出す**（Wiki設計者の指示、2026-09-27。
    # 閲覧の権限が無いページ（`views.no_view_body_html`）と同じ案内にそろえる）。
    # 以前は、システムが決まったログイン画面を持たなかったためリンクを出して
    # いなかった（2026-09-11）が、いまは `/.login` がある。
    #
    # **ログインしているかどうかで中身を変えない。** 閲覧を断るページは未ログインの
    # ときだけリンクを出すが、ここは「ログインしていない」と「権限がない」を分けて
    # 伝えない決まり（tests/test_adminui.py の「断る理由は分けて伝えない」）なので、
    # リンクは常に出す。ログインしている人には、別のアカウントで入り直す入口になる。
    #
    # 戻り先（`?back=`）は付けない——システムの画面は戻り先にしない決まり
    # （`themes.login_href`・`auth.back_page_url`）なので、ログインのあとはその
    # Wikiのトップへ戻る。
    #
    # **「管理者」で言い切らない**（Wiki設計者の指示、2026-09-11）。この画面は
    # 管理者だけの入口と、管理者と助手の入口の両方から共通で使われる。
    # 「管理者としてログインしてください」だと助手には不正確なので、
    # どちらでも成り立つ言いかたに揃えてある。
    return f"""<div class="acct acct-denied">
  <p class="acct-notice acct-notice-error" role="status">
    この画面は権限がある人だけが開けます。有効なアカウントでログインしてから開いてください。</p>
  <p class="acct-denied-link"><a href="{escape(login_href(base_url))}">ログインする</a></p>
  <p class="acct-denied-link"><a href="{escape(base_url)}/">トップページへ戻る</a></p>
  <p class="acct-hint">このWikiにアカウントの記録がまだ無い場合は、
    <code>./wiki.py initusers</code> で用意してください。</p>
</div>
"""
