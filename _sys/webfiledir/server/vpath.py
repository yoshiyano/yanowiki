"""API で使うパス（`/a/b/c.txt` 形式）の検査と分解。

規則は Wiki の「設計の全体像 > パスの扱い」を正とする。
**おかしなパスは直さずに拒否する。**黙って正規化すると、想定外の場所を指したまま操作が通るため。
"""

from .errors import ApiError

MAX_PATH = 4096


def split(path) -> tuple[str, ...]:
    """パスを要素の組にする。根（"/"）は空の組。規則に反すれば ApiError("bad_path")。"""
    if not isinstance(path, str) or not path.startswith("/"):
        raise ApiError("bad_path", "パスは / で始めてください", _shown(path))
    if len(path) > MAX_PATH:
        raise ApiError("bad_path", "パスが長すぎます", None)
    if path == "/":
        return ()
    parts = tuple(path[1:].split("/"))
    for p in parts:
        # 空の要素は "//" や末尾の "/" から生じる
        if p in ("", ".", "..") or "\0" in p:
            raise ApiError("bad_path", "パスに使えない要素（空・.・..・NUL）があります", _shown(path))
    return parts


def join(parts) -> str:
    return "/" + "/".join(parts)


def check_name(name) -> str:
    """1 つの名前（パスの要素）として使えるか確かめる。"""
    if not isinstance(name, str) or name in ("", ".", "..") or "/" in name or "\0" in name:
        raise ApiError("bad_name", "名前に使えない文字（/・NUL）か、使えない名前（空・.・..）です",
                       None)
    return name


def _shown(path):
    # NUL などを含むパスをそのまま JSON に返しても害は無いが、長すぎるものは載せない
    return path if isinstance(path, str) and len(path) <= MAX_PATH else None
