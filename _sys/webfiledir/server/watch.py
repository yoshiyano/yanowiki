"""フォルダの変化を見張り、購読者へ知らせる（Linux の inotify を ctypes で直接使う）。

画面の自動更新（GET /api/v1/events）が使う。問い合わせを繰り返す（polling）のではなく、
OS からの知らせを受けて、変わったフォルダの購読者だけに伝える。
1 つのフォルダの変化が短い間に続いたら（大きなコピーなど）、DEBOUNCE 秒ごとに 1 回にまとめる。
"""

import ctypes
import ctypes.util
import errno
import logging
import os
import select
import struct
import threading
import time

log = logging.getLogger(__name__)

IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ONLYDIR = 0x01000000

# 一覧に出る値（名前・種類・サイズ・更新日時）が変わりうる出来事
WATCH_MASK = (IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE
              | IN_DELETE | IN_DELETE_SELF | IN_MOVE_SELF | IN_ONLYDIR)
EVENT_HEADER = struct.Struct("iIII")  # wd, mask, cookie, len（そのあとに名前が len バイト）
DEBOUNCE = 0.2


def _load_libc():
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
        libc.inotify_init1  # noqa: B018 — 無ければ AttributeError（Linux 以外）
        return libc
    except (OSError, AttributeError):
        return None


_libc = _load_libc()


class FolderWatcher:
    """フォルダ（OS のパス）ごとに購読者を持ち、変わったら呼ぶ。

    subscribe(path, callback) は解除の関数を返す。見張れなければ None。
    callback は見張りのスレッドから引数なしで呼ばれるので、すぐ戻ること（キューに入れるなど）。
    """

    def __init__(self, debounce: float = DEBOUNCE):
        self.debounce = debounce
        self._lock = threading.Lock()
        self._subs: dict[str, set] = {}     # パス → 購読者の集合
        self._wd_of: dict[str, int] = {}    # パス → inotify の番号
        self._paths_of: dict[int, set] = {}  # 番号 → パスの集合（同じフォルダを別のパスで見張ることがある）
        self._pending: dict[str, float] = {}  # 知らせを待っているパス → 知らせる時刻
        self._fd = -1
        if _libc is not None:
            fd = _libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
            if fd >= 0:
                self._fd = fd
            else:
                log.warning("inotify を使えません: %s", os.strerror(ctypes.get_errno()))
        if self._fd >= 0:
            threading.Thread(target=self._loop, name="FolderWatcher", daemon=True).start()

    @property
    def available(self) -> bool:
        return self._fd >= 0

    def subscribe(self, path: str, callback):
        if not self.available:
            return None
        with self._lock:
            if path not in self._wd_of:
                wd = _libc.inotify_add_watch(self._fd, os.fsencode(path), WATCH_MASK)
                if wd < 0:
                    e = ctypes.get_errno()
                    if e == errno.ENOSPC:
                        log.warning("見張れるフォルダの数の上限です（fs.inotify.max_user_watches）: %s", path)
                    return None
                self._wd_of[path] = wd
                self._paths_of.setdefault(wd, set()).add(path)
            self._subs.setdefault(path, set()).add(callback)

        def unsubscribe():
            with self._lock:
                subs = self._subs.get(path)
                if subs is None:
                    return
                subs.discard(callback)
                if subs:
                    return
                del self._subs[path]
                self._pending.pop(path, None)
                wd = self._wd_of.pop(path, None)
                if wd is None:
                    return
                paths = self._paths_of.get(wd, set())
                paths.discard(path)
                if not paths:
                    self._paths_of.pop(wd, None)
                    _libc.inotify_rm_watch(self._fd, wd)

        return unsubscribe

    def watched_count(self) -> int:
        with self._lock:
            return len(self._wd_of)

    # --- 見張りのスレッド ---

    def _loop(self):
        while True:
            with self._lock:
                deadline = min(self._pending.values(), default=None)
            timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
            ready, _, _ = select.select([self._fd], [], [], timeout)
            if ready:
                self._read_events()
            self._fire_due()

    def _read_events(self):
        try:
            data = os.read(self._fd, 65536)
        except BlockingIOError:
            return
        now = time.monotonic()
        offset = 0
        with self._lock:
            while offset + EVENT_HEADER.size <= len(data):
                wd, mask, _cookie, length = EVENT_HEADER.unpack_from(data, offset)
                offset += EVENT_HEADER.size + length
                if mask & IN_Q_OVERFLOW:
                    # 取りこぼした。どこが変わったか分からないので、すべてに知らせる
                    targets = set(self._subs)
                else:
                    targets = set(self._paths_of.get(wd, ()))
                for p in targets:
                    # 最初の出来事から debounce 後に 1 回（出来事が続いても知らせが遅れ続けないように）
                    self._pending.setdefault(p, now + self.debounce)
                if mask & IN_IGNORED:
                    # フォルダが消えた・移ったなどで見張りが外れた。購読は残し、知らせは上で出す
                    for p in self._paths_of.pop(wd, set()):
                        self._wd_of.pop(p, None)

    def _fire_due(self):
        now = time.monotonic()
        with self._lock:
            due = [p for p, t in self._pending.items() if t <= now]
            calls = []
            for p in due:
                del self._pending[p]
                calls.extend(self._subs.get(p, ()))
        for cb in calls:
            try:
                cb()
            except Exception:
                log.exception("フォルダの変化の知らせで例外")


class ChangeHub:
    """OS のパスを持たないマウント（仮想構造）の変化の知らせ役。

    仮想構造は inotify で見張れないが、変更はすべてこのサーバの API を通るので、変更の API が終わったら
    publish(マウント名) で知らせれば取りこぼさない。購読者（自動更新の接続）は、そのマウントで見ている
    フォルダをまとめて読み直す（どのフォルダが変わったかまでは分けない。仮想構造は小さいので読み直しで足りる）。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: dict[str, set] = {}

    def subscribe(self, mount: str, callback):
        with self._lock:
            self._subs.setdefault(mount, set()).add(callback)

        def unsubscribe():
            with self._lock:
                subs = self._subs.get(mount)
                if subs is not None:
                    subs.discard(callback)
                    if not subs:
                        del self._subs[mount]

        return unsubscribe

    def publish(self, mount: str) -> None:
        with self._lock:
            calls = list(self._subs.get(mount, ()))
        for cb in calls:
            try:
                cb()
            except Exception:
                log.exception("仮想構造の変化の知らせで例外")
