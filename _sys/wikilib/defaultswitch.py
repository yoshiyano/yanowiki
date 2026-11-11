"""既にあるWikiを起点Wiki（`farm.default`）に切り替える（`/.allwiki` のボタン）。

Webから切り替える道は、これまで「新しく作るときに選ぶ」（`/.newwiki`）だけで、
既にあるWikiへは `config/server.yaml` を手で書き換えるしかなかった。

    1. 一覧の行の「起点Wikiにする」     確認の画面へ（まだ何も変わらない）
    2. 切り替え先の管理者のパスワード   通ったらその場で書き換える

## 3つの条件（クロコの案。設計者は 2026-11-07「その案で実装してください」と承認）

切り替えると、再起動・Wikiの作成と削除・一覧を扱える人がまるごと移り、実行した
本人はその権限を失う。**操作を間違えても画面からは戻せない**ので、次を求める。

  - **管理者のいないWikiへは切り替えない。** Web上で管理操作をできる人が
    いなくなるため（`target_problem`）
  - **切り替え先の管理者のパスワードを求める。** 起点Wikiの管理者であることは、
    別のWikiへサービス全体の権限を渡してよい証しにならない。`/.delwiki` が消される側の
    パスワードを求めるのと同じ考えかた
  - **実行できるのは起点Wikiの管理者だけ。** 助手が一覧を見られても（`site.allwiki`）、
    切り替えは通さない。ボタンも出さない

パスワードの照合は `auth.try_password` に通す。記録とロックをログインと同じ扱いに
するためで、理由は `delwiki._to_check` と同じ（ここだけ素通しにすると、そのWikiの
管理者のパスワードを当て放題に試せる窓口になる）。

## 書き込める名前を絞る

`set_default_farm` は名前をYAMLの値としてそのまま書く。手で `wikidata/` に置いた
Wikiの名前は決まりの外のことがあり、`a b` は次に書き換えるときに行を壊し、`123` や
`true` は文字列として読み戻せない（`writable_name`）。新規作成の決まり
（`newwiki.WIKI_NAME_RE`）は `_system` を弾くので、`_system` へ戻す切り替えに使えない。

## 操作の記録

`stafflog` には残さない。実行できるのが管理者だけで、管理者の操作は記録しない決まり
（`wikilib.stafflog` 冒頭）のため。
"""
import re
from html import escape

from bottle import request

from wikilib import allwiki, auth, delwiki, sysui
from wikilib.newwiki import reads_back_as_name
from wikilib.paths import farm_wiki_dir
from wikilib.themes import make_plugin_context
from wikilib.wikiconfig import load_default_farm, set_default_farm

STEP_CHOOSE = "choose"      # 一覧のボタンから来た
STEP_PASSWORD = "password"  # 確認の画面から来た

# `_system` を通すため、先頭の `_` を許す（`newwiki.WIKI_NAME_RE` は弾く）
_WRITABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")


def writable_name(name):
    """`server.yaml` に書いて、同じ文字列として読み戻せる名前か（冒頭の説明を参照）。"""
    return bool(_WRITABLE_NAME_RE.match(name)) and reads_back_as_name(name)


def target_problem(name, config):
    """切り替えられない理由。問題なければ None。

    **名前は実在する一覧との一致で見る**（`delwiki.target_problem` と同じ）。"""
    if not name:
        return "切り替え先のWikiを選んでください。"
    if name not in allwiki.wiki_names():
        return "「{}」というWikiはありません。".format(name)
    if name == load_default_farm(config):
        return "「{}」は、すでに起点Wikiです。".format(name)
    if not writable_name(name):
        return ("「{}」は名前に使えない字を含むか数値などに読めるため、"
                "ここからは切り替えられません。".format(name))
    target_dir = farm_wiki_dir(name)
    if target_dir is None or delwiki.admin_row(target_dir) is None:
        return ("「{}」には管理者がいないので切り替えられません。"
                "`./wiki.py initusers ={}` で用意してからやり直してください。"
                .format(name, name))
    return None


def handle_post(wiki_dir, config, farm, explicit_farm, urlpath):
    """`/.allwiki` へのPOST。起点Wikiか（`require_on_default_farm`）は呼ぶ側で確かめ済み。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm, urlpath, auth.ADMIN_ONLY)
    if denied is not None:
        return denied

    name = (request.forms.getunicode("name", "") or "").strip()
    problem = target_problem(name, config)
    if problem:
        return allwiki.list_page(wiki_dir, config, farm, explicit_farm, urlpath,
                                 problem=problem)

    if request.forms.get("step") != STEP_PASSWORD:
        return _confirm_page(wiki_dir, config, farm, explicit_farm, urlpath, name)

    admin = delwiki.admin_row(farm_wiki_dir(name))
    typed = request.forms.getunicode("admin_pw", "") or ""
    user, locked, left = auth.try_password(farm_wiki_dir(name), admin["uid"],
                                           admin["uid"], typed)
    if user is None:
        warning = "" if left is None else auth.lock_warning(str(left))
        note = ("「{}」の管理者のパスワードが違います。".format(name)
                + ("このアカウントはロックされています。" if locked else warning))
        return _confirm_page(wiki_dir, config, farm, explicit_farm, urlpath, name,
                             problem=note.strip(), status=403)

    if not set_default_farm(name):
        return _confirm_page(
            wiki_dir, config, farm, explicit_farm, urlpath, name,
            problem=("`config/server.yaml` を書き換えられませんでした。"
                     "起点Wikiは変わっていません。ファイルの権限と、`farm:` の下に "
                     "`default:` の行があるかを確かめてください。"),
            status=500)
    return _done_page(wiki_dir, config, farm, explicit_farm, urlpath, name)


def _root_of(config, farm, wiki_dir, explicit_farm, urlpath):
    context = make_plugin_context(config, farm, wiki_dir, urlpath, explicit_farm)
    return context.base_url, allwiki.site_root_of(context.base_url)


def _confirm_page(wiki_dir, config, farm, explicit_farm, urlpath, name, problem="", status=200):
    """確認の画面。**何が変わるかを、パスワードを入れる前に見せる。**"""
    base, root = _root_of(config, farm, wiki_dir, explicit_farm, urlpath)
    old = load_default_farm(config)
    body = f"""{sysui.notice(problem, bad=True, prefix="allwiki")}
<div class="allwiki">
  <p class="allwiki-lead">起点Wikiを <strong>{escape(old)}</strong> から
    <strong class="allwiki-target">{escape(name)}</strong> へ切り替えます。</p>
  <ul class="allwiki-effects">
    <li>Wiki名なしのURL（<code>/</code> や <code>/ページ名</code>）は「{escape(name)}」を開きます。
      「{escape(old)}」は <code>/={escape(old)}/</code> で開きます。</li>
    <li><strong>Wikiの作成・削除・一覧と再起動ができる人が、「{escape(name)}」の管理者と助手に
      移ります。</strong>「{escape(old)}」の管理者は、これらを使えなくなります。</li>
    <li>戻すには、「{escape(name)}」の管理者が同じ操作をするか、
      <code>config/server.yaml</code> の <code>farm.default</code> を書き換えます。</li>
  </ul>
  <form class="allwiki-form" method="post" action="{escape(base)}/{escape(urlpath)}">
    <input type="hidden" name="step" value="{STEP_PASSWORD}">
    <input type="hidden" name="name" value="{escape(name)}">
    <label for="aw-adminpw">「{escape(name)}」の管理者のパスワード</label>
    <input id="aw-adminpw" type="password" name="admin_pw"
           autocomplete="current-password" required>
    <p class="allwiki-hint">まちがえた回数は、ふだんのログインと同じように数えられます。
      分からないときは、サーバー上で <code>./wiki.py resetpw ={escape(name)}</code>
      を実行すると入れ直せます。</p>
    <div class="allwiki-actions">
      <button type="submit" class="allwiki-go">切り替える</button>
      <a class="allwiki-cancel" href="{escape(root)}/{escape(urlpath)}">やめる</a>
    </div>
  </form>
</div>
"""
    return sysui.page(wiki_dir, config, farm, explicit_farm, urlpath, "起点Wikiの切り替え",
                      body, css_url=f"{urlpath}.css", status=status)


def _done_page(wiki_dir, config, farm, explicit_farm, urlpath, name):
    """切り替えたあとの画面。

    **もう起点Wikiの管理者ではないので、一覧へは戻さない**（戻すと403になる）。
    `config` は切り替え前のものなので、Wiki名はここで渡された名前で書く。"""
    _base, root = _root_of(config, farm, wiki_dir, explicit_farm, urlpath)
    old = load_default_farm(config)
    message = "起点Wikiを「{}」に切り替えました。".format(name)
    body = f"""{sysui.notice(message, prefix="allwiki")}
<div class="allwiki">
  <p class="allwiki-lead">これから <code>/</code> は「{escape(name)}」を開きます。
    「{escape(old)}」は <code>/={escape(old)}/</code> で開けます。</p>
  <p class="allwiki-hint">Wikiの作成・削除・一覧と再起動には、「{escape(name)}」の管理者か
    助手としてログインしてください。</p>
  <div class="allwiki-actions">
    <a class="allwiki-go" href="{escape(root)}/.login">「{escape(name)}」にログインする</a>
    <a class="allwiki-cancel" href="{escape(root)}/={escape(old)}/">「{escape(old)}」を開く</a>
  </div>
</div>
"""
    return sysui.page(wiki_dir, config, farm, explicit_farm, urlpath, "起点Wikiの切り替え",
                      body, css_url=f"{urlpath}.css")
