"""bottle のアプリケーション。ルーティングと JSON の出し入れを受け持つ。

API の形は Wiki の「API 設計」を正とする。
"""

import functools
import json
import logging
import mimetypes
import queue
import re
import threading
from urllib.parse import quote, urlsplit
from dataclasses import dataclass
from pathlib import Path

import bottle

from . import ops, vpath
from .attributes import check_attributes
from .icons import check_icons
from .config import Config, ConfigError, MountConfig
from .errors import ApiError
from .providers import LocalProvider, MemoryProvider, OpenMethod, OpenResult, Provider
from .watch import ChangeHub, FolderWatcher

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
API = "/api/v1"
MAX_BULK = 10000  # 一括操作で一度に受け付ける項目数
MAX_WATCH_TARGETS = 256  # 自動更新で 1 つの接続が見張れるフォルダの数
HEARTBEAT = 20.0  # 自動更新の接続へ空の行を送る間隔（秒）。切れた接続に気付き、途中のプロキシに切られないように


@dataclass(frozen=True)
class Mount:
    config: MountConfig
    provider: Provider

    def to_json(self, access: str = "rw") -> dict:
        readonly = self.config.readonly or access == "ro"
        return {
            "id": self.config.id,
            "label": self.config.label,
            "readonly": readonly,
            # 読み取り専用なら、プロバイダが持っていても変更系は申告しない。開く（open）は変更ではないので申告する
            "capabilities": sorted(([] if readonly else list(self.provider.capabilities))
                                   + (["open"] if open_methods_of(self.provider) else [])),
            # 開く経路（先頭が既定。modifier のキーを押しながら開くとその経路）
            "openMethods": [o.to_json() for o in open_methods_of(self.provider)],
            # フォルダの開く経路（既定の「中に入る」は画面が持ち、ここには入れない）
            "dirOpenMethods": [o.to_json() for o in dir_open_methods_of(self.provider)],
            # 詳細表示の列・並べ替えのキーになる属性の定義（値の規則と表現方法）
            "attributes": [a.to_json() for a in self.provider.attributes],
            # 持ち込んだアイコン {名前: {viewBox, shapes}} と、ツリーのマウントの行のアイコンの名前
            "icons": {k: v.to_json() for k, v in self.provider.icons.items()},
            "icon": self.provider.mount_icon,
        }


# 組み込みのプロバイダの種類 → 作る関数（MountConfig を受け取り Provider を返す）
BUILTIN_PROVIDERS = {
    "local": lambda m: LocalProvider(m.root, m.trash),
    "memory": lambda m: MemoryProvider(),
}
KNOWN_CAPABILITIES = frozenset({"mkdir", "touch", "rename", "delete", "copy", "move", "stream", "trash"})


def provider_table(providers=None) -> dict:
    """組み込みの種類に、利用する側が差し込んだ種類（providers）を足した対応表。"""
    table = dict(BUILTIN_PROVIDERS)
    for name, factory in (providers or {}).items():
        if not isinstance(name, str) or not name:
            raise ValueError("providers のキー（種類の名前）は空でない文字列にしてください")
        if name in BUILTIN_PROVIDERS:
            # local は根の外に出さない確かめなどを持つ。黙って置き換えられると安全の前提が崩れる
            raise ValueError(f"組み込みの種類 {name} は置き換えられません。別の名前にしてください")
        if not callable(factory):
            raise ValueError(f"providers[{name!r}] はプロバイダを作る関数にしてください")
        table[name] = factory
    return table


def build_mounts(config: Config, providers=None) -> dict[str, Mount]:
    """設定のマウントごとにプロバイダを作る。種類が無い・作れない・約束に合わなければ ConfigError。"""
    table = provider_table(providers)
    mounts = {}
    for m in config.mounts:
        where = f"マウント {m.id}"
        factory = table.get(m.type)
        if factory is None:
            raise ConfigError(f"{where}: type は {', '.join(sorted(table))} のどれかにしてください")
        try:
            provider = factory(m)
        except ConfigError as e:
            # 差し込んだ種類の固有の設定（options）の誤りは、作る関数が ConfigError で知らせる
            raise ConfigError(f"{where}: {e}") from None
        if not isinstance(provider, Provider):
            raise ConfigError(f"{where}: type = {m.type!r} の作る関数が Provider を返しませんでした")
        unknown = set(provider.capabilities) - KNOWN_CAPABILITIES
        if unknown:
            raise ConfigError(f"{where}: 知らない capabilities があります: {', '.join(sorted(unknown))}")
        err = (check_attributes(provider.attributes) or check_icons(provider.icons, provider.mount_icon)
               or check_open_methods(provider.open_methods)
               or (check_open_methods(provider.dir_open_methods, "dir_open_methods", first_is_default=False)
                   if provider.dir_open_methods is not None else None))
        if err:
            raise ConfigError(f"{where}: {err}")
        mounts[m.id] = Mount(m, provider)
    return mounts


# 中身を読める（"stream"）プロバイダの既定の開く経路。API 層が GET /api/v1/raw へ移す
STREAM_OPEN_METHODS = (
    OpenMethod("view", "ブラウザで表示"),
    OpenMethod("download", "ダウンロード", modifier="shift"),
)
# フォルダの既定の開く経路（画面の既定の「中に入る」のあとに続く）。API 層が、そのフォルダを
# 新しいタブ・隣の画面で表示させる（action "browse"）
DIR_OPEN_METHODS = (
    OpenMethod("tab", "新しいタブで開く", modifier="shift"),
    OpenMethod("pane", "隣の画面で開く"),
)
DIR_BROWSE_TARGETS = {"tab": "_blank", "pane": "other"}  # 既定の経路の id → browse の target
BROWSE_TARGETS = ("_self", "_blank", "other")
NAVIGATE_METHODS = ("GET", "POST")  # navigate の送りかた（ブラウザでページを開く形で送れるもの）
OPEN_MODIFIERS = ("shift",)  # Ctrl はクリックでの選択に使うので使わない
OPEN_METHOD_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


def open_methods_of(p: Provider) -> tuple:
    """プロバイダのファイルの開く経路（宣言が無ければ自動で決める）。"""
    if p.open_methods:
        return tuple(p.open_methods)
    if type(p).open is not Provider.open:
        return (OpenMethod("open", "開く"),)
    if "stream" in p.capabilities:
        return STREAM_OPEN_METHODS
    return ()


def dir_open_methods_of(p: Provider) -> tuple:
    """プロバイダのフォルダの開く経路（None なら既定の 2 つ。既定の「中に入る」は含まない）。"""
    return DIR_OPEN_METHODS if p.dir_open_methods is None else tuple(p.dir_open_methods)


def check_open_methods(methods, name: str = "open_methods", first_is_default: bool = True) -> str | None:
    """経路の並びを確かめる。first_is_default なら先頭が既定の経路なので modifier を付けさせない
    （フォルダの経路は、既定が画面の「中に入る」なので付けてよい）。"""
    if not isinstance(methods, (tuple, list)):
        return f"{name} は OpenMethod の並びにしてください"
    ids, mods = set(), set()
    for o in methods:
        if not isinstance(o, OpenMethod):
            return f"{name} に OpenMethod でないものがあります: {o!r}"
        if not isinstance(o.id, str) or not OPEN_METHOD_ID_RE.match(o.id) or o.id in ids:
            return f"開く経路の id {o.id!r} は英小文字で始まる英小文字・数字・- の 32 文字までで、重ならないこと"
        if not isinstance(o.label, str) or not o.label:
            return f"開く経路 {o.id!r}: label は空でない文字列にしてください"
        if o.modifier is not None and (o.modifier not in OPEN_MODIFIERS or o.modifier in mods):
            return f"開く経路 {o.id!r}: modifier は {', '.join(OPEN_MODIFIERS)} か None で、重ならないこと"
        ids.add(o.id)
        mods.add(o.modifier)
    if first_is_default and methods and methods[0].modifier is not None:
        return "先頭の開く経路（既定）には modifier を付けないでください"
    return None


RAW_CHUNK = 64 * 1024
# GET raw の見せかた（?mode=）→ Content-Disposition。キーは中身を読めるマウントの既定の開く経路の id
RAW_MODES = {"view": "inline", "download": "attachment"}


def json_response(data, status: int = 200) -> str:
    bottle.response.status = status
    bottle.response.content_type = "application/json; charset=utf-8"
    # 一覧は変わりうるので、ブラウザに古いものを使わせない
    bottle.response.set_header("Cache-Control", "no-store")
    return json.dumps(data, ensure_ascii=False)


def api_route(func):
    """API の関数の戻り値を JSON にし、例外をエラーの形にそろえる。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return json_response(func(*args, **kwargs))
        except ApiError as e:
            return json_response(e.to_json(), e.status)
        except Exception:
            # 中身はログへ。画面には出しすぎない
            log.exception("API で想定外の例外: %s %s", bottle.request.method, bottle.request.path)
            return json_response(ApiError("internal", "サーバで想定外のエラーが起きました").to_json(), 500)

    return wrapper


def check_mutation_request(allowed_origins) -> None:
    """変更系 API（POST）の要求が、このツールの画面か利用する側のシステムから来たものか確かめる。

    - X-WebFileDir: 1 と Content-Type: application/json が無ければ拒否（フォームの送信では付けられない）
    - Origin があれば、自分自身か allowed_origins のどれかでなければ拒否（別サイトのページからの CSRF）
    - Origin が無い要求（ブラウザ以外のプログラムから）は通す。CSRF はブラウザでだけ起きるため
    """
    req = bottle.request
    if req.get_header("X-WebFileDir") != "1":
        raise ApiError("bad_request", "X-WebFileDir ヘッダがありません")
    ctype = (req.content_type or "").split(";")[0].strip().lower()
    if ctype != "application/json":
        raise ApiError("bad_request", "本文は application/json で送ってください")
    origin = req.get_header("Origin")
    if origin is None:
        return
    own = f"{req.urlparts.scheme}://{req.get_header('Host', '')}"
    if origin != own and origin not in allowed_origins:
        raise ApiError("bad_origin", "許されていないページからの要求です")


def mutation(func):
    """変更系 API に付ける（@api_route の内側に）。Phase 2 で POST の API を足すときに使う。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # bottle のアプリに mount すると、ルートは組み込む側のアプリに合流し、request.app は組み込む側に
        # なる（設定が無い）。ルートを持っているアプリ（このアプリ）から読む
        config = bottle.request.route.app.config["webfiledir.config"]
        check_mutation_request(config.server.allowed_origins)
        return func(*args, **kwargs)

    return wrapper


ACCESS_VALUES = ("rw", "ro", None)


def create_app(config: Config, static_dir: Path = STATIC_DIR, heartbeat: float = HEARTBEAT, *,
               authorize=None, mount_access=None, live_updates: bool = True,
               providers=None) -> bottle.Bottle:
    """webFileDir の WSGI アプリ（bottle）を作る。

    組み込む側のシステム（server/embed.py の mount_webfiledir など）が渡す口:
      authorize(request)            … 要求ごとに呼ぶ。False を返すと 403。bottle.HTTPResponse を投げれば
                                      それを返す（ログイン画面へのリダイレクトなど）。画面・API・自動更新のすべてに効く
      mount_access(request, mount)  … マウントごとの許し。"rw"（読み書き）/ "ro"（読み取りのみ）/ None（見せない）。
                                      設定の readonly = true は "rw" より強い
      live_updates                  … False なら自動更新（GET /api/v1/events）を使わせない。組み込む側が
                                      1 本ずつしか処理しないサーバで動くとき（開いたままの接続でほかの要求が止まる）
      providers                     … 差し込むプロバイダの種類 {"種類の名前": 作る関数}。作る関数は MountConfig を
                                      受け取り Provider を返す（固有の設定は MountConfig.options）。設定の type に書ける
                                      ようになる。組み込みの local / memory は置き換えられない（ValueError）
    種類が無い・作れないマウントがあれば ConfigError。
    """
    app = bottle.Bottle()
    app.config["webfiledir.config"] = config
    mounts = build_mounts(config, providers)

    def access_of(mid: str):
        """このマウントへの、今の要求の許し（"rw" / "ro" / None）。"""
        if mid not in mounts:
            return None
        if mount_access is None:
            access = "rw"
        else:
            access = mount_access(bottle.request, mid)
            if access not in ACCESS_VALUES:
                raise ValueError(f"mount_access は rw / ro / None を返してください（{access!r}）")
        if access == "rw" and mounts[mid].config.readonly:
            access = "ro"
        return access

    if authorize is not None:
        class AuthorizePlugin:
            """要求ごとに authorize を呼ぶ bottle のプラグイン（ルートを受け取る 2 版の形）。"""
            name = "webfiledir_authorize"
            api = 2

            def apply(self, callback, route):
                is_api = "/api/v1/" in route.rule

                @functools.wraps(callback)
                def wrapper(*args, **kwargs):
                    if authorize(bottle.request) is False:
                        if is_api:
                            return json_response(ApiError("forbidden", "許可されていません").to_json(), 403)
                        raise bottle.HTTPError(403, "許可されていません")
                    return callback(*args, **kwargs)

                return wrapper

        # bottle のプラグインは、このアプリのすべてのルートに効く（mount で組み込む側に合流しても、
        # ルートの持ち主はこのアプリなので効く。組み込む側のプラグインはこのアプリのルートには効かない）
        app.install(AuthorizePlugin())
    root = str(static_dir)
    watcher_lock = threading.Lock()
    watcher: list[FolderWatcher] = []  # 最初の自動更新の接続で作る（inotify の資源を使わない構成もあるため）

    def get_watcher() -> FolderWatcher:
        with watcher_lock:
            if not watcher:
                watcher.append(FolderWatcher())
            return watcher[0]

    app.config["webfiledir.watcher"] = get_watcher  # テストが見張りの数を確かめるため

    def target() -> tuple[Mount, tuple[str, ...]]:
        """クエリの mount と path を検査して返す。"""
        q = bottle.request.query
        mid = q.getunicode("mount")
        if mid is None or access_of(mid) is None:
            raise ApiError("not_found", "そのマウントはありません")
        # getunicode は UTF-8 として読めないと黙って既定値を返すので、「無い」と「読めない」を分ける
        if "path" not in q:
            return mounts[mid], ()
        path = q.getunicode("path")
        if path is None:
            raise ApiError("bad_path", "パスを UTF-8 として読めません")
        return mounts[mid], vpath.split(path)

    # --- 読み取り系 API ---

    @app.get(f"{API}/mounts")
    @api_route
    def api_mounts():
        # 見せないマウント（mount_access が None）は一覧に出さない
        return [m.to_json(a) for m in mounts.values() if (a := access_of(m.config.id)) is not None]

    @app.get(f"{API}/list")
    @api_route
    def api_list():
        mount, path = target()
        entries = mount.provider.listdir(path)
        # dir はこのフォルダ自身（画面が、この中へ作成・貼り付けできるか＝ writeauth を知るため）
        return {"path": vpath.join(path), "dir": mount.provider.stat(path).to_json(),
                "entries": [e.to_json() for e in entries]}

    @app.get(f"{API}/tree")
    @api_route
    def api_tree():
        mount, path = target()
        p = mount.provider
        dirs = [e for e in p.listdir(path) if e.kind == "dir"]
        for e in dirs:
            e.has_children = p.has_children(path + (e.name,))
        return {"path": vpath.join(path), "entries": [e.to_json() for e in dirs]}

    @app.get(f"{API}/stat")
    @api_route
    def api_stat():
        mount, path = target()
        return mount.provider.stat(path).to_json()

    # --- 開く ---

    def raw_url(mid: str, path: tuple[str, ...], mode: str | None = None) -> str:
        """中身の URL（/api/v1/raw/<マウント>/<パス>）。画面（index.html）からの相対。
        見せかたは ?mode=<開く経路の id> で切り替える（省けば表示。download なら保存として）。

        ほかの API と違い、マウントとパスを URL のパス部分に埋め込む（2026-09-28 設計者の指示）。ブラウザの
        タブ・保存の名前がファイル名になり、HTML の中の相対リンクもパスとして解決される。名前は 1 段ずつ
        パーセント符号化するので、# ? % 空白も読み違えない（名前に / は入らないので段の区切りと混ざらない）。
        """
        segments = "/".join(quote(s, safe="") for s in (mid, *path))
        return f"api/v1/raw/{segments}" + (f"?mode={quote(mode, safe='')}" if mode else "")

    def checked_open_result(r) -> dict:
        """プロバイダが返した開きかたを確かめる（誤りはプロバイダの不具合なので internal になる）。"""
        if not isinstance(r, OpenResult) or r.action not in ("navigate", "modal", "browse"):
            raise ValueError(f"open が OpenResult（action は navigate / modal / browse）を返しませんでした: {r!r}")
        if r.action == "browse":
            # 表示させるのは、この要求を出した人が使えるマウントの、あるフォルダだけ
            if r.target not in BROWSE_TARGETS:
                raise ValueError(f"browse の target は {' / '.join(BROWSE_TARGETS)} のどれかです: {r!r}")
            if not isinstance(r.mount, str) or r.mount not in mounts or access_of(r.mount) is None:
                raise ValueError(f"browse の mount がありません（使えません）: {r!r}")
            try:
                parts = vpath.split(r.path)
            except ApiError:
                raise ValueError(f"browse の path が正しい形（/a/b）ではありません: {r!r}") from None
            # 無くなっていれば stat が not_found を返す（そのまま画面へ知らせる）
            if mounts[r.mount].provider.stat(parts).kind != "dir":
                raise ValueError(f"browse の path はフォルダを指してください: {r!r}")
        if r.action == "navigate":
            if not isinstance(r.url, str) or not r.url or r.target not in ("_blank", "_self"):
                raise ValueError(f"navigate には url と target（_blank / _self）が要ります: {r!r}")
            # javascript: などで画面の中でスクリプトを動かせないように、http・https・相対だけを通す
            if urlsplit(r.url).scheme not in ("", "http", "https"):
                raise ValueError(f"navigate の url に使えない形です: {r.url!r}")
            # ページを開く形で送れるのは GET と POST だけ（POST は画面がフォームを作って送る）
            if r.method not in NAVIGATE_METHODS:
                raise ValueError(f"navigate の method は {' / '.join(NAVIGATE_METHODS)} のどれかです: {r!r}")
            if not isinstance(r.params, dict) or not all(
                    isinstance(k, str) and k and isinstance(v, str) for k, v in r.params.items()):
                raise ValueError(f"navigate の params は {{名前: 文字列}} にしてください: {r!r}")
        json.dumps(r.data)  # JSON にできなければ例外
        return r.to_json()

    @app.post(f"{API}/open")
    @api_route
    @mutation
    def api_open():
        """項目を開く。画面がすること（ページへ移る / モーダルで表示する / フォルダを表示する）を返す。
        変更ではないので読み取り専用のマウントでも開ける。プロバイダの開く処理が何かを起こしうるので、
        変更系と同じ POST と CSRF の確かめ（@mutation）を通す。
        フォルダの既定の開きかた（中に入る）は画面がするので、フォルダには経路（method）が要る。"""
        data = body()
        mid = data.get("mount")
        if not isinstance(mid, str) or mid not in mounts or access_of(mid) is None:
            raise ApiError("not_found", "そのマウントはありません")
        m = mounts[mid]
        path = path_field(data, "path")
        is_dir = m.provider.stat(path).kind == "dir"
        methods = dir_open_methods_of(m.provider) if is_dir else open_methods_of(m.provider)
        if not methods:
            raise ApiError("unsupported", f"このマウントでは{'フォルダを中に入る以外の方法' if is_dir else 'ファイル'}"
                           "で開けません", vpath.join(path))
        if is_dir and "method" not in data:
            raise ApiError("bad_request", "フォルダを開く経路（method）を指定してください（中に入るのは画面がします）")
        method = data.get("method", methods[0].id)  # ファイルは省けば既定（先頭）の経路
        if method not in {o.id for o in methods}:
            raise ApiError("bad_request", f"開く経路 {method!r} はこのマウントにありません")
        # フォルダの既定の経路（dir_open_methods を宣言していない）は API 層だけで扱い、open を呼ばない。
        # ファイルのためだけに open を上書きしたプロバイダに、知らない経路の id を渡さないため
        auto_dir = is_dir and m.provider.dir_open_methods is None
        result = None if auto_dir else m.provider.open(path, method)
        if result is None and is_dir:
            if method not in DIR_BROWSE_TARGETS:
                raise ApiError("unsupported", "このフォルダはその方法では開けません", vpath.join(path))
            result = OpenResult("browse", target=DIR_BROWSE_TARGETS[method], mount=mid, path=vpath.join(path))
        elif result is None:
            if "stream" in m.provider.capabilities and method in ("view", "download"):
                # 中身を読めるかをここで確かめる（権限が無いなど）。確かめずに URL を返すと、画面は新しいタブを
                # 開き、そのタブに誤りの JSON が出る（2026-09-29、mode 000 のファイルで起きた）
                with m.provider.open_read(path):
                    pass
            if "stream" in m.provider.capabilities and method == "view":
                result = OpenResult("navigate", raw_url(mid, path), "_blank")
            elif "stream" in m.provider.capabilities and method == "download":
                # 保存として返すので、この画面から移ってもページは変わらない
                result = OpenResult("navigate", raw_url(mid, path, "download"), "_self")
            else:
                raise ApiError("unsupported", "この項目はその方法では開けません", vpath.join(path))
        return checked_open_result(result)

    @app.get(f"{API}/raw/<mount_id>/<rest:path>")
    def api_raw(mount_id: str, rest: str):
        """ファイルの中身をそのまま返す。?mode= で見せかたを切り替える（RAW_MODES。省けば表示）。
        マウントとパスは URL に埋め込む（raw_url）。WSGI サーバがパーセント符号を解いた名前が rest に入る。

        **根の下の .html・.svg のスクリプトが、この画面と同じ出どころで動かないように**、CSP の sandbox
        （スクリプトを止め、別の出どころ扱いにする）と nosniff を付ける。
        """
        mode = bottle.request.query.getunicode("mode") or "view"
        try:
            if mode not in RAW_MODES:
                raise ApiError("bad_request", f"mode は {', '.join(RAW_MODES)} のどれかにしてください")
            if access_of(mount_id) is None or mount_id not in mounts:
                raise ApiError("not_found", "そのマウントはありません")
            m, path = mounts[mount_id], vpath.split("/" + rest)
            if "stream" not in m.provider.capabilities:
                raise ApiError("unsupported", "このマウントでは中身を読めません", vpath.join(path))
            entry = m.provider.stat(path)
            if entry.kind == "dir":
                raise ApiError("bad_path", "フォルダは開けません", vpath.join(path))
            reader = m.provider.open_read(path)
        except ApiError as e:
            return json_response(e.to_json(), e.status)
        ctype = mimetypes.guess_type(entry.name)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        res = bottle.response
        res.content_type = ctype
        res.set_header("Content-Security-Policy", "sandbox")
        res.set_header("X-Content-Type-Options", "nosniff")
        res.set_header("Cache-Control", "no-store")
        disposition = RAW_MODES[mode]
        res.set_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(entry.name)}")
        if entry.size is not None:
            res.set_header("Content-Length", str(entry.size))

        def stream():
            with reader as f:
                while chunk := f.read(RAW_CHUNK):
                    yield chunk

        return stream()

    # --- 変更系 API（POST + JSON。@mutation でヘッダと Origin を確かめる） ---

    def body() -> dict:
        try:
            data = json.loads(bottle.request.body.read() or b"null")
        except (ValueError, UnicodeDecodeError):
            raise ApiError("bad_request", "本文を JSON として読めません") from None
        if not isinstance(data, dict):
            raise ApiError("bad_request", "本文は JSON のオブジェクトにしてください")
        return data

    hub = ChangeHub()  # 仮想構造（OS のパスを持たないマウント）の変化の知らせ役
    for mount_id, m in mounts.items():
        # プロバイダが API の外での変化を知ったとき（notify_changed）も、同じ知らせ役を通す
        m.provider._add_change_listener(lambda mount_id=mount_id: hub.publish(mount_id))

    def is_virtual(m: Mount) -> bool:
        """inotify で見張れないマウントか（プロバイダが watch_path を持たない）。"""
        return type(m.provider).watch_path is Provider.watch_path

    def touched(mid: str) -> None:
        """この要求で変えるマウントとして覚える（notifying が、終わったあとに知らせる）。"""
        bottle.request.environ.setdefault("webfiledir.touched", set()).add(mid)

    def notifying(func):
        """変更系 API に付ける（@mutation の内側に）。終わったら、変えた仮想構造のマウントを知らせる。"""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            finally:
                # 一部だけ失敗しても（一括の結果）、変わったものはあるので知らせる
                for mid in bottle.request.environ.get("webfiledir.touched", ()):
                    if is_virtual(mounts[mid]):
                        hub.publish(mid)

        return wrapper

    def writable(data: dict, capability: str) -> Mount:
        """本文の mount を、変更してよいマウントとして返す。"""
        return writable_mount(data.get("mount"), capability)

    def writable_mount(mid, capability: str) -> Mount:
        if not isinstance(mid, str) or mid not in mounts:
            raise ApiError("not_found", "そのマウントはありません")
        access = access_of(mid)
        if access is None:
            raise ApiError("not_found", "そのマウントはありません")
        m = mounts[mid]
        if access == "ro":
            raise ApiError("forbidden", "読み取り専用のマウントです")
        if capability not in m.provider.capabilities:
            raise ApiError("unsupported", "このマウントではできない操作です")
        touched(mid)
        return m

    def path_field(data: dict, name: str) -> tuple[str, ...]:
        return vpath.split(data.get(name))

    def list_field(data: dict, name: str, check) -> list:
        items = data.get(name)
        if not isinstance(items, list) or not items:
            raise ApiError("bad_request", f"{name} は空でない配列にしてください")
        if len(items) > MAX_BULK:
            raise ApiError("bad_request", f"一度に扱えるのは {MAX_BULK} 個までです")
        for item in items:
            check(item)
        return items

    def on_conflict_field(data: dict) -> str:
        value = data.get("onConflict", "error")
        if value not in ops.ON_CONFLICT:
            raise ApiError("bad_request", f"onConflict は {', '.join(ops.ON_CONFLICT)} のどれかにしてください")
        return value

    def create_route(kind: str):
        def handler():
            data = body()
            m = writable(data, "mkdir" if kind == "dir" else "touch")
            return ops.create(m.provider, path_field(data, "parent"), data.get("name"), kind).to_json()
        return handler

    app.post(f"{API}/mkdir", callback=api_route(mutation(notifying(create_route("dir")))))
    app.post(f"{API}/touch", callback=api_route(mutation(notifying(create_route("file")))))

    @app.post(f"{API}/rename")
    @api_route
    @mutation
    @notifying
    def api_rename():
        data = body()
        m = writable(data, "rename")
        path = path_field(data, "path")
        if not path:
            raise ApiError("bad_path", "マウントの根は名前を変えられません", "/")
        return m.provider.rename(path, vpath.check_name(data.get("newName"))).to_json()

    @app.post(f"{API}/delete")
    @api_route
    @mutation
    @notifying
    def api_delete():
        data = body()
        permanent = data.get("permanent", False)
        if not isinstance(permanent, bool):
            raise ApiError("bad_request", "permanent は true か false にしてください")
        m = writable(data, "delete" if permanent else "trash")
        p = m.provider
        paths = list_field(data, "paths", vpath.split)
        if permanent:
            return ops.bulk(paths, lambda s: p.delete(vpath.split(s)))
        return ops.bulk(paths, lambda s: {"trashId": p.trash(vpath.split(s)).id})

    def transfer_route(mode: str):
        def handler():
            data = body()
            dest = path_field(data, "dest")
            on_conflict = on_conflict_field(data)
            srcs = list_field(data, "srcs", vpath.split)
            dest_mid = data.get("destMount", data.get("mount"))
            if dest_mid == data.get("mount"):
                p = writable(data, mode).provider
                return ops.bulk(srcs, lambda s: ops.transfer_one(p, mode, s, dest, on_conflict))
            # マウントをまたぐ: 元は読めること（移動なら消せること）、先は書けること
            src_mid = data.get("mount")
            if mode == "move":
                src = writable_mount(src_mid, "delete")
            else:
                if not isinstance(src_mid, str) or access_of(src_mid) is None:
                    raise ApiError("not_found", "そのマウントはありません")
                src = mounts[src_mid]
            if "stream" not in src.provider.capabilities:
                raise ApiError("unsupported", "このマウントからは、ほかのマウントへ写せません")
            dst = writable_mount(dest_mid, "stream")
            return ops.bulk(srcs, lambda s: ops.transfer_across(src.provider, dst.provider, mode, s, dest,
                                                                on_conflict))
        return handler

    # destMount を省くか mount と同じなら同じマウントの中。違えばマウントをまたぐ（Phase 4）
    app.post(f"{API}/copy", callback=api_route(mutation(notifying(transfer_route("copy")))))
    app.post(f"{API}/move", callback=api_route(mutation(notifying(transfer_route("move")))))

    # --- ごみ箱 ---

    def check_id(value):
        if not isinstance(value, str):
            raise ApiError("bad_request", "ids は文字列の配列にしてください")

    @app.get(f"{API}/trash")
    @api_route
    def api_trash():
        mid = bottle.request.query.getunicode("mount")
        if mid is None or access_of(mid) is None:
            raise ApiError("not_found", "そのマウントはありません")
        p = mounts[mid].provider
        if "trash" not in p.capabilities:
            raise ApiError("unsupported", "このマウントにはごみ箱がありません")
        return {"items": [i.to_json() for i in p.list_trash()]}

    @app.post(f"{API}/trash/restore")
    @api_route
    @mutation
    @notifying
    def api_trash_restore():
        data = body()
        p = writable(data, "trash").provider
        on_conflict = on_conflict_field(data)
        ids = list_field(data, "ids", check_id)
        return ops.bulk(ids, lambda i: ops.restore_one(p, i, on_conflict), key="id")

    @app.post(f"{API}/trash/purge")
    @api_route
    @mutation
    @notifying
    def api_trash_purge():
        data = body()
        p = writable(data, "trash").provider
        return ops.bulk(list_field(data, "ids", check_id), p.purge, key="id")

    @app.post(f"{API}/trash/empty")
    @api_route
    @mutation
    @notifying
    def api_trash_empty():
        data = body()
        p = writable(data, "trash").provider
        return ops.bulk([i.id for i in p.list_trash()], p.purge, key="id")

    # --- 自動更新（Server-Sent Events） ---

    def watch_targets() -> list[dict]:
        """クエリ targets（JSON の配列 [{mount, path} | {mount, trash: true}]）を検査して返す。"""
        text = bottle.request.query.getunicode("targets")
        try:
            items = json.loads(text) if text is not None else None
        except ValueError:
            items = None
        if not isinstance(items, list) or not items:
            raise ApiError("bad_request", "targets は空でない JSON の配列にしてください")
        if len(items) > MAX_WATCH_TARGETS:
            raise ApiError("bad_request", f"一度に見張れるのは {MAX_WATCH_TARGETS} 個までです")
        result = []
        for t in items:
            if not isinstance(t, dict) or not isinstance(t.get("mount"), str):
                raise ApiError("bad_request", "targets の要素は {mount, path} か {mount, trash: true} にしてください")
            if t.get("trash") is True:
                result.append({"mount": t["mount"], "trash": True})
            else:
                result.append({"mount": t["mount"], "path": vpath.join(vpath.split(t.get("path")))})
        return result

    def os_path_of(t: dict) -> str | None:
        """見張る OS のパス。無い・見張れない・マウントの外なら None（その対象は自動更新しない）。"""
        m = mounts.get(t["mount"])
        if m is None or access_of(t["mount"]) is None:
            return None
        try:
            if t.get("trash"):
                return m.provider.watch_trash_path()
            return m.provider.watch_path(vpath.split(t["path"]))
        except ApiError:
            return None

    def sse(event: str, data) -> bytes:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()

    @app.get(f"{API}/events")
    def api_events():
        """見張っているフォルダが変わったら "change" を送る。画面はそのフォルダを読み直す。

        問い合わせの繰り返し（polling）はしない。接続は開いたままにし、HEARTBEAT 秒ごとに
        コメント行だけを送る（切れた接続を片付け、途中のプロキシに切られないように）。
        """
        try:
            targets = watch_targets()
        except ApiError as e:
            return json_response(e.to_json(), e.status)
        bottle.response.content_type = "text/event-stream; charset=utf-8"
        bottle.response.set_header("Cache-Control", "no-store")
        bottle.response.set_header("X-Accel-Buffering", "no")  # nginx などに溜めさせない
        if not live_updates:
            # 組み込む側が自動更新を止めた。画面は "unavailable" を受けたら繋ぎ直さない
            return [sse("unavailable", {"message": "自動更新は使えない設定です"})]
        # 仮想構造（OS のパスを持たないマウント）の対象は、変更の API のあとの知らせ（ChangeHub）で見張る
        virtual: dict[str, list[dict]] = {}
        on_disk = []
        for t in targets:
            m = mounts.get(t["mount"])
            if m is None or access_of(t["mount"]) is None:
                continue
            (virtual.setdefault(t["mount"], []) if is_virtual(m) else on_disk).append(t)
        w = get_watcher()
        if not w.available and not virtual:
            # 見張れない環境。画面は "unavailable" を受けたら繋ぎ直さない（繋ぎ直しの繰り返しにしない）
            return [sse("unavailable", {"message": "この環境ではフォルダの変化を見張れません"})]

        changed: queue.Queue = queue.Queue()
        unsubscribes = []
        watching = []
        for t in on_disk if w.available else []:
            p = os_path_of(t)
            unsub = w.subscribe(p, lambda t=t: changed.put(json.dumps(t, sort_keys=True))) if p else None
            if unsub:
                unsubscribes.append(unsub)
                watching.append(t)
        for mid, ts in virtual.items():
            watching.extend(ts)
        # ChangeHub は、仮想構造の変更の API のあとと、プロバイダの notify_changed（API の外での変化）で知らせる。
        # notify_changed は inotify で見張るプロバイダも呼べるので、見張っている対象はすべてマウントごとに購読する
        by_mount: dict[str, list[str]] = {}
        for t in watching:
            by_mount.setdefault(t["mount"], []).append(json.dumps(t, sort_keys=True))
        for mid, keys in by_mount.items():
            unsubscribes.append(hub.subscribe(mid, lambda keys=keys: [changed.put(k) for k in keys]))

        def stream():
            try:
                # retry: 切れたときにブラウザが繋ぎ直すまでの待ち（ミリ秒）
                yield b"retry: 3000\n\n" + sse("ready", {"watching": watching})
                while True:
                    try:
                        first = changed.get(timeout=heartbeat)
                    except queue.Empty:
                        yield b": ping\n\n"
                        continue
                    batch = {first}
                    while True:  # たまっている知らせは 1 回ずつにまとめる
                        try:
                            batch.add(changed.get_nowait())
                        except queue.Empty:
                            break
                    yield b"".join(sse("change", json.loads(t)) for t in sorted(batch))
            finally:
                for u in unsubscribes:
                    u()

        return stream()

    @app.route(f"{API}/<rest:path>", method=["GET", "POST", "PUT", "DELETE", "PATCH"])
    @api_route
    def api_unknown(rest):
        # bottle の既定の 404 は HTML なので、API ではエラーの形にそろえる
        raise ApiError("not_found", "その API はありません")

    # --- 画面 ---

    def static_response(filepath: str):
        """静的ファイル。使う前に毎回サーバへ確かめさせる（Cache-Control: no-cache）。

        付けないと、ブラウザは Last-Modified からの経過時間で「しばらくは新しい」と推測してキャッシュを使い、
        Chrome のふつうの再読み込みでは index.html だけを確かめ直して、JS は古いままになる
        （更新した画面が出ない・自動更新が動かない、が起きた）。ビルドで名前に版を付けていないので、
        毎回確かめさせる。変わっていなければ ETag / Last-Modified で 304 が返るだけなので軽い。
        """
        res = bottle.static_file(filepath, root=root)  # root の外を指すパス（..）は 403
        res.set_header("Cache-Control", "no-cache")
        return res

    @app.get("/")
    def index():
        return static_response("index.html")

    @app.get("/static/<filepath:path>")
    def static(filepath):
        return static_response(filepath)

    return app
