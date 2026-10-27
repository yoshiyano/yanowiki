"""bottle のアプリケーション。ルーティングと JSON の出し入れを受け持つ。

API の形は Wiki の「API 設計」を正とする。
"""

import functools
import json
import logging
import mimetypes
import queue
import threading
from urllib.parse import quote
from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path

import bottle

from . import ops, vpath
from .attributes import check_attributes
from .icons import check_icons
from .config import Config, ConfigError, MountConfig
from .errors import ApiError
from .builtin import BUILTIN_IDS, HANDLERS, USES_SOURCE, builtin_commands, size_text
from .commands import (AUTH_BITS, Command, CommandContext, CommandError, check_command, check_command_set,
                       check_effect_values, ANSWER_RE, ANSWER_VALUES, Modal)
from .jobs import Job, Jobs
from .providers import LocalProvider, MemoryProvider, Provider
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
    # このマウントのコマンドの宣言（既定・プロバイダ・設定を重ね、止めたものを外したもの）。読み書きできる人と、
    # 読み取りのみの人（readonly のマウント、mount_access が "ro"）で別に持つ。起動時に確かめ済み
    commands_rw: tuple[Command, ...] = ()
    commands_ro: tuple[Command, ...] = ()
    # ごみ箱の中のコマンド（読み書きできる人の宣言で数える）。1 つでも残っていればごみ箱を見せる。
    # 読み取り専用の人にも、ごみ箱の中は見せる（戻す・消すはできない。0.x と同じ）
    trash_commands: frozenset = frozenset()

    def commands_for(self, access: str) -> tuple[Command, ...]:
        return self.commands_ro if access == "ro" or self.config.readonly else self.commands_rw

    def to_json(self, access: str = "rw", commands=None, trash: bool = False) -> dict:
        readonly = self.config.readonly or access == "ro"
        return {
            "id": self.config.id,
            "label": self.config.label,
            "readonly": readonly,
            # 読み取り専用なら、プロバイダが持っていても変更系は申告しない。画面はツリーのごみ箱・マウントを
            # またげるかに使う（操作を出すかは commands で決まる）
            "capabilities": sorted([] if readonly else self.provider.capabilities),
            # 操作者ができる操作の宣言（Wiki「コマンドの宣言」）
            "commands": [c.to_json() for c in (self.commands_for(access) if commands is None else commands)],
            # ツリーにごみ箱を出すか（ごみ箱を持ち、ごみ箱の中のコマンドを止め切っていない）
            "trash": trash,
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
DELETE_ANSWER = "confirmDelete"  # 既定の削除の確認（サーバが出す はい・いいえ）の答えの名前
KNOWN_CAPABILITIES = frozenset({"mkdir", "touch", "rename", "delete", "copy", "move", "stream", "trash", "update_mtime",
                                "replace", "before_delete"})


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


def mount_commands(m: MountConfig, provider: Provider, readonly: bool) -> tuple[Command, ...]:
    """1 つのマウントのコマンドの宣言を組み立てて確かめる。

    重ねる順は「既定 → プロバイダの独自のコマンド → プロバイダの見せかたの変更 → 設定の見せかたの変更」、
    最後にプロバイダと設定で止めたものを外す。誤りは CommandError。
    """
    custom = list(provider.commands)
    for c in custom:
        check_command(c, builtin=False)
        if c.id in BUILTIN_IDS:
            raise CommandError(f"コマンド {c.id!r}: 既定のコマンドと同じ id は使えません")
    commands = {c.id: c for c in builtin_commands(provider.capabilities, readonly, m.samples)}
    commands.update({c.id: c for c in custom})
    known = BUILTIN_IDS | {c.id for c in custom}  # 止める・変えるに書いてよい id（今は宣言されていない既定も）

    def unknown_ids(ids, what):
        bad = sorted(set(ids) - known)
        if bad:
            raise CommandError(f"{what} に知らないコマンドがあります: {', '.join(bad)}")

    if not isinstance(provider.command_overrides, dict):
        raise CommandError("command_overrides は {id: {変える項目: 値}} にしてください")
    unknown_ids(provider.command_overrides, "command_overrides")
    for cid, changes in provider.command_overrides.items():
        if cid not in BUILTIN_IDS:
            raise CommandError(f"command_overrides: {cid!r} は既定のコマンドではありません（独自のコマンドは宣言を直す）")
        if cid in commands:
            commands[cid] = commands[cid].overridden(changes, f"command_overrides[{cid!r}]")
    unknown_ids(m.commands, "設定の commands")
    for cid, changes in m.commands.items():
        if cid in commands:
            commands[cid] = commands[cid].overridden(changes, f"設定の commands.{cid}")
    unknown_ids(provider.disable_commands, "disable_commands")
    unknown_ids(m.disable, "設定の disable")
    for cid in set(provider.disable_commands) | set(m.disable):
        commands.pop(cid, None)
    result = tuple(commands.values())
    for c in result:
        check_command(c, builtin=c.id in BUILTIN_IDS)  # 変えたあとの宣言も同じに確かめる（予約のキーなど）
    check_command_set(result)
    return result


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
        err = check_attributes(provider.attributes) or check_icons(provider.icons, provider.mount_icon)
        if err:
            raise ConfigError(f"{where}: {err}")
        try:
            commands_ro = mount_commands(m, provider, True)
            full = mount_commands(m, provider, False)  # 読み取り専用のマウントでも、ごみ箱を見せるかに使う
            commands_rw = commands_ro if m.readonly else full
        except CommandError as e:
            raise ConfigError(f"{where}: {e}") from None
        trash = frozenset(c.id for c in full if c.when.get("view") == "trash") if "trash" in provider.capabilities \
            else frozenset()
        mounts[m.id] = Mount(m, provider, commands_rw, commands_ro, trash)
    return mounts


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


def check_mutation_request(allowed_origins, content_type: str = "application/json") -> None:
    """変更系 API（POST）の要求が、このツールの画面か利用する側のシステムから来たものか確かめる。

    - X-WebFileDir: 1 と Content-Type（ふつうは application/json、アップロードは application/octet-stream）が
      無ければ拒否（フォームの送信では X-WebFileDir を付けられず、別サイトのページからは事前の確かめで止まる）
    - Origin があれば、自分自身か allowed_origins のどれかでなければ拒否（別サイトのページからの CSRF）
    - Origin が無い要求（ブラウザ以外のプログラムから）は通す。CSRF はブラウザでだけ起きるため
    """
    req = bottle.request
    if req.get_header("X-WebFileDir") != "1":
        raise ApiError("bad_request", "X-WebFileDir ヘッダがありません")
    ctype = (req.content_type or "").split(";")[0].strip().lower()
    if ctype != content_type:
        raise ApiError("bad_request", f"本文は {content_type} で送ってください")
    origin = req.get_header("Origin")
    if origin is None:
        return
    own = f"{req.urlparts.scheme}://{req.get_header('Host', '')}"
    if origin != own and origin not in allowed_origins:
        raise ApiError("bad_origin", "許されていないページからの要求です")


def mutation(func=None, *, content_type: str = "application/json"):
    """変更系 API に付ける（@api_route の内側に）。本文がファイルの中身なら content_type を変える。"""
    if func is None:
        return functools.partial(mutation, content_type=content_type)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # bottle のアプリに mount すると、ルートは組み込む側のアプリに合流し、request.app は組み込む側に
        # なる（設定が無い）。ルートを持っているアプリ（このアプリ）から読む
        config = bottle.request.route.app.config["webfiledir.config"]
        check_mutation_request(config.server.allowed_origins, content_type)
        return func(*args, **kwargs)

    return wrapper


class UploadBody:
    """アップロードの本文（wsgi.input）を、Content-Length の分だけ読ませるもの（プロバイダの write_file に渡す）。
    足りないまま終わったら（送る側が途中でやめた・切れた）例外を投げ、プロバイダに書きかけを消させる。"""

    def __init__(self, raw, length: int):
        self.raw = raw
        self.left = length

    def read(self, n: int = -1) -> bytes:
        if self.left <= 0:
            return b""
        n = self.left if n is None or n < 0 else min(n, self.left)
        data = self.raw.read(n)
        if not data:
            raise ApiError("bad_request", "送信が途中で切れました")
        self.left -= len(data)
        return data

    def drain(self) -> None:
        """読まなかった残りを読み捨てる（断ったときも、接続を次の要求に使えるように）。"""
        try:
            while self.read(1024 * 1024):
                pass
        except ApiError:
            pass


ACCESS_VALUES = ("rw", "ro", None)


def create_app(config: Config, static_dir: Path = STATIC_DIR, heartbeat: float = HEARTBEAT, *,
               authorize=None, mount_access=None, live_updates: bool = True,
               providers=None) -> bottle.Bottle:
    """webFileDir の WSGI アプリ（bottle）を作る。

    組み込む側のシステム（server/embed.py の mount_webfiledir など）が渡す引数:
      authorize(request)            … 要求ごとに呼ぶ。False を返すと 403。bottle.HTTPResponse を投げれば
                                      それを返す（ログイン画面へのリダイレクトなど）。画面・API・自動更新のすべてに効く
      mount_access(request, mount)  … マウントごとの許し。"rw"（読み書き）/ "ro"（読み取りのみ）/ None（見せない）か、
                                      {"access": "rw" | "ro", "disable": [コマンドの id…]}（その人には出さない
                                      コマンド。画面にも出ず、コマンド API も受け付けない）。
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

    def grant(mid: str) -> tuple:
        """このマウントへの、今の要求の許し (access, disable)。access は "rw" / "ro" / None（見せない）、
        disable はこの人には出さないコマンドの id。mount_access は "rw" / "ro" / None か、
        {"access": "rw" | "ro", "disable": [id…]} を返す（Wiki「サーバ側 > コマンドを止める」）。"""
        if mid not in mounts:
            return None, frozenset()
        access = "rw" if mount_access is None else mount_access(bottle.request, mid)
        disable = frozenset()
        if isinstance(access, dict):
            if set(access) - {"access", "disable"}:
                raise ValueError(f"mount_access の戻り値に知らない項目があります（{access!r}）")
            ids = access.get("disable", [])
            if not isinstance(ids, (list, tuple, set, frozenset)) or not all(isinstance(x, str) for x in ids):
                raise ValueError(f"mount_access の disable はコマンドの id の配列にしてください（{ids!r}）")
            unknown = set(ids) - BUILTIN_IDS - {c.id for c in mounts[mid].provider.commands}
            if unknown:
                raise ValueError(f"mount_access の disable に知らないコマンドがあります: {', '.join(sorted(unknown))}")
            disable, access = frozenset(ids), access.get("access", "rw")
        if access not in ACCESS_VALUES:
            raise ValueError(f"mount_access は rw / ro / None か {{access, disable}} を返してください（{access!r}）")
        if access == "rw" and mounts[mid].config.readonly:
            access = "ro"
        return access, disable

    def access_of(mid: str):
        """このマウントへの、今の要求の許し（"rw" / "ro" / None）。"""
        return grant(mid)[0]

    def trash_visible(mid: str) -> bool:
        """ごみ箱を見せるか: ごみ箱の中のコマンドが、止める設定（設定・プロバイダ・この人の disable）で
        すべて外されていないこと。読み取り専用の人にも見せる。"""
        access, disable = grant(mid)
        return access is not None and bool(mounts[mid].trash_commands - disable)

    def declared(mid: str) -> tuple[Command, ...]:
        """今の要求の人に宣言するコマンド（画面に渡すものと、コマンド API が受け付けるものは同じ）。"""
        access, disable = grant(mid)
        if access is None:
            return ()
        return tuple(c for c in mounts[mid].commands_for(access) if c.id not in disable)

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
        return [m.to_json(a, declared(m.config.id), trash_visible(m.config.id)) for m in mounts.values()
                if (a := access_of(m.config.id)) is not None]

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

    # --- 中身 ---

    def raw_url(mid: str, path: tuple[str, ...], mode: str | None = None) -> str:
        """中身の URL（/api/v1/raw/<マウント>/<パス>）。画面（index.html）からの相対。
        見せかたは ?mode= で切り替える（省けば表示。download なら保存として）。

        ほかの API と違い、マウントとパスを URL のパス部分に埋め込む（2026-09-28 設計者の指示）。ブラウザの
        タブ・保存の名前がファイル名になり、HTML の中の相対リンクもパスとして解決される。名前は 1 段ずつ
        パーセント符号化するので、# ? % 空白も読み違えない（名前に / は入らないので段の区切りと混ざらない）。
        """
        segments = "/".join(quote(s, safe="") for s in (mid, *path))
        return f"api/v1/raw/{segments}" + (f"?mode={quote(mode, safe='')}" if mode else "")

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

    def make_env(access, touch):
        """既定のコマンドの処理（server/builtin.py）に渡すもの。access(mid) はマウントへの許し、touch(mid) は
        変えたマウントの記録。要求の中では今の要求から決め、ジョブの中では始める前に固めた値を使う
        （ジョブのスレッドには要求が無い）。"""

        def readable(mid) -> Mount:
            if not isinstance(mid, str) or mid not in mounts or access(mid) is None:
                raise ApiError("not_found", "そのマウントはありません")
            return mounts[mid]

        def writable(mid, capability: str) -> Mount:
            m = readable(mid)
            if access(mid) == "ro":
                raise ApiError("forbidden", "読み取り専用のマウントです")
            if capability not in m.provider.capabilities:
                raise ApiError("unsupported", "このマウントではできない操作です")
            touch(mid)
            return m

        return SimpleNamespace(mount=readable, writable=writable, raw_url=raw_url)

    env = make_env(access_of, touched)
    readable_mount, writable_mount = env.mount, env.writable
    jobs = Jobs()  # 裏で行っているコマンド（server/jobs.py）

    # --- コマンド API（Wiki「API 設計 > コマンド API」） ---

    def paths_field(value, name: str) -> list[tuple[str, ...]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ApiError("bad_request", f"{name} はパスの配列にしてください")
        if len(value) > MAX_BULK:
            raise ApiError("bad_request", f"一度に扱えるのは {MAX_BULK} 個までです")
        # 1 つでも形のおかしいパスがあれば、何もせずに要求ごと bad_path（項目ごとの失敗にしない）
        return [vpath.split(x) for x in value]

    def command_context(data: dict, mid: str, cmd: Command) -> CommandContext:
        """本文を検査して CommandContext にする。形の誤りは bad_request / bad_path。"""
        unknown = set(data) - {"mount", "dir", "paths", "ids", "input", "source", "dest", "answers"}
        if unknown:
            raise ApiError("bad_request", f"本文に知らない項目があります: {', '.join(sorted(unknown))}")
        ctx = CommandContext(mount=mid, readonly=access_of(mid) == "ro")
        if data.get("dir") is not None:
            ctx.dir = vpath.split(data["dir"])
        ctx.paths = paths_field(data.get("paths"), "paths")
        ids = data.get("ids") or []
        if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids) or len(ids) > MAX_BULK:
            raise ApiError("bad_request", "ids は文字列の配列にしてください")
        ctx.ids = ids
        if data.get("input") is not None and not isinstance(data["input"], str):
            raise ApiError("bad_request", "input は文字列にしてください")
        ctx.input = data.get("input")
        if data.get("source") is not None:
            src = data["source"]
            if not isinstance(src, dict) or set(src) - {"mount", "paths", "mode"} \
                    or src.get("mode", "copy") not in ("copy", "cut"):
                raise ApiError("bad_request", "source は {mount, paths, mode: copy | cut} にしてください")
            readable_mount(src.get("mount"))
            ctx.source = {"mount": src["mount"], "paths": paths_field(src.get("paths"), "source.paths"),
                          "mode": src.get("mode", "copy")}
        if data.get("dest") is not None:
            dest = data["dest"]
            if not isinstance(dest, dict) or set(dest) - {"mount", "path"}:
                raise ApiError("bad_request", "dest は {mount, path} にしてください")
            readable_mount(dest.get("mount"))
            ctx.dest = {"mount": dest["mount"], "path": vpath.split(dest.get("path"))}
        answers = data.get("answers") or {}
        # onConflict（名前の衝突の答え）と、状態表示のダイアログの「はい・いいえ」の答え（名前: "yes" | "no"）
        if not isinstance(answers, dict) or answers.get("onConflict", "error") not in ops.ON_CONFLICT or not all(
                k == "onConflict" or (isinstance(k, str) and ANSWER_RE.fullmatch(k) and v in ANSWER_VALUES)
                for k, v in answers.items()):
            raise ApiError("bad_request", f"answers は {{onConflict: {' | '.join(ops.ON_CONFLICT)}, "
                                          "<答えの名前>: yes | no}} にしてください")
        ctx.answers = answers
        # コマンドごとに要るもの
        if cmd.id in USES_SOURCE and (ctx.source is None or ctx.dest is None or not ctx.source["paths"]):
            raise ApiError("bad_request", "このコマンドには source（運ぶ項目）と dest（先）が要ります")
        if cmd.id in ("new-folder", "new-file") and ctx.dir is None:
            raise ApiError("bad_request", "このコマンドには dir（今いるフォルダ）が要ります")
        return ctx

    auth_denied = {"move": "動かす権限がありません", "read": "読む権限がありません",
                   "write": "書く権限がありません", "exec": "実行する権限がありません"}

    def check_when(cmd: Command, ctx: CommandContext) -> list[dict]:
        """宣言の when をサーバでも確かめる（画面の判断を信じない）。満たさなければ forbidden。
        partial のコマンドで権限の無い項目は、外して一括の結果の失敗として返す（2026-09-29 設計者の指示
        「権限のないものだけ失敗させる形に」を、サーバでも守る）。"""
        when = cmd.when
        view = when.get("view", "folder")
        if (view == "trash" and ctx.paths) or (view == "folder" and ctx.ids):
            raise ApiError("bad_request", "ごみ箱の中の項目は ids、フォルダの中の項目は paths で指してください")
        uses_source = cmd.id in USES_SOURCE
        # 数・種類・開けないリンクは、選んだ項目（paths。「このフォルダに貼り付け」ならそのフォルダ）で確かめる
        count = len(ctx.ids) if view == "trash" else len(ctx.paths)
        select = when.get("select", "any")
        if (select == "none" and count) or (select == "one" and count != 1) or (select == "some" and not count):
            raise ApiError("forbidden", "選んだ項目の数が、このコマンドに合いません")
        if view != "trash" and ("kinds" in when or when.get("reachable")):
            provider = mounts[ctx.mount].provider
            kinds = when.get("kinds", ["file", "dir"])
            for path in ctx.paths:
                entry = provider.stat(path)
                if entry.kind not in kinds:
                    raise ApiError("forbidden", "この種類の項目には使えないコマンドです", vpath.join(path))
                if when.get("reachable") and entry.extra.get("unreachable"):
                    raise ApiError("forbidden", "開けない項目です", vpath.join(path))
        # 項目の権限は、運ぶコマンド（貼り付け・ドロップ）なら運ぶ項目（source）で、ほかは選んだ項目で確かめる
        denied = []
        if view != "trash" and "items" in when:
            item_mount = ctx.source["mount"] if uses_source else ctx.mount
            items = ctx.source["paths"] if uses_source else ctx.paths
            provider = mounts[item_mount].provider
            auth = when["items"]["auth"]
            partial = when["items"].get("partial", False)
            kept = []
            for path in items:
                try:
                    entry = provider.stat(path)
                except ApiError as e:
                    if not partial:
                        raise
                    # 無くなった項目など。1 つずつのコマンドでは、その項目だけの失敗にする（0.x と同じ）
                    denied.append({"src": vpath.join(path), "ok": False, **e.to_json()})
                    continue
                if not entry.auth & AUTH_BITS[auth]:
                    if not partial:
                        name = path[-1] if path else "/"
                        raise ApiError("forbidden", f"「{name}」の{auth_denied[auth]}", vpath.join(path))
                    denied.append({"src": vpath.join(path), "ok": False,
                                   **ApiError("forbidden", auth_denied[auth], vpath.join(path)).to_json()})
                    continue
                kept.append(path)
            if uses_source:
                ctx.source["paths"] = kept
            else:
                ctx.paths = kept
        for key, place in (("dir", (ctx.mount, ctx.dir)),
                           ("dest", (ctx.dest["mount"], ctx.dest["path"]) if ctx.dest else None)):
            need = when.get(key)
            if need is None:
                continue
            if place is None or place[1] is None:
                raise ApiError("bad_request", f"このコマンドには {key} が要ります")
            entry = mounts[place[0]].provider.stat(place[1])
            if entry.kind != "dir" or not entry.auth & AUTH_BITS[need["auth"]]:
                raise ApiError("forbidden", f"その場所に{auth_denied[need['auth']]}", vpath.join(place[1]))
        return denied

    def checked_effects(effects, cid: str, access=None) -> list[dict]:
        """プロバイダの run_command が返した語彙を確かめる（誤りはプロバイダの不具合なので internal になる）。
        access はマウントへの許し（ジョブの中では始める前に固めた値。省けば今の要求から）。"""
        access = access or access_of
        effects = list(effects or [])
        check_effect_values(effects, f"コマンド {cid!r} の応答")
        for e in effects:
            if e["do"] == "browse":
                # 表示させるのは、この要求を出した人が使えるマウントの、あるフォルダだけ
                if e["mount"] not in mounts or access(e["mount"]) is None:
                    raise ValueError(f"browse の mount がありません（使えません）: {e!r}")
                try:
                    parts = vpath.split(e["path"])
                except ApiError:
                    raise ValueError(f"browse の path が正しい形（/a/b）ではありません: {e!r}") from None
                # 無くなっていれば stat が not_found を返す（そのまま画面へ知らせる）
                if mounts[e["mount"]].provider.stat(parts).kind != "dir":
                    raise ValueError(f"browse の path はフォルダを指してください: {e!r}")
        json.dumps(effects)  # JSON にできなければ例外
        return effects

    def ask_before_delete(cid: str, mid: str, ctx: CommandContext) -> dict | None:
        """既定の削除（delete・purge）の前に、プロバイダが問い返す（capabilities の before_delete）。
        問い返す・取りやめるなら、そのまま返す応答（削除はしない）。そのまま削除してよければ None。"""
        provider = mounts[mid].provider
        if cid not in ("delete", "purge") or "before_delete" not in provider.capabilities:
            return None
        verdict = provider.before_delete(list(ctx.paths), dict(ctx.answers))
        if verdict is True:
            return None
        if verdict is None:
            # 問い返さないとき、完全に削除するなら（宣言から confirm を外してあるので）サーバが確かめる
            if cid == "delete" and "trash" in provider.capabilities:
                return None
            answer = ctx.answers.get(DELETE_ANSWER)
            if answer == "yes":
                return None
            if answer is None:
                names = [p[-1] for p in ctx.paths]
                what = f"「{names[0]}」" if len(names) == 1 else f"{len(names)} 個の項目"
                return {"effects": [Modal("完全に削除",
                                          f"{what}を完全に削除しますか？\nこの操作は元に戻せません。フォルダは中身ごと消えます。",
                                          type="yesno", answer=DELETE_ANSWER, default="no")]}
            return {"effects": []}
        if verdict is False or verdict == []:
            return {"effects": []}
        return {"effects": checked_effects(verdict, cid)}

    @app.post(f"{API}/commands/<cid>")
    @api_route
    @mutation
    @notifying
    def api_command(cid: str):
        """コマンドを 1 つ行う。画面の変更の操作・開く・独自のコマンドは、すべてここを通る（C1 案 B）。
        変更ではない開くも、プロバイダの処理が何かを起こしうるので、POST と X-WebFileDir・Origin の確かめを通す。"""
        data = body()
        mid = data.get("mount")
        readable_mount(mid)
        cmd = next((c for c in declared(mid) if c.id == cid), None)
        if cmd is None:
            # 宣言していない（止めた・読み取り専用・capabilities に無い）コマンドは、直接呼んでも通さない
            raise ApiError("forbidden", "このマウントでは使えないコマンドです")
        if cmd.request != "server":
            raise ApiError("bad_request", "このコマンドはサーバに送るものではありません")
        ctx = command_context(data, mid, cmd)
        denied = check_when(cmd, ctx)
        left = ctx.source["paths"] if cid in USES_SOURCE else ctx.paths
        if denied and not left:
            # 全部の項目が失敗（権限が無い・無くなった）。要求そのものは正しいので、一括の結果で返す（0.x と同じ）
            return {"results": denied}
        asked = ask_before_delete(cid, mid, ctx)
        if asked is not None:
            return asked
        if cmd.job:
            return {"job": start_job(cid, mid, ctx, denied).id}
        if cid in BUILTIN_IDS:
            res = HANDLERS[cid](ctx, env)
        else:
            touched(mid)  # 独自のコマンドは何を変えるか分からないので、変えたものとして知らせる
            res = {"effects": checked_effects(mounts[mid].provider.run_command(cid, ctx), cid)}
        if denied:
            res["results"] = res.get("results", []) + denied
        return res

    def query_text(name: str, required: bool = True) -> str | None:
        q = bottle.request.query
        if name not in q:
            if required:
                raise ApiError("bad_request", f"{name} がありません")
            return None
        value = q.getunicode(name)
        if value is None:
            raise ApiError("bad_request", f"{name} を UTF-8 として読めません")
        return value

    @app.post(f"{API}/commands/<cid>/upload")
    @api_route
    @mutation(content_type="application/octet-stream")
    @notifying
    def api_upload(cid: str):
        """ファイルを送るコマンド（宣言の request が upload）で、手元のファイル 1 つかフォルダ 1 つを置く。
        クエリ: mount・dest（置く先のフォルダ）・path（dest からの相対の名前の並び "a/b.txt"。親は先に作っておく）・
        kind（file | dir）・mtime（元の更新日時。秒。省けば今）・onConflict・check（1 なら確かめるだけ）。本文はファイルの中身。"""
        config = bottle.request.route.app.config["webfiledir.config"].server
        environ = bottle.request.environ
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = -1
        body = UploadBody(environ["wsgi.input"], max(length, 0))
        try:
            if length < 0:
                raise ApiError("bad_request", "Content-Length が正しくありません")
            mid = query_text("mount")
            readable_mount(mid)
            cmd = next((c for c in declared(mid) if c.id == cid), None)
            if cmd is None:
                raise ApiError("forbidden", "このマウントでは使えないコマンドです")
            if cmd.request != "upload":
                raise ApiError("bad_request", "このコマンドはファイルを送るものではありません")
            dest = vpath.split(query_text("dest"))
            rel = tuple(query_text("path").split("/"))
            for name in rel:
                vpath.check_name(name)
            kind = query_text("kind")
            if kind not in ("file", "dir"):
                raise ApiError("bad_request", "kind は file か dir にしてください")
            on_conflict = query_text("onConflict", False) or "error"
            if on_conflict not in ops.ON_CONFLICT:
                raise ApiError("bad_request", f"onConflict は {' | '.join(ops.ON_CONFLICT)} のどれかです")
            check_only = query_text("check", False) == "1"
            mtime = query_text("mtime", False)
            if mtime is not None:
                try:
                    mtime = float(mtime)
                except ValueError:
                    mtime = -1.0
                if not 0 <= mtime < 1e11:  # NaN もここで断る
                    raise ApiError("bad_request", "mtime は UNIX 時刻（秒）にしてください")
            # 確かめるだけの要求は、送るつもりの大きさを size に書く
            size = length
            if check_only:
                try:
                    size = int(query_text("size", False) or 0)
                except ValueError:
                    raise ApiError("bad_request", "size は整数（バイト）にしてください") from None
            if kind == "dir" and length:
                raise ApiError("bad_request", "フォルダには本文を付けません")
            if kind == "file" and config.max_upload_size is not None and size > config.max_upload_size:
                raise ApiError("too_large", f"ファイルが大きすぎます（上限は {size_text(config.max_upload_size)}）",
                               vpath.join(dest + rel))
            # 宣言の when（置く先に書けるか）を、コマンド API と同じに確かめる
            ctx = CommandContext(mount=mid, readonly=access_of(mid) == "ro", dest={"mount": mid, "path": dest})
            check_when(cmd, ctx)
            provider = (readable_mount(mid) if check_only else writable_mount(mid, "stream")).provider
            parent = dest + rel[:-1]
            if rel[:-1]:
                # フォルダごとのとき、中の段は同じアップロードで作ったもの。書けるフォルダであること
                entry = provider.stat(parent)
                if entry.kind != "dir" or not entry.auth & AUTH_BITS["write"]:
                    raise ApiError("forbidden", "その場所に書く権限がありません", vpath.join(parent))
            return ops.upload_one(provider, parent, rel[-1], kind, body, mtime, on_conflict,
                                  config.upload_deny_exts, check_only)
        finally:
            body.drain()

    def start_job(cid: str, mid: str, ctx: CommandContext, denied: list) -> Job:
        """コマンドを裏で行う。許しは今（要求の中で）固め、変えた仮想構造のマウントは終わったときに知らせる。"""
        granted = {m: access_of(m) for m in mounts}
        changed: set[str] = set()
        job_env = make_env(granted.get, changed.add)

        def work() -> dict:
            if cid in BUILTIN_IDS:
                res = HANDLERS[cid](ctx, job_env)
            else:
                changed.add(mid)
                res = {"effects": checked_effects(mounts[mid].provider.run_command(cid, ctx), cid, granted.get)}
            if denied:
                res["results"] = res.get("results", []) + denied
            return res

        def finish() -> None:
            for m in changed:
                if is_virtual(mounts[m]):
                    hub.publish(m)

        return jobs.start(mid, work, finish)

    # --- ジョブ（裏で行っているコマンド）の進み具合と中止 ---

    def own_job(jid: str) -> Job:
        """今の要求の人が見てよいジョブ（始めたマウントを使える人）。"""
        job = jobs.get(jid)
        if job is None or access_of(job.mount) is None:
            raise ApiError("not_found", "そのジョブはありません")
        return job

    @app.get(f"{API}/jobs/<jid>")
    @api_route
    def api_job(jid: str):
        """進み具合 {state, done, total, item, cancelled}。終わったら result（コマンド API の応答と同じ形）か error。"""
        return own_job(jid).to_json()

    @app.post(f"{API}/jobs/<jid>/cancel")
    @api_route
    @mutation
    def api_job_cancel(jid: str):
        """中止する。項目と項目の間で止まり、行わなかった項目は cancelled の失敗になる。"""
        own_job(jid).cancel()
        return {"ok": True}

    # --- ごみ箱の一覧 ---

    @app.get(f"{API}/trash")
    @api_route
    def api_trash():
        mid = bottle.request.query.getunicode("mount")
        if mid is None or access_of(mid) is None:
            raise ApiError("not_found", "そのマウントはありません")
        p = mounts[mid].provider
        if "trash" not in p.capabilities:
            raise ApiError("unsupported", "このマウントにはごみ箱がありません")
        # ごみ箱の中のコマンドを 1 つも宣言していなければ、ごみ箱は見せない（ツリーにも出ない）
        if not trash_visible(mid):
            raise ApiError("forbidden", "このマウントのごみ箱は使えません")
        return {"items": [i.to_json() for i in p.list_trash()]}

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
