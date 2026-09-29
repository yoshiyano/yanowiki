"""実ファイルシステムのプロバイダ。

**組み立てたパスを realpath で解決し、根の中にあることを確かめてから触る。**
シンボリックリンクで根の外へ出るのを防ぐため（Wiki「設計の全体像 > 安全対策」）。
変更系（名前の変更・削除・ごみ箱へ）は**親フォルダを realpath で解決し、最後の名前は辿らない。**
リンクを消したり名前を変えたりするときに、リンク先のほうを触らないため。

シンボリックリンクの見せかた（ToDo「決めていないこと」の 7 の案）:
- 根の中を指すもの … 辿った先として見せる（extra.symlink = True）
- 根の外を指すもの・壊れたもの … 一覧には出すが開けない
  （kind = "file"、extra.unreachable = "outside" / "broken"）。名前の変更・削除はできる

ごみ箱（Wiki「設計の全体像 > ごみ箱」）:
- 既定の置き場所は根の直下の .fdweb-trash。中は files/<ID>/<元の名前> と info/<ID>.json
- ごみ箱のフォルダは一覧にも API のパスにも出さない（その名前は作れない・開けない）
"""

import errno
import json
import logging
import os
import re
import shutil
import stat as st
import time
import uuid

from ..errors import ApiError
from .. import vpath
from .base import AUTH_ALL, Entry, Provider, TrashItem

log = logging.getLogger(__name__)

# has_children で中を見る項目数の上限。超えたら「不明」にして、巨大なフォルダで待たせない
HAS_CHILDREN_SCAN_LIMIT = 2000

TRASH_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class LocalProvider(Provider):
    capabilities = frozenset({"mkdir", "touch", "rename", "delete", "trash", "copy", "move", "stream"})

    def __init__(self, root: str | os.PathLike, trash_dir: str | os.PathLike | None = None):
        # 根そのものは起動時に（シンボリックリンクでないことを含めて）確かめてある
        self.root = os.path.realpath(root)
        self.trash_root = os.path.realpath(trash_dir) if trash_dir else os.path.join(self.root, ".fdweb-trash")
        self.trash_files = os.path.join(self.trash_root, "files")
        self.trash_info = os.path.join(self.trash_root, "info")

    # --- 読み取り ---

    def stat(self, path):
        real = self._resolve(path)
        s = self._os(os.stat, real, path)
        name = path[-1] if path else ""
        # マウントの根は動かせない（place を渡さない）
        return self._entry(name, s, is_link=bool(path) and os.path.islink(self._joined(path)), real=real,
                           place=self._joined(path) if path else None)

    def listdir(self, path):
        real = self._resolve(path)
        entries = []
        with self._os(os.scandir, real, path) as it:
            for de in it:
                if self._is_trash_root(de.path):
                    continue  # ごみ箱のフォルダそのもの。ごみ箱を指すリンクは「開けないリンク」として出す
                entries.append(self._path_entry(de.path, de.name))
        return entries

    def has_children(self, path):
        real = self._resolve(path)
        try:
            with os.scandir(real) as it:
                for i, de in enumerate(it):
                    if i >= HAS_CHILDREN_SCAN_LIMIT:
                        return None
                    if not self._is_trash_root(de.path) and self._is_reachable_dir(de):
                        return True
        except OSError:
            return None  # 読めないフォルダは「不明」。開いたときにエラーを見せる
        return False

    def exists(self, path):
        if not path:
            return True
        return os.path.lexists(self._target(path))

    # --- 変更 ---

    def mkdir(self, parent, name):
        target = self._new_target(parent, name)
        self._os(lambda p: os.mkdir(p), target, parent + (name,))
        return self._path_entry(target, name)

    def create_file(self, parent, name):
        target = self._new_target(parent, name)
        # O_EXCL: 同じ名前があれば上書きせずに失敗させる
        fd = self._os(lambda p: os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666), target,
                      parent + (name,))
        os.close(fd)
        return self._path_entry(target, name)

    def rename(self, path, new_name):
        src = self._existing_target(path)
        if new_name == path[-1]:
            return self._path_entry(src, new_name)
        dst = self._new_target(path[:-1], new_name)
        # os.rename は同じ名前のファイルを黙って上書きするので先に確かめる。
        # 確かめてから名前を変えるまでの間に作られると上書きしうるが、標準ライブラリに
        # 「上書きしない名前の変更」（renameat2 の RENAME_NOREPLACE）が無いので受け入れる
        if os.path.lexists(dst):
            raise ApiError("exists", "同じ名前の項目があります", vpath.join(path[:-1] + (new_name,)))
        self._os(lambda p: os.rename(p, dst), src, path)
        return self._path_entry(dst, new_name)

    def delete(self, path):
        target = self._existing_target(path)

        def remove(p):
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.unlink(p)  # ファイルとシンボリックリンク（リンク先は消さない）

        self._os(remove, target, path)

    # --- 中身の読み書き（マウントをまたぐコピー・移動） ---

    def open_read(self, path):
        real = self._resolve(path)  # 根の中を指すリンクは辿る（読み取りと同じ規則）
        if os.path.isdir(real):
            raise ApiError("bad_path", "フォルダは中身を読めません", vpath.join(path))
        return self._os(lambda p: open(p, "rb"), real, path)

    def write_file(self, parent, name, stream):
        target = self._new_target(parent, name)
        shown = parent + (name,)
        # O_EXCL: 同じ名前があれば上書きせずに失敗させる（確かめてから書くまでの間に作られても上書きしない）
        fd = self._os(lambda p: os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666), target, shown)
        try:
            with os.fdopen(fd, "wb") as out:
                shutil.copyfileobj(stream, out, 1024 * 1024)
        except BaseException as e:
            # 書きかけのファイルを残さない
            try:
                os.unlink(target)
            except OSError:
                pass
            if isinstance(e, OSError):
                self._raise_os(e, vpath.join(shown))  # ディスクが一杯などを、ほかの操作と同じエラーの形に
            raise
        return self._path_entry(target, name)

    def copy(self, src, dest_dir, new_name=None):
        s, dst, name = self._transfer_targets(src, dest_dir, new_name)

        def do_copy(p):
            # リンクはリンクのまま写す（辿らない）。根の外を指すリンクを写しても、外の中身は読まない
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.copytree(p, dst, symlinks=True)
            else:
                shutil.copy2(p, dst, follow_symlinks=False)

        self._os(do_copy, s, src)
        return self._path_entry(dst, name)

    def move(self, src, dest_dir, new_name=None):
        s, dst, name = self._transfer_targets(src, dest_dir, new_name)

        def do_move(p):
            try:
                os.rename(p, dst)
            except OSError as e:
                if e.errno != errno.EXDEV:
                    raise
                # 同じマウントの中に別のファイルシステムがあるとき。写してから消す（リンクは辿らない）
                shutil.move(p, dst, copy_function=lambda a, b: shutil.copy2(a, b, follow_symlinks=False))

        self._os(do_move, s, src)
        return self._path_entry(dst, name)

    def _transfer_targets(self, src, dest_dir, new_name):
        """コピー・移動の元と先の実パス。同じ名前があれば exists、フォルダを自分の中へなら into_self。"""
        s = self._existing_target(src)
        name = new_name if new_name is not None else src[-1]
        dst = self._new_target(dest_dir, name)
        if os.path.isdir(s) and not os.path.islink(s):
            dest_real = os.path.realpath(os.path.dirname(dst))
            s_real = os.path.realpath(s)
            if dest_real == s_real or dest_real.startswith(s_real + os.sep):
                raise ApiError("into_self", "フォルダをそのフォルダ自身の中へは入れられません", vpath.join(src))
        if os.path.lexists(dst):
            raise ApiError("exists", "同じ名前の項目があります", vpath.join(dest_dir + (name,)))
        return s, dst, name

    # --- ごみ箱 ---

    def trash(self, path):
        target = self._existing_target(path)
        self._prepare_trash()
        trash_id = uuid.uuid4().hex
        box = os.path.join(self.trash_files, trash_id)
        os.mkdir(box, 0o700)
        name = path[-1]
        try:
            os.rename(target, os.path.join(box, name))
        except OSError as e:
            os.rmdir(box)
            if e.errno == errno.EXDEV:
                raise ApiError("forbidden", "ごみ箱が別のファイルシステムにあるので移せません",
                               vpath.join(path)) from None
            self._raise_os(e, vpath.join(path))
        info = {"originalPath": vpath.join(path), "deletedAt": time.time(), "name": name}
        try:
            with open(os.path.join(self.trash_info, f"{trash_id}.json"), "x", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False)
        except OSError:
            # 記録が書けなければ戻せなくなるので、元に戻して失敗にする
            os.rename(os.path.join(box, name), target)
            os.rmdir(box)
            raise
        return self.trash_item(trash_id)

    def list_trash(self):
        items = []
        try:
            names = os.listdir(self.trash_info)
        except FileNotFoundError:
            return []
        for fn in names:
            if fn.endswith(".json") and TRASH_ID_RE.match(fn[:-5]):
                try:
                    items.append(self.trash_item(fn[:-5]))
                except ApiError:
                    continue  # 中身の無い記録などは飛ばす
        return items

    def trash_item(self, trash_id):
        info = self._read_info(trash_id)
        item_path = os.path.join(self.trash_files, trash_id, info["name"])
        if not os.path.lexists(item_path):
            raise ApiError("not_found", "ごみ箱にその項目がありません")
        return TrashItem(id=trash_id, original_path=info["originalPath"], deleted_at=info["deletedAt"],
                         entry=self._path_entry(item_path, info["name"]))

    def restore(self, trash_id, new_name=None):
        info = self._read_info(trash_id)
        parts = vpath.split(info["originalPath"])
        parent = parts[:-1]
        name = new_name if new_name is not None else parts[-1]
        self._make_parents(parent)
        dst = self._new_target(parent, name)
        if os.path.lexists(dst):
            raise ApiError("exists", "元の場所に同じ名前の項目があります", vpath.join(parent + (name,)))
        src = os.path.join(self.trash_files, trash_id, info["name"])
        self._os(lambda p: os.rename(p, dst), src, parts)
        self._forget(trash_id)
        return self._path_entry(dst, name)

    def purge(self, trash_id):
        self._read_info(trash_id)  # 無い ID は not_found
        box = os.path.join(self.trash_files, trash_id)
        if os.path.isdir(box):
            shutil.rmtree(box)
        self._forget(trash_id)

    # --- 自動更新 ---

    def watch_path(self, path):
        real = self._resolve(path)  # 根の外・ごみ箱の中は ApiError
        if not os.path.isdir(real):
            raise ApiError("not_found", "フォルダが見つかりません", vpath.join(path))
        return real

    def watch_trash_path(self):
        # まだ一度もごみ箱へ移していなければ無い。見張るためだけにフォルダを作らない
        # （読み取り専用のマウントでも呼ばれるため）
        return self.trash_info if os.path.isdir(self.trash_info) else None

    # --- 下請け: パス ---

    def _joined(self, path) -> str:
        return os.path.join(self.root, *path)

    def _inside(self, real: str) -> bool:
        return real == self.root or real.startswith(self.root + os.sep)

    def _is_trash_root(self, p: str) -> bool:
        """p（辿らずに置いたパス）がごみ箱のフォルダそのものか。"""
        return os.path.normpath(p) == self.trash_root

    def _in_trash(self, p: str) -> bool:
        real = os.path.realpath(p)
        return real == self.trash_root or real.startswith(self.trash_root + os.sep)

    def _resolve(self, path) -> str:
        """読み取り用。最後の名前まで辿り、根の中で、ごみ箱の外であることを確かめる。"""
        real = os.path.realpath(self._joined(path))
        if not self._inside(real):
            raise ApiError("forbidden", "マウントの外を指しています", vpath.join(path))
        if self._in_trash(real):
            raise ApiError("not_found", "見つかりません", vpath.join(path))
        return real

    def _target(self, path) -> str:
        """変更用。親フォルダだけを辿り、最後の名前は辿らない実パス。"""
        if not path:
            raise ApiError("bad_path", "マウントの根は変えられません", "/")
        parent = self._resolve(path[:-1])
        target = os.path.join(parent, path[-1])
        if os.path.normpath(target) == self.trash_root:
            raise ApiError("not_found", "見つかりません", vpath.join(path))
        return target

    def _existing_target(self, path) -> str:
        target = self._target(path)
        if not os.path.lexists(target):
            raise ApiError("not_found", "見つかりません", vpath.join(path))
        if self.trash_root.startswith(os.path.normpath(target) + os.sep):
            # 設定でごみ箱をこのフォルダの中に置いている。動かすとごみ箱ごと動く・消える
            raise ApiError("forbidden", "ごみ箱を中に含むフォルダは変えられません", vpath.join(path))
        return target

    def _new_target(self, parent, name) -> str:
        """これから作る（名前を付ける）項目の実パス。親はフォルダでなければならない。"""
        parent_real = self._resolve(parent)
        if not os.path.isdir(parent_real):
            if not os.path.lexists(parent_real):
                raise ApiError("not_found", "フォルダが見つかりません", vpath.join(parent))
            raise ApiError("bad_path", "フォルダではありません", vpath.join(parent))
        target = os.path.join(parent_real, name)
        if os.path.normpath(target) == self.trash_root:
            raise ApiError("bad_name", "その名前はここでは使えません（ごみ箱の名前です）",
                           vpath.join(parent + (name,)))
        return target

    def _make_parents(self, parent) -> None:
        """元の場所へ戻すとき、無くなったフォルダを作り直す。"""
        for i in range(1, len(parent) + 1):
            p = self._target(parent[:i])
            if not os.path.lexists(p):
                self._os(lambda x: os.mkdir(x), p, parent[:i])

    # --- 下請け: ごみ箱 ---

    def _prepare_trash(self) -> None:
        for p in (self.trash_root, self.trash_files, self.trash_info):
            try:
                os.mkdir(p, 0o700)
            except FileExistsError:
                pass
            s = os.lstat(p)
            # 誰かが置いたリンクを辿ってごみ箱の中身を外へ移さないよう、本物のフォルダか確かめる
            if not st.S_ISDIR(s.st_mode):
                raise ApiError("internal", "ごみ箱のフォルダが壊れています")

    def _read_info(self, trash_id) -> dict:
        if not isinstance(trash_id, str) or not TRASH_ID_RE.match(trash_id):
            raise ApiError("not_found", "ごみ箱にその項目がありません")
        try:
            with open(os.path.join(self.trash_info, f"{trash_id}.json"), encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, ValueError):
            raise ApiError("not_found", "ごみ箱にその項目がありません") from None
        if not (isinstance(info, dict) and isinstance(info.get("originalPath"), str)
                and isinstance(info.get("name"), str) and isinstance(info.get("deletedAt"), (int, float))):
            raise ApiError("not_found", "ごみ箱の記録が壊れています")
        vpath.check_name(info["name"])
        vpath.split(info["originalPath"])
        return info

    def _forget(self, trash_id) -> None:
        box = os.path.join(self.trash_files, trash_id)
        try:
            os.rmdir(box)
        except OSError:
            pass
        try:
            os.unlink(os.path.join(self.trash_info, f"{trash_id}.json"))
        except FileNotFoundError:
            pass

    # --- 下請け: OS と Entry ---

    def _raise_os(self, e: OSError, shown: str):
        if isinstance(e, FileNotFoundError):
            raise ApiError("not_found", "見つかりません", shown) from None
        if isinstance(e, FileExistsError):
            raise ApiError("exists", "同じ名前の項目があります", shown) from None
        if isinstance(e, NotADirectoryError):
            raise ApiError("bad_path", "フォルダではありません", shown) from None
        if isinstance(e, PermissionError):
            raise ApiError("forbidden", "権限がありません", shown) from None
        if isinstance(e, IsADirectoryError):
            raise ApiError("bad_path", "フォルダです", shown) from None
        if e.errno == errno.ENAMETOOLONG:
            raise ApiError("bad_name", "名前が長すぎます", shown) from None
        raise e

    def _os(self, func, real, path):
        """OS の呼び出しの例外を ApiError に直す。"""
        try:
            return func(real)
        except OSError as e:
            self._raise_os(e, vpath.join(path))

    def _entry(self, name, s, is_link=False, extra=None, real=None, place=None) -> Entry:
        """real は権限を調べる実パス（リンクなら辿った先）。place は項目が置かれている実パス（リンクならリンク
        自身。名前の変更・移動で動くのはこちら）で、None なら動かせない（マウントの根）。"""
        is_dir = st.S_ISDIR(s.st_mode)
        extra = dict(extra or {})
        if is_link:
            extra["symlink"] = True
        return Entry(
            name=name,
            kind="dir" if is_dir else "file",
            size=None if is_dir else s.st_size,
            mtime=s.st_mtime,
            extra=extra,
            auth=self._auth(real, is_dir, place) if real is not None else AUTH_ALL,
        )

    @staticmethod
    def _auth(real: str, is_dir: bool, place: str | None) -> int:
        """実ファイルの権限の値。**値の出しかたはクロコの実装例**（設計者は、画面が項目ごとの値を見ることだけを
        決め、実ファイルでの値の出しかたはサーバ側の別の話とした。2026-09-29）。

        このサーバのプロセスが実際にできることを入れる（os.access。所有者以外のファイル・root でも正しい）。
        フォルダの「書く」は、中に作る・消すのに要る「書く＋実行」の両方。「動かす」は、OS がこの項目の名前の
        変更・移動を許すか（_can_move）。"""
        read = os.access(real, os.R_OK)
        write = os.access(real, os.W_OK | os.X_OK) if is_dir else os.access(real, os.W_OK)
        execute = os.access(real, os.X_OK)
        move = place is not None and LocalProvider._can_move(place)
        return (8 if move else 0) | (4 if read else 0) | (2 if write else 0) | (1 if execute else 0)

    @staticmethod
    def _can_move(place: str) -> bool:
        """OS が place（項目が置かれている実パス）の名前の変更・移動を許すか。Linux では、入っているフォルダに
        「書く＋実行」があり、そのフォルダにスティッキービット（/tmp など）があれば、項目かフォルダの持ち主
        （か root）であること。"""
        parent = os.path.dirname(place)
        if not os.access(parent, os.W_OK | os.X_OK):
            return False
        try:
            ps = os.stat(parent)
            if ps.st_mode & st.S_ISVTX:
                euid = os.geteuid()
                return euid == 0 or euid in (ps.st_uid, os.lstat(place).st_uid)
        except OSError:
            return False
        return True

    def _path_entry(self, p: str, name: str) -> Entry:
        """p（最後の名前は辿らずに置いた実パス）の Entry。リンクは見せかたの規則に従う。"""
        lst = os.lstat(p)
        if not st.S_ISLNK(lst.st_mode):
            return self._entry(name, lst, real=p, place=p)
        target = os.path.realpath(p)
        if not self._inside(target) or self._in_trash(target):
            reason = "outside"
        elif not os.path.exists(target):
            reason = "broken"
        else:
            try:
                return self._entry(name, os.stat(target), is_link=True, real=target, place=p)
            except OSError:
                reason = "broken"
        return Entry(name=name, kind="file", size=None, mtime=lst.st_mtime,
                     extra={"symlink": True, "unreachable": reason})

    def _is_reachable_dir(self, de: os.DirEntry) -> bool:
        try:
            if not de.is_symlink():
                return de.is_dir(follow_symlinks=False)
            target = os.path.realpath(de.path)
            return self._inside(target) and not self._in_trash(target) and os.path.isdir(target)
        except OSError:
            return False
