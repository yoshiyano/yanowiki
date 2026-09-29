"""bottle.py を使っているシステムへの組み込み。

    import bottle
    from server.embed import mount_webfiledir

    app = bottle.Bottle()                     # 組み込む側のアプリ
    mount_webfiledir(app, "/files/", "webfiledir.toml",
                     authorize=lambda req: current_user(req) is not None,
                     mount_access=lambda req, mount: "rw" if is_admin(req) else "ro")

同じプロセスの中に組み込むので、webFileDir への要求は必ず組み込む側のアプリを通る。
組み込む側の認証（authorize）と認可（mount_access）を webFileDir の手前で効かせられる。
細部は Wiki の「組み込みかた」（配布物では EMBED.md）の 7 章。
"""

import os

import bottle

from .app import create_app
from .config import Config, load_config, prepare_mounts


def mount_webfiledir(host: bottle.Bottle, prefix: str, config: Config | str | os.PathLike, *,
                     authorize=None, mount_access=None, live_updates: bool = True,
                     check_roots: bool = True, providers=None) -> bottle.Bottle:
    """webFileDir を host の prefix（例: "/files/"）の下に組み込み、webFileDir のアプリを返す。

    config          … Config か、設定ファイル（TOML）のパス。[server] の host / port は使わない
                      （待ち受けは組み込む側のもの）。allowed_origins は変更系の Origin の確認に使う
    authorize       … authorize(request) -> bool。False なら 403。bottle.HTTPResponse を投げれば
                      それを返す（例: bottle.redirect("/login")）
    mount_access    … mount_access(request, mount_id) -> "rw" | "ro" | None（None は見せない）
    live_updates    … 組み込む側が 1 本ずつしか処理しないサーバ（bottle の既定の wsgiref など）で動くなら
                      False にする。自動更新は接続を開いたままにするので、ほかの要求が止まる
    check_roots     … マウントの根を用意し、持ち主などを確かめる（起動時と同じ。使えなければ ConfigError）
    providers       … 差し込むプロバイダの種類 {"種類の名前": 作る関数}（create_app と同じ。Wiki「プロバイダの作りかた」）
    """
    if not isinstance(prefix, str) or not prefix.startswith("/") or prefix == "/":
        raise ValueError('prefix は "/files/" のように / で始まる、根以外のパスにしてください')
    prefix = prefix.rstrip("/") + "/"  # bottle は末尾が / のときだけルートを合流させる（速く、素直に動く）
    if not isinstance(config, Config):
        config = load_config(config)
    if check_roots:
        prepare_mounts(config)
    app = create_app(config, authorize=authorize, mount_access=mount_access, live_updates=live_updates,
                     providers=providers)
    host.mount(prefix, app)

    # "/files" で来たら "/files/" へ（画面の相対 URL が、末尾の / を前提にしているため）
    @host.route(prefix.rstrip("/"), method=["GET", "HEAD"])
    def to_slash():
        q = bottle.request.query_string
        bottle.redirect(prefix + ("?" + q if q else ""), 307)

    return app
