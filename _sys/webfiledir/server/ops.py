"""プロバイダ共通の処理: 既定の名前の番号付け、一括処理、名前の衝突の扱い。

プロバイダには 1 件ずつの操作だけを持たせ、ここで組み合わせる（Wiki「設計の全体像 > プロバイダ」）。
一括処理は **1 件の失敗で全体を止めず、やり直しもしない**（Wiki「API 設計 > 一括の結果」）。
"""

from . import vpath
from .errors import ApiError
from .providers import Provider

DEFAULT_FOLDER = "新しいフォルダ"
DEFAULT_FILE = "新しいテキスト ドキュメント.txt"
MAX_NUMBER = 10000

ON_CONFLICT = ("error", "rename", "skip", "overwrite")


def split_ext(name: str) -> tuple[str, str]:
    """拡張子の手前と拡張子（"." を含まない）。規則は画面の filetypes.js の splitExt と同じ。"""
    lead = len(name) - len(name.lstrip("."))
    i = name.rfind(".")
    if i < lead or i == len(name) - 1:
        return name, ""
    return name[:i], name[i + 1:]


def numbered(name: str, n: int, is_dir: bool) -> str:
    """n 番目の別名。1 ならそのまま、2 以降は「名前 (2).txt」（フォルダは拡張子を持たない）。"""
    if n == 1:
        return name
    if is_dir:
        return f"{name} ({n})"
    stem, ext = split_ext(name)
    return f"{stem} ({n}).{ext}" if ext else f"{name} ({n})"


def free_name(provider: Provider, parent: tuple[str, ...], name: str, is_dir: bool) -> str:
    """parent の中で使われていない名前（name、name (2)、name (3) …）。"""
    for n in range(1, MAX_NUMBER + 1):
        candidate = numbered(name, n, is_dir)
        if not provider.exists(parent + (candidate,)):
            return candidate
    raise ApiError("exists", "空いている名前が見つかりません", vpath.join(parent + (name,)))


def create(provider: Provider, parent: tuple[str, ...], name, kind: str):
    """新しいフォルダ・空ファイル。名前が空なら既定の名前に番号を付ける（エクスプローラーと同じ）。"""
    is_dir = kind == "dir"
    if name in (None, ""):
        name = free_name(provider, parent, DEFAULT_FOLDER if is_dir else DEFAULT_FILE, is_dir)
    else:
        vpath.check_name(name)
    return provider.mkdir(parent, name) if is_dir else provider.create_file(parent, name)


def bulk(items, func, key: str = "src") -> dict:
    """items の 1 つずつに func を行い、項目ごとの結果を返す。func は結果に足す dict を返す。"""
    results = []
    for item in items:
        try:
            extra = func(item) or {}
            results.append({key: item, "ok": True, **extra})
        except ApiError as e:
            results.append({key: item, "ok": False, **e.to_json()})
    return {"results": results}


def restore_one(provider: Provider, trash_id: str, on_conflict: str) -> dict:
    """ごみ箱から 1 つ戻す。元の場所に同じ名前があれば on_conflict に従う。"""
    try:
        return {"entry": provider.restore(trash_id).to_json()}
    except ApiError as e:
        if e.code != "exists" or on_conflict == "error":
            raise
    item = provider.trash_item(trash_id)
    parts = vpath.split(item.original_path)
    parent, name = parts[:-1], parts[-1]
    is_dir = item.entry.kind == "dir"
    if on_conflict == "skip":
        return {"skipped": True}
    if on_conflict == "rename":
        new_name = free_name(provider, parent, name, is_dir)
        return {"entry": provider.restore(trash_id, new_name).to_json()}
    # overwrite: ファイル同士だけ。置き換えられるほうは消さずにごみ箱へ移す（戻せるように）
    if is_dir or _kind(provider, parts) == "dir":
        raise ApiError("exists", "フォルダは置き換えられません", item.original_path)
    _set_aside(provider, parts)
    return {"entry": provider.restore(trash_id).to_json()}


def copy_name(provider: Provider, parent: tuple[str, ...], name: str, is_dir: bool) -> str:
    """同じフォルダへのコピーの名前: 「名前 - コピー.txt」、「名前 - コピー (2).txt」…（エクスプローラーと同じ）。"""
    if is_dir:
        base = f"{name} - コピー"
    else:
        stem, ext = split_ext(name)
        base = f"{stem} - コピー.{ext}" if ext else f"{name} - コピー"
    return free_name(provider, parent, base, is_dir)


def _kind(provider: Provider, path: tuple[str, ...]) -> str:
    """種類。開けないリンク（壊れた・外を指す）はファイルと同じに扱う。"""
    try:
        return provider.stat(path).kind
    except ApiError as e:
        if e.code not in ("not_found", "forbidden"):
            raise
        return "file"


def _set_aside(provider: Provider, path: tuple[str, ...]) -> None:
    """置き換えられる項目を片付ける。消さずにごみ箱へ（戻せるように）。ごみ箱が無ければ完全に削除。"""
    if "trash" in provider.capabilities:
        provider.trash(path)
    else:
        provider.delete(path)


def transfer_one(provider: Provider, mode: str, src_text: str, dest: tuple[str, ...], on_conflict: str) -> dict:
    """1 つをコピー（mode="copy"）か移動（mode="move"）する。名前の衝突は on_conflict に従う。"""
    src = vpath.split(src_text)
    if not src:
        raise ApiError("bad_path", "マウントの根はコピー・移動できません", "/")
    op = provider.copy if mode == "copy" else provider.move
    name = src[-1]
    is_dir = _kind(provider, src) == "dir"
    if dest == src[:-1]:
        if mode == "move":
            return {"entry": provider.stat(src).to_json(), "unchanged": True}  # 同じ場所への移動は何もしない
        return {"entry": op(src, dest, copy_name(provider, dest, name, is_dir)).to_json()}
    try:
        return {"entry": op(src, dest).to_json()}
    except ApiError as e:
        if e.code != "exists" or on_conflict == "error":
            raise
    target = dest + (name,)
    if on_conflict == "skip":
        return {"skipped": True}
    if on_conflict == "rename":
        return {"entry": op(src, dest, free_name(provider, dest, name, is_dir)).to_json()}
    # overwrite: ファイル同士だけ。フォルダの中身をまぜる動きは作らない（ToDo「決めていないこと」の 6）
    if is_dir or _kind(provider, target) == "dir":
        raise ApiError("exists", "フォルダは置き換えられません", vpath.join(target))
    _set_aside(provider, target)
    return {"entry": op(src, dest).to_json()}


# --- マウントをまたぐコピー・移動 ---
# プロバイダの copy / move は同じマウントの中だけ。マウントをまたぐときは、元を読んで先に書く
# （open_read / write_file。どちらのプロバイダも "stream" を持つこと）。移動は写し終えてから元を消す
# （エクスプローラーでドライブをまたいで移動するときと同じ）。

def _refuse_link(entry, path) -> None:
    """シンボリックリンクはマウントをまたいで写さない。リンクという考えを持たない構造があり、
    辿って中身を写すと、根の外を指すリンクの先を読むことになりうるため。"""
    if entry.extra.get("symlink"):
        raise ApiError("unsupported", "シンボリックリンクはマウントをまたいで写せません", vpath.join(path))


def _copy_tree(src_p: Provider, src: tuple[str, ...], dst_p: Provider, dest_dir: tuple[str, ...], name: str):
    """src（src_p の中）を、dst_p の dest_dir に name で写す。フォルダは中を 1 つずつたどる。
    途中で失敗したら、そこまで写したものは残す（やり直しはしない。Wiki「API 設計 > 一括の結果」）。"""
    entry = src_p.stat(src)
    _refuse_link(entry, src)
    if entry.kind != "dir":
        with src_p.open_read(src) as f:
            return dst_p.write_file(dest_dir, name, f)
    if "mkdir" not in dst_p.capabilities:
        raise ApiError("unsupported", "写し先のマウントにはフォルダを作れません", vpath.join(dest_dir + (name,)))
    made = dst_p.mkdir(dest_dir, name)
    for child in src_p.listdir(src):
        _refuse_link(child, src + (child.name,))
        _copy_tree(src_p, src + (child.name,), dst_p, dest_dir + (name,), child.name)
    return made


def transfer_across(src_p: Provider, dst_p: Provider, mode: str, src_text: str, dest: tuple[str, ...],
                    on_conflict: str) -> dict:
    """マウントをまたいで 1 つをコピー（mode="copy"）か移動（mode="move"）する。名前の衝突は on_conflict に従う。"""
    src = vpath.split(src_text)
    if not src:
        raise ApiError("bad_path", "マウントの根はコピー・移動できません", "/")
    name = src[-1]
    is_dir = _kind(src_p, src) == "dir"
    target = dest + (name,)
    if dst_p.exists(target):
        if on_conflict == "error":
            raise ApiError("exists", "同じ名前の項目があります", vpath.join(target))
        if on_conflict == "skip":
            return {"skipped": True}
        if on_conflict == "rename":
            name = free_name(dst_p, dest, name, is_dir)
        else:  # overwrite: ファイル同士だけ。置き換えられるほうは消さずにごみ箱へ
            if is_dir or _kind(dst_p, target) == "dir":
                raise ApiError("exists", "フォルダは置き換えられません", vpath.join(target))
            _set_aside(dst_p, target)
    entry = _copy_tree(src_p, src, dst_p, dest, name)
    if mode == "move":
        src_p.delete(src)  # 写し終えてから消す。写し先にあるので、ごみ箱へは移さない
    return {"entry": dst_p.stat(dest + (entry.name,)).to_json()}
