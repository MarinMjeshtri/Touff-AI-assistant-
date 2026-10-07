"""The whitelist of things Touff is allowed to do, and the code that does them.

Neither the local brain nor Claude can run anything that isn't in ACTIONS.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
import webbrowser
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable
from urllib.parse import quote_plus

from . import windows
from .apps import AppIndex

if TYPE_CHECKING:
    from ..store import Store


@dataclass(frozen=True)
class ActionSpec:
    description: str
    arg: str
    risky: bool = False


ACTIONS: dict[str, ActionSpec] = {
    "open_app": ActionSpec("Open an installed app, Steam game, website or folder by its name", "app/game/site name"),
    "open_steam_game": ActionSpec("Launch a Steam game (starts Steam if needed)", "Steam appid or game name"),
    "open_url": ActionSpec("Open a web address in the browser", "URL"),
    "google_search": ActionSpec("Search Google", "search query"),
    "youtube_search": ActionSpec("Show YouTube search results (only when the user wants to browse results)", "search query"),
    "youtube_play": ActionSpec(
        "Open and play one specific YouTube video directly: a channel's newest upload, or the top result for a search",
        "latest:<channel name> | <search query>",
    ),
    "spotify_search": ActionSpec("Open Spotify on a search for a song/artist/playlist", "search query"),
    "media": ActionSpec("Control whatever music/video is playing", "play_pause | next | previous | stop"),
    "volume": ActionSpec("Change the system volume", "up | down | mute"),
    "window": ActionSpec(
        "Manage an app's window. Operations: focus (bring to front; opens the app if it isn't running), maximize, "
        "minimize, restore, close (politely, the app may ask to save), move (to another monitor), snap_left / snap_right "
        "(left/right half of its monitor), minimize_all (show the desktop, no app needed). Monitors: 1 = primary, "
        "others numbered left to right; also next/other, previous, left, right. App 'active' = the frontmost window. "
        "Works right after open_app in the same reply (waits for the window to appear)",
        "operation:app[:monitor], e.g. move:chrome:2 | move:discord:next | maximize:spotify | focus:vs code | "
        "snap_left:chrome | close:notepad | minimize:active | minimize_all:",
    ),
    "hotkey": ActionSpec(
        "Press a keyboard shortcut in whatever window is in front (win+r and win+x are blocked)",
        "keys joined with +, e.g. ctrl+t | ctrl+shift+esc | win+shift+s | alt+tab | alt+f4 | f5 | space",
    ),
    "timer": ActionSpec("Start a countdown; Touff announces when it's done", "number of seconds"),
    "run_command": ActionSpec("Run one of the user's custom commands", "custom command name"),
    "open_settings": ActionSpec("Open Touff's own settings window (not the Windows Settings app)", "(empty)"),
    "lock_pc": ActionSpec("Lock the computer", "(empty)", risky=True),
    "sleep_pc": ActionSpec("Put the computer to sleep", "(empty)", risky=True),
    "shutdown_pc": ActionSpec("Shut the computer down (30 second grace period)", "(empty)", risky=True),
}

_VK = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
    "mute": 0xAD,
    "down": 0xAE,
    "up": 0xAF,
}


def _press(vk: int, times: int = 1) -> None:
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP


def _startfile(target: str) -> None:
    os.startfile(target)  # type: ignore[attr-defined]  # Windows only


def is_risky(actions: list[dict[str, str]]) -> bool:
    return any(ACTIONS.get(a.get("type", ""), ActionSpec("", "")).risky for a in actions)


def valid(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    """Drop anything that isn't on the whitelist (e.g. an action Claude invented)."""
    return [{"type": a["type"], "arg": str(a.get("arg", ""))} for a in actions if a.get("type") in ACTIONS]


class Executor:
    def __init__(self, apps: AppIndex, store: "Store", announce: Callable[[str], None]):
        self.apps = apps
        self.store = store
        self.announce = announce  # speak something later (timers)
        self.timers: list[threading.Timer] = []
        self._opened: tuple[float, set[int]] | None = None  # when the last app was launched, and the windows before it
        self.on_open_settings: Callable[[], None] | None = None  # set by the desktop app (no window in --console/--text)

    def run(self, actions: list[dict[str, str]], depth: int = 0) -> list[str]:
        """Run actions in order. Returns problems worth telling the user about."""
        problems = []
        for action in valid(actions):
            if action["type"] in ("open_app", "open_steam_game"):
                self._opened = (time.monotonic(), windows.snapshot())  # so a following "window" can find the new one
            handler = getattr(self, f"_do_{action['type']}")
            try:
                problem = handler(action["arg"].strip(), depth) if action["type"] == "run_command" else handler(action["arg"].strip())
            except Exception as exc:  # never let one action kill the assistant
                problem = f"{action['type']} failed: {exc}"
            if problem:
                problems.append(problem)
        return problems

    # -- handlers (return None on success, or a short problem description) --

    def _do_open_app(self, name: str) -> str | None:
        if name.lower().startswith(("http://", "https://")):
            return self._do_open_url(name)
        app = self.apps.find(name)
        if app is None:
            if "." in name and " " not in name:  # "open reddit.com"
                return self._do_open_url(name)
            return f"I couldn't find anything called {name}"
        if app.kind == "steam":
            _startfile(f"steam://rungameid/{app.target}")
        elif app.kind == "start":
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app.target}"])
        elif app.kind == "url":
            webbrowser.open(app.target)
        elif app.kind == "folder":
            _startfile(app.target)
        return None

    def _do_open_steam_game(self, arg: str) -> str | None:
        if arg.isdigit():
            _startfile(f"steam://rungameid/{arg}")
            return None
        return self._do_open_app(arg)

    def _do_open_url(self, url: str) -> str | None:
        if not url:
            return "no web address given"
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return None

    def _do_google_search(self, query: str) -> str | None:
        webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
        return None

    def _do_youtube_play(self, arg: str) -> str | None:
        from . import youtube

        latest = arg.lower().startswith("latest:")
        query = arg.split(":", 1)[1].strip() if latest else arg
        try:
            video = youtube.latest_video(query) if latest else youtube.top_video(query)
        except Exception:  # offline, YouTube changed its page, unknown channel...
            return self._do_youtube_search(query + (" newest video" if latest else ""))
        webbrowser.open(video.url)
        return None

    def _do_youtube_search(self, query: str) -> str | None:
        webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(query))
        return None

    def _do_spotify_search(self, query: str) -> str | None:
        if self.apps.find("spotify") is not None:
            _startfile("spotify:search:" + quote_plus(query).replace("+", "%20"))
        else:
            webbrowser.open("https://open.spotify.com/search/" + quote_plus(query).replace("+", "%20"))
        return None

    def _do_media(self, what: str) -> str | None:
        what = {"play": "play_pause", "pause": "play_pause", "resume": "play_pause", "skip": "next", "back": "previous"}.get(what, what)
        if what not in ("play_pause", "next", "previous", "stop"):
            return f"unknown media control {what}"
        _press(_VK[what])
        return None

    def _do_volume(self, what: str) -> str | None:
        if what not in ("up", "down", "mute"):
            return f"unknown volume change {what}"
        _press(_VK[what], 1 if what == "mute" else 5)  # each press is 2%
        return None

    def _do_timer(self, seconds: str) -> str | None:
        try:
            secs = max(1, int(float(seconds)))
        except ValueError:
            return f"{seconds} isn't a number of seconds"
        label = _describe_duration(secs)
        timer = threading.Timer(secs, self.announce, args=(f"Ding ding! Your {label} timer is done.",))
        timer.daemon = True
        timer.start()
        self.timers.append(timer)
        return None

    def _do_run_command(self, name: str, depth: int) -> str | None:
        if depth > 2:  # commands that call commands that call...
            return "that command loops back on itself"
        wanted = name.lower()
        for cmd in self.store.commands:
            if cmd["name"].lower() == wanted or cmd["id"] == name or wanted in (p.lower() for p in cmd["phrases"]):
                problems = self.run(cmd["actions"], depth + 1)
                return "; ".join(problems) or None
        return f"there's no custom command called {name}"

    def _do_window(self, arg: str) -> str | None:
        try:
            op, app, monitor = windows.parse_window_arg(arg)
        except ValueError as err:
            return str(err)
        if op == "minimize_all":
            windows.minimize_all()
            return None
        opened = self._opened
        if opened and time.monotonic() - opened[0] < 20 and app != "active":
            win = windows.wait_for_window(app, opened[1])  # the app may still be starting
            self._opened = None if win else opened  # found it: later actions needn't wait
        else:
            win = windows.find_window(app)
        if win is None:
            if op in ("focus", "restore"):  # "switch to spotify" when it isn't running: open it
                return self._do_open_app(app)
            return f"I can't see a {app} window"
        return windows.apply(op, win, monitor)

    def _do_hotkey(self, combo: str) -> str | None:
        try:
            mods, key = windows.parse_hotkey(combo)
        except (ValueError, PermissionError) as err:
            return str(err)
        windows.press_keys(mods, key)
        return None

    def _do_open_settings(self, _: str) -> str | None:
        if self.on_open_settings is None:
            return "my settings window isn't open in this mode"
        self.on_open_settings()
        return None

    def _do_lock_pc(self, _: str) -> str | None:
        ctypes.windll.user32.LockWorkStation()
        return None

    def _do_sleep_pc(self, _: str) -> str | None:
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return None

    def _do_shutdown_pc(self, _: str) -> str | None:
        # 30s grace period; "shutdown /a" in a terminal cancels it.
        subprocess.Popen(["shutdown", "/s", "/t", "30"])
        return None


def _describe_duration(secs: int) -> str:
    if secs % 3600 == 0:
        n, unit = secs // 3600, "hour"
    elif secs % 60 == 0:
        n, unit = secs // 60, "minute"
    else:
        n, unit = secs, "second"
    return f"{n} {unit}"
