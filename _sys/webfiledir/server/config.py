"""設定ファイル（TOML）の読み込みと、マウントの根の準備。

設定の形は Wiki の「設計の全体像 > 設定」を正とする。
"""

import os
import re
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# 組み込みのプロバイダの種類。local … 実ファイル（root が要る）/ memory … メモリ上の仮想構造（root は要らない）
# これ以外の種類は、利用する側が create_app(providers=...) で差し込む（Wiki「プロバイダの作りかた」）。
# 種類が実在するかは、プロバイダを組み立てるとき（server/app.py の build_mounts）に確かめる
BUILTIN_PROVIDER_TYPES = frozenset({"local", "memory"})
MOUNT_COMMON_KEYS = frozenset({"id", "type", "readonly", "label"})
DEFAULT_LABEL = "(root)"  # label を書かないマウントの表示名

# マウント名は URL のハッシュ（#/<mount>/...）と API の引数に載るので、使える文字を限る
MOUNT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

TRASH_DIRNAME = ".fdweb-trash"


class ConfigError(Exception):
    """設定の誤り、またはマウントの根が安全に使えないこと。起動を止める。"""


@dataclass(frozen=True)
class MountConfig:
    id: str
    type: str
    root: Path | None  # type = "local" のときだけ。memory は None
    readonly: bool = False
    trash: Path | None = None  # None なら根の直下の .fdweb-trash
    label: str = ""
    # 差し込んだ種類に固有の設定（共通の項目以外すべて）。組み込みの種類では空。検査はプロバイダを作る関数が行う
    options: dict = field(default_factory=dict)

    @property
    def trash_dir(self) -> Path:
        return self.trash if self.trash is not None else self.root / TRASH_DIRNAME


@dataclass(frozen=True)
class ServerConfig:
    # 書き忘れたときは外から届かない側にしておく。LAN に開くときは設定に明示する
    host: str = "127.0.0.1"
    port: int = 8616
    allowed_origins: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    server: ServerConfig
    mounts: tuple[MountConfig, ...]


def load_config(path: str | os.PathLike) -> Config:
    """TOML ファイルを読んで Config にする。誤りは ConfigError にする。"""
    path = Path(path)
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"設定ファイルがありません: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"設定ファイルを TOML として読めません: {path}: {e}") from None
    return parse_config(data)


def parse_config(data: dict) -> Config:
    # 打ち間違い（[mounts] など）を黙って無視すると、意図と違う設定のまま起動してしまう
    _reject_unknown(data, {"server", "mount"}, "設定ファイル")
    server = _parse_server(data.get("server", {}))
    raw_mounts = data.get("mount", [])
    if not isinstance(raw_mounts, list) or not raw_mounts:
        raise ConfigError("[[mount]] が 1 つもありません")
    mounts = tuple(_parse_mount(m, i) for i, m in enumerate(raw_mounts))
    ids = [m.id for m in mounts]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ConfigError(f"マウントの id が重複しています: {', '.join(dup)}")
    return Config(server=server, mounts=mounts)


def _parse_server(s) -> ServerConfig:
    if not isinstance(s, dict):
        raise ConfigError("[server] は表（テーブル）で書いてください")
    _reject_unknown(s, {"host", "port", "allowed_origins"}, "[server]")
    host = s.get("host", ServerConfig.host)
    port = s.get("port", ServerConfig.port)
    origins = s.get("allowed_origins", [])
    if not isinstance(host, str) or not host:
        raise ConfigError("[server] host は空でない文字列にしてください")
    # bool は int の一種なので先に除く
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigError("[server] port は 1〜65535 の整数にしてください")
    if not isinstance(origins, list) or not all(isinstance(o, str) for o in origins):
        raise ConfigError("[server] allowed_origins は文字列の配列にしてください")
    return ServerConfig(host=host, port=port, allowed_origins=tuple(origins))


def _parse_mount(m, index: int) -> MountConfig:
    where = f"[[mount]] の {index + 1} 番目"
    if not isinstance(m, dict):
        raise ConfigError(f"{where} は表（テーブル）で書いてください")

    mid = m.get("id")
    if not isinstance(mid, str) or not MOUNT_ID_RE.match(mid):
        raise ConfigError(f"{where}: id は英数字・_・- の 1〜64 文字にしてください")
    where = f"マウント {mid}"

    mtype = m.get("type")
    if not isinstance(mtype, str) or not mtype:
        raise ConfigError(f"{where}: type を書いてください")

    options = {}
    if mtype not in BUILTIN_PROVIDER_TYPES:
        # 差し込んだ種類。共通の項目以外はそのまま渡す（その種類にとって正しいかは、ここでは分からない）
        options = {k: v for k, v in m.items() if k not in MOUNT_COMMON_KEYS}
        root = trash = None
    else:
        _reject_unknown(m, MOUNT_COMMON_KEYS | {"root", "trash"}, where)
        if mtype == "local":
            root = _abs_path(m.get("root"), f"{where}: root")
            trash = m.get("trash")
            trash = None if trash is None else _abs_path(trash, f"{where}: trash")
        else:
            # 実フォルダを持たないプロバイダ。root・trash を書いていたら誤りとして知らせる（効かない設定を黙って受けない）
            for key in ("root", "trash"):
                if key in m:
                    raise ConfigError(f"{where}: type = \"{mtype}\" には {key} を書けません")
            root = trash = None

    readonly = m.get("readonly", False)
    if not isinstance(readonly, bool):
        raise ConfigError(f"{where}: readonly は true か false にしてください")
    # 画面に出す名前。id は URL・API の識別子で、画面の表示には使わない（書かなければ "(root)"）
    label = m.get("label", DEFAULT_LABEL)
    if not isinstance(label, str):
        raise ConfigError(f"{where}: label は文字列にしてください")

    return MountConfig(id=mid, type=mtype, root=root, readonly=readonly, trash=trash, label=label,
                       options=options)


def _abs_path(value, what: str) -> Path:
    # 相対パスは起動したフォルダによって指す場所が変わるので受け付けない
    if not isinstance(value, str) or not os.path.isabs(value):
        raise ConfigError(f"{what} は絶対パスで書いてください")
    return Path(os.path.normpath(value))


def _reject_unknown(d: dict, known: set[str], where: str) -> None:
    unknown = set(d) - known
    if unknown:
        raise ConfigError(f"{where} に知らない設定があります: {', '.join(sorted(unknown))}")


def prepare_root(root: Path) -> None:
    """マウントの根を用意する。無ければ 0700 で作り、あれば安全に使えるか確かめる。

    /tmp は誰でも書けるので、他のアカウントが先に同じ名前のフォルダや
    シンボリックリンクを置いていることがある。その場合は起動しない。
    """
    try:
        # 「無いことを確かめてから作る」だと、その間に他人に作られうる。先に作ってみる。
        # umask は権限を削るだけなので、0700 より広がることはない
        os.mkdir(root, 0o700)
        return
    except FileExistsError:
        pass
    except FileNotFoundError:
        raise ConfigError(f"根の親フォルダがありません: {root.parent}") from None
    except PermissionError:
        raise ConfigError(f"根を作る権限がありません: {root}") from None

    st = os.lstat(root)  # シンボリックリンクを辿らずに調べる
    if stat.S_ISLNK(st.st_mode):
        raise ConfigError(f"根がシンボリックリンクです（辿った先を根にしません）: {root}")
    if not stat.S_ISDIR(st.st_mode):
        raise ConfigError(f"根がフォルダではありません: {root}")
    if st.st_uid != os.geteuid():
        raise ConfigError(
            f"根の持ち主がこのサーバを動かすアカウントではありません（uid {st.st_uid}）: {root}"
        )


def prepare_mounts(config: Config) -> None:
    """すべてのマウントの根を用意する。1 つでも使えなければ ConfigError。"""
    for m in config.mounts:
        if m.root is not None:  # 実フォルダを持たないプロバイダ（memory）は用意するものが無い
            prepare_root(m.root)
