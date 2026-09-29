"""メモリ上の仮想ファイル構造のプロバイダ（ToDo「決めていないこと」の 5 の候補の 1 つ）。

**サーバを止めると中身は消える。**実ファイル以外でもプロバイダの契約（tests/test_provider_contract.py）を
満たせることを確かめる、いちばん小さな仮想構造として作った。一時的な置き場所や、試しに触ってみる場所にも使える。
OS のパスを持たないので、inotify による自動更新はしない（変更の API のあとにサーバ自身が知らせる）。

要求ごとにスレッドが立つサーバで動くので、木を触るところはすべて 1 つの錠で守る。
"""

import copy as _copy
import io
import threading
import time
import uuid

from ..errors import ApiError
from .. import vpath
from .base import Entry, Provider, TrashItem

MAX_FILE_SIZE = 64 * 1024 * 1024  # 1 つのファイルの上限（メモリを使い切らないように）


class _Node:
    __slots__ = ("kind", "children", "data", "mtime")

    def __init__(self, kind: str, data: bytes = b""):
        self.kind = kind                                   # "dir" か "file"
        self.children: dict[str, "_Node"] | None = {} if kind == "dir" else None
        self.data = data if kind == "file" else b""
        self.mtime = time.time()

    def touch(self):
        self.mtime = time.time()


class MemoryProvider(Provider):
    capabilities = frozenset({"mkdir", "touch", "rename", "delete", "trash", "copy", "move", "stream"})

    def __init__(self):
        self._root = _Node("dir")
        self._trash: dict[str, dict] = {}  # ID → {"originalPath", "deletedAt", "name", "node"}
        self._lock = threading.RLock()

    # --- 下請け ---

    def _node(self, path) -> _Node:
        node = self._root
        for i, name in enumerate(path):
            if node.kind != "dir":
                raise ApiError("bad_path", "フォルダではありません", vpath.join(path[:i]))
            if name not in node.children:
                raise ApiError("not_found", "見つかりません", vpath.join(path))
            node = node.children[name]
        return node

    def _dir(self, path) -> _Node:
        node = self._node(path)
        if node.kind != "dir":
            raise ApiError("bad_path", "フォルダではありません", vpath.join(path))
        return node

    def _parent_and_name(self, path):
        if not path:
            raise ApiError("bad_path", "マウントの根は変えられません", "/")
        parent = self._dir(path[:-1])
        if path[-1] not in parent.children:
            raise ApiError("not_found", "見つかりません", vpath.join(path))
        return parent, path[-1]

    def _free(self, parent_node: _Node, parent, name):
        if name in parent_node.children:
            raise ApiError("exists", "同じ名前の項目があります", vpath.join(parent + (name,)))

    @staticmethod
    def _entry(name, node: _Node) -> Entry:
        return Entry(name=name, kind=node.kind, size=len(node.data) if node.kind == "file" else None,
                     mtime=node.mtime)

    @staticmethod
    def _contains(ancestor: _Node, node: _Node) -> bool:
        """node が ancestor 自身か、その中にあるか。"""
        if ancestor is node:
            return True
        if ancestor.kind != "dir":
            return False
        return any(MemoryProvider._contains(child, node) for child in ancestor.children.values())

    # --- 読み取り ---

    def stat(self, path):
        with self._lock:
            return self._entry(path[-1] if path else "", self._node(path))

    def listdir(self, path):
        with self._lock:
            return [self._entry(n, c) for n, c in self._dir(path).children.items()]

    def has_children(self, path):
        with self._lock:
            return any(c.kind == "dir" for c in self._dir(path).children.values())

    def exists(self, path):
        with self._lock:
            try:
                self._node(path)
                return True
            except ApiError as e:
                if e.code == "not_found":
                    return False
                raise

    # --- 変更 ---

    def _create(self, parent, name, node: _Node) -> Entry:
        with self._lock:
            d = self._dir(parent)
            self._free(d, parent, name)
            d.children[name] = node
            d.touch()
            return self._entry(name, node)

    def mkdir(self, parent, name):
        return self._create(parent, name, _Node("dir"))

    def create_file(self, parent, name):
        return self._create(parent, name, _Node("file"))

    def rename(self, path, new_name):
        with self._lock:
            parent, name = self._parent_and_name(path)
            if new_name == name:
                return self._entry(name, parent.children[name])
            self._free(parent, path[:-1], new_name)
            parent.children[new_name] = parent.children.pop(name)
            parent.touch()
            return self._entry(new_name, parent.children[new_name])

    def delete(self, path):
        with self._lock:
            parent, name = self._parent_and_name(path)
            del parent.children[name]
            parent.touch()

    def _transfer(self, src, dest_dir, new_name, move: bool) -> Entry:
        with self._lock:
            parent, name = self._parent_and_name(src)
            node = parent.children[name]
            dest = self._dir(dest_dir)
            target_name = new_name if new_name is not None else name
            if node.kind == "dir" and self._contains(node, dest):
                raise ApiError("into_self", "フォルダをそのフォルダ自身の中へは入れられません", vpath.join(src))
            self._free(dest, dest_dir, target_name)
            if move:
                del parent.children[name]
                parent.touch()
                placed = node
            else:
                placed = _copy.deepcopy(node)
                placed.touch()
            dest.children[target_name] = placed
            dest.touch()
            return self._entry(target_name, placed)

    def copy(self, src, dest_dir, new_name=None):
        return self._transfer(src, dest_dir, new_name, move=False)

    def move(self, src, dest_dir, new_name=None):
        return self._transfer(src, dest_dir, new_name, move=True)

    # --- 中身の読み書き ---

    def open_read(self, path):
        with self._lock:
            node = self._node(path)
            if node.kind != "file":
                raise ApiError("bad_path", "フォルダは中身を読めません", vpath.join(path))
            return io.BytesIO(node.data)  # 読んでいるあいだに書き換えられても、読み始めたときの中身を返す

    def write_file(self, parent, name, stream):
        with self._lock:  # 先に名前を確かめる（大きな中身を読んでから断らないように）
            self._free(self._dir(parent), parent, name)
        buf = io.BytesIO()
        while chunk := stream.read(1024 * 1024):
            buf.write(chunk)
            if buf.tell() > MAX_FILE_SIZE:
                raise ApiError("forbidden", f"メモリのマウントには {MAX_FILE_SIZE // (1024 * 1024)}MB を超えるファイルを置けません",
                               vpath.join(parent + (name,)))
        return self._create(parent, name, _Node("file", buf.getvalue()))

    # --- ごみ箱 ---

    def trash(self, path):
        with self._lock:
            parent, name = self._parent_and_name(path)
            node = parent.children.pop(name)
            parent.touch()
            trash_id = uuid.uuid4().hex
            self._trash[trash_id] = {"originalPath": vpath.join(path), "deletedAt": time.time(),
                                     "name": name, "node": node}
            return self._item(trash_id)

    def _item(self, trash_id) -> TrashItem:
        info = self._trash.get(trash_id) if isinstance(trash_id, str) else None
        if info is None:
            raise ApiError("not_found", "ごみ箱にその項目がありません")
        return TrashItem(id=trash_id, original_path=info["originalPath"], deleted_at=info["deletedAt"],
                         entry=self._entry(info["name"], info["node"]))

    def list_trash(self):
        with self._lock:
            return [self._item(i) for i in self._trash]

    def trash_item(self, trash_id):
        with self._lock:
            return self._item(trash_id)

    def restore(self, trash_id, new_name=None):
        with self._lock:
            self._item(trash_id)  # 無い ID は not_found
            info = self._trash[trash_id]
            parts = vpath.split(info["originalPath"])
            parent = parts[:-1]
            name = new_name if new_name is not None else parts[-1]
            # 元のフォルダが無ければ作り直す
            node = self._root
            for i, part in enumerate(parent):
                if part not in node.children:
                    node.children[part] = _Node("dir")
                    node.touch()
                node = node.children[part]
                if node.kind != "dir":
                    raise ApiError("bad_path", "元の場所がフォルダではありません", vpath.join(parent[:i + 1]))
            if name in node.children:
                raise ApiError("exists", "元の場所に同じ名前の項目があります", vpath.join(parent + (name,)))
            node.children[name] = info["node"]
            node.touch()
            del self._trash[trash_id]
            return self._entry(name, info["node"])

    def purge(self, trash_id):
        with self._lock:
            self._item(trash_id)
            del self._trash[trash_id]
