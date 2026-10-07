"""Only one Touff at a time: two copies would fight over the microphone and the GPU.

The first copy takes a named mutex (Windows releases it automatically when the process
dies, even on a crash) and listens on a random localhost port. instance.json in the data
directory says where, plus a random key, so only someone who can read that file can talk
to her. A second launch finds the mutex taken, asks the running copy to show its
settings, and exits.

Both the mutex name and instance.json come from the data directory, so a TOUFF_HOME
somewhere else is a completely separate Touff (tests and side-by-side dev copies).
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Client, Listener, answer_challenge, deliver_challenge
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

INFO_FILE = "instance.json"
_ERROR_ALREADY_EXISTS = 183
_STILL_ACTIVE = 259
_mutex: int | None = None  # held for the life of the process


@dataclass(frozen=True)
class Info:
    pid: int
    port: int
    key: bytes


# -- pure-ish helpers (tested) ------------------------------------------------------


def mutex_name(data_dir: Path) -> str:
    """Per user session and per data directory."""
    digest = hashlib.sha1(os.path.normcase(str(Path(data_dir).resolve())).encode("utf-8")).hexdigest()[:16]
    return f"Local\\Touff-{digest}"


def parse_info(raw: Any) -> Info | None:
    """instance.json contents -> Info, or None when it's missing bits or garbage."""
    if not isinstance(raw, dict):
        return None
    pid, port, key = raw.get("pid"), raw.get("port"), raw.get("key")
    if not (isinstance(pid, int) and pid > 0 and isinstance(port, int) and 0 < port < 65536 and isinstance(key, str)):
        return None
    try:
        key_bytes = bytes.fromhex(key)
    except ValueError:
        return None
    return Info(pid, port, key_bytes) if len(key_bytes) >= 16 else None


def read_info(path: Path, alive: Callable[[int], bool] | None = None) -> Info | None:
    """The running copy's address, or None if the file is missing, broken, or left behind
    by a copy that has since died (crash, killed from Task Manager)."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    info = parse_info(raw)
    if info is None or not (alive or pid_alive)(info.pid):
        return None
    return info


def write_info(path: Path, info: Info) -> None:
    """Atomic, so a second launch never reads half a file."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"pid": info.pid, "port": info.port, "key": info.key.hex()}), encoding="utf-8")
    os.replace(tmp, path)


def remove_info(path: Path, pid: int) -> None:
    """Delete instance.json, but only if it's still ours."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("pid") == pid:
            Path(path).unlink()
    except (OSError, ValueError):
        pass


def pid_alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # access denied: exists, just not ours
    try:
        code = ctypes.c_ulong()
        if not k32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))


# -- Win32 mutex -----------------------------------------------------------------------


def acquire(data_dir: Path) -> bool:
    """True if we're the only Touff for this data directory (and now hold the lock)."""
    global _mutex
    if _mutex is not None:
        return True
    if sys.platform != "win32":
        return True
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    handle = k32.CreateMutexW(None, False, mutex_name(data_dir))
    err = ctypes.get_last_error()
    if not handle:
        log.warning("couldn't create the single-instance mutex (error %s); carrying on", err)
        return True
    if err == _ERROR_ALREADY_EXISTS:
        k32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _mutex = handle
    return True


# -- the little localhost channel ------------------------------------------------------


class Server:
    """Listens for "show" from later launches and calls on_show."""

    def __init__(self, data_dir: Path, on_show: Callable[[], None]):
        self.path = Path(data_dir) / INFO_FILE
        self.on_show = on_show
        key = secrets.token_bytes(32)
        # No authkey on the Listener itself: the handshake happens per connection in its own
        # thread, so a client that connects and says nothing can't block everyone else.
        self._listener = Listener(("127.0.0.1", 0))
        self._key = key
        self.info = Info(os.getpid(), self._listener.address[1], key)
        write_info(self.path, self.info)
        self._closed = False
        threading.Thread(target=self._serve, name="touff-instance", daemon=True).start()

    def _serve(self) -> None:
        while not self._closed:
            try:
                conn = self._listener.accept()
            except OSError:
                if self._closed:
                    return
                time.sleep(0.1)
                continue
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn) -> None:
        try:
            deliver_challenge(conn, self._key)  # raises on a wrong key
            answer_challenge(conn, self._key)
            if conn.poll(3):
                msg = conn.recv()
                if isinstance(msg, dict) and msg.get("cmd") == "show":
                    conn.send("ok")
                    self._show()
        except Exception:  # wrong key, garbage from some port scanner, client gone...
            pass
        finally:
            conn.close()

    def _show(self) -> None:
        try:
            self.on_show()
        except Exception:
            log.exception("couldn't show settings for a second launch")

    def close(self) -> None:
        self._closed = True
        remove_info(self.path, self.info.pid)
        try:
            self._listener.close()
        except OSError:
            pass


def _send(info: Info, msg: dict[str, Any], timeout: float) -> bool:
    """Send one message; a stuck connection (port reused by something else) can't hang us."""
    result: list[bool] = []

    def go() -> None:
        try:
            with Client(("127.0.0.1", info.port), authkey=info.key) as conn:
                conn.send(msg)
                result.append(conn.poll(timeout) and conn.recv() == "ok")
        except Exception:
            result.append(False)

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(timeout + 1)
    return bool(result and result[0])


def notify_show(data_dir: Path, wait: float = 10.0) -> bool:
    """Ask the running copy to show its settings. Retries for a while: she may still be
    starting up (lock taken, instance.json not written yet, or one left over from a crash)."""
    path = Path(data_dir) / INFO_FILE
    deadline = time.monotonic() + wait
    allowed: set[int] = set()
    while True:
        info = read_info(path)
        if info is not None:
            if info.pid not in allowed and sys.platform == "win32":
                # We were just launched by the user, so we may hand over the right to come to the front.
                ctypes.windll.user32.AllowSetForegroundWindow(info.pid)
                allowed.add(info.pid)
            if _send(info, {"cmd": "show"}, timeout=3.0):
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.3)
