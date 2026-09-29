"""login — ページの中でログイン・ログアウト・パスワード変更・アカウント作成をする。

    &login();          いま入っている人の表示名（未ログインなら「来訪者」）
    &login(id);        いま入っている人のID（未ログインなら「未登録」）

    #login()           未ログイン時 … ログインフォーム
                          （タブを切り替えてアカウント作成も受け付ける）
                        ログイン中  … 現在のユーザー情報＋ログアウトボタンと、
                          パスワード変更をタブで切り替え
                        **管理者と助手**… さらに「管理者メニュー」のタブが
                          増え、`/.admin` と同じ道具の一覧がそこに出る
    #login(){案内文}    案内文（Wikiテキスト）をフォームの上に添える

`#login()`が作る領域は`<fieldset>`（見出しは「ログインフォーム」）で
囲みます。

 1. id … 単語を書くと、`&login();`の表示をIDにする (default: 表示名)
       `#login()`側では意味を持ちません（常にID・表示名の両方を出します）

中身（`{}`）は省略できます。書けば、フォームの上に案内文として表示されます
（例: 「社内向けページです。ログインしてください」）。

ログイン画面そのものは持ちません。このプラグインを置いたページが、その
まま入口になります（どのページに置くかはページを書く人が決めます）。

**アカウントは誰でも作成できます。** 作ったばかりのアカウントには何の
権限も付きません（`/Tech/LoginPlugin`参照）。
"""

""" 技術資料
wikiSystem側が用意した受け口（`/Tech/LoginPlugin`、Wiki設計者の指示、2026-09-08）
を使う。cookieとDBの書き換えはシステム側（`POST /.plugin/login` /
`POST /.passwd`）が行い、このプラグインは画面（フォーム）を組み立てるだけ。

## いま誰が入っているか

`wikilib.auth.current_user(context.wiki_dir, context.farm)`。ログイン中
ならアカウント辞書（`uid`/`name`/`uidnum`/`pw`）、いなければ`None`。

## フォームの送り先

- ログイン・ログアウト・アカウント作成 → `POST {base_url}/.plugin/login`
  （`cmd`で用を分ける。無し=ログイン、`logout`、`signup`。**このプラグイン
  自身の`_action`が受ける**（Wiki設計者の指示、2026-09-11。専用URL `/.login` を
  廃止し、他のプラグインと同じ`_action`の窓口に一本化した）
- パスワード変更 → `POST {base_url}/.passwd`（こちらは変わらずシステム側）

`PLUGIN_URLPATH`/`PASSWD_URLPATH`は`wikilib.paths`の定数をそのまま使う
（`.plugin`/`.passwd`を直書きしない）。`_action`が呼ばれたときの`context`
（`wikilib.plugins.PluginContext`）を、そのまま`wikilib.auth.do_login`
等へ渡す——画面（フォーム）はこちらが作り、cookieとDBの書き換えは
向こうが受け持つ、という分担は変わっていない。

## `back`（戻り先）

すべてのフォームに`<input type="hidden" name="back" value="そのページの
パス">`を入れる。`wikilib.auth.back_page_url`が読み、済んだらそのページ
へ303で戻す。**ページパスだけを送る**（`context.page`を`strip("/")`した
もの。ルートページなら空文字列）。`back`フィールド自体を省くと戻り先が
無くなり、`do_login`等がそのWikiの入口へ飛ばしてしまうため、常に送る
（値が空文字列でも「送っている」ことが重要——`back_page_url`は
`"back" not in request.forms`かどうかで判定しており、空文字列は
ルートページとして正しく扱われる）。

## 結果の読み取り

戻ってきたページのURLには`?login=done|made|applied|pending|out|revoked|ng|lock`が付く
（`applied`は承認制のWikiで申請できたとき、`pending`は承認待ちのアカウントでログインしようとしたとき）
（`ng`には`&left=n`が付くことがある）。専用のヘルパーは無いため、
`_convert`の中で`bottle.request.query`から直接読む（wikiSystem側に確認済み、
2026-09-08）。ロック接近の文言は自分で組み立てず
`wikilib.auth.lock_warning(left)`を呼ぶ（同じ文言を2か所に書くと
片方だけ直したときに食い違うため。当初`_lock_warning`という内部専用関数
だったが、この依頼を機にwikiSystem側で`lock_warning`という公開名に
改名してもらった）。

## 複数回呼び出しの区別

`id`属性・タブのradioの`name`をページ内で一意にするため、`context`に
連番（`context._login_seq`）を持たせて振る（`vote.py`等の
`context._<name>_counters`と同じ発想。呼び出しごとに使い捨てでよいので
辞書ではなく単純なカウンタで足りる）。

## タブはCSSだけで作る（JS不要）

`plugin/login.js`は無い。radioボタン＋labelの`:checked`と隣接兄弟結合子
（`~`）だけでパネルを切り替える、JavaScript無しのCSSタブ
（`plugin/login.css`）。「JavaScript無しでも使えるようにするかは既存
プラグインの流儀に合わせる」よう言われたが、`ls.py`の`ajaxview`（JS無しでも
通常のページ遷移として機能する）のように、この機能自体がJS前提で設計する
必然性が無かったため、最初からCSSだけで作った（JS版に後退させたのでは
ない）。

**タブの骨組み（`_tabs_html`）は未ログイン時・ログイン中で共通化してある**
（Wiki設計者の指示、2026-09-08「パスワード変更はログインユーザ情報とタブ切り替え
で入れ替えで表示」）。CSSのクラス名も`login-tab-radio-in`/`-up`のような
場面ごとの名前ではなく`login-tab-radio-1`/`-2`という位置ベースの名前に
した（未ログイン時は1=ログイン・2=アカウント作成、ログイン中は
1=アカウント・2=パスワード変更、と中身だけが変わる）。

## `<fieldset>`で囲む（Wiki設計者の指示、2026-09-08）

`#login()`が作る領域全体を`<fieldset class="login"><legend>ログイン
フォーム</legend>...</fieldset>`で囲む。中に複数の独立した`<form>`
（ログイン・アカウント作成・パスワード変更・ログアウト）を持つ変則的な
使いかたになるが、指示どおり「`#login`で作った領域」全体を1つの
`<fieldset>`として視覚的にまとめている。

## `&login(id)`（Wiki設計者の指示、2026-09-08）

`id`は`flag: True`（単語を書くだけで有効になる真偽フラグ、`ls.py`の
`recursive`と同じ糖衣構文）。`_inline`だけが参照し、`_convert`
（`#login()`側）では使わない——**フレームワーク側は`args`の宣言を
`_convert`/`_inline`のどちらでも共通に見るため、`#login(id)`のように
ブロックで書いても構文エラーにはならず、単に`_convert`が`resolved["id"]`
を読まないので効果が無いだけ**（README「ブロック専用にしたい引数」の
逆で、インライン専用にしたい引数も同じ扱いになる）。

## `&login();`の未ログイン時の表示（Wiki設計者の指示、2026-09-08）

当初は未ログインなら空文字列を返していたが、「表示名は『来訪者』、IDは
『未登録』を返してほしい」との指示で、`_GUEST_NAME`/`_GUEST_ID`という
固定文字列を返すよう変更した。`#login()`側の判定（`user is None`かどうか
で分岐）には影響しない——`&login();`だけの見せかたの話。

## パスワード変更フォームの`uid`

`wikilib.accounts.render_passwd`（`/.passwd`単体のページ）は`uid`を
利用者に入力させる（誰でも開けるページで、押した相手が誰かをその場では
特定できないため）。`#login`のパスワード変更フォームは**ログイン中にしか
出さない**ので、`current_user`で分かっている`uid`を隠しフィールドに固定し、
毎回入力させない（同じ`render_passwd`を送り先にしていても、フォームの
出しかたはプラグイン側の判断でよい——`render_passwd`はどのフォームから
POSTされたかを区別しない）。

## エスケープ

`current_user`の`name`/`uid`、`context.page`由来の`back`、bodyの案内文
（`expand_block`/`expand_inline`/`expand_plugin`を宣言しているので展開済み
HTMLとして渡ってくる。`note.py`と同じ扱いでエスケープしない）以外は、
組み立てる文字列はすべて固定のテンプレートなので追加のエスケープ対象は無い。

## CSRF対策は追加していない

`/.plugin/login`/`.passwd`のcookieは`samesite="lax"`（`accounts.py`
`_remember_login`）で、クロスサイトのPOSTには送られない。既存の
`accounts.py`側のフォーム自体もCSRFトークンを持たない設計なので、
このプラグインだけ別の対策を足すと一貫性が崩れる。踏み台対策
（`back`に外部URLを渡せない）は`back_page_url`側が担っている。

## `_action`と`context.explicit_farm`（Wiki設計者の指示、2026-09-11）

`_action(context)`は`ls.py`・`updateDB.py`等と同じ、`/.plugin/<name>`の
汎用の窓口（`wikilib.plugins.render_plugin_action`）から呼ばれる。
`wikilib.auth.back_page_url`/`do_login`/`do_logout`/`do_signup`は
`(config, farm, wiki_dir, explicit_farm)`を引数に取る古いシグネチャの
ままなので、`context.explicit_farm`（この依頼を機にwikiSystem側で
`PluginContext`へ追加してもらった）からそのまま渡す。**`base_url`を
渡す形に作り替えなかったのは、`render_passwd`等の既存の呼び出しと
シグネチャを揃えたかったため**（wikiSystem側の判断）。
"""
from html import escape

from bottle import request

from wikilib.auth import (back_page_url, current_user, do_login, do_logout,
                         do_revoke_others, do_signup, lock_warning)
from wikilib.paths import (LOGIN_COOKIE, LOGIN_URLPATH, PASSWD_URLPATH, PLUGIN_URLPATH,
                          wiki_cookie_name)

PLUGIN_INFO = {
    "help": "#login() / &login(id);",
    "expand_block": True,
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "id", "flag": True, "default": False},
    ],
}

_GUEST_NAME = "来訪者"
_GUEST_ID = "未登録"


def _next_id(context):
    n = getattr(context, "_login_seq", 0) + 1
    context._login_seq = n
    return str(n)


def _notice(message, bad=False):
    if not message:
        return ""
    cls = "login-notice login-notice-error" if bad else "login-notice"
    return f'<div class="{cls}" role="status">{escape(message)}</div>'


def _result_notice():
    result = request.query.get("login") or ""
    if result == "done":
        return _notice("ログインしました。")
    if result == "made":
        return _notice("アカウントを作成しました。")
    if result == "applied":
        return _notice("アカウントを申請しました。管理者か助手が承認するまで、ログインできません。")
    if result == "pending":
        return _notice("このアカウントは承認待ちです。承認されるまで、ログインできません。", bad=True)
    if result == "out":
        return _notice("ログアウトしました。")
    if result == "revoked":
        return _notice("他の端末のログイン状態を取り消しました。この端末はそのままご利用いただけます。")
    if result == "lock":
        return _notice("このアカウントはロックされています。管理者に解除を頼んでください。", bad=True)
    if result == "ng":
        left = request.query.get("left") or ""
        return _notice("IDかパスワードが違います。" + lock_warning(left), bad=True)
    return ""


def _hidden_back(back):
    """戻り先の隠し欄。**ログインの入口（`/.login`）に置いたときだけ、ログインしたあとに
    戻るページ（`?back=`）を `next` として添える**（Wiki設計者の指示、2026-09-21）。
    値の確かめは本体（`wikilib.auth.back_page_url`）が行う。ここは運ぶだけ。"""
    html = f'<input type="hidden" name="back" value="{escape(back)}">'
    if back == LOGIN_URLPATH:
        # **`getunicode` で読む。** `query.get` は日本語のページ名をLatin-1として読んで
        # 文字化けさせる（`[TA向け]` が壊れてログイン後の転送先が違っていた。2026-09-21）
        after = request.query.getunicode("back", "")
        html += f'<input type="hidden" name="next" value="{escape(after)}">'
    return html


def _login_action_url(context):
    """ログイン・ログアウト・アカウント作成の送信先。`_action`（下）が
    `/.plugin/login` で受ける（Wiki設計者の指示、2026-09-11。旧 `/.login` を廃止）。"""
    return escape(f"{context.base_url}/{PLUGIN_URLPATH}/login")


def _login_form_html(context, back, uid, i):
    login_url = _login_action_url(context)
    return f"""<form class="login-form" method="post" action="{login_url}">
  <div class="login-row">
    <label for="login-uid-{i}">ID</label>
    <input id="login-uid-{i}" type="text" name="uid" value="{escape(uid)}"
           autocomplete="username" autofocus required
           pattern="[0-9A-Za-z]+" title="半角の英数字だけが使えます">
  </div>
  <div class="login-row">
    <label for="login-pw-{i}">パスワード</label>
    <input id="login-pw-{i}" type="password" name="pw" autocomplete="current-password" required>
  </div>
  {_hidden_back(back)}
  <div class="login-actions">
    <button type="submit" class="login-go">ログイン</button>
  </div>
</form>"""


def _signup_form_html(context, back, i):
    login_url = _login_action_url(context)
    return f"""<form class="login-form" method="post" action="{login_url}">
  <input type="hidden" name="cmd" value="signup">
  <p class="login-signup-note">アカウントはどなたでも作成できます。</p>
  <div class="login-row">
    <label for="login-signup-uid-{i}">ID</label>
    <input id="login-signup-uid-{i}" type="text" name="uid"
           autocomplete="username" required
           pattern="[0-9A-Za-z]+" title="半角の英数字だけが使えます">
  </div>
  <div class="login-row">
    <label for="login-signup-name-{i}">表示名</label>
    <input id="login-signup-name-{i}" type="text" name="name">
  </div>
  <div class="login-row">
    <label for="login-signup-pw-{i}">パスワード</label>
    <input id="login-signup-pw-{i}" type="password" name="pw" autocomplete="new-password" required>
  </div>
  <div class="login-row">
    <label for="login-signup-pw2-{i}">もう一度</label>
    <input id="login-signup-pw2-{i}" type="password" name="pw2" autocomplete="new-password" required>
  </div>
  {_hidden_back(back)}
  <div class="login-actions">
    <button type="submit" class="login-go">作成してログイン</button>
  </div>
</form>"""


def _tabs_html(i, *pairs):
    """位置ベースのクラス名（`-1`/`-2`/`-3`）で組み立てるCSSタブの骨組み。

    `pairs` は `(見出し, 中身)` の並び。未ログイン時（ログイン/アカウント
    作成）・ログイン中（アカウント/パスワード変更）のどちらも、中身だけを
    差し替えてこれを使う。

    **枚数は可変**（Wiki設計者の指示、2026-09-13。管理者と助手には
    「管理者メニュー」が3枚目として増える）。CSSは位置ベースなので、
    増やせる上限は `login.css` が持つクラスの数と揃っている
    （いまは3枚まで）。"""
    radios, labels, panels = [], [], []
    for n, (label, panel) in enumerate(pairs, 1):
        checked = " checked" if n == 1 else ""
        radios.append(
            f'  <input type="radio" name="login-mode-{i}" id="login-mode-{n}-{i}"\n'
            f'         class="login-tab-radio login-tab-radio-{n}"{checked}>')
        labels.append(
            f'    <label for="login-mode-{n}-{i}" '
            f'class="login-tab login-tab-{n}">{label}</label>')
        panels.append(
            f'  <div class="login-tab-panel login-tab-panel-{n}">{panel}</div>')
    nl = "\n"
    return f"""<div class="login-tabs" id="login-tabs-{i}">
{nl.join(radios)}
  <div class="login-tab-list" role="tablist">
{nl.join(labels)}
  </div>
{nl.join(panels)}
</div>"""


def _logged_out_html(context, back, i):
    # 前に入っていたIDを初期値に出す。cookieの名前はWikiごとに分かれている
    # （`wikilib.paths.wiki_cookie_name`）ので、そのWikiのぶんを名指しで読む。
    uid = request.get_cookie(wiki_cookie_name(LOGIN_COOKIE, context.farm)) or ""
    login_form = _login_form_html(context, back, uid, i)
    signup_form = _signup_form_html(context, back, i)
    return _tabs_html(i, ("ログイン", login_form), ("アカウント作成", signup_form))


def _passwd_form_html(context, back, user, i):
    passwd_url = escape(f"{context.base_url}/{PASSWD_URLPATH}")
    return f"""<form class="login-form" method="post" action="{passwd_url}">
  <input type="hidden" name="uid" value="{escape(user['uid'])}">
  <div class="login-row">
    <label for="login-cur-{i}">いまのパスワード</label>
    <input id="login-cur-{i}" type="password" name="current" autocomplete="current-password" required>
  </div>
  <div class="login-row">
    <label for="login-new1-{i}">新しいパスワード</label>
    <input id="login-new1-{i}" type="password" name="new1" autocomplete="new-password" required>
  </div>
  <div class="login-row">
    <label for="login-new2-{i}">もう一度</label>
    <input id="login-new2-{i}" type="password" name="new2" autocomplete="new-password" required>
  </div>
  {_hidden_back(back)}
  <div class="login-actions">
    <button type="submit" class="login-go">パスワードを変える</button>
  </div>
</form>"""


def _logout_form_html(context, back):
    login_url = _login_action_url(context)
    return f"""<form class="login-form login-logout" method="post" action="{login_url}">
  <input type="hidden" name="cmd" value="logout">
  {_hidden_back(back)}
  <button type="submit" class="login-go login-logout-go">ログアウト</button>
</form>"""


def _revoke_form_html(context, back):
    """「他端末からの認証を解除する」。**ログアウトのすぐ上**に置く
    （Wiki設計者の指示、2026-09-24）。押した端末は入ったまま残る。"""
    login_url = _login_action_url(context)
    return f"""<form class="login-form login-revoke" method="post" action="{login_url}">
  <input type="hidden" name="cmd" value="revoke">
  {_hidden_back(back)}
  <button type="submit" class="login-go login-revoke-go">他端末からの認証を解除する</button>
</form>"""


_AUTH_PERIOD_NOTE = (
    "このログイン状態は1日ごとに更新します。同じブラウザから毎日"
    "利用していれば認証不要です。しかし2日以上利用が無いと"
    "再びログインを要求します。"
)


def _pending_html(context, user):
    """「承認待ち x人」の赤字。**承認できる人（管理者と助手）だけ**に、承認待ちがあるときだけ出す。

    判定は本体の `wikilib.auth.is_staff`、人数は `wikilib.userdb.pending_users` に任せる
    （プラグイン側で「承認できるのは誰か」「承認待ちとは何か」を決め直さない）。"""
    from wikilib.auth import is_staff
    from wikilib.paths import APPROVALS_URLPATH
    from wikilib.userdb import pending_users

    if not is_staff(context.wiki_dir, user):
        return ""
    waiting = len(pending_users(context.wiki_dir))
    if not waiting:
        return ""
    url = escape(f"{context.base_url}/{APPROVALS_URLPATH}")
    return (f'<p class="login-pending"><a href="{url}" title="承認する画面を開く">'
            f"承認待ち {waiting}人</a></p>\n  ")


def _account_panel_html(context, user, back):
    """現在ログイン中のユーザー情報＋ログアウトボタン（タブの1枚目）。
    「ようこそ、○○さん」ではなく現在のユーザーそのものを示す表示に
    する（Wiki設計者の指示、2026-09-08）。

    **認証される期間の説明を添える**（Wiki設計者の指示、2026-09-11）。旧
    `/.login`（GETで開き直したときの完了画面）にあった文言で、独立画面を
    廃止したいまはここが唯一の置き場所になる。

    **管理者と助手には、承認待ちのアカウントがあるとき、ログイン中のユーザーの
    すぐ下に赤字で「承認待ち x人」を出す**（Wiki設計者の指示、2026-09-21）。
    押すと承認する画面（`/.admin/approvals`）へ行く。承認待ちが0人なら出さない。"""
    name = user["name"] or user["uid"]
    return f"""<p class="login-current">現在ログイン中のユーザー:
    <strong>{escape(name)}</strong>（ID: <code>{escape(user["uid"])}</code>）</p>
  {_pending_html(context, user)}<p class="login-hint">{_AUTH_PERIOD_NOTE}</p>
  {_revoke_form_html(context, back)}
  {_logout_form_html(context, back)}"""


def _admin_panel_html(context, user):
    """「管理者メニュー」の中身。**`/.admin` に出るものと同じ一覧**。

    組み立ては本体（`wikilib.adminui.admin_tools_html`）に任せる
    （Wiki設計者の指示、2026-09-13）。**同じ一覧を2か所で作るとかならず
    食い違う**ので、道具を足すときは `adminui.TOOLS` に1行書けば、
    `/.admin` とこのタブの両方に出る。

    見た目は `accounts.css`（`acct-` のクラス）が持っている。ふつうの
    ページに差し込むこのタブではそれが届かないので、**`/.admin` への
    入口も添えて**、体裁が崩れていてもそちらへ行けるようにしてある。"""
    from wikilib.adminui import ADMIN_URLPATH, admin_tools_html
    from wikilib.userdb import is_admin

    tools = admin_tools_html(context.base_url, user, is_admin(user))
    admin_url = escape(f"{context.base_url}/{ADMIN_URLPATH}")
    return (f'<div class="login-admin">{tools}'
            f'<p class="login-admin-more">'
            f'<a href="{admin_url}">管理の窓口（/{escape(ADMIN_URLPATH)}）を開く</a>'
            f"</p></div>")


def _logged_in_html(context, user, back, i):
    """ログイン中の画面。**管理者と助手には「管理者メニュー」が増える**
    （Wiki設計者の指示、2026-09-13）。

    判定は本体の `wikilib.auth.is_staff`（＝`admin` か `g:staff`）に任せる。
    プラグイン側で「管理者とは誰か」を決め直さないため。"""
    from wikilib.auth import is_staff

    tabs = [("アカウント", _account_panel_html(context, user, back)),
            ("パスワード変更", _passwd_form_html(context, back, user, i))]
    if is_staff(context.wiki_dir, user):
        tabs.append(("管理者メニュー", _admin_panel_html(context, user)))
    return _tabs_html(i, *tabs)


def _convert(resolved, body, context):
    user = current_user(context.wiki_dir, context.farm)
    back = (context.page or "").strip("/")
    i = _next_id(context)
    note = f'<div class="login-note">{body}</div>' if body else ""
    panel = _logged_in_html(context, user, back, i) if user is not None \
        else _logged_out_html(context, back, i)
    # **div.login-notice は div.login-tabs（= panel）の下に置く**
    # （Wiki設計者の指示、2026-09-11）。以前は案内文・タブより先頭に出していた。
    return (f'<fieldset class="login"><legend>ログインフォーム</legend>'
            f'{note}{panel}{_result_notice()}</fieldset>')


def _inline(resolved, body, context):
    user = current_user(context.wiki_dir, context.farm)
    if user is None:
        return escape(_GUEST_ID if resolved["id"] else _GUEST_NAME)
    if resolved["id"]:
        return escape(user["uid"])
    return escape(user["name"] or user["uid"])


def _action(context):
    """`POST /.plugin/login` の受け口。フォームの送信先を一本化する
    （Wiki設計者の指示、2026-09-11。旧 `/.login` を廃止）。

    **画面はこちら（プラグイン）が作り、cookieとDBの書き換えはシステム側
    （`wikilib.accounts`）が受け持つ**という分担は変わらない
    （`Tech/LoginPlugin`参照）。`cmd` で用を分けるのは旧`/.login`と同じ。"""
    back = back_page_url(context.config, context.farm, context.wiki_dir,
                         context.explicit_farm)
    cmd = request.forms.get("cmd") or ""
    if cmd == "logout":
        return do_logout(context.config, context.farm, context.wiki_dir,
                         context.explicit_farm, back)
    if cmd == "revoke":
        return do_revoke_others(context.config, context.farm, context.wiki_dir,
                                context.explicit_farm, back)
    if cmd == "signup":
        return do_signup(context.config, context.farm, context.wiki_dir,
                         context.explicit_farm, back)
    return do_login(context.config, context.farm, context.wiki_dir,
                    context.explicit_farm, back)
