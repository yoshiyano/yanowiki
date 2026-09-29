"""サービスの再起動（/.restart）。

動かしかたによって「再起動」の意味が変わるため、まず動作環境を見分けてから
それぞれに合った方法をとる。共通しているのは **応答を返しきってから実行する**
ことで、そうしないと再起動を頼んだ相手に結果が届かない。

    standalone  … wiki.py を直接実行（bottleの内蔵サーバ）
                  自分自身を exec し直す。プロセスIDは変わらないのでPIDファイルもそのまま
    gunicorn    … 親（master）に SIGHUP を送る。workerが順に入れ替わり、
                  そのときアプリを読み直すのでコードの更新も反映される
    uwsgi       … uwsgi.reload() を呼ぶ。uWSGI自身が入れ替わりを面倒みる
    mod_wsgi    … デーモンモードなら自分に SIGINT を送る（mod_wsgiの作法）。
                  埋め込みモードでは自分を止められないので、入口スクリプトの
                  時刻だけ更新して、リロード監視に拾ってもらう
    unknown     … 入口スクリプトの時刻を更新するだけ（拾われるかは環境しだい）

nginx は Python を直接動かさず、gunicorn や uWSGI の前に立つ役なので、
見分けるのは「後ろで動いているWSGIサーバ」のほう。nginx越しでも判別は変わらない。
ただし応答が手元を離れてから届くまでに一手間ある分、返しきる猶予は少し長めにとる。

どの方法でも、次に立ち上がるプロセスはコードを読み直すので、
ファイルを更新してからここを叩けば、更新を反映した状態で再開できる。
"""
import os
import signal
import sys
import threading
import time
from html import escape

from bottle import HTTPResponse, request

from wikilib.paths import BASE_DIR, RESTART_URLPATH

# wiki.py を直接実行したときだけ、その argv を覚えておく（exec し直すのに使う）。
# 推測に頼らず、起動した側が名乗る形にしている。
_standalone_argv = None

# 応答を返しきるまでの猶予。リバースプロキシ（nginx等）を挟むと
# 手元を離れてから相手に届くまでに一手間あるため、少し長めにとる。
RESTART_DELAY = 1.0


def mark_standalone(argv):
    """wiki.py を直接実行して起動したことを記録する。"""
    global _standalone_argv
    _standalone_argv = list(argv)


def entry_script():
    """リロード監視に見てもらう入口スクリプト。無ければ None。"""
    for name in ("wiki.wsgi", "wiki.py"):
        path = os.path.join(BASE_DIR, name)
        if os.path.isfile(path):
            return path
    return None


def detect_mode(environ=None):
    """いまどうやって動いているかを返す。"""
    env = environ if environ is not None else {}
    software = (env.get("SERVER_SOFTWARE")
                or os.environ.get("SERVER_SOFTWARE") or "").lower()

    if "mod_wsgi" in software or "mod_wsgi.process_group" in env:
        return "mod_wsgi"
    if "uwsgi" in sys.modules or "uwsgi" in software:
        return "uwsgi"
    if "gunicorn" in software or "gunicorn.workers" in sys.modules:
        return "gunicorn"
    if _standalone_argv is not None:
        return "standalone"
    return "unknown"


def mod_wsgi_is_daemon(environ):
    """mod_wsgi のデーモンモードか。空文字列なら埋め込みモード（自分は止められない）。"""
    return bool(environ.get("mod_wsgi.process_group"))


def touch_entry_script():
    """入口スクリプトの更新時刻だけ新しくする。

    mod_wsgi（WSGIScriptReloading）や、その種のリロード監視を持つ環境に
    「読み直してほしい」と伝えるための合図。中身は変えない。"""
    path = entry_script()
    if path is None:
        return False
    try:
        os.utime(path, None)
        return True
    except OSError:
        return False


def describe(mode, environ=None):
    """その環境で再起動を頼むと何が起きるかの説明。画面に出す。"""
    if mode == "standalone":
        return "このプロセスを起動し直します（wiki.py の直接実行）。"
    if mode == "gunicorn":
        return "gunicorn の親プロセスに合図を送り、ワーカーを順に入れ替えます。"
    if mode == "uwsgi":
        return "uWSGI に読み直しを頼みます。"
    if mode == "mod_wsgi":
        if environ is not None and not mod_wsgi_is_daemon(environ):
            return ("mod_wsgi の埋め込みモードで動いています。プロセス自体は止められないため、"
                    "入口スクリプトの時刻を更新して読み直しを促します"
                    "（反映されない場合はApacheの再読み込みが必要です）。")
        return "mod_wsgi のデーモンプロセスを起動し直します。"
    return ("起動のしかたを判別できませんでした。入口スクリプトの時刻を更新して"
            "読み直しを促しますが、反映されるかは環境しだいです。")


def request_restart(environ=None):
    """再起動を予約する。(方式, 受け付けたか) を返す。

    応答を返しきってから実行したいので、少し待ってから別スレッドで行う。
    ここで待たずに実行すると、頼んだ相手に結果が届かないまま接続が切れる。"""
    mode = detect_mode(environ)
    daemon = mod_wsgi_is_daemon(environ or {})

    def run():
        time.sleep(RESTART_DELAY)
        try:
            if mode == "standalone":
                # 実行ファイルを置き換える。プロセスIDは変わらないので、
                # PIDファイルの内容も正しいまま
                os.execv(sys.executable, [sys.executable] + _standalone_argv)
            elif mode == "gunicorn":
                os.kill(os.getppid(), signal.SIGHUP)
            elif mode == "uwsgi":
                import uwsgi  # uWSGI の中でだけ読める組み込みモジュール

                uwsgi.reload()
            elif mode == "mod_wsgi" and daemon:
                touch_entry_script()
                os.kill(os.getpid(), signal.SIGINT)  # mod_wsgi の自己再起動の作法
            else:
                touch_entry_script()
        except Exception:
            # 再起動できなくても、いま動いているサービスは止めない
            pass

    threading.Thread(target=run, daemon=True).start()
    return mode, True


def serve_restart(wiki_dir, config, farm, explicit_farm):
    """`/.restart` の取り次ぎ。**既定Wikiの管理者と助手だけ**が通る
    （Wiki設計者の指示、2026-09-13）。関門は `sysui.require_on_default_farm`。

    **入口をここ1つにまとめてあるのは、`?now=1` を守り忘れないため。**
    あちらは画面を介さずその場で再起動するので、関門が画面側にしか無いと、
    そこが素通りの抜け道になる。

    **道具から叩く使いかた（`?now=1`）にもログイン状態が要るようになった。**
    cookieを持たないコマンド（素の `curl` など）からは通らない。"""
    from wikilib import sysui  # 循環を避けるため呼び出し時に読み込む

    denied = sysui.require_on_default_farm(config, farm, wiki_dir, explicit_farm,
                                           RESTART_URLPATH)
    if denied is not None:
        return denied
    if request.query.get("now"):
        _staff_record(wiki_dir, farm)
        return restart_response()
    return render_restart(wiki_dir, config, farm, explicit_farm)


def _staff_record(wiki_dir, farm):
    """助手の再起動を記録する（戻すものは無い。wikilib.stafflog）。"""
    from wikilib import stafflog

    staff = stafflog.actor(wiki_dir, farm)
    if staff is not None:
        stafflog.record(wiki_dir, staff, "restart", "", "再起動した")


def render_restart(wiki_dir, config, farm, explicit_farm):
    """/.restart の画面。GETで確認、POSTで実行する。

    **関門は `serve_restart` が通してある**（この関数を直接呼ばないこと）。"""
    from wikilib import sysui
    from wikilib.themes import make_plugin_context

    context = make_plugin_context(config, farm, wiki_dir, RESTART_URLPATH, explicit_farm)
    action = context.base_url + "/" + RESTART_URLPATH
    mode = detect_mode(request.environ)
    note = describe(mode, request.environ)

    if request.method == "POST":
        _staff_record(wiki_dir, farm)
        request_restart(request.environ)
        body = (
            '<div class="restart">'
            '<p class="restart-message">再起動を受け付けました。</p>'
            f'<p class="restart-note">{escape(note)}</p>'
            '<p class="restart-hint">数秒ほどで戻ります。'
            f'つながらない場合は、少し待ってから<a href="{escape(context.base_url)}/">'
            'トップページ</a>を開き直してください。</p>'
            "</div>"
        )
        # Connection ヘッダは WSGI が扱う領分（hop-by-hop）なのでアプリからは付けない。
        # 応答を返しきる時間は RESTART_DELAY の待ちで確保する。
        return sysui.page(wiki_dir, config, farm, explicit_farm, RESTART_URLPATH, "再起動", body)

    body = (
        '<div class="restart">'
        '<p class="restart-message">このWikiサービスを再起動します。</p>'
        f'<p class="restart-note">{escape(note)}</p>'
        '<p class="restart-hint">再起動の間、数秒ほどページが開けなくなります。'
        '編集中の内容がある場合は、先に保存してください。</p>'
        f'<form class="restart-form" method="post" action="{escape(action)}">'
        '<button type="submit" class="restart-go">再起動する</button>'
        f'<a class="restart-cancel" href="{escape(context.base_url)}/">やめる</a>'
        "</form></div>"
    )
    return sysui.page(wiki_dir, config, farm, explicit_farm, RESTART_URLPATH, "再起動", body)


def restart_response():
    """画面を介さず、その場で再起動だけを受け付ける（プレーンテキストで返す）。
    `/.restart?now=1` のように、道具から叩く場合に使う。

    **関門は `serve_restart` が通してある**（この関数を直接呼ばないこと）。
    ここを素で呼べる場所を作ると、そこが再起動の抜け道になる。"""
    mode, _ = request_restart(request.environ)
    return HTTPResponse(body=f"restarting ({mode})\n", status=200,
                        content_type="text/plain; charset=utf-8")
