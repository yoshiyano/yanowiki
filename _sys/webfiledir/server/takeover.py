"""二重起動のとき、同じポートで先に動いている webFileDir を止めて入れ替わる（run.py が使う）。

Linux の /proc を読んで、ポートで待ち受けているプロセスを探す。**止めるのは、このアカウントで動いている
webFileDir の run.py だけ。**別のプログラムがポートを使っていれば止めずに TakeoverError にする
（関係のないプロセスを誤って止めないため）。
"""

import os
import signal
import time
from pathlib import Path

LISTEN = "0A"  # /proc/net/tcp の st（状態）: 待ち受け


class TakeoverError(Exception):
    """ポートを別のプログラムが使っている、または先の webFileDir を止められなかった。"""


def _listening_sockets(port: int) -> set[str]:
    """port で待ち受けているソケット（"socket:[inode]"）。どのアカウントのものも見える。"""
    inodes = set()
    for name in ("tcp", "tcp6"):
        try:
            lines = Path(f"/proc/net/{name}").read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            local, state, inode = fields[1], fields[3], fields[9]
            if state == LISTEN and int(local.rsplit(":", 1)[1], 16) == port:
                inodes.add(f"socket:[{inode}]")
    return inodes


def listening_pids(port: int) -> set[int]:
    """port で待ち受けているプロセスの pid（見られるもの＝このアカウントのものだけ）。"""
    inodes = _listening_sockets(port)
    pids = set()
    if not inodes:
        return pids
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            for fd in (d / "fd").iterdir():
                if os.readlink(fd) in inodes:
                    pids.add(int(d.name))
                    break
        except OSError:
            continue  # 別のアカウントのプロセス、または調べているあいだに終わった
    return pids


def command_line(pid: int) -> list[str]:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").split("\0")[:-1]
    except OSError:
        return []


def is_webfiledir(pid: int) -> bool:
    """このアカウントで動いている webFileDir の run.py か（引数の run.py の隣に server/httpserver.py がある）。"""
    try:
        if os.stat(f"/proc/{pid}").st_uid != os.getuid():
            return False
        cwd = Path(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        return False
    for arg in command_line(pid)[1:]:
        if Path(arg).name == "run.py":
            script = (cwd / arg).resolve()
            return (script.parent / "server" / "httpserver.py").is_file()
    return False


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # 親が回収していない終わったプロセス（ゾンビ）は、もう待ち受けていないので終わったとみなす
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def _wait_port_free(port: int, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not _listening_sockets(port):
            return True
        time.sleep(0.05)
    return not _listening_sockets(port)


def _wait_gone(pid: int, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


def stop_previous(port: int, timeout: float = 5.0) -> list[int]:
    """port で動いている先の webFileDir を止め、止めた pid を返す。別のプログラムなら TakeoverError。"""
    pids = sorted(listening_pids(port) - {os.getpid()})
    for pid in pids:
        if not is_webfiledir(pid):
            cmd = " ".join(command_line(pid)) or "不明"
            raise TakeoverError(f"ポート {port} は webFileDir でないプログラムが使っています（pid {pid}: {cmd}）")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        if not _wait_gone(pid, timeout):
            os.kill(pid, signal.SIGKILL)  # 止まらなければ強制的に
            if not _wait_gone(pid, 2.0):
                raise TakeoverError(f"先に動いている webFileDir（pid {pid}）を止められませんでした")
    # プロセスが終わったように見えても、ポートがまだ空いていないことがある。スレッドを持つプロセスは、
    # メインのスレッドが先に終わって（ゾンビ）、ほかのスレッド（自動更新の接続など）が終わるまで
    # 待ち受けのソケットを持ち続けるため（2026-09-28 に入れ替わりが「Address already in use」で失敗した）
    if pids and not _wait_port_free(port, timeout):
        raise TakeoverError(f"先に動いていた webFileDir を止めましたが、ポート {port} が空きません")
    return pids
