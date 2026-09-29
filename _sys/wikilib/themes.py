"""テーマ（Jinja2テンプレート）でページ全体を組み立てる。

本文HTMLは呼び出し側が用意する。ここはその外側（ヘッダ・メニュー・目次・
TopicPath）を組み立てて1枚のページにするところまでを受け持つ。
"""
import datetime
import os
import re
import time
from urllib.parse import quote as urlquote
from html import escape

from bottle import HTTPResponse, request
from jinja2 import (
    ChoiceLoader, Environment, FileSystemLoader, PrefixLoader, TemplateError,
    select_autoescape,
)
from markupsafe import Markup

from wikilib.paths import (
    LOGIN_URLPATH, MARKERS_PANEL_URLPATH,
    MARKERS_URLPATH, SEARCH_URLPATH, THEME_COOKIE,
    THEME_COOKIE_MAX_AGE, THEME_DIR, THEMESELECT_URLPATH, THEME_URLPATH,
    farm_plugin_dir, is_valid_pagepath, resolve_page, safe_join, wiki_cookie_name,
)
from wikilib.diskusage import DiskUsage
from wikilib.draft import has_draft
from wikilib.plugins import (
    PluginContext, build_markdown_renderer, plugin_script_urls, plugin_style_urls,
)
from wikilib.render import parse_source, render_source, rewrite_content_links
from wikilib.web import plain, static_file
from wikilib.wikiconfig import farm_base_url, version_label

DEFAULT_THEMEFILE = "base"  # 既定のテーマ名（theme/base.html を参照する）
THEME_COMMON_PREFIX = "common"  # 個別Wiki固有テーマから全Wiki共通テーマを継承するための名前空間

_jinja_envs = {}


def theme_dirs(wiki_dir):
    """テーマの探索パス。個別Wiki固有のtheme/を優先し、無ければ全Wiki共通のtheme/を使う。"""
    return [os.path.join(os.path.dirname(wiki_dir), "theme"), THEME_DIR]


def theme_search_dirs(wiki_dir, themefile):
    """テーマ本体（`<themefile>.html`）とその資材（css/js等）を探すパスの一覧。

    theme_dirs()の各探索先の直下に `<themefile>/` というフォルダがあれば、
    そのフォルダ自体を（サブフォルダとしてではなく）basedirとして先に探させる。
    フォルダ形式のテーマは、これまでのフラットな置き方と同じ命名
    （`tname.html`・`tname.css`・`tname.js`）のまま、その中に一式まとめて置ける
    （wikiThemesからの依頼、2026-09-04）。

    common.css等、テーマ間で共有する資材はフォルダの中には置かない想定なので、
    その場合はこの並びのまま次の探索先（フラットなtheme_dirs側）まで
    フォールバックして見つかる。

    themefileの結合には`wikilib.paths.safe_join`を使い、各探索先dの外に
    出る値（`../../etc`等）ならフォルダ探索を行わない。`theme.name`は
    運用者が書く設定値だが、素の`os.path.join`に渡すと設定ミスや共有環境
    での意図しない値から探索先が広がってしまうため。

    **フォルダとして見るのは、探索先の「下」にあるものだけ。** `theme.name`が
    `"."`のような値だと結合結果が探索先そのものになり、同じディレクトリが
    2回並んでしまう（実害は無いが、探索を無駄に2度行い、Jinja環境の
    使い回しの鍵も余計に増える）。境界の中には収まるので`safe_join`では
    弾かれないため、ここで見分ける。"""
    dirs = []
    for d in theme_dirs(wiki_dir):
        cand = safe_join(d, themefile) if themefile else None
        if (cand is not None and cand != os.path.normpath(os.path.abspath(d))
                and os.path.isdir(cand)):
            dirs.append(cand)
        dirs.append(d)
    return dirs


def list_theme_names(wiki_dir):
    """選べるテーマ名の一覧（個別Wiki固有・全Wiki共通の両方、重複を除いて昇順）。

    数えかたは `theme_search_dirs` の探索規則と揃える。そのディレクトリ直下に
    `<名前>.html` があるか、`<名前>/` フォルダの中に `<名前>.html` がある
    （フォルダ形式のテーマ）かのどちらかを1つのテーマとして数える
    （wikitheme プラグインの `_list_themes` と同じ仕様。Wiki設計者の指示、
    2026-09-04）。

    `search.html` のような、他のテーマへ `{% extends %}` する断片テンプレートも
    この規則では拾えてしまう（自分自身への継承で無限再帰になる）。**それを
    ここで見分けようとはしない**——`render_theme` が描画に失敗しても既定の
    テーマへ後退する仕組みを持っているため（`render_theme` のdocstring参照）、
    選ばれてもサイトは止まらない。"""
    names = set()
    for d in theme_dirs(wiki_dir):
        if not os.path.isdir(d):
            continue
        for entry in os.listdir(d):
            full = os.path.join(d, entry)
            if entry.endswith(".html") and os.path.isfile(full):
                names.add(entry[:-len(".html")])
            elif os.path.isdir(full) and os.path.isfile(os.path.join(full, entry + ".html")):
                names.add(entry)
    return sorted(names)


LOGIN_AS_PREFIX = "Logged in as "


def login_label(wiki_dir, farm):
    """フッタに出す「誰で入っているか」。**未ログインなら空文字。**

    出すのは表示名（無ければログインID）で、`"Logged in as 山田太郎"` の形
    （Wiki設計者の指示、2026-09-14）。**文言は英語**——フッタの他の項目
    （`Convert-time`・`Last-modified`・`DiskUsage`・`Powered by`）に揃えてある。

    テーマ側は**空なら出さない**（`{% if login_as %}`）。値そのものを渡すので、
    テーマが文言を組み立て直す必要はない（`version` や `disk_usage.text` と
    同じ構え）。

    `auth` は `themes` を使う（`make_plugin_context`）ので、**ここでの
    読み込みは呼び出し時**にする——先頭で import すると循環する。"""
    from wikilib.auth import current_user

    user = current_user(wiki_dir, farm)
    if user is None:
        return ""
    return LOGIN_AS_PREFIX + (user["name"] or user["uid"])


def show_selector(config):
    """テーマのセレクタを画面に出すか（設定 theme.selector、既定は出さない）。

    **これは主にサイトを作る人のための道具**で、閲覧者にテーマを選ばせたい
    サイトだけが真にする（Wiki設計者の指示、2026-09-04）。出す・出さないだけを
    決める設定で、cookieに覚えたテーマ自体はこの設定と関係なく効く
    （`cookie_theme` 参照。プラグイン `wikitheme` から設定された場合も
    同じcookieを使うため、ここで無効化すると片方だけ効かなくなる）。"""
    return _flag(config, "selector", default=False)


def cookie_theme(wiki_dir, farm):
    """cookieに覚えてあるテーマ名。無い・実在しない名前ならNone。

    cookieの名前とPathはWiki（farm）ごとに分けてあるので、いま開いている
    Wikiで選んだものだけが届く（`serve_theme_select` 参照）。**名前まで
    分けるのは、Pathだけでは足りないため**——Pathの付かない既定のWikiの
    cookieはどのWikiにも送られ、名前が同じだと後から届いたほうで上書き
    されてしまう（`paths.wiki_cookie_name` に経緯）。

    **値は必ず実在のテーマ名かどうか確かめてから使う**——cookieは閲覧者が
    自由に書き換えられる値で、そのまま `theme_search_dirs` へ渡す入り口に
    なるため（`safe_join` で境界の外には出られないが、確かめられるものは
    確かめておく）。"""
    name = (request.get_cookie(wiki_cookie_name(THEME_COOKIE, farm)) or "").strip()
    if not name:
        return None
    return name if name in list_theme_names(wiki_dir) else None


def theme_selector_html(base_url, wiki_dir, pagepath, current):
    """テーマのセレクタ（選ぶ`<select>`と、cookieを消すリセットボタン）。

    **テーマ側に手を入れずに出せるよう、menu1の中身の先頭へ差し込む**
    （`render_theme`。Wiki設計者の指示、2026-09-04）。`marker_asset_tags` を
    本文の末尾へ足しているのと同じ考えかたで、どのテーマでも自動的に
    出るようにするためのもの。

    送信先は `/.themeselect`（`serve_theme_select`）。JavaScriptは使わず、
    `<select>` の `onchange` でフォームを送るだけにしてある（画面側の
    資材を増やさず、JSが動かない環境でも「選ぶ→送る」ボタンが無いだけで
    同じことができる）。"""
    api = escape(base_url + "/" + THEMESELECT_URLPATH, quote=True)
    back = escape(pagepath, quote=True)
    options = ['<option value="">（既定のテーマ）</option>']
    for name in list_theme_names(wiki_dir):
        selected = " selected" if name == current else ""
        options.append(f'<option value="{escape(name, quote=True)}"{selected}>{escape(name)}</option>')
    return (
        '<div class="theme-selector">'
        f'<form class="theme-selector-form" method="post" action="{api}">'
        f'<input type="hidden" name="page" value="{back}">'
        '<label class="theme-selector-label">テーマ: '
        '<select class="theme-selector-select" name="theme" onchange="this.form.submit()">'
        + "".join(options) +
        '</select></label>'
        '<button type="submit" class="theme-selector-go">切替</button>'
        '</form>'
        f'<form class="theme-selector-reset" method="post" action="{api}">'
        f'<input type="hidden" name="page" value="{back}">'
        '<input type="hidden" name="reset" value="1">'
        '<button type="submit" class="theme-selector-reset-go">既定に戻す</button>'
        '</form>'
        '</div>'
    )


def serve_theme_select(wiki_dir, config, farm, explicit_farm):
    """`/.themeselect` へのPOST。選んだテーマをcookieに覚え、元のページへ戻す。

    受け取るもの（フォーム）:

        theme  選んだテーマ名（空＝既定に戻す）
        reset  "1" なら、themeの値に関わらずcookieを消す
        page   戻り先のページパス（このWiki内のページパスだけ。`/` から
               始まる生のURLや他所のURLは受け取らない——戻り先を自由に
               指定させると、そのまま外部サイトへ飛ばす踏み台になるため）

    cookieの名前はWikiごとに分け（`wikitheme_<Wiki名>`）、`Path`はこのWikiの
    base_urlにする。この2つで `/=foo/` で選んだテーマが `/=bar/` に影響
    しない（Pathだけに頼ると、既定のWikiのcookieが他のWikiにも届いて
    取り違えが起きる。`paths.wiki_cookie_name` 参照）。有効期限は1日
    （`THEME_COOKIE_MAX_AGE`。Wiki設計者の指示）。"""
    base_url = farm_base_url(config, farm, explicit_farm)

    pagepath = (request.forms.getunicode("page", "") or "").strip("/")
    if pagepath and (not is_valid_pagepath(pagepath) or "://" in pagepath):
        # 妙な戻り先はトップに倒す（拒むほどのことではない）。
        # is_valid_pagepath が "=farm名" と "." 始まり（"../" を含む）を弾き、
        # "://" は外部URLらしい値を弾く。**戻り先は必ず base_url の下へ
        # 組み立てる**ので、これらを通しても外部サイトへは飛ばないが、
        # 「このWikiのページパス」以外を受け取らないほうが意図が明確なため。
        pagepath = ""

    # cookieのPathは、このWikiの入口。空（既定のfarmをサブパス無しで
    # 使っている）ときは "/" にする——Pathを空にするとブラウザが
    # 「いまのURLのディレクトリ」を使い、ページによって届いたり届かなかったり
    # してしまうため。
    cookie_path = base_url or "/"

    # **cookieは「返すHTTPResponse自身」に設定する。** bottleは、ハンドラが
    # HTTPResponseを返した場合、スレッドローカルの`response`ではなく返された
    # ほうを使う。`response.set_cookie(...)`と書くとSet-Cookieが落ちて
    # 何も起きない（実際にこれで一度動かなかった）。
    out = HTTPResponse(status=303, headers={"Location": base_url + "/" + pagepath})

    if request.forms.get("reset") == "1":
        out.delete_cookie(wiki_cookie_name(THEME_COOKIE, farm), path=cookie_path)
    else:
        name = (request.forms.getunicode("theme", "") or "").strip()
        if not name:
            out.delete_cookie(wiki_cookie_name(THEME_COOKIE, farm), path=cookie_path)
        elif name in list_theme_names(wiki_dir):
            out.set_cookie(wiki_cookie_name(THEME_COOKIE, farm), name, path=cookie_path,
                           max_age=THEME_COOKIE_MAX_AGE, samesite="lax")
        # 実在しない名前は黙って無視する（cookieは触らない）。画面から選ぶ
        # 限り起こらず、起きても既定のテーマのまま表示されるだけでよい

    return out


def get_jinja_env(dirs):
    key = tuple(dirs)
    env = _jinja_envs.get(key)
    if env is None:
        env = Environment(
            loader=ChoiceLoader([
                FileSystemLoader(dirs),
                # 個別Wiki固有テーマから全Wiki共通テーマを継承できるようにするための別名。
                # 単に "base.html" をextendsすると自分自身を継承して無限再帰するため、
                # 共通テーマには "common/base.html" という名前でも到達できるようにする。
                PrefixLoader({THEME_COMMON_PREFIX: FileSystemLoader(THEME_DIR)}, delimiter="/"),
            ]),
            autoescape=select_autoescape(["html", "xml"]),
        )
        _jinja_envs[key] = env
    return env


def html_page(title, body_html):
    """テーマのテンプレートが見つからない場合に使う最低限のHTML。"""
    return (
        "<!doctype html>\n"
        '<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{escape(title)}</title>\n</head>\n<body>\n{body_html}\n</body>\n</html>\n"
    )


def render_menu(engine, wiki_dir, base_url, name, context=None):
    """メニューページ（mainmenu/submenu等）をレンダリングする。
    本文と同じく、そのページの拡張子の記法で描く（メニューだけMarkdownに
    縛られると、PukiWiki記法で書いているWikiでメニューが書けなくなる）。
    該当ページが無い場合は空文字列を返す（メニュー無しとして扱われる）。

    **閲覧の権限が無いメニューページ（`-`）も空文字列**（Wiki設計者の指示、
    2026-09-15）。メニューはどのページにも出るので、ここで見ないと、読めない
    ページの本文があらゆるページの横に出てしまう。"""
    if not name:
        return ""
    # メニューもページなので、本文と同じく公開された内容（DB）を出す。
    # auth はこのモジュールを読むので、呼び出し時に読み込む
    from wikilib.auth import PAGE_NONE
    from wikilib.pagedb import published_ref
    ref = published_ref(wiki_dir, name)
    if ref is None or not ref.exists or ref.privilege == PAGE_NONE:
        return ""
    ext, body = ref.ext, ref.body
    env = {"wiki": context}
    html = engine.renderer.render(parse_source(engine, body, ext, env), engine.options, env)
    return rewrite_content_links(html, base_url, name, wiki_dir)


def page_title_of(extracted_title, pagepath, default):
    """先頭のh1から取り出したタイトルを使う。無ければページ名。"""
    return extracted_title or os.path.basename(pagepath) or default


def login_href(base_url, pagepath=""):
    """ログインの入口（`/.login`）へのリンク先。

    **いま開いているページを戻り先（`?back=`）として付ける**（Wiki設計者の報告、2026-09-21。
    ページ単位の閲覧制限（`#readauth`）で読めないページから、ナビの「ログイン」を踏んだら
    トップへ行ってしまった）。ログインできたら、そのページへ戻る。

    戻り先を付けるのは**ふつうのページ**だけ。トップ（空）・システムの画面（`.search`・
    `.admin/…` など。`.` や `=` で始まる名前）は付けない。値の確かめは本体
    （`wikilib.auth.back_page_url`）がもう一度行う。"""
    href = f"{base_url}/{LOGIN_URLPATH}"
    if pagepath and is_valid_pagepath(pagepath):
        href += "?back=" + urlquote(pagepath, safe="/")
    return href


def common_menu_html(base_url, login_url, edit_url, pagepath, editable):
    """全テーマ共通のメニュー（ログイン・トップ・編集・新規）をMarkupで返す。

    テーマは `{{ common_menu }}` と置くだけにし、4項目のマークアップ・出し分け・
    ホットキー属性を自前で持たない（wikiThemesからの依頼、2026-09-24）。
    出し分けはここで行う。

      ログイン・トップ … 常に出す
      編集・新規 … editable（そのページの編集の権限）が真のときだけ。
                   編集には data-hotkey="edit"（Alt+E）を付ける

    渡す範囲はこの4項目だけ（検索・ズーム・履歴などは各テーマが持つ）。
    全体を `<span class="common-menu">` で包むのは、テーマが配置・折り返しを
    指定する目印にするため。編集はGETを受け付けないので、そのページ自身の
    通常URLへ POST（cmd=edit）するフォームにする。値はすべて escape する。"""
    sep = '<span class="command-sep" aria-hidden="true">/</span>'
    parts = [
        f'<a class="command" href="{escape(login_url)}">ログイン</a>',
        f'<a class="command" href="{escape(base_url)}/">トップ</a>',
    ]
    if editable:
        parts.append(
            f'<form class="command-form" method="post" '
            f'action="{escape(edit_url)}/{escape(pagepath)}">'
            f'<input type="hidden" name="cmd" value="edit">'
            f'<button type="submit" class="command" data-hotkey="edit">編集</button></form>')
        parts.append('<button type="button" class="command" data-new-page-open>新規</button>')
    html = sep.join(parts)
    if editable:
        # 「開く」で cmd=edit へ移るのは common.js の役目。既存ページ名を入れても、
        # その編集画面が開くだけでよい。送り先の入口URLは**ダイアログ自身の
        # data-base-url** に持たせる——.content[data-editable] の data-base-url は
        # テーマが置くもので、置かないテーマ（Wiki固有のテーマなど）だと空になり、
        # どのWikiから開いても既定のWikiのページになってしまったため。
        # × にも formnovalidate を付ける（入力欄は required なので、無いと
        # 空欄のまま × を押したとき検証で止まり、閉じられない）
        html += (
            f'<dialog class="new-page-dialog" data-base-url="{escape(edit_url)}">'
            '<form method="dialog" class="new-page-form">'
            '<div class="new-page-head">'
            '<strong class="new-page-title">新しいページを開く</strong>'
            '<button type="submit" value="cancel" class="new-page-x" aria-label="閉じる"'
            ' formnovalidate>×</button>'
            '</div>'
            '<label class="new-page-row"><span>ページ名</span>'
            '<input type="text" class="new-page-input" autocomplete="off" required></label>'
            '<div class="new-page-foot">'
            '<button type="submit" value="cancel" class="new-page-cancel" formnovalidate>やめる</button>'
            '<button type="submit" value="ok" class="new-page-ok" disabled>開く</button>'
            '</div></form></dialog>')
    return Markup(f'<span class="common-menu">{html}</span>')


def topic_path_links(base_url, pagepath):
    """TopicPathの各階層を [{label, url}, ...] で返す。
    urlはそのフォルダ（の index）へのリンク。現在のページ自身（末尾の階層）はurlをNoneにし、
    テンプレート側でリンクにしない。ルートの "/" 自体はテンプレート側で別途描画する。"""
    segments = [s for s in pagepath.split("/") if s]
    links = []
    prefix = base_url
    for i, seg in enumerate(segments):
        prefix = prefix + "/" + seg
        is_last = i == len(segments) - 1
        links.append({"label": seg, "url": None if is_last else prefix})
    return links


def show_index(config):
    """ページ一覧に index を出すか（設定 theme.show_index、既定は出さない）。

    index はファイルの置き場所を決めるためにシステムが要求している名前で、
    使う人から見れば**フォルダそのもの**を指す。`/Tech` を開けば `Tech/index` が
    出るのだから、一覧で2つに分けて見せる意味がない。そこで既定では出さず、
    フォルダの行がその入口ページを兼ねる。

    index を名指しで扱いたい場面のために、真にすれば出せるようにしてある。"""
    return _flag(config, "show_index", default=False)


def _flag(config, name, default=True):
    """theme の設定を真偽値として読む。書きかたの揺れ（"false" "no" "off" "0"）を吸収する。

    YAMLが偽と読んだ場合だけでなく、文字列で書かれた場合も同じに扱う。
    設定は人が手で書くものなので、`false` と `"false"` で挙動が変わらないようにする。"""
    value = (config.get("theme") or {}).get(name, default)
    return value is not False and str(value).strip().lower() not in ("false", "no", "off", "0")


def marker_asset_tags(base_url):
    """マーカーシステム本体（CSS/JS）を本文の末尾に足すためのHTML断片。

    **本文（content）へ足す**のは、テーマのテンプレート（`{% block scripts %}`
    等）を一切変えずに、どのテーマでも自動で読み込まれるようにするため
    （全ページ共通にするため、テーマ側の修正を要らないこの1か所――
    `render_theme` が `content` を組み立てる場所――にまとめて足す）。

    操作用ウィンドウ（`/.markers-panel`）を開くための場所（`base_url`）は
    `data-base-url` 属性で渡す（`markers.js` の `document.currentScript` から
    読む。サーバー側のURL構成――サブパス設置やfarmの明示――を知っているのは
    ここだけなので、JS側では判断しない）。"""
    return (
        f'<link rel="stylesheet" href="{escape(base_url)}/{MARKERS_URLPATH}.css">'
        f'<script src="{escape(base_url)}/{MARKERS_URLPATH}.js" '
        f'data-base-url="{escape(base_url)}" '
        f'data-panel-url="{escape(base_url)}/{MARKERS_PANEL_URLPATH}" defer></script>'
    )


# サイドバーのメニュー枠。既定名を持つのは menu1（mainmenu）・menu2（submenu）の
# 2つだけで、3つ目以降（menu3等）は config 側に menuN_page/menuN_mode を
# 書いたときだけ現れる（既定名を持たない＝書かなければ何も足されない）。
DEFAULT_MENU_PAGES = {1: "mainmenu", 2: "submenu"}
_MENU_KEY_RE = re.compile(r"^menu(\d+)_(?:page|mode)$")


def menu_slot_numbers(theme_conf):
    """`theme_conf` に現れる `menuN_page`/`menuN_mode` から、使われている
    メニュー枠の番号を集める（1・2は既定名を持つため常に含める）。

    **新しい枠（menu3、menu4、…）を増やすのに、このモジュールを直す必要は
    無い。** config側で `menu3_page`/`menu3_mode` を書けば、それだけで
    `menu3`/`menu3_mode` が自動でテンプレートへ渡る（テーマ側で `{{ menu3 }}`
    を参照する記述を足すのは別途要る。あくまでこちら側の対応の話）。"""
    nums = set(DEFAULT_MENU_PAGES)
    for key in theme_conf:
        m = _MENU_KEY_RE.match(key)
        if m:
            nums.add(int(m.group(1)))
    return sorted(nums)


def resolve_menu_mode(page, entries):
    """`theme.menu1_mode`/`theme.menu2_mode` の宣言から、このページの
    開閉モードを決める（menu1・menu2共通。判定の中身に違いは無いため）。

    entries は `"ページ名,モード"` 形式の文字列のリスト（`config/default.yaml`
    参照）。該当が無い・モードの綴りが `"auto"`/`"fix"` のどちらでもない場合は
    `"auto"`（既定＝狭い画面で帯として折りたたむ）を返す。宣言そのものを
    省略した場合も同じ（この設定を書かなくても動きが変わらないように）。"""
    for entry in entries or []:
        name, _, mode = entry.partition(",")
        if name.strip() != page:
            continue
        mode = mode.strip() or "auto"
        return mode if mode in ("auto", "fix") else "auto"
    return "auto"


def render_theme(engine, wiki_dir, config, farm, pagepath, title, content, toc=(),
                template=None, editable=True, explicit_farm=False, attach_subpath="",
                context=None, status=200, **extra):
    """テーマでページ全体を組み立てて返す。
    本文HTMLは呼び出し側が用意する（wikiページ・検索結果など用途を問わず使える）。

    explicit_farm: URLで "=farm名" が明示されていたか。デフォルトfarmであっても
    明示的に "/=_system/..." でアクセスしていた場合は、生成するリンクにも
    "=_system/" を残す（省略すると、そのページから見えていた景色が変わってしまうため）。

    attach_subpath: このページ自身の添付ファイルの置き場所（wikidata/<Wiki名>/attach/ 以下の
    相対パス）。本文中の "logo.png" のような裸のファイル名参照を解決するのに使う。"""
    theme_conf = config.get("theme") or {}
    # どのテーマで描くかは、次の順で決まる。**閲覧者が選んだものが最優先**。
    #
    #   1. cookie … 閲覧者が画面のセレクタ（や wikitheme プラグイン）で
    #      選んだテーマ。Wiki（farm）ごとにPathで分けてあり、有効期限は1日
    #      （cookie_theme・serve_theme_select）
    #   2. context.theme_override … ページ単位の指定。本文のプラグイン
    #      （wikitheme等）が立てる、そのページの既定
    #      （PluginContext.theme_override 参照）
    #   3. config の theme.name … そのWikiの既定
    #
    # **cookieを1番目にしてあるのは、そうしないとセレクタが黙って効かない
    # ページができてしまうため。** 当初はページ単位の指定を優先していたが、
    # `#wikitheme(名前)` が書かれたページではセレクタで選んでも何も起きず、
    # Wiki設計者が「セレクタが機能しない」として本文の記法を消して回避する、
    # という状態になった（2026-09-04）。設定の重なりとしても、
    # 「閲覧者本人がいま選んだもの」＞「ページの書き手の既定」＞
    # 「サイト管理者の既定」の順が自然（ダークモードの切替と同じ関係）。
    #
    # cookieは theme.selector（セレクタを画面に出すか）とは切り離して常に見る。
    # 選ぶ入口はセレクタだけでなく wikitheme プラグインもあり、設定で入口を
    # 隠しただけで既に選んであるものが効かなくなるのは筋が通らないため。
    themefile = (cookie_theme(wiki_dir, farm)
                 or getattr(context, "theme_override", None)
                 or theme_conf.get("name", DEFAULT_THEMEFILE))
    # 編集の入口は editable（呼び出し元がページの編集の権限から決める）だけで出し分ける。
    # 入口を一律に伏せる設定（theme.show_edit・theme.edit_hotkey）は、Wiki設計者の
    # 「show_edit, theme.edit_hotkey は廃止、入口も権限で出し分けて」（2026-09-29）で廃止した
    base_url = farm_base_url(config, farm, explicit_farm)

    # メニュー枠ごとに (HTML, 開閉モード) を組み立てる。番号は
    # menu_slot_numbers が theme_conf から見つけたものすべて（1・2は常に含む）
    menu_slots = {}
    for n in menu_slot_numbers(theme_conf):
        menu_name = theme_conf.get(f"menu{n}_page", DEFAULT_MENU_PAGES.get(n, ""))
        html = render_menu(engine, wiki_dir, base_url, menu_name, context) if menu_name else ""
        menu_slots[n] = (html, resolve_menu_mode(pagepath, theme_conf.get(f"menu{n}_mode")))

    # テーマのセレクタは menu1 の中身の先頭へ差し込む（theme.selector が真の
    # ときだけ）。**テーマ側のテンプレートを1つも直さずに、menu1を出す
    # どのテーマでも使えるようにするため**（Wiki設計者の指示、2026-09-04。
    # menu1のページ（mainmenu）へ書く手も試されたが、ページが無いWikiでは
    # 出せない・記法の制約を受ける、という理由でこちらになった）。
    # menu1のページが無く中身が空でも、セレクタだけは出す。
    if show_selector(config):
        html, mode = menu_slots.get(1, ("", "auto"))
        menu_slots[1] = (theme_selector_html(base_url, wiki_dir, pagepath, themefile) + html,
                         mode)

    # 本文・各メニュー枠はすべて同じ context でレンダリングしているため、ここまでで
    # このページ（サイドバー含む）が使ったプラグインが context.used_plugins に揃っている。
    # CSSを持つものだけ、テーマ自身のCSSより先に読み込む（衝突時にテーマを優先するため）。
    plugin_dir = farm_plugin_dir(wiki_dir)
    plugin_styles = (
        plugin_style_urls(base_url, plugin_dir, context.used_plugins) if context is not None else []
    )
    plugin_scripts = (
        plugin_script_urls(base_url, plugin_dir, context.used_plugins) if context is not None else []
    )

    context = {
        "plugin_styles": plugin_styles,
        "plugin_scripts": plugin_scripts,
        "site_title": theme_conf.get("site_title", "wikiSystem"),
        # フッタのcopyright表示用。現在の年を渡すだけ（固定年の設定は今のところ無い）
        "copyright_year": datetime.date.today().year,
        # 版と改訂（"Ver 0.49 Rev 7.1"）。値は wiki.py が持つ
        "version": version_label(),
        # フッタに出す「誰で入っているか」（"Logged in as 山田太郎"）。
        # 未ログインなら空文字（テーマ側は空なら出さない）
        "login_as": login_label(wiki_dir, farm),
        # このWikiが使っている場所（ページと添付。バックアップは含めない）。
        # フッタ向け（Wiki設計者の指示、2026-08-31）。**渡すだけでは何も数えない**ので、
        # 使わないテーマに費用はかからない（wikilib.diskusage 参照）
        "disk_usage": DiskUsage(wiki_dir),
        "page_title": title,
        "farm": farm,
        "page": pagepath,
        "topic_path": topic_path_links(base_url, pagepath),
        "themefile": themefile,
        "base_url": base_url,
        "theme_url": base_url + "/" + THEME_URLPATH,
        "search_url": base_url + "/" + SEARCH_URLPATH,
        # ナビの「ログイン」リンク。指す先はログインの入口（/.login。ページの権限の
        # 対象ではない）。**いま開いているページを戻り先として付ける**（`login_href`。
        # Wiki設計者の指示、2026-09-21）
        "login_url": login_href(base_url, pagepath),
        # 編集画面は別パスを持たない（'.editwikipage' は旧URLの受け皿だけ）。
        # テーマは
        # "{{ edit_url }}/{{ page }}" の形でそのページ自身の通常URLへ
        # POST（cmd=edit）する（wiki.pyのdispatch参照）。
        "edit_url": base_url,
        # 名前を変える画面（`rename_url`）は 2026-09-29 に外した。名前の変更・移動は
        # ファイル一覧（編集画面から開く）で行う。変更の記録は編集画面の「履歴」タブ
        # だけにしたので、`backup_url` も渡さない
        "editable": editable,
        # ログイン・トップ・編集・新規の4項目。テーマは {{ common_menu }} と置くだけ
        "common_menu": common_menu_html(
            base_url, login_href(base_url, pagepath), base_url, pagepath, editable),
        # そのページを誰かが編集の途中（一時保存を預かっている）かどうか。
        # テーマはタイトルの脇に {{ title_note }} を出し、本文には data-draft が付く
        "editing": False,
        "title_note": Markup(""),
        "content": Markup(rewrite_content_links(
            content, base_url, attach_subpath, wiki_dir) + marker_asset_tags(base_url)),
        "toc": toc,
        # 検索結果から来た場合、URLの ?q= をヘッダの検索窓にも残しておく
        "query": request.query.getunicode("q", ""),
        "mode": "and",
        "target": "all",
        "path_filter": "",
    }
    for n, (html, mode) in menu_slots.items():
        context[f"menu{n}"] = Markup(html)
        context[f"menu{n}_mode"] = mode
    context.update(extra)

    env = get_jinja_env(theme_search_dirs(wiki_dir, themefile))
    try:
        html = env.get_template(template or themefile + ".html").render(**context)
    except (TemplateError, RecursionError):
        default_themefile = theme_conf.get("name", DEFAULT_THEMEFILE)
        if template is None and themefile != default_themefile:
            # ページ単位のtheme_overrideが原因で描画できなかった可能性がある
            # （例: 他のテーマへ{% extends %}する断片テンプレート（search.html
            # 等）をtheme_overrideに指定され、自分自身への継承で無限再帰＝
            # RecursionErrorになる、といった事故）。テンプレート自体が
            # 見つからない場合を含め、Jinja2の例外はすべてTemplateError系に
            # まとまっている（TemplateNotFoundもその1つ）。
            #
            # そのWikiの既定テーマ（theme.name）で再試行し、それも失敗すれば
            # 下の最小限のHTMLへ後退する（wikiPluginからの依頼、
            # 2026-09-04。ページ内指定はページ著者が書ける値なので、
            # その失敗でサイト全体を500で止めないようにする。一方
            # templateが明示指定されている画面――検索結果等――は
            # theme_overrideの影響を受けないので、ここでの再試行は行わない）。
            context["themefile"] = default_themefile
            try:
                fallback_env = get_jinja_env(theme_search_dirs(wiki_dir, default_themefile))
                html = fallback_env.get_template(default_themefile + ".html").render(**context)
            except (TemplateError, RecursionError):
                html = html_page(title, content)
        else:
            html = html_page(title, content)
    return HTTPResponse(body=html, status=status, content_type="text/html; charset=utf-8")


def make_plugin_context(config, farm, wiki_dir, page="", explicit_farm=False, partial=False,
                        ext=".md"):
    base_url = farm_base_url(config, farm, explicit_farm)
    return PluginContext(config=config, farm=farm, wiki_dir=wiki_dir,
                         page=page, base_url=base_url, partial=partial, ext=ext,
                         explicit_farm=explicit_farm)


def render_with_theme(wiki_dir, config, farm, pagepath, body, explicit_farm, attach_subpath,
                     ext=".md", source_path=None, editable=True):
    # ページのレンダリング時間（wikiThemesからの要望、フッターに表示する）。
    # 計るのは「本文平文を受け取ってから、render_theme に渡す本文HTMLが
    # できあがるまで」（Markdown/PukiWiki変換＋DB未取り込み分の取り出し）。
    # render_theme自身（menu1/menu2のレンダリング・テンプレートの組み立て）は
    # ここでは計らない——render_theme は検索結果・バックアップ管理・
    # リネーム画面など多くの画面で使い回す汎用関数で、「ページのレンダリング
    # 時間」という言葉の指す範囲（本文の変換）とは別物のため。
    render_start = time.perf_counter()
    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm, ext=ext)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    # DBに取り出し済みの情報（タイトル・目次・リンク）が無ければ、ここで補う。
    # 作り直したDBには本文しか入っていない（全文のパースが重いので省いている）ため、
    # 開かれたページから順に埋めていく。1ページあたり数ミリ秒
    from wikilib.links import ensure_page_info
    ensure_page_info(wiki_dir, attach_subpath, engine, body, ext, config)
    md_conf = config.get("markdown") or {}
    content, extracted_title, toc = render_source(
        engine, body, ext, md_conf.get("first_h1_as_title", True), context,
        toc_depth=md_conf.get("toc_depth", 3),
    )
    # プラグインが「このページは出さない」と決めていたら、本文を差し替える
    # （PluginContext.block_view。閲覧期間の設定など、認証とは別の理由で
    #  表示を止めたいプラグインのための窓口。Wiki設計者の指示、2026-09-05）。
    #
    # **本文の代わりに出すだけで、読めなくするものではない。** 編集画面・
    # 見出し単位の取り出し・バックアップ・検索の抜粋からは今までどおり読める
    # （block_view のdocstring参照）。
    #
    # **編集リンクは消さない。** 閲覧できないことと編集できないことは別物で、
    # 閲覧を止めるプラグインが編集まで止めてよい理由が無い（Wiki設計者の指示、
    # 2026-09-05。編集そのものを止めたいなら、閲覧停止の上位の指定として
    # 別に用意する話になる）。はじめは editable=False にしていたが、
    # そうすると**編集ボタンとAlt+Eだけが消え、cmd=edit のPOSTは通る**という
    # 中途半端な状態になり、期間を書き間違えたページを画面から直せなくなる。
    # 出し分けはこれまでどおり editable（編集の権限）とテーマの実装だけで決まる。
    block = getattr(context, "view_block", None)
    if block:
        content = block["message"]
        toc = ()
        # 見出しは本文から取ったものなので使わない（出さないと決めたページの
        # 中身が、題名として出てしまう）。URLに出ているページ名で代える
        extracted_title = None

    # 誰かが編集の途中なら、タイトルの脇にそう出す。
    # 気づかずに直しにかかると、あとで一時保存のほうに上書きされてしまうため。
    editing = has_draft(wiki_dir, attach_subpath)
    note = Markup('<span class="page-editing" title="一時保存があります">（編集中）</span>') \
        if editing else Markup("")
    render_ms = round((time.perf_counter() - render_start) * 1000, 1)

    extra = {"editing": editing, "title_note": note, "render_ms": render_ms}
    # 平文ファイル（DBではなく実ファイル）の最終更新日時（wikiThemesからの
    # 要望）。DBは「公開された内容」の最後の取り込み時点のスナップショットで、
    # 直接編集された分は取り込む（updatepage）まで反映されない
    # （詳しくは Tech/PageDataBase の「DBが公開済み、平文は作業中」）。
    # source_mtime はそのズレに気づく手がかりとして、DB側の日時
    # ではなく実ファイルの mtime をそのまま見せる。
    if source_path is not None:
        try:
            mtime = os.path.getmtime(source_path)
        except OSError:
            mtime = None
        if mtime is not None:
            extra["source_mtime"] = datetime.datetime.fromtimestamp(mtime).strftime(
                "%Y-%m-%d %H:%M")

    # editable は呼び出し元（views.render_page）が編集の権限から決める
    # （Wiki設計者の指示、2026-09-17）。テーマは「編集・履歴・リネーム」も
    # セクション編集の目印（data-editable）もホットキーの目印も、これ1つで
    # 出し分けている。
    return render_theme(engine, wiki_dir, config, farm, pagepath,
                       page_title_of(extracted_title, pagepath, farm), content, toc,
                       explicit_farm=explicit_farm, attach_subpath=attach_subpath, context=context,
                       status=block["status"] if block else 200, editable=editable,
                       **extra)


def serve_theme_asset(wiki_dir, config, filename):
    """テーマのCSS/JS等を配信する。個別Wiki固有のtheme/を優先し、無ければ全Wiki共通のtheme/から返す。
    theme.name がフォルダ形式のテーマなら、そのフォルダの中も同じ優先順位で探す
    （render_theme のテンプレート探索と同じ theme_search_dirs を使う）。"""
    theme_conf = config.get("theme") or {}
    themefile = theme_conf.get("name", DEFAULT_THEMEFILE)
    for d in theme_search_dirs(wiki_dir, themefile):
        target = safe_join(d, filename)
        if target is not None and os.path.isfile(target):
            return static_file(filename, root=d)
    return plain("no page", status=404)
