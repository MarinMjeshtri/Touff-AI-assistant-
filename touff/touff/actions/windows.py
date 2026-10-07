"""Window management: find app windows, move them between monitors, snap, focus, press hotkeys.

Plain ctypes/Win32. The pure bits (monitor numbering, target resolution, rect scaling,
arg and hotkey parsing) are separate functions so they can be tested anywhere.
"""

from __future__ import annotations

import ctypes
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from rapidfuzz import fuzz

from ..brain.text import normalize

Rect = tuple[int, int, int, int]  # left, top, right, bottom

OPERATIONS = ("focus", "maximize", "minimize", "restore", "close", "move", "snap_left", "snap_right", "minimize_all")
MATCH_THRESHOLD = 80

# What people say -> exe stems (lowercase, no ".exe").
ALIASES: dict[str, tuple[str, ...]] = {
    "chrome": ("chrome",), "google chrome": ("chrome",),
    "edge": ("msedge",), "microsoft edge": ("msedge",),
    "firefox": ("firefox",), "mozilla firefox": ("firefox",),
    "brave": ("brave",), "opera": ("opera", "opera_gx"), "opera gx": ("opera",),
    "vs code": ("code",), "vscode": ("code",), "code": ("code",), "visual studio code": ("code",),
    "visual studio": ("devenv",),
    "explorer": ("explorer",), "file explorer": ("explorer",), "files": ("explorer",), "my files": ("explorer",),
    "notepad": ("notepad",),
    "terminal": ("windowsterminal",), "windows terminal": ("windowsterminal",),
    "cmd": ("cmd",), "command prompt": ("cmd",), "powershell": ("powershell", "pwsh"),
    "word": ("winword",), "microsoft word": ("winword",),
    "excel": ("excel",), "microsoft excel": ("excel",),
    "powerpoint": ("powerpnt",), "microsoft powerpoint": ("powerpnt",),
    "outlook": ("outlook", "olk"), "teams": ("ms-teams", "teams"), "microsoft teams": ("ms-teams", "teams"),
    "spotify": ("spotify",), "discord": ("discord",), "steam": ("steamwebhelper", "steam"),
    "task manager": ("taskmgr",), "paint": ("mspaint",), "obs": ("obs64", "obs"),
    "claude": ("claude",), "chatgpt": ("chatgpt",), "whatsapp": ("whatsapp",), "slack": ("slack",),
    "zoom": ("zoom",), "vlc": ("vlc",), "epic games": ("epicgameslauncher",), "epic": ("epicgameslauncher",),
}
# Windows that belong to the shell, not to an app.
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow"}
_ACTIVE = {"it", "this", "that", "window", "screen", "current", "current window", "active window", "active", "focused window"}

_ORDINALS = {
    "first": 1, "1st": 1, "one": 1, "main": 1, "primary": 1,
    "second": 2, "2nd": 2, "two": 2,
    "third": 3, "3rd": 3, "three": 3,
    "fourth": 4, "4th": 4, "four": 4,
}


# -- pure helpers ----------------------------------------------------------------


def clean_app_name(spoken: str) -> str:
    """'my chrome screen' -> 'chrome', 'the spotify window' -> 'spotify'."""
    t = normalize(spoken)
    t = re.sub(r"^(?:the|my|our|that|this)\s+(?=\S)", "", t)
    t = re.sub(r"(?:\s+(?:window|windows|screen|app|application|program|tab))+$", "", t)
    return "active" if t in _ACTIVE else t


def is_known_alias(name: str) -> bool:
    return normalize(name) in ALIASES


def monitor_word(word: str) -> str | None:
    """Spoken monitor target -> '1'..'n' | 'next' | 'previous' | 'left' | 'right'."""
    w = normalize(word)
    w = re.sub(r"^(?:the|my)\s+", "", w)
    w = re.sub(r"\s+(?:monitor|screen|display|one)$", "", w)
    if w.isdigit():
        return w if int(w) >= 1 else None
    if w in _ORDINALS:
        return str(_ORDINALS[w])
    if w in ("other", "next", "another"):
        return "next"
    if w in ("previous", "prev", "last"):
        return "previous"
    if w in ("left", "right"):
        return w
    return None


def order_monitors(rects: list[tuple[Rect, bool]]) -> list[int]:
    """Indices in spoken order: monitor 1 = primary, then the others left to right."""
    primary = [i for i, (_, p) in enumerate(rects) if p][:1]
    rest = sorted((i for i in range(len(rects)) if i not in primary), key=lambda i: (rects[i][0][0], rects[i][0][1]))
    return primary + rest


def resolve_target(monitors: list[Rect], current: int, target: str) -> int | None:
    """Pick a monitor (index into the already-ordered list) for a target from monitor_word()."""
    n = len(monitors)
    if not n:
        return None
    if target.isdigit():
        i = int(target) - 1
        return i if 0 <= i < n else None
    if target == "next":
        return (current + 1) % n
    if target == "previous":
        return (current - 1) % n
    if target in ("left", "right"):
        cx = (monitors[current][0] + monitors[current][2]) / 2
        sign = -1 if target == "left" else 1
        options = [(sign * ((m[0] + m[2]) / 2 - cx), i) for i, m in enumerate(monitors) if i != current]
        options = [o for o in options if o[0] > 0]
        return min(options)[1] if options else None
    return None


def scale_rect(win: Rect, src: Rect, dst: Rect) -> Rect:
    """Keep a window's relative position and size when moving it from one work area to another."""
    sw, sh = max(1, src[2] - src[0]), max(1, src[3] - src[1])
    dw, dh = dst[2] - dst[0], dst[3] - dst[1]
    w = min(dw, round((win[2] - win[0]) * dw / sw))
    h = min(dh, round((win[3] - win[1]) * dh / sh))
    x = dst[0] + round((win[0] - src[0]) * dw / sw)
    y = dst[1] + round((win[1] - src[1]) * dh / sh)
    x = max(dst[0], min(x, dst[2] - w))  # stay fully on the target monitor
    y = max(dst[1], min(y, dst[3] - h))
    return x, y, x + w, y + h


def half_rect(work: Rect, side: str) -> Rect:
    mid = (work[0] + work[2]) // 2
    return (work[0], work[1], mid, work[3]) if side == "left" else (mid, work[1], work[2], work[3])


def parse_window_arg(arg: str) -> tuple[str, str, str]:
    """'move:chrome:2' -> ('move', 'chrome', '2'). App names may contain colons
    ('The Binding of Isaac: Rebirth'), so the monitor is only split off when it looks like one."""
    op, _, rest = arg.strip().partition(":")
    op = op.strip().lower().replace(" ", "_").replace("-", "_")
    op = {"maximise": "maximize", "minimise": "minimize", "switch": "focus", "show": "focus", "snap": "snap_left"}.get(op, op)
    app, monitor = rest.strip(), ""
    if ":" in rest:
        head, _, tail = rest.rpartition(":")
        if monitor_word(tail) is not None:
            app, monitor = head.strip(), monitor_word(tail) or ""
    if op not in OPERATIONS:
        raise ValueError(f"unknown window operation {op or '(none)'}")
    if op != "minimize_all" and not app:
        raise ValueError(f"which window should I {op.replace('_', ' ')}?")
    if op == "move":
        monitor = monitor or "next"
    return op, app, monitor


_MODS = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B, "super": 0x5B, "meta": 0x5B, "cmd": 0x5B}
_KEYS = {
    "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "space": 0x20, "spacebar": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "ins": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "printscreen": 0x2C, "prtsc": 0x2C, "capslock": 0x14, "pause": 0x13, "apps": 0x5D, "menu": 0x5D,
    "plus": 0xBB, "equals": 0xBB, "=": 0xBB, "minus": 0xBD, "-": 0xBD, "comma": 0xBC, ",": 0xBC, "period": 0xBE, "dot": 0xBE,
    ".": 0xBE, "slash": 0xBF, "/": 0xBF, "backslash": 0xDC, "\\": 0xDC, "semicolon": 0xBA, ";": 0xBA, "quote": 0xDE,
    "'": 0xDE, "backtick": 0xC0, "grave": 0xC0, "`": 0xC0, "[": 0xDB, "]": 0xDD,
    "volumeup": 0xAF, "volumedown": 0xAE, "volumemute": 0xAD, "playpause": 0xB3, "nexttrack": 0xB0, "prevtrack": 0xB1,
}
_KEYS.update({chr(c): ord(chr(c).upper()) for c in range(ord("a"), ord("z") + 1)})
_KEYS.update({str(d): 0x30 + d for d in range(10)})
_KEYS.update({f"f{n}": 0x6F + n for n in range(1, 25)})
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5D}
_MULTIWORD = {"page up": "pageup", "page down": "pagedown", "print screen": "printscreen", "caps lock": "capslock",
              "arrow up": "up", "arrow down": "down", "arrow left": "left", "arrow right": "right", "up arrow": "up",
              "down arrow": "down", "left arrow": "left", "right arrow": "right", "volume up": "volumeup",
              "volume down": "volumedown", "windows key": "win", "control key": "ctrl", "space bar": "space"}
# Win+R (run box) and Win+X (admin/terminal menu) could launch anything: never by voice or by AI.
BLOCKED_WITH_WIN = {0x52: "win+r", 0x58: "win+x"}


def parse_hotkey(combo: str) -> tuple[list[int], int]:
    """'ctrl+shift+esc' / 'control shift escape' -> ([modifier vks], key vk). Raises ValueError."""
    t = combo.strip().lower()
    for words, key in _MULTIWORD.items():
        t = t.replace(words, key)
    t = t.replace("++", "+plus") if t.endswith("++") else t
    parts = [p for p in re.split(r"\s*\+\s*|\s+", t) if p]
    if not parts:
        raise ValueError("no keys given")
    mods: list[int] = []
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"{p} isn't a modifier key")
        if _MODS[p] not in mods:
            mods.append(_MODS[p])
    last = parts[-1]
    if last in _MODS and len(parts) == 1:
        key = _MODS[last]  # a lone "win" or "alt" tap
    elif last in _KEYS:
        key = _KEYS[last]
    else:
        raise ValueError(f"I don't know a key called {last}")
    if 0x5B in mods and key in BLOCKED_WITH_WIN:
        raise PermissionError(f"{BLOCKED_WITH_WIN[key]} is blocked, it opens a run/command menu")
    return mods, key


# -- Win32 ------------------------------------------------------------------------

if sys.platform == "win32":
    from ctypes import wintypes as wt

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi")
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    _MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wt.LPARAM]
    _user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), _MONITORENUMPROC, wt.LPARAM]
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    _user32.GetAncestor.restype = wt.HWND
    _user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
    _user32.GetWindow.restype = wt.HWND
    _user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
    _user32.GetForegroundWindow.restype = wt.HWND
    _user32.MonitorFromWindow.restype = wt.HMONITOR
    _user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
    _user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    _user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    _user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
    _user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    _kernel32.OpenProcess.restype = wt.HANDLE
    _dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    class _WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [("length", wt.UINT), ("flags", wt.UINT), ("showCmd", wt.UINT), ("ptMinPosition", wt.POINT),
                    ("ptMaxPosition", wt.POINT), ("rcNormalPosition", wt.RECT)]

_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x80
_WS_EX_APPWINDOW = 0x40000
_GW_OWNER = 4
_DWMWA_EXTENDED_FRAME_BOUNDS = 9
_DWMWA_CLOAKED = 14
_SW_MAXIMIZE, _SW_MINIMIZE, _SW_RESTORE, _SW_SHOWMAXIMIZED, _SW_SHOWMINIMIZED = 3, 6, 9, 3, 2
_SWP_NOZORDER, _SWP_NOACTIVATE = 0x4, 0x10
_WM_CLOSE = 0x10
_KEYUP, _EXTENDEDKEY = 0x2, 0x1


@dataclass
class Window:
    hwnd: int
    title: str
    exe: str  # lowercase stem: "chrome"
    cls: str
    z: int  # 0 = topmost


@dataclass
class Monitor:
    number: int  # spoken number, 1 = primary
    rect: Rect
    work: Rect
    primary: bool


def _rect(r) -> Rect:
    return r.left, r.top, r.right, r.bottom


@contextmanager
def _dpi_aware() -> Iterator[None]:
    """Per-monitor-v2 DPI awareness for this thread only, so coordinates are physical pixels
    without changing how Touff's own UI is scaled. Failures are ignored (older Windows)."""
    old = None
    try:
        old = _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass
    try:
        yield
    finally:
        if old:
            try:
                _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))
            except (AttributeError, OSError):
                pass


def _exe_of(hwnd: int, cache: dict[int, str]) -> tuple[int, str]:
    pid = wt.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value not in cache:
        name = ""
        handle = _kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            buf = ctypes.create_unicode_buffer(1024)
            size = wt.DWORD(len(buf))
            if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                name = os.path.splitext(os.path.basename(buf.value))[0].lower()
            _kernel32.CloseHandle(handle)
        cache[pid.value] = name
    return pid.value, cache[pid.value]


def list_windows() -> list[Window]:
    """Visible top-level app windows, topmost first (EnumWindows walks the z-order)."""
    found: list[Window] = []
    me, cache = os.getpid(), {}

    def visit(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        ex = _user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
        if ex & _WS_EX_TOOLWINDOW and not ex & _WS_EX_APPWINDOW:
            return True
        if _user32.GetWindow(hwnd, _GW_OWNER) and not ex & _WS_EX_APPWINDOW:
            return True  # dialogs and pop-ups owned by another window
        cloaked = wt.DWORD()
        if _dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), 4) == 0 and cloaked.value:
            return True  # suspended UWP apps and windows on other virtual desktops
        length = _user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, title, length + 1)
        cls = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in _SHELL_CLASSES:
            return True
        pid, exe = _exe_of(hwnd, cache)
        if pid != me:
            found.append(Window(int(hwnd), title.value, exe, cls.value, len(found)))
        return True

    with _dpi_aware():
        _user32.EnumWindows(_WNDENUMPROC(visit), 0)
    return found


def list_monitors() -> list[Monitor]:
    raw: list[tuple[Rect, Rect, bool]] = []

    def visit(hmon, _hdc, _rc, _):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if _user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            raw.append((_rect(info.rcMonitor), _rect(info.rcWork), bool(info.dwFlags & 1)))
        return True

    with _dpi_aware():
        _user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(visit), 0)
    order = order_monitors([(r[0], r[2]) for r in raw])
    return [Monitor(n + 1, raw[i][0], raw[i][1], raw[i][2]) for n, i in enumerate(order)]


def window_score(query: str, win: Window) -> float:
    q = normalize(query)
    if not q:
        return 0.0
    exes = ALIASES.get(q)
    if exes:
        if win.exe in exes and not (win.exe == "explorer" and win.cls != "CabinetWClass"):
            return 100.0
    elif win.exe and fuzz.ratio(q.replace(" ", ""), win.exe) >= 85:
        return fuzz.ratio(q.replace(" ", ""), win.exe)
    title = normalize(win.title)
    if re.search(rf"(?:^|\W){re.escape(q)}(?:\W|$)", title):
        return 90.0
    if len(q) >= 5 and len(q) <= len(title):
        return fuzz.partial_ratio(q, title) * 0.88
    if len(q) >= 5:
        return fuzz.ratio(q, title) * 0.9
    return 0.0


def find_window(query: str, windows: list[Window] | None = None) -> Window | None:
    """Best window for a spoken app name; among equally good matches, the topmost one."""
    windows = list_windows() if windows is None else windows
    q = clean_app_name(query)
    if q == "active":
        return windows[0] if windows else None
    scored = [(window_score(q, w), w) for w in windows]
    scored = [(s, w) for s, w in scored if s >= MATCH_THRESHOLD]
    if not scored:
        return None
    return min(scored, key=lambda sw: (-round(sw[0] / 5), sw[1].z))[1]


def wait_for_window(query: str, before: set[int] | None, timeout: float = 8.0) -> Window | None:
    """Poll for a window that was just launched. A brand-new window wins; an existing one
    is accepted after a short grace period (single-instance apps just bring theirs forward)."""
    start = time.monotonic()
    while True:
        windows = list_windows()
        q = clean_app_name(query)
        fresh = [w for w in windows if before is not None and w.hwnd not in before]
        new = find_window(q, fresh) if fresh else None
        if new is not None:
            time.sleep(0.4)  # let the app finish placing its window before we move it
            return new
        elapsed = time.monotonic() - start
        if before is None or elapsed > 2.0:
            win = find_window(q, windows)
            if win is not None:
                return win
        if elapsed > timeout:
            return None
        time.sleep(0.25)


def snapshot() -> set[int]:
    try:
        return {w.hwnd for w in list_windows()}
    except OSError:
        return set()


# -- operations --------------------------------------------------------------------


def _window_rect(hwnd: int) -> Rect:
    r = wt.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(r))
    return _rect(r)


def _borders(hwnd: int) -> Rect:
    """Invisible resize borders (window rect minus what DWM actually draws)."""
    outer = _window_rect(hwnd)
    r = wt.RECT()
    if _dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        return 0, 0, 0, 0
    return r.left - outer[0], r.top - outer[1], outer[2] - r.right, outer[3] - r.bottom


def _show_state(hwnd: int) -> int:
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(wp)
    _user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
    return wp.showCmd


def _set_rect(hwnd: int, rect: Rect) -> None:
    x, y, w, h = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
    _user32.SetWindowPos(hwnd, None, x, y, w, h, _SWP_NOZORDER | _SWP_NOACTIVATE)
    if _window_rect(hwnd) != rect:  # crossing to a monitor with another DPI makes apps resize themselves
        _user32.SetWindowPos(hwnd, None, x, y, w, h, _SWP_NOZORDER | _SWP_NOACTIVATE)


def _monitor_index(hwnd: int, monitors: list[Monitor]) -> int:
    rect = _window_rect(hwnd)
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    for i, m in enumerate(monitors):
        if m.rect[0] <= cx < m.rect[2] and m.rect[1] <= cy < m.rect[3]:
            return i
    best = max(range(len(monitors)), key=lambda i: _overlap(rect, monitors[i].rect))
    return best


def _overlap(a: Rect, b: Rect) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def focus(hwnd: int) -> bool:
    """Bring a window to the front despite Windows' focus-stealing rules."""
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, _SW_RESTORE)
    if _user32.SetForegroundWindow(hwnd) and _user32.GetForegroundWindow() == hwnd:
        return True
    fg = _user32.GetForegroundWindow()
    fg_thread = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = _kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and _user32.AttachThreadInput(me, fg_thread, True))
    try:
        # Alt down goes to the old window, Alt up to the new one: Windows then counts us as
        # "the last input" and lets us switch, without popping open anyone's menu bar.
        _user32.keybd_event(0x12, 0, 0, 0)  # left Alt (the extended one is AltGr on many layouts)
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
        _user32.keybd_event(0x12, 0, _KEYUP, 0)
    finally:
        if attached:
            _user32.AttachThreadInput(me, fg_thread, False)
    return _user32.GetForegroundWindow() == hwnd


def move_to_monitor(hwnd: int, target: str) -> str | None:
    with _dpi_aware():
        monitors = list_monitors()
        if len(monitors) < 2:
            return "you've only got one monitor"
        current = _monitor_index(hwnd, monitors)
        dest = resolve_target([m.rect for m in monitors], current, target)
        if dest is None:
            where = {"left": "to the left", "right": "to the right"}.get(target, f"number {target}")
            return f"there's no monitor {where}"
        if dest == current:
            return None
        state = _show_state(hwnd)
        maximized = state == _SW_SHOWMAXIMIZED
        if maximized or state == _SW_SHOWMINIMIZED:
            _user32.ShowWindow(hwnd, _SW_RESTORE)
            current = _monitor_index(hwnd, monitors)  # its restored size may live on another monitor
        if current != dest:
            _set_rect(hwnd, scale_rect(_window_rect(hwnd), monitors[current].work, monitors[dest].work))
        if maximized:
            _user32.ShowWindow(hwnd, _SW_MAXIMIZE)
    return None


def snap(hwnd: int, side: str) -> None:
    with _dpi_aware():
        if _show_state(hwnd) != 1:  # SW_SHOWNORMAL
            _user32.ShowWindow(hwnd, _SW_RESTORE)
        monitors = list_monitors()
        work = monitors[_monitor_index(hwnd, monitors)].work
        b = _borders(hwnd)
        half = half_rect(work, side)
        _set_rect(hwnd, (half[0] - b[0], half[1] - b[1], half[2] + b[2], half[3] + b[3]))


def press_keys(mods: list[int], key: int) -> None:
    def ev(vk: int, up: bool) -> None:
        flags = (_EXTENDEDKEY if vk in _EXTENDED else 0) | (_KEYUP if up else 0)
        _user32.keybd_event(vk, 0, flags, 0)

    for vk in mods:
        ev(vk, False)
    ev(key, False)
    ev(key, True)
    for vk in reversed(mods):
        ev(vk, True)


def minimize_all() -> None:
    press_keys([0x5B], 0x44)  # Win+D


def apply(op: str, win: Window, monitor: str = "") -> str | None:
    """Run one window operation. Returns None or a short problem."""
    hwnd = win.hwnd
    if not _user32.IsWindow(hwnd):
        return "that window just disappeared"
    if op == "focus":
        return None if focus(hwnd) else f"Windows wouldn't let me bring {win.title or win.exe} to the front"
    if op == "maximize":
        _user32.ShowWindow(hwnd, _SW_MAXIMIZE)
    elif op == "minimize":
        _user32.ShowWindow(hwnd, _SW_MINIMIZE)
    elif op == "restore":
        _user32.ShowWindow(hwnd, _SW_RESTORE)
    elif op == "close":
        _user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
    elif op == "move":
        return move_to_monitor(hwnd, monitor or "next")
    elif op in ("snap_left", "snap_right"):
        snap(hwnd, op[5:])
    return None
