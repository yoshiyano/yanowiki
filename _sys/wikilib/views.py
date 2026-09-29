"""ページが無いとき・Wikiが無いときの画面と、ページ本体の表示。"""
import os
from html import escape
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib import auth
from wikilib.accesslog import record_access
from wikilib.dbbackup import maybe_backup
from wikilib.paths import (
    LOGIN_URLPATH, SEARCH_URLPATH, default_markup_ext, farm_plugin_dir, is_valid_pagepath,
    pagepath_of_subpath,
)
from wikilib.pagedb import page_updated_at, published_ref
from wikilib.plugins import build_markdown_renderer
from wikilib.render import render_source
from wikilib.wikiconfig import default_markup
from wikilib.themes import (
    login_href, make_plugin_context, render_theme, render_with_theme,
)

NO_PAGE_ICON = (
    '<svg class="no-page-icon" viewBox="0 0 24 24" width="56" height="56" aria-hidden="true" '
    'fill="none" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 3v5h5"/><path d="M12 12v4"/><path d="M12 18.5v.01"/>'
    "</svg>"
)

NO_VIEW_ICON = (
    '<svg class="no-page-icon" viewBox="0 0 24 24" width="56" height="56" aria-hidden="true" '
    'fill="none" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round">'
    # 錠前の形。ページが無いときの「紙」と見分けが付くようにしている
    '<rect x="5" y="11" width="14" height="10" rx="2"/>'
    '<path d="M8 11V7a4 4 0 0 1 8 0v4"/><path d="M12 15v2"/>'
    "</svg>"
)

NO_FARM_ICON = (
    '<svg viewBox="0 0 24 24" width="64" height="64" aria-hidden="true" '
    'fill="none" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><path d="M12 16.5v.01"/>'
    "</svg>"
)


def render_no_page(wiki_dir, config, farm, pagepath, explicit_farm):
    """存在しないページ。Wiki自体は在るのでテーマを適用し、本文領域に案内を出す。
    メニュー・検索・TopicPathはいつもどおり使えるので、そこから移動できる。"""
    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    shown = "/" + pagepath if pagepath else "/"
    # 作成リンクを出す条件は2つ。
    #   1. 予約プレフィックス（"=" や "."）で始まらない＝ページとして作れる名前
    #      （作れない名前で誘っても行き止まりになる）
    #   2. 閲覧者がそのページの編集の権限（W）を持つ（入口は権限で出し分ける。
    #      Wiki設計者の指示、2026-09-29）
    create = ""
    if is_valid_pagepath(pagepath) and \
            auth.page_privilege(wiki_dir, auth.current_uid(wiki_dir, farm)).check(pagepath) \
            == auth.PAGE_WRITE:
        # 編集画面は'.edit'という別パスを持たない。そのページ自身の通常URLへ
        # cmd=editを送ることで開く（wiki.pyのdispatch参照）。
        edit_href = "{}/{}".format(escape(context.base_url), escape(urlquote(pagepath)))
        create = (
            '<p class="no-page-actions">'
            f'<form method="post" action="{edit_href}">'
            '<input type="hidden" name="cmd" value="edit">'
            '<button type="submit" class="no-page-create">このページを作る</button>'
            "</form></p>"
        )
    body = (
        '<div class="no-page">'
        + NO_PAGE_ICON
        + '<p class="no-page-message">このページはまだありません</p>'
        f'<p class="no-page-path"><code>{escape(shown)}</code></p>'
        + create +
        '<p class="no-page-hint">'
        f'名前の綴りを確かめるか、<a href="{escape(context.base_url)}/{SEARCH_URLPATH}'
        f'?q={escape(urlquote(os.path.basename(pagepath)))}">この名前で検索</a>してみてください。'
        "</p>"
        f'<p class="no-page-hint"><a href="{escape(context.base_url)}/">トップページへ戻る</a></p>'
        "</div>"
    )
    title = os.path.basename(pagepath) or farm
    return render_theme(engine, wiki_dir, config, farm, pagepath, title, body,
                       editable=False, explicit_farm=explicit_farm, context=context, status=404)


def _login_link_html(base_url, pagepath):
    """未ログイン向けの「ログインする」リンク（403の画面に添える）。"""
    return (f'<p class="no-page-hint"><a href="{escape(login_href(base_url, pagepath))}">'
            "ログインする</a></p>")


def render_login(wiki_dir, config, farm, explicit_farm):
    """ログインの入口（`/.login`）。中身は `#login()` と同じフォーム。

    **ページの権限の対象ではない**（Wiki設計者の指示、2026-09-21）。ページの本文を
    出す画面ではなく、閲覧にもログインを求めるWikiでも、ここが開かないと誰も入れない。
    ページ名でもないので、`Login` という名前のページを作っても衝突しない。

    フォームの部品と、送信の結果（`?login=…`）の文言は `#login` プラグインが持つ。
    ここはそれを**そのまま出すだけ**にして、フォームを二重に持たない。
    `?back=<ページ>` があれば、ログインできたあとにそのページへ戻る
    （プラグインが `next` として送り、`auth.back_page_url` が確かめる）。"""
    ext = default_markup_ext(default_markup(config))
    context = make_plugin_context(config, farm, wiki_dir, LOGIN_URLPATH, explicit_farm, ext=ext)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    content, _title, _toc = render_source(engine, "#login()", ext, True, context)
    return render_theme(engine, wiki_dir, config, farm, LOGIN_URLPATH, "ログイン", content,
                        editable=False, explicit_farm=explicit_farm, context=context)


def render_no_view(wiki_dir, config, farm, pagepath, explicit_farm, logged_in):
    """閲覧する権限が無いページ（403）。

    **ページのデータを使わずに描く。** 呼び出し元（`render_page`）は権限を
    `published_ref` の戻り値で見るので、データ自体は読み出し済みだが
    （Wiki設計者の指示、2026-09-15）、本文も題名もここへは渡さない。出すのは
    URLに書かれていたページ名だけ。

    **無いページでも、読めなければこの画面にする。** 「まだありません」と作成の
    誘いを出しても、作ったあとで本人が開けない行き止まりになるため。ページが
    在るかどうかを隠すためではない（Wiki設計者、2026-09-15。「閲覧権のない人に
    閲覧できないページがあることを知られることは問題ではありません」）。

    編集の入口も出さない（`editable=False`）。**読めないページは編集もできない**
    という枠組みで、ここから編集画面へ誘っても行き止まりになる。"""
    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    body = no_view_body_html(context.base_url, pagepath, logged_in)
    title = os.path.basename(pagepath) or farm
    return render_theme(engine, wiki_dir, config, farm, pagepath, title, body,
                       editable=False, explicit_farm=explicit_farm, context=context, status=403)


def no_view_body_html(base_url, pagepath, logged_in):
    """「このページを閲覧する権限がありません」の本文HTML（標準の403の画面の中身）。

    **`#readauth` などのプラグインも、これを使って止める**（`PluginContext.deny_view`。
    Wiki設計者の指示、2026-09-21）。プラグインごとに文言を持たず、閲覧の権限で断られたときと
    同じ画面・同じ案内（未ログインならログインのリンクつき）にそろえるため。"""
    pagepath = (pagepath or "").strip("/")
    shown = "/" + pagepath if pagepath else "/"
    if logged_in:
        hint = "閲覧できるアカウントでログインし直すか、Wikiの管理者に相談してください。"
    else:
        hint = "閲覧できるアカウントでログインしてから開いてください。"
    return (
        '<div class="no-page no-view">'
        + NO_VIEW_ICON
        + '<p class="no-page-message">このページを閲覧する権限がありません</p>'
        f'<p class="no-page-path"><code>{escape(shown)}</code></p>'
        f'<p class="no-page-hint">{hint}</p>'
        + ("" if logged_in else _login_link_html(base_url, pagepath))
        + f'<p class="no-page-hint"><a href="{escape(base_url)}/">トップページへ戻る</a></p>'
        "</div>"
    )


def render_no_edit(wiki_dir, config, farm, pagepath, explicit_farm, logged_in):
    """編集する権限が無いページ（403）。

    **閲覧はできるが編集はできない**場面の断り（Wiki設計者の指示、2026-09-17）。
    テーマの「編集・履歴・リネーム」は権限に応じて出さないが、URLを直に叩けば
    編集の入口（`cmd=edit` のPOST）へ届くので、画面としても断る。

    読めないページはここへ来ない（`render_no_view` のほうが先に出る）。
    本文は出さない——編集を断る画面に本文を並べても使い道が無いため。"""
    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    shown = "/" + pagepath if pagepath else "/"
    if logged_in:
        hint = "編集できるアカウントでログインし直すか、Wikiの管理者に相談してください。"
    else:
        hint = "編集するにはログインしてください。"
    body = (
        '<div class="no-page no-edit">'
        + NO_VIEW_ICON
        + '<p class="no-page-message">このページを編集する権限がありません</p>'
        f'<p class="no-page-path"><code>{escape(shown)}</code></p>'
        f'<p class="no-page-hint">{hint}</p>'
        + ("" if logged_in else _login_link_html(context.base_url, pagepath))
        + f'<p class="no-page-hint"><a href="{escape(context.base_url)}/{escape(urlquote(pagepath))}">'
        "ページの表示に戻る</a></p>"
        "</div>"
    )
    title = os.path.basename(pagepath) or farm
    return render_theme(engine, wiki_dir, config, farm, pagepath, title, body,
                       editable=False, explicit_farm=explicit_farm, context=context, status=403)


def render_no_farm(farm):
    """存在しないWiki。Wiki自体が無い＝テーマも設定も辿れないため、
    どのテーマにも依存しない自己完結のHTMLを返す。"""
    name = escape(farm or "")
    named = f"<p class=\"name\"><code>{name}</code></p>" if name else ""
    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wikiが見つかりません</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    margin: 0; min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background: #f7f7f8; color: #26262b;
    font-family: system-ui, -apple-system, "Segoe UI", "Noto Sans JP", "Hiragino Sans", Meiryo, sans-serif;
    line-height: 1.8;
  }}
  .box {{
    max-width: 30rem; margin: 2rem; padding: 2.5rem 2rem;
    text-align: center; background: #fff;
    border: 1px solid #e0e0e4; border-radius: 12px;
    box-shadow: 0 2px 16px rgb(0 0 0 / 6%);
  }}
  .icon {{ color: #b0862f; }}
  h1 {{ margin: 1rem 0 0.5rem; font-size: 1.25rem; font-weight: 600; }}
  p {{ margin: 0.5rem 0; font-size: 0.95rem; color: #5c5c66; }}
  code {{
    padding: 0.15em 0.5em; border-radius: 5px;
    background: #f0f0f3; color: #26262b;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #16161a; color: #e6e6ea; }}
    .box {{ background: #1e1e23; border-color: #32323a; box-shadow: none; }}
    p {{ color: #a0a0ac; }}
    code {{ background: #2a2a31; color: #e6e6ea; }}
  }}
</style>
</head>
<body>
<div class="box">
  <div class="icon">{NO_FARM_ICON}</div>
  <h1>アクセスしたWikiは存在しません</h1>
  {named}
  <p>アドレスを確認してください。</p>
</div>
</body>
</html>
"""
    return HTTPResponse(body=html, status=404, content_type="text/html; charset=utf-8")


def render_page(wiki_dir, config, farm, pagepath, explicit_farm, had_trailing_slash=False):
    # URLの正規化。フォルダを兼ねるページの実体名（.../index）がそのままURLに
    # 来た場合や、末尾スラッシュ（Tech/）付きで来た場合は、正規のURL
    # （.../index を落とし、末尾スラッシュも無い形）へ寄せる。
    # ページ名が"index"を含むこと自体は起こり得ない
    # （is_valid_pagepathでは弾いていないが、通常の操作では作れない・
    #   resolve_page_refがフォルダの実体として先に解決してしまうため）。
    normalized = pagepath_of_subpath(pagepath)
    if had_trailing_slash or normalized != pagepath:
        context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm)
        location = context.base_url + ("/" + normalized if normalized else "/")
        return HTTPResponse(status=303, headers={"Location": location})

    # 表示するのは**公開された内容**（DB）。平文ファイルだけを書き換えた分は、
    # 取り込む（./wiki.py updatepage）まで出てこない
    ref = published_ref(wiki_dir, pagepath)

    # 閲覧の権限は `published_ref` が入れてくる `ref.privilege` で見る（Wiki設計者の
    # 指示、2026-09-15。以前は読み出す前に `auth.page_privilege` を別に呼んでいた）。
    # `-` でも ref には本文が入っているが、**描画も記録もしない**。
    # **在る・無いより先に見る**——読めない名前に「まだありません」と作成の誘いを
    # 出すと、作ったあと本人が開けない（`render_no_view` 参照）。
    # 管理者・助手もここでは特別扱いしない（判定器の決まりどおり。特別扱いは
    # あとで指示を受けて足す）。
    if ref is not None and ref.privilege == auth.PAGE_NONE:
        return render_no_view(wiki_dir, config, farm, pagepath, explicit_farm,
                              logged_in=auth.current_uid(wiki_dir, farm) is not None)
    if ref is None or not ref.exists:
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)

    record_access(wiki_dir, request.path, request.remote_addr,
                  request.headers.get("User-Agent"),
                  content_updated_at=page_updated_at(wiki_dir, ref.subpath))
    # DBの控えが前日以前なら取り直す（別スレッド。ふだんは日付を1つ見るだけ）
    maybe_backup(wiki_dir)

    # 記法（.md ならMarkdown、.txt ならPukiWiki記法）の違いは
    # render_source が引き受けるので、ここでは拡張子をそのまま渡す。
    #
    # 編集の権限（`W`）が無ければ `editable=False` で描く（Wiki設計者の指示、
    # 2026-09-17）。テーマはこれ1つで「編集・履歴・リネーム」もホットキーの
    # 目印も、セクション編集の目印（`data-editable`）も落とす。**画面から
    # 消すだけでなく、編集の入口自体も断る**（`editor.render_edit`・
    # `editor.serve_section`）。
    return render_with_theme(
        wiki_dir, config, farm, pagepath, ref.body, explicit_farm, ref.subpath, ref.ext,
        source_path=ref.path, editable=ref.privilege == auth.PAGE_WRITE)
