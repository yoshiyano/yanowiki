#!/usr/bin/env python3
"""wikiSystem の入口。

このファイルは起動とURLの振り分けだけを受け持ち、実際の処理は
`_sys/wikilib/` の各モジュールが持つ（構成は wikilib/__init__.py を参照）。

依存パッケージを import する前に _venv での再実行を済ませる必要があるため、
起動時の下ごしらえだけはこのファイルの先頭に置いてある。
"""
# ---- 版と改訂 ---------------------------------------------------------------
VERSION = "1.1"
VERSION_DATE = "2026-09-30"
REVISION = "7"

import argparse
import atexit
import datetime
import os
import signal
import socket
import socketserver
import subprocess
import sys
import time
import wsgiref.simple_server

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYS_DIR = os.path.join(BASE_DIR, "_sys")
sys.path.insert(0, SYS_DIR)

# ---- 版と改訂の決まり -------------------------------------------------------
# 画面のフッタに "Ver.0.9 Rev.17" の形で出る。
#
#   VERSION       版。main で公開するときに上げる
#   VERSION_DATE  その版に番号を付けた日。改訂の数えはじめの日
#   REVISION      VERSION_DATE の00:00:00から、いまのHEADまでの総コミット数
#
# 以前は「経過日数.その日のコミット回数」の2部構成だったが、単一の数値に
# 変えた（2026-08-27）。**コミットするたびに1増やす**もので、
# `_sys/_tools/get_revision.py --next` が次に入れるべき値を出す。
#
# VERSION_DATE は、いまの版を出した日。版を上げるたびに更新する
# （0.9 として GitHub の main へ初めて公開したのが 2026-08-27、
#  1.0 が 2026-09-05）。


def version_label():
    """フッタなどに出す表示。"""
    return f"Ver.{VERSION} Rev.{REVISION}"


def _reexec_with_venv_if_needed(allow_exec=True):
    """BASE_DIR基準の_venvが存在すれば、無条件にそちらのpythonで自分自身を再実行する。
    shebangを絶対パスで固定すると配置場所が変わるPCで壊れるため、実行時に自分の場所を
    基準として_venvを探すことでポータビリティを保つ。
    （システムPythonに依存パッケージの一部だけが入っていて import は通るが別パッケージが
    欠けている、という中途半端な状態を避けるため、import成否ではなく_venvの有無で判定する）

    allow_exec=False のときは再実行しない。gunicorn や mod_wsgi から
    このファイルを import して使う場合、勝手に自分を置き換えるとサーバごと壊れるため
    （その場合は、サーバを起動する側が正しいPythonを使う）。"""
    venv_python = os.path.join(
        BASE_DIR, "_venv",
        "Scripts" if os.name == "nt" else "bin",
        "python.exe" if os.name == "nt" else "python",
    )
    if (allow_exec and os.path.isfile(venv_python)
            and os.path.abspath(sys.executable) != os.path.abspath(venv_python)):
        os.execv(venv_python, [venv_python] + sys.argv)
        return

    try:
        import yaml  # noqa: F401
        import markdown_it  # noqa: F401
        import mdit_py_plugins  # noqa: F401
    except ImportError as e:
        sys.exit(
            f"依存パッケージが見つかりません（{e}）。"
            "`UV_PROJECT_ENVIRONMENT=_venv uv sync` を実行してインストールしてください。"
        )


_reexec_with_venv_if_needed(allow_exec=__name__ == "__main__")

import bottle
from bottle import Bottle, HTTPResponse, request

from wikilib.paths import (
    ACCOUNTS_URLPATH, ADMIN_URLPATH, APPROVALS_URLPATH, ATTACH_URLPATH,
    LOGIN_URLPATH,
    CONFIGWIKI_URLPATH, HISTORY_URLPATH, CONFLICT_URLPATH, DELWIKI_URLPATH,
    EDITOR_URLPATH, EDIT_URLPATH, FARM_PREFIX, FILES_URLPATH, GROUPS_URLPATH,
    MARKERS_PANEL_URLPATH,
    MARKERS_URLPATH, PAGETREE_URLPATH, PASSWD_URLPATH, PWHASH_URLPATH,
    PID_DIR, NEWWIKI_URLPATH, PRIVILEGES_URLPATH, RESTART_URLPATH,
    GARBAGECOLLECT_URLPATH, UPDATEPAGEAUTH_URLPATH,
    SYSTEM_PREFIX,
    TREEVIEW_URLPATH, PLUGIN_URLPATH, SEARCH_URLPATH, SECTION_URLPATH,
    THEMESELECT_URLPATH, THEME_URLPATH, VENDOR_URLPATH,
    farm_wiki_dir, is_valid_pagepath, resolve_page_ref,
)
from wikilib.attach import serve_attach
from wikilib.backupui import render_history, serve_history_asset
from wikilib.vendor import serve_vendor_asset
from wikilib.editor import (
    render_diff, render_edit, render_preview, serve_editor_asset, serve_section,
)
from wikilib.markers import (
    render_markers_panel, serve_markers_asset, serve_markers_panel_asset,
)
from wikilib.dbbackup import sweep_leftovers
from wikilib.pagesync import farm_of_cwd, format_result, start_watcher, sync_all, wiki_names
from wikilib.pagetree import serve_page_tree
from wikilib.plugins import render_plugin_action, serve_plugin_asset
from wikilib.allwiki import render_allwiki, serve_allwiki_asset
from wikilib.delwiki import render_delwiki, serve_delwiki_asset
from wikilib.newwiki import render_newwiki, serve_newwiki_asset
from wikilib.conflict import render_conflict, serve_conflict_asset
from wikilib.treeview import serve_treeview_asset
from wikilib.restart import mark_standalone, serve_restart
from wikilib.search import render_search, serve_search_asset
from wikilib.themes import serve_theme_asset, serve_theme_select
from wikilib.views import render_no_farm, render_no_page, render_page
from wikilib.web import html_page
from wikilib.wikiconfig import (
    allwiki_command, ensure_root_config_files, farm_base_url,
    load_config, load_default_farm, load_wiki_config, set_force_debug,
    set_version_label, split_farm_and_page, strip_url_prefix, url_prefix,
)

# テーマが {{ version }} で使えるように配っておく。ここで渡すのは、
# 版と改訂の値をこのファイル1か所だけで持つため（wikilib 側は受け取るだけ）。
# gunicorn や mod_wsgi から読み込まれた場合もこの行を通る
set_version_label(version_label())

# 受け取るPOSTの大きさの上限。bottle の既定は100KBで、これを超えると本文を
# 読む前に 413 で撥ねられる。
#
# **フォームの送信は「1バイト＝最大3バイト」に膨らむ。** 日本語は UTF-8 で
# 1文字3バイト、それが %E3%81%82 のように1バイトあたり3文字へ置き換わるため、
# 4万バイトほどのページでも12万バイトを超えて既定の上限に届いてしまう
# （PukiWiki の記法解説のような長いページがこれにあたる）。
#
# ここを上げるとページの本文だけでなく添付もメモリに載る量が増えるので、
# 添付1件の上限（20MB）より小さく取ってある。8MB あれば、すべて日本語の
# ページでも90万バイトほどまで保存できる。
bottle.BaseRequest.MEMFILE_MAX = 8 * 1024 * 1024

app = Bottle()


@app.error(413)
def too_large(error):
    """上限を超えたときの案内。

    bottle の既定の画面は「Request entity too large」とだけ出る。保存を押した
    直後にこれが出ると、何が起きたのか分からないまま編集画面から放り出される。
    **まず戻れば書いたものはそこにある**ことと、次に何をすればよいかを伝える。"""
    return html_page("大きすぎます", (
        "<h1>大きすぎて受け取れませんでした</h1>"
        "<p>送られた内容が上限（{limit}MB）を超えています。</p>"
        "<p>ブラウザの<strong>「戻る」で編集画面に戻ってください</strong>。"
        "そのうえで、ページを分けるか、大きな部分を添付ファイルにしてください。</p>"
    ).format(limit=bottle.BaseRequest.MEMFILE_MAX // (1024 * 1024)))


@app.route("/", method=["GET", "POST"])
@app.route("/<urlpath:path>", method=["GET", "POST"])
def dispatch(urlpath=""):
    config = load_config()
    urlpath = strip_url_prefix(urlpath, url_prefix(config))
    farm, pagepath, explicit_farm = split_farm_and_page(urlpath, config)
    # 末尾スラッシュ（Tech/）は正規のページURL（Tech）ではないので、
    # render_page 側で303に倒す。トップページ（pagepath==""）は対象外
    # （そちらは末尾スラッシュ付きが正規形）。
    had_trailing_slash = pagepath not in ("", "/") and pagepath.endswith("/")
    pagepath = pagepath.strip("/")
    wiki_dir = farm_wiki_dir(farm)
    if wiki_dir is None:
        # Wiki自体が無いとテーマも設定も辿れないため、テーマに依存しない専用の画面を返す
        return render_no_farm(farm)
    # どのWikiかが決まったので、ここから先はそのWikiの設定（既定値＋個別）で動かす。
    # 個別Wiki側にconfig/default.yaml等が無くても、load_wiki_config()が
    # 既定値（config/*.example.yaml）へ自然に落ちるので、ここで作っておく
    # 必要はない（旧ensure_farm_config_files。理由はwikiconfig.load_config
    # のdocstring参照）
    config = load_wiki_config(wiki_dir)

    if pagepath == THEME_URLPATH or pagepath.startswith(THEME_URLPATH + "/"):
        return serve_theme_asset(wiki_dir, config, pagepath[len(THEME_URLPATH):].strip("/"))
    if pagepath == THEMESELECT_URLPATH:
        # 画面のテーマセレクタからの送信。選んだテーマをcookieへ覚えて元のページへ戻す
        return serve_theme_select(wiki_dir, config, farm, explicit_farm)
    if pagepath == VENDOR_URLPATH or pagepath.startswith(VENDOR_URLPATH + "/"):
        # 第三者ライブラリの資材（例: /.vendor/diffmerge/diffmerge.umd.js）
        return serve_vendor_asset(pagepath[len(VENDOR_URLPATH):].strip("/"))
    if pagepath == ATTACH_URLPATH or pagepath.startswith(ATTACH_URLPATH + "/"):
        return serve_attach(wiki_dir, config, farm,
                            pagepath[len(ATTACH_URLPATH):].strip("/"), explicit_farm)
    if pagepath.startswith(SEARCH_URLPATH + "."):
        # 検索結果が自前で持つCSS/JS（/.search.css, /.search.js）
        return serve_search_asset(pagepath[len(SEARCH_URLPATH) + 1:])
    if pagepath == SEARCH_URLPATH:
        return render_search(wiki_dir, config, farm, explicit_farm)
    if pagepath == EDIT_URLPATH or pagepath.startswith(EDIT_URLPATH + "/"):
        # 旧URL。このパス自体が「ここが編集の入口だ」と閲覧者に
        # 教えてしまうため、いまの入口ではない。メソッドを問わず、ここへ
        # 来たら常にそのページの通常URL（この名前を含まない）へ303で
        # 送り返すだけにする（GETはブラウザがそのままGETで再送する。
        # POSTでもボディは見ずに送り返すだけでよい——編集そのものは
        # 下の render_page 直前にある cmd=edit の分岐が担う）。
        target_pagepath = pagepath[len(EDIT_URLPATH):].strip("/")
        return HTTPResponse(status=303, headers={
            "Location": farm_base_url(config, farm, explicit_farm) + "/" + target_pagepath,
        })
    if pagepath == SECTION_URLPATH or pagepath.startswith(SECTION_URLPATH + "/"):
        # GETで生テキストを取り出し、POSTでその節を保存する（editor.save_section）
        return serve_section(wiki_dir, config, farm,
                             pagepath[len(SECTION_URLPATH):].strip("/"), explicit_farm)
    if pagepath == FILES_URLPATH or pagepath.startswith(FILES_URLPATH + "/"):
        # ファイル一覧（webFileDir を組み込んだ画面。変更はできず、ページを開くまで）。
        # 見えるページは閲覧の権限で絞る（wikilib.filesui）
        from wikilib.filesui import serve_files
        return serve_files(wiki_dir, farm,
                           farm_base_url(config, farm, explicit_farm) + "/" + FILES_URLPATH)
    if pagepath == PAGETREE_URLPATH:
        # ページ選択ダイアログが読むページ一覧（ツリー）
        return serve_page_tree(wiki_dir)
    if pagepath == PLUGIN_URLPATH or pagepath.startswith(PLUGIN_URLPATH + "/"):
        name = pagepath[len(PLUGIN_URLPATH):].strip("/")
        for ext in (".css", ".js"):
            if name.endswith(ext):
                # プラグインが自前で持つ資材（/.plugin/note.css など）
                return serve_plugin_asset(wiki_dir, name[: -len(ext)], ext)
        return render_plugin_action(wiki_dir, config, farm, explicit_farm, name)
    if pagepath.startswith(HISTORY_URLPATH + "."):
        # 編集画面の「履歴」タブが自前で持つCSS/JS。履歴そのものは ?cmd=history（下）
        return serve_history_asset(pagepath[len(HISTORY_URLPATH) + 1:])
    # 新しいWikiを作る（/.newwiki）。CSSは /.delwiki.css と同じくその場で返す
    if pagepath.startswith(NEWWIKI_URLPATH + "."):
        return serve_newwiki_asset(pagepath[len(NEWWIKI_URLPATH) + 1:])
    if pagepath == NEWWIKI_URLPATH:
        return render_newwiki(wiki_dir, config, farm, explicit_farm)
    # 既にあるWikiを消す（/.delwiki）。権限（既定Wikiの管理者と助手）は
    # render_delwiki の中で見る。CSSはその場で返す——見た目の決まりだけで、
    # どんなWikiがあるかは何も載っていない（/.allwiki.css と同じ扱い）
    if pagepath.startswith(DELWIKI_URLPATH + "."):
        return serve_delwiki_asset(pagepath[len(DELWIKI_URLPATH) + 1:])
    if pagepath == DELWIKI_URLPATH:
        return render_delwiki(wiki_dir, config, farm, explicit_farm)
    # アカウント（ログイン・一覧と編集・ハッシュ値づくり）。資材は3画面で共有する
    if pagepath.startswith(ACCOUNTS_URLPATH + "."):
        from wikilib.accounts import serve_accounts_asset
        return serve_accounts_asset(pagepath[len(ACCOUNTS_URLPATH) + 1:])
    # 一覧（/.admin/accounts）の更新・削除を1件ずつ受けるJSON API
    # （/.admin/accounts/api。Wiki設計者の指示、2026-09-12）
    if pagepath == ACCOUNTS_URLPATH + "/api":
        from wikilib.accounts import render_accounts_api
        return render_accounts_api(wiki_dir, config, farm, explicit_farm)
    # ログインの入口（/.login）。中身は #login() と同じフォームで、ページの権限の対象では
    # ない（Wiki設計者の指示、2026-09-21。2026-09-11にいちど「持たない」とした画面を戻した）。
    # ログイン・ログアウト・アカウント作成の受け口は #login プラグインの _action
    # （/.plugin/login。上のPLUGIN_URLPATHの分岐が受け持つ）
    if pagepath == LOGIN_URLPATH:
        from wikilib.views import render_login
        return render_login(wiki_dir, config, farm, explicit_farm)
    if pagepath == ACCOUNTS_URLPATH:
        from wikilib.accounts import render_accounts
        return render_accounts(wiki_dir, config, farm, explicit_farm)
    if pagepath == PASSWD_URLPATH:
        from wikilib.accounts import render_passwd
        return render_passwd(wiki_dir, config, farm, explicit_farm)
    if pagepath == PWHASH_URLPATH:
        from wikilib.accounts import render_pwhash
        return render_pwhash(wiki_dir, config, farm, explicit_farm)
    # Wikiの設定を書き換える画面（管理者と助手）。資材は /.admin/configwiki.css・.js
    # **/.admin配下だが、ADMIN_URLPATHの分岐より先に見る**——そちらが
    # startswith(ADMIN_URLPATH + "/") で先に奪ってしまうため（Wiki設計者の指示、
    # 2026-09-12。/.accounts・/.configwiki を /.admin 配下へ移した一環）。
    if pagepath.startswith(CONFIGWIKI_URLPATH + "."):
        from wikilib.configui import serve_configui_asset
        return serve_configui_asset(pagepath[len(CONFIGWIKI_URLPATH) + 1:])
    if pagepath == CONFIGWIKI_URLPATH + "/api":
        # 直した項目1つを受け取る窓口（画面に保存ボタンは無い）
        from wikilib.configui import render_configwiki_api
        return render_configwiki_api(wiki_dir, config, farm, explicit_farm)
    if pagepath == CONFIGWIKI_URLPATH:
        from wikilib.configui import render_configwiki
        return render_configwiki(wiki_dir, config, farm, explicit_farm)
    # 承認待ちのアカウントを承認する画面（管理者と助手）。**/.admin配下だが、
    # ADMIN_URLPATHの分岐より先に見る**（上の /.admin/configwiki と同じ理由）
    if pagepath == APPROVALS_URLPATH:
        from wikilib.approvalsui import render_approvals
        return render_approvals(wiki_dir, config, farm, explicit_farm)
    # ページごとのアクセス制限を編集する画面（管理者と助手）。資材は
    # /.admin/privileges.css /.js。**ここも ADMIN_URLPATH の分岐より先に見る**
    # （上の /.admin/configwiki と同じ理由。Wiki設計者の指示、2026-09-13）
    if pagepath.startswith(PRIVILEGES_URLPATH + "."):
        from wikilib.privilegesui import serve_privileges_asset
        return serve_privileges_asset(pagepath[len(PRIVILEGES_URLPATH) + 1:])
    if pagepath == PRIVILEGES_URLPATH + "/api":
        from wikilib.privilegesui import render_privileges_api
        return render_privileges_api(wiki_dir, config, farm, explicit_farm)
    if pagepath == PRIVILEGES_URLPATH:
        from wikilib.privilegesui import render_privileges
        return render_privileges(wiki_dir, config, farm, explicit_farm)
    # ユーザーが自分で作れる汎用グループの管理画面（/.groups）。
    # ログインしていれば誰でも開ける（Wiki設計者の指示、2026-09-12）
    if pagepath.startswith(GROUPS_URLPATH + "."):
        from wikilib.groupsui import serve_groups_asset
        return serve_groups_asset(pagepath[len(GROUPS_URLPATH) + 1:])
    if pagepath == GROUPS_URLPATH + "/api":
        from wikilib.groupsui import render_groups_api
        return render_groups_api(wiki_dir, config, farm, explicit_farm)
    if pagepath == GROUPS_URLPATH:
        from wikilib.groupsui import render_groups
        return render_groups(wiki_dir, config, farm, explicit_farm)
    # 管理の道具の窓口（/.admin）。**これから作る管理の道具はここへつなぐ**
    # （Wiki設計者の指示、2026-09-08）。助手グループの出し入れ（旧 /.admin/staff）は
    # /.groups?group=staff に一本化した（Wiki設計者の指示、2026-09-12）
    if pagepath == ADMIN_URLPATH or pagepath.startswith(ADMIN_URLPATH + "/"):
        from wikilib.adminui import serve_admin
        return serve_admin(wiki_dir, config, farm, explicit_farm,
                           pagepath[len(ADMIN_URLPATH):])
    # 全Wikiの一覧。URL名は server.yaml の farm.allwiki で決まる（空なら出さない）。
    # 権限（既定Wikiの管理者と助手）は render_allwiki の中で見る。CSSはその場で
    # 返す——見た目の決まりだけで、どんなWikiがあるかは何も載っていないため
    allwiki = allwiki_command(config)
    if allwiki:
        if pagepath == SYSTEM_PREFIX + allwiki + ".css":
            return serve_allwiki_asset("css")
        if pagepath == SYSTEM_PREFIX + allwiki:
            return render_allwiki(wiki_dir, config, farm, explicit_farm)
    if pagepath.startswith(TREEVIEW_URLPATH + "."):
        # ページ一覧のTreeView。ページ選択・名前を変える・履歴の3画面で使い回す
        return serve_treeview_asset(pagepath[len(TREEVIEW_URLPATH) + 1:])
    if pagepath.startswith(CONFLICT_URLPATH + "."):
        # 競合を統合する画面が自前で持つCSS/JS（/.conflict.css, /.conflict.js）
        return serve_conflict_asset(pagepath[len(CONFLICT_URLPATH) + 1:])
    if pagepath == CONFLICT_URLPATH or pagepath.startswith(CONFLICT_URLPATH + "/"):
        # 編集の競合を3文書マージで統合する画面。編集画面が保存時に競合を
        # 見つけると、ここへ303で送り込む（editor.render_edit）
        return render_conflict(wiki_dir, config, farm,
                               pagepath[len(CONFLICT_URLPATH):].strip("/"), explicit_farm)
    if pagepath == GARBAGECOLLECT_URLPATH:
        # 削除したページの添付を trashbox へ集める。管理者と助手（関門は中で見る）
        from wikilib.garbagecollect import serve_garbage_collect
        return serve_garbage_collect(wiki_dir, config, farm, explicit_farm)
    if pagepath == UPDATEPAGEAUTH_URLPATH:
        # 機能していないページの権限の記録を消す。誰でも（回数の制限は中で見る）
        from wikilib.updatepageauth import serve_update_page_auth
        return serve_update_page_auth(wiki_dir, config, farm, explicit_farm)
    if pagepath == RESTART_URLPATH:
        # 画面（確認してから実行）と ?now=1（その場で実行）の両方を serve_restart が
        # 受け持つ。**関門をあちらに1つ置くため**で、ここで ?now=1 を先に
        # 拾ってしまうと、その道だけ守りを素通りする（Wiki設計者の指示、2026-09-13）
        return serve_restart(wiki_dir, config, farm, explicit_farm)
    if pagepath.startswith(EDITOR_URLPATH + "."):
        # 編集機能が自前で持つCSS/JS。テーマに依存しないための配信URL
        return serve_editor_asset(pagepath[len(EDITOR_URLPATH) + 1:])
    if pagepath.startswith(MARKERS_PANEL_URLPATH + "."):
        # マーカーシステムの操作用ウィンドウが自前で持つCSS/JS
        return serve_markers_panel_asset(pagepath[len(MARKERS_PANEL_URLPATH) + 1:])
    if pagepath == MARKERS_PANEL_URLPATH:
        # マーカーシステムの操作用ウィンドウ本体（window.openで開く）。
        # 特定のWiki・farmに紐づかないので wiki_dir は渡さない
        return render_markers_panel()
    if pagepath.startswith(MARKERS_URLPATH + "."):
        # マーカーシステム本体のCSS/JS。全ページに自動で差し込む（themes.render_theme）
        return serve_markers_asset(pagepath[len(MARKERS_URLPATH) + 1:])

    if not is_valid_pagepath(pagepath):
        # "=" や "." で始まるページ名は使えない。ページとして存在しないので同じ案内を出す
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)
    # 編集画面はページ自身の通常URLに重ねる（'.edit' という別パスを持たない）。
    # そのページを閲覧しているだけの人からは、URLだけを見ても編集の入口が
    # あることが分からないようにするため。POSTでcmdが付いていることが唯一の
    # 目印で、GETでは常にただの閲覧画面が返る。
    #
    # **プレビューと差分もここへ寄せてある**（Wiki設計者の指示、2026-09-17。
    # 以前は `/.preview/<ページパス>`・`/.diff/<ページパス>` という別のURLだった）。
    # この2つは**本文をそのまま本体に載せて送る**ので、フォームとしては読めない。
    # そこで `cmd` はクエリで受ける（`?cmd=preview`）。編集画面からの操作
    # （edit/save/draft/attach）はこれまでどおりフォームの `cmd` で来る。
    if request.method == "POST":
        cmd = request.query.get("cmd") or request.forms.get("cmd")
        if cmd == "preview":
            return render_preview(wiki_dir, config, farm, explicit_farm, pagepath)
        if cmd == "diff":
            return render_diff(wiki_dir, config, farm, explicit_farm, pagepath)
        if cmd == "history":
            # 編集画面の「履歴」タブ（以前の /.backup。wikilib.backupui の冒頭）
            return render_history(wiki_dir, config, farm, explicit_farm, pagepath)
        if cmd is not None:
            return render_edit(wiki_dir, config, farm, pagepath, explicit_farm)
    return render_page(wiki_dir, config, farm, pagepath, explicit_farm,
                       had_trailing_slash=had_trailing_slash)


def _pid_file(port):
    return os.path.join(PID_DIR, f"{port}.pid")


def _port_available(host, port):
    """host:portが（今すぐ）bindできるかどうか。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
    except OSError:
        return False
    finally:
        s.close()
    return True


def _pid_alive(pid):
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                 capture_output=True, text=True, timeout=3)
            return str(pid) in out.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 存在はするが別ユーザーの所有等。生きてはいる
    except OSError:
        return False
    return True


def _process_cmdline(pid):
    """指定PIDの起動コマンドラインを可能な範囲で取得する。取得できなければNone。
    「本当に自分自身(wiki.py)の前回起動か」を確かめるためだけに使う。"""
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"],
                capture_output=True, text=True, timeout=3,
            )
            return out.stdout
        except Exception:
            return None
    proc_cmdline = f"/proc/{pid}/cmdline"
    if os.path.isfile(proc_cmdline):
        try:
            with open(proc_cmdline, "rb") as f:
                return f.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            pass
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=3)
        return out.stdout
    except Exception:
        return None


def _terminate_pid(pid, force=False):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid)] + (["/F"] if force else []),
                       capture_output=True, timeout=5)
        return
    try:
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
    except OSError:
        pass


def stop_previous_instance(host, port):
    """同じポートで前回起動した自分自身(wiki.py)がまだ動いていれば停止する。

    PIDファイルに記録があっても、そのPIDが今どのプロセスなのかまでは保証できない
    （プロセス終了後にPIDが別プロセスへ再利用される可能性があるため）。そのため、
    起動コマンドラインに "wiki.py" が含まれるかを確認できた場合に限って停止する。
    確認できない場合は、無関係のプロセスを誤って止めないよう何もしない
    （ポートが本当にふさがっていれば、この後のbottle.run()が従来どおりエラーになる）。"""
    if _port_available(host, port):
        return

    pid_file = _pid_file(port)
    if not os.path.isfile(pid_file):
        return
    try:
        with open(pid_file, encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return

    if pid == os.getpid() or not _pid_alive(pid):
        return

    cmdline = _process_cmdline(pid)
    if cmdline is None or os.path.basename(__file__) not in cmdline:
        return

    print(f"ポート {port} で前回のサービス（PID {pid}）が動作中のため停止します。", file=sys.stderr)
    _terminate_pid(pid)
    for _ in range(50):  # 最大5秒、正常終了(SIGTERM)を待つ
        if _port_available(host, port):
            return
        time.sleep(0.1)

    _terminate_pid(pid, force=True)  # 応答が無ければ強制終了
    for _ in range(20):  # さらに最大2秒待つ
        if _port_available(host, port):
            return
        time.sleep(0.1)


def _write_pid_file(port):
    os.makedirs(PID_DIR, exist_ok=True)
    pid_file = _pid_file(port)
    with open(pid_file, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    def _cleanup():
        try:
            if open(pid_file, encoding="utf-8").read().strip() == str(os.getpid()):
                os.remove(pid_file)
        except OSError:
            pass

    atexit.register(_cleanup)

    # SIGTERM（次回起動時に自分自身を止めてもらう際に使う号令）はatexitを経由しないため、
    # 明示的にsys.exit()へつなぎ直して後始末（PIDファイル削除）を確実にする。
    # SIGTERMを扱えない環境（一部のWindows環境等）では諦める。次回起動時の生死確認・
    # コマンドライン照合が働くので、ファイルが残っても誤動作はしない。
    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    except (ValueError, OSError, AttributeError):
        pass


def run_version(argv):
    """`./wiki.py version` … いまの版と改訂、次のコミットで入れるべき改訂を出す。

    改訂は "VERSION_DATE の00:00:00から、いまのHEADまでの総コミット数"。
    次のコミットが何回目になるかは「いまの総コミット数 + 1」になる。"""
    parser = argparse.ArgumentParser(
        prog="wiki.py version", description="版と改訂を表示する")
    parser.add_argument("--next", action="store_true",
                        help="次のコミットで入れるべき改訂だけを出す")
    args = parser.parse_args(argv)

    origin = datetime.date.fromisoformat(VERSION_DATE)
    try:
        out = subprocess.run(
            ["git", "log", "--since", origin.isoformat() + " 00:00:00", "--oneline"],
            capture_output=True, text=True, timeout=10, cwd=BASE_DIR)
        count = len([ln for ln in out.stdout.splitlines() if ln.strip()])
    except Exception:
        count = None

    if count is None:
        if args.next:
            print("（gitの記録を読めないため、コミット回数を数えられません）",
                  file=sys.stderr)
            return 1
        print(version_label())
        print("  次の改訂: ??? （gitの記録を読めません）")
        return 0

    nxt = count + 1
    if args.next:
        print(nxt)
        return 0
    print(version_label())
    print(f"  数えはじめ: {VERSION_DATE} 00:00:00")
    print(f"  総コミット数: {count}")
    print(f"  次のコミットで入れる改訂: {nxt}")
    return 0


def run_updatepage(argv):
    """`./wiki.py updatepage [ページ名] [--force]` … 平文の直接編集をDBに取り込む。

    見るのは**1つのWikiだけ**で、どのWikiかは次の順で決まる。

        =Wiki名 / =Wiki名/ページ名   そのWiki
        wikidata/<Wiki名>/ の中で実行  そのWiki（いま手を入れているもの）
        それ以外の場所で実行           既定のWiki

    ページ名を省けばそのWikiの全ページが対象になり、消えたページの後始末も行う。
    `--force` は食い違いを見ずに、対象のページをすべて読み直して入れ直す。

    クロコ（Claude）やWiki設計者がファイルを直に書き換えたあと、これを動かすと
    システム側の記録（バックアップ・リンク・目次・更新履歴）が揃う。

    `X.拡張子` と同じ場所を指すフォルダ `X/` が両方あって読めないページが
    見つかった場合は、そのページ一覧を表示したうえで終了コード2を返す
    （0は正常終了、1はWiki自体が見つからない場合）。"""
    parser = argparse.ArgumentParser(
        prog="wiki.py updatepage",
        description="平文ファイルの直接編集を取り込み、システム側の記録を揃える")
    parser.add_argument("page", nargs="?", default="",
                        help="取り込むページ（省略するとそのWikiの全ページ）。"
                             "Wikiは =Wiki名 または =Wiki名/ページ名 の形で指定する")
    parser.add_argument("--force", action="store_true",
                        help="DBとの一致・不一致に関わらず、ファイルを読み直して入れ直す")
    args = parser.parse_args(argv)

    target = (args.page or "").strip("/")
    if target.startswith(FARM_PREFIX):
        farm, _, target = target[len(FARM_PREFIX):].partition("/")
    else:
        # 引数でWikiを指定していなければ、いまいる場所のWikiを対象にする
        farm = farm_of_cwd() or load_default_farm(load_config())
    wiki_dir = farm_wiki_dir(farm)
    if wiki_dir is None:
        print(f"Wiki「{farm}」がありません。", file=sys.stderr)
        return 1

    subpath = None
    if target:
        ref = resolve_page_ref(wiki_dir, target)
        if ref is None:
            print(f"ページ「{target}」を指定できません。", file=sys.stderr)
            return 1
        subpath = ref.subpath

    results = sync_all(farm=farm, subpath=subpath, force=args.force)
    if not results:
        print("Wikiが見つかりませんでした。", file=sys.stderr)
        return 1
    for name, r in results.items():
        if r.get("first"):
            # 取ってきた直後の1回目は**全ページが「追加」**になる。1行ずつ
            # 並べると何百行にもなって、下の要約が埋もれてしまう
            continue
        for kind, sub in r["pages"]:
            label = {"updated": "更新", "added": "追加", "removed": "削除"}[kind]
            print(f"  [{name}] {label}: {sub}")
    print(format_result(results))
    if any(r.get("shadowed") for r in results.values()):
        return 2
    return 0


def run_initusers(argv):
    """`./wiki.py initusers [=Wiki名]` … アカウントの記録を用意する。

    `wikidata/<Wiki名>/config/users.db` を作り、`admin` を1つ入れる。
    **すでにあれば何もしない**（中身は触らない）。

    どのWikiかは updatepage と同じ決めかた（`=Wiki名` / いまいる場所 /
    既定のWiki）。新しく作ったWikiには `/.newwiki` が同じものを用意するので、
    これを使うのは**それより前からあるWiki**向け。

    画面を開いたときには作らない。誰でも開ける画面へのアクセスで、既定の
    パスワードを持つ管理者アカウントが生えてしまうため
    （Wiki設計者の指示、2026-09-05。詳しくは wikilib.userdb の冒頭）。"""
    from wikilib.userdb import create_db

    parser = argparse.ArgumentParser(
        prog="wiki.py initusers",
        description="そのWikiのアカウントの記録（config/users.db）を用意する")
    parser.add_argument("farm", nargs="?", default="",
                        help="対象のWiki（=Wiki名）。省略すると、いまいる場所か既定のWiki")
    parser.add_argument("--password", default="",
                        help="管理者の最初のパスワード（省略すると聞きます）")
    args = parser.parse_args(argv)

    name = (args.farm or "").strip("/")
    if name.startswith(FARM_PREFIX):
        name = name[len(FARM_PREFIX):]
    if not name:
        name = farm_of_cwd() or load_default_farm(load_config())
    wiki_dir = farm_wiki_dir(name)
    if wiki_dir is None:
        print(f"Wiki「{name}」がありません。", file=sys.stderr)
        return 1

    # 最初のパスワードも決めてもらう（Wiki設計者の指示、2026-09-08）。既定値のまま
    # だと、そのWikiは「誰でも知っている値で管理者に入れる」状態から始まる
    password = args.password or ask_password(f"[{name}] 管理者の最初のパスワード")
    if not password:
        return 1
    ok, message = create_db(wiki_dir, password)
    print(f"[{name}] {message}")
    if ok:
        # 助手グループ（staff）にadminを先に入れておく（Wiki設計者の指示、
        # 2026-09-12。「予め作る」）。以降は普通のグループと同じ扱いになる
        from wikilib.groups import ensure_staff_group
        ensure_staff_group(wiki_dir)
    return 0 if ok else 1


def ask_password(prompt="新しいパスワード"):
    """パスワードを2回聞いて、一致したら返す。合わなければ空文字。

    打った文字は画面に出さない（`getpass`）。**2回聞くのは、打ち間違えた
    ものをそのまま登録してしまわないため**——画面側の `/.pwhash` と同じ
    考えかた。端末が無い場合（パイプ越しなど）は聞けないので空文字を返す。"""
    import getpass

    if not sys.stdin.isatty():
        print("パスワードは --password で渡してください（端末がありません）。",
              file=sys.stderr)
        return ""
    first = getpass.getpass(f"{prompt}: ")
    if not first:
        print("パスワードが空です。", file=sys.stderr)
        return ""
    if first != getpass.getpass("もう一度: "):
        print("2回の入力が一致しません。", file=sys.stderr)
        return ""
    return first


def choose_farm(argv_name, purpose):
    """どのWikiを対象にするか決める。決まらなければ空文字。

    名前が渡されていればそれ。**省略されたときは一覧から選んでもらう**
    （Wiki設計者の指示、2026-09-08）。取り違えると別のWikiの管理者パスワードを
    書き換えてしまうので、いまいる場所や既定のWikiで黙って進めない。"""
    from wikilib.allwiki import wiki_names

    name = (argv_name or "").strip("/")
    if name.startswith(FARM_PREFIX):
        name = name[len(FARM_PREFIX):]
    if name:
        return name

    names = wiki_names()
    if not names:
        print("Wikiが1つもありません。", file=sys.stderr)
        return ""
    if not sys.stdin.isatty():
        print("対象のWikiを =Wiki名 で指定してください（端末がありません）。",
              file=sys.stderr)
        return ""
    print(f"{purpose}Wikiを選んでください。")
    for i, one in enumerate(names, 1):
        print(f"  {i}. {one}")
    try:
        answer = input("番号（やめるならEnter）: ").strip()
    except EOFError:
        return ""
    if not answer.isdigit() or not 1 <= int(answer) <= len(names):
        print("やめました。")
        return ""
    return names[int(answer) - 1]


def wiki_fingerprint(wiki_dir):
    """そのWikiのトップページのフッターに出ている値を返す。

    `resetpw` の**取り違え防止**に使う（Wiki設計者の指示、2026-09-08）。画面の
    フッターに出ているのと同じ2つを、同じ書きかたで作る。

        Last-modified: 2026-09-07 09:52          トップページの平文の更新日時
        DiskUsage: Page/Attached 88KB/4.7MB      wiki/ と attach/ の合計

    Convert-time は毎回変わるので使わない。

    **中身は `wikilib.wikimark` が持つ。** 同じ確かめかたを `/.delwiki` の
    3段目でも使うようになったので、2か所に同じ組み立てを置かずに済むよう
    移した（2026-09-18）。ここは道具側の名前として残してある。"""
    from wikilib.wikimark import marks

    return marks(wiki_dir)


def read_pasted_footer():
    """貼り付けを1回ぶん読む。空で終われば空文字。"""
    lines = []
    while True:
        try:
            line = input("> ")
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    # 貼り付けの空白は当てにしない（改行やタブが混ざる）
    return " ".join(" ".join(lines).split())


def confirm_by_footer(name, wiki_dir):
    """トップページのフッターを貼ってもらって、Wikiの取り違えを防ぐ。

    **他人のなりすまし対策ではない**（Wiki設計者の指示、2026-09-08）。サーバーで
    実行できる人しかここへ来ないので、防ぎたいのは「別のWikiを指してしまう」
    ほうだけ。それなら、**その画面を実際に開いた人にしか貼れないもの**を
    求めれば足りる。

    見るのは `Last-modified` と `DiskUsage` の**両方**（Wiki設計者の指示）。
    毎回変わる `Convert-time` は使わない。

    **合わなければ、その場でやり直してもらう**（同）。貼るあいだにページが
    更新されたり添付が増えたりすると `DiskUsage` は変わるので、そのときは
    開き直して貼り直せば済む。値は聞くたびに数え直す。やめるときは空行。"""
    from wikilib import wikimark

    while True:
        marks = wiki_fingerprint(wiki_dir)
        if len(marks) < 2:
            print(f"[{name}] トップページが読めないので、貼り合わせでの確認は"
                  "できません。--no-check で実行してください。", file=sys.stderr)
            return False
        print(f"[{name}] のトップページを開き、"
              "**フッターを丸ごと**貼り付けてください。")
        print("  （例:  Convert-time: 17.1ms Last-modified: … DiskUsage: … ）")
        print("  貼り終えたら空行でEnter。やめるならそのままEnter。")
        pasted = read_pasted_footer()
        if not pasted:
            print("やめました。")
            return False
        missing = wikimark.missing_marks(wiki_dir, pasted)
        if not missing:
            print(f"[{name}] 確認できました。")
            return True
        print(f"[{name}] フッターが合いません（{' / '.join(missing)} が見つかりません）。",
              file=sys.stderr)
        print("  **別のWikiのものではありませんか。** 変わっただけなら、"
              "ページを開き直して貼り直してください。", file=sys.stderr)


def run_resetpw(argv):
    """`./wiki.py resetpw [=Wiki名] [--password …]` … 管理者のパスワードを入れ直す。

    **画面からは戻れなくなったときの逃げ道**（Wiki設計者の指示、2026-09-08）。
    管理者がパスワードを忘れたときや、まちがえ続けて**自分をロック**して
    しまったときに使う。アカウントの一覧（`/.admin/accounts`）は管理者しか
    開けないので、そこからは戻せない。

    書き換えるのは `uidnum = 1` の `pw` だけ。**ロックもこれで解ける**
    （ロックは `pw` が `LOCKED` なだけなので）。`uid` と `name` は触らない。

    対象のWikiは `=Wiki名` で指定する。**省略したときは一覧から選んでもらう**
    ——取り違えると別のWikiの管理者パスワードを書き換えてしまうため、
    いまいる場所や既定のWikiで黙って進めない。

    そのうえで、**そのWikiのトップページのフッターを貼ってもらう**
    （`confirm_by_footer`。Wiki設計者の指示、2026-09-08）。名前だけで進めると、
    似た名前のWikiを取り違えたまま書き換えてしまう。`--no-check` で省ける。"""
    from wikilib.userdb import exists, reset_admin_password

    parser = argparse.ArgumentParser(
        prog="wiki.py resetpw",
        description="そのWikiの管理者（admin）のパスワードを入れ直す")
    parser.add_argument("farm", nargs="?", default="",
                        help="対象のWiki（=Wiki名）。省略すると一覧から選ぶ")
    parser.add_argument("--password", default="",
                        help="新しいパスワード（省略すると聞きます）")
    parser.add_argument("--no-check", action="store_true",
                        help="トップページのフッターでの確認を省く")
    args = parser.parse_args(argv)

    name = choose_farm(args.farm, "管理者のパスワードを入れ直す")
    if not name:
        return 1
    wiki_dir = farm_wiki_dir(name)
    if wiki_dir is None:
        print(f"Wiki「{name}」がありません。", file=sys.stderr)
        return 1
    if not exists(wiki_dir):
        print(f"[{name}] アカウントの記録がありません。"
              "`./wiki.py initusers` で用意してください。", file=sys.stderr)
        return 1

    # **どのWikiかを取り違えていないか、貼り合わせで確かめる**（Wiki設計者の指示、
    # 2026-09-08）。名前が似ているWikiを取り違えると、関係のないWikiの管理者
    # パスワードを書き換えてしまう
    if not args.no_check:
        if not sys.stdin.isatty():
            print("確認できないので、--no-check を付けて実行してください"
                  "（端末がありません）。", file=sys.stderr)
            return 1
        if not confirm_by_footer(name, wiki_dir):
            return 1

    password = args.password or ask_password(f"[{name}] 管理者の新しいパスワード")
    if not password:
        return 1
    ok, message = reset_admin_password(wiki_dir, password)
    print(f"[{name}] {message}", file=sys.stderr if not ok else sys.stdout)
    return 0 if ok else 1


def run_convwiki(argv):
    """`./wiki.py convwiki <PukiWiki名> <Wiki名>` … PukiWikiのデータを写す。

        ./wiki.py convwiki 1ev-c Prog1

    `~/syncthing/pukiwiki/1ev-c/` のページと添付ファイルをもとに、
    `wikidata/Prog1/` を**新しいWikiとして**作る。何をどう写すかは
    `wikilib.convwiki` の冒頭を参照。

    既にあるWikiには書き込まない（`newwiki.validate_name` が弾く）。数百ページを
    一度に置く操作なので、取り違えたときに元のWikiへ混ざらないほうがよい。
    入れ直したいときは、作られたディレクトリごと消してから実行する。

    管理者の最初のパスワードは、`initusers` と同じく必ず決めてもらう
    （Wiki設計者の指示、2026-09-08）。写しただけのWikiでも、誰でも知っている
    既定値で管理者に入れる状態から始めないため。試算（`--dry-run`）では
    何も作らないので聞かない。"""
    from wikilib.convwiki import DEFAULT_SOURCE_ROOT, DEFAULT_THEME, convert

    parser = argparse.ArgumentParser(
        prog="wiki.py convwiki",
        description="PukiWikiのデータを写して、新しいWikiを作る")
    parser.add_argument("source", help="変換元（PukiWikiのディレクトリ名、またはパス）")
    parser.add_argument("name", help="作るWikiの名前（wikidata/<名前>/ になる）")
    parser.add_argument("--title", default="", help="トップページの見出し（省略するとWiki名）")
    parser.add_argument("--src-root", default=DEFAULT_SOURCE_ROOT,
                        help=f"変換元の置き場所（既定: {DEFAULT_SOURCE_ROOT}）")
    parser.add_argument("--password", default="",
                        help="管理者の最初のパスワード（省略すると聞きます）")
    parser.add_argument("--include-system", action="store_true",
                        help="PukiWikiの設定ページ（:config など）も写す")
    parser.add_argument("--include-stock", action="store_true",
                        help="PukiWiki付属のページ（FormattingRules・SandBox など）も写す")
    parser.add_argument("--toppage", default="",
                        help="index にするページ（省略するとPukiWikiの $defaultpage）")
    parser.add_argument("--theme", default=DEFAULT_THEME,
                        help=f"写したWikiで使うテーマ（既定: {DEFAULT_THEME}。"
                             "空文字なら設定に書かない）")
    parser.add_argument("--dry-run", action="store_true",
                        help="何も書かずに、何をどこへ写すかだけを出す")
    args = parser.parse_args(argv)

    name = args.name.strip("/")
    if name.startswith(FARM_PREFIX):
        name = name[len(FARM_PREFIX):]

    password = ""
    if not args.dry_run:
        password = args.password or ask_password(f"[{name}] 管理者の最初のパスワード")
        if not password:
            return 1

    ok, _ = convert(args.source, name, title=args.title, admin_password=password,
                    source_root=args.src_root, include_system=args.include_system,
                    include_stock=args.include_stock, top_page=args.toppage,
                    theme=args.theme, dry_run=args.dry_run)
    return 0 if ok else 1


# サブコマンド一覧。(名前, 実行する関数, 一覧に出す一行説明) の並び。
# main() での振り分けと、`./wiki.py --help` の一覧表示の両方がここを見る
# （同じ一覧を2箇所に書いて、増やしたときに片方だけ直し忘れるのを防ぐ）。
# 各サブコマンドの詳しい引数は `./wiki.py <名前> --help` で個別に見られる
# （それぞれが自分のargparseを持つため。ここに書くのは一覧に出す一行だけ）。
SUBCOMMANDS = [
    ("updatepage", run_updatepage, "平文ファイルの直接編集を取り込み、システム側の記録を揃える"),
    ("version", run_version, "版と改訂を表示する"),
    ("initusers", run_initusers, "そのWikiのアカウントの記録（config/users.db）を用意する"),
    ("resetpw", run_resetpw, "そのWikiの管理者（admin）のパスワードを入れ直す"),
    ("convwiki", run_convwiki, "PukiWikiのデータを写して、新しいWikiを作る"),
]


def subcommands_epilog():
    """`./wiki.py --help` の末尾に添える、サブコマンドの一覧。

    SUBCOMMANDSから作るので、サブコマンドを増やしてもここは直さなくてよい。"""
    width = max(len(name) for name, _, _ in SUBCOMMANDS)
    lines = ["サブコマンド:"]
    lines += [f"  {name:<{width}}  {desc}" for name, _, desc in SUBCOMMANDS]
    lines.append("")
    lines.append("詳しい引数は `./wiki.py <サブコマンド> --help` で見られます。")
    return "\n".join(lines)


# bottleの既定サーバー（wsgiref）はシングルスレッドで1接続ずつしか捌けない。
# 編集画面のようにCSS/JS/埋め込みJSONなど多数のリソースを一度に読み込む画面で、
# ハードリロード等により並行接続がTCPのlisten backlog（既定5）を超えると、
# 溢れた接続はSYNごと捨てられ、クライアント側のTCP再送（数十秒〜）待ちになって
# 「応答がない」ように見えてしまう。スレッドで並行に捌けるようにしておく。
class _ThreadingWSGIServer(socketserver.ThreadingMixIn, wsgiref.simple_server.WSGIServer):
    daemon_threads = True  # メインプロセスの終了を待たせない


def main():
    # 設定ファイルが1つも無いと何も読めないまま動き出してしまうので、
    # 何より先に、無い分だけ雛形（*.example.yaml）から作っておく。
    ensure_root_config_files()

    # `./wiki.py updatepage …` のように、先頭が命令ならそちらを実行する。
    # 起動の引数（--host など）と混ざらないよう、argparse に渡す前に振り分ける
    if len(sys.argv) > 1:
        for name, runner, _ in SUBCOMMANDS:
            if sys.argv[1] == name:
                sys.exit(runner(sys.argv[2:]))

    # 待受ホスト・ポートの既定値はconfigから読み込み、コマンドライン引数があればそちらを優先する
    server_conf = load_config().get("server") or {}
    parser = argparse.ArgumentParser(
        description="Python + bottle 製 Wiki Farm システム",
        epilog=subcommands_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=server_conf.get("host", "127.0.0.1"),
                        help="待受ホスト（外部公開する場合は 0.0.0.0 を指定）")
    parser.add_argument("--port", type=int, default=server_conf.get("port", 8619), help="待受ポート")
    parser.add_argument("--debug", action="store_true", help="bottleのデバッグモードを有効化")
    args = parser.parse_args()

    if args.debug:
        # プラグインのエラー詳細も表示する（config の debug: true と同じ扱い）
        set_force_debug(True)

    # /.restart で自分を起動し直せるよう、実行時の引数を控えておく
    mark_standalone(sys.argv)

    stop_previous_instance(args.host, args.port)
    _write_pid_file(args.port)

    # DBの控えを作る途中で止められた一時ファイル（pageinfo/dbbackup-*）を片づける。
    # 前のプロセスを止めたあとなので、控えを取っている最中のものは無い
    swept = sum(sweep_leftovers(farm_wiki_dir(name)) for name in wiki_names())
    if swept:
        print("DBの控えの作りかけを片づけました: {}個".format(swept), flush=True)

    # 止まっている間にファイルが直接書き換えられているかもしれないので、
    # 受け付けを始める前に取り込んでおく。かかった時間も出す。
    # flush するのは、出力先がファイルだと stdout が溜め込まれ、bottleの起動案内
    # （stderr）より後に出てしまうため
    print(format_result(sync_all()), flush=True)
    # 動かしている間も定期的に見に行く（既定は1時間ごと）
    start_watcher(log=lambda line: print(line, flush=True))

    bottle.run(app, host=args.host, port=args.port, debug=args.debug, reloader=args.debug,
              server_class=_ThreadingWSGIServer)


if __name__ == "__main__":
    main()
