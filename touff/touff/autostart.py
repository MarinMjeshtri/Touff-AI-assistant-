"""Start Touff when Windows starts (HKCU Run key, no admin needed)."""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "Touff"
FLAG = "--background"  # at login she goes straight to the tray; a manual launch opens settings


def _command() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller build
        return f'"{sys.executable}" {FLAG}'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m touff {FLAG}'


def set_enabled(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, _NAME)
            except FileNotFoundError:
                pass


def is_enabled() -> bool:
    """Whether a Run entry exists (the installer's "Start Touff with Windows" box sets one too)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
            winreg.QueryValueEx(key, _NAME)
            return True
    except OSError:
        return False


def with_background_flag(value: str) -> str:
    """A Run value from before --background existed -> the same command with it."""
    value = value.strip()
    return value if FLAG in value.split() else f"{value} {FLAG}"


def upgrade() -> None:
    """Add --background to an existing Run entry (made by an older Touff or installer), so
    logging in doesn't pop the settings window up. Keeps whatever exe the entry points at,
    so a dev checkout never takes over the installed app's entry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            value, kind = winreg.QueryValueEx(key, _NAME)
            if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(value, str) and value.strip():
                new = with_background_flag(value)
                if new != value:
                    winreg.SetValueEx(key, _NAME, 0, kind, new)
    except OSError:
        pass
