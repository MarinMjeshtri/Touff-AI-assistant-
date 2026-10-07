"""Desktop shell: the pop-up blob, the settings window and the tray icon.

Windows are pywebview (Edge WebView2, already part of Windows 11), so the UI is
plain HTML/CSS/JS without shipping a browser.
"""

from __future__ import annotations

import json
import logging
import random
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import webview

from .. import autostart
from ..actions import windows as win32
from ..actions.registry import ACTIONS
from ..brain.claude_cli import BrainError
from ..audio.expressive import available as expressive_available
from ..brain.text import strip_tags
from ..models import VOICES

if TYPE_CHECKING:
    from ..assistant import Assistant

log = logging.getLogger(__name__)
WEB = Path(__file__).parent / "web"
POPUP_W, POPUP_H = 380, 190
SETTINGS_TITLE = "Touff settings"
SETTINGS_MIN = (720, 520)

GREETINGS = [
    "[happy] {name} online. Missed me?",
    "[happy] Hi! Just say {name} when you need me.",
    "[dramatic] {name} is awake... and slightly caffeinated. [laugh]",
    "[happy] Hello hello! {name}, reporting for duty.",
    "[sigh] Ugh, fine, I'm up. What do you need?",
]


class PopupUI:
    """Implements the Assistant's UI protocol on top of the pop-up window."""

    def __init__(self, app: "DesktopApp"):
        self.app = app
        self.state = "idle"
        self._gen = 0  # bumps on every show, so stale hide timers do nothing
        self.visible = False

    def _js(self, script: str) -> None:
        win = self.app.popup
        if win is not None:
            try:
                win.evaluate_js(script)
            except Exception:  # window not ready yet / closing
                pass

    def show(self, state: str) -> None:
        self._gen += 1
        self.state = state
        if not self.app.store.config.get("popup", True):
            return
        self._js(f"setState({json.dumps(state)})")
        if not self.visible:
            self.visible = True
            self.app.place_popup()
            self.app.popup.show()

    def heard(self, text: str) -> None:
        self._js(f"setHeard({json.dumps(text)})")

    def said(self, text: str) -> None:
        self._js(f"setSaid({json.dumps(text)})")

    def status(self, text: str) -> None:
        self._js(f"setStatus({json.dumps(text)})")

    def hide(self, delay: float = 0) -> None:
        gen = self._gen

        def later() -> None:
            time.sleep(delay)
            if gen != self._gen:
                return
            self._js("fadeOut()")
            time.sleep(0.35)
            if gen == self._gen and self.visible:
                self.visible = False
                self.state = "idle"
                self.app.popup.hide()

        threading.Thread(target=later, daemon=True).start()


class Api:
    """Everything the settings page can call (window.pywebview.api.*)."""

    def __init__(self, app: "DesktopApp"):
        self._app = app
        self._pack: dict[str, Any] = {"state": "idle", "log": [], "message": ""}

    @property
    def _a(self) -> "Assistant":
        return self._app.assistant

    def get_all(self) -> dict[str, Any]:
        a, store = self._a, self._app.store
        wake = None
        if a.wake is not None:
            wake = {"listening_for": sorted(a.wake.words), "unknown": a.wake.unknown}
        from ..audio.mic import list_devices

        try:
            mics = list_devices()
        except Exception:
            mics = []
        return {
            "config": store.config,
            "commands": store.commands,
            "memories": store.memories,
            "history": list(reversed(store.history[-80:])),
            "apps": [{"name": x.name, "kind": x.kind} for x in sorted(a.apps.apps, key=lambda x: x.name.lower())],
            "voices": [{"id": v, "label": label} for v, label in VOICES],
            "actions": {k: {"description": s.description, "arg": s.arg, "risky": s.risky} for k, s in ACTIONS.items()},
            "mics": mics,
            "wake": wake,
            "brain_installed": a.brain.available,
            "expressive_installed": expressive_available(),
            "voice_engine_active": "expressive" if type(a.voice).__name__ == "ExpressiveVoice" else "piper",
            "voice_pack": self.voice_pack_status(),
            "ready": a.ready.is_set(),
        }

    def save_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        store = self._app.store
        voice_keys = ("voice", "voice_engine", "voice_clip", "stt_engine")
        old = {k: store.config.get(k) for k in voice_keys}
        store.update_config(changes)
        if "start_with_windows" in changes:
            autostart.set_enabled(bool(changes["start_with_windows"]))
        if any(k in changes and changes[k] != old[k] for k in voice_keys) and self._a.ready.is_set():
            threading.Thread(target=self._swap_voice, daemon=True).start()
        return self.get_all()

    def _swap_voice(self) -> None:
        self._a.change_voice()
        self._a.speak(random.choice(["[happy] How do I sound?", "New voice, who dis? [laugh]", "Testing, testing. [gasp] Ooh, I like this."]))

    def save_commands(self, commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._app.store.set_commands(commands)
        return self._app.store.commands

    def save_memories(self, memories: dict[str, Any]) -> dict[str, Any]:
        self._app.store.set_memories(memories)
        return self._app.store.memories

    def try_text(self, text: str) -> dict[str, Any]:
        """Type instead of talk: runs the full pipeline and speaks the answer."""
        reply = self._a.handle_text(text)
        if self._a.ready.is_set():
            threading.Thread(target=self._a.speak, args=(reply.say,), daemon=True).start()
        return {"say": reply.say, "actions": reply.actions, "source": reply.source}

    def run_actions(self, actions: list[dict[str, str]]) -> list[str]:
        return self._a.executor.run(actions)

    def suggest_wake(self, name: str) -> list[str]:
        if self._a.wake is None:
            return []
        return self._a.wake.suggest(name)

    def rescan_apps(self) -> int:
        return self._a.apps.refresh()

    def check_brain(self) -> str:
        try:
            out = self._a.brain.ask("Say hi in five words or less.", [])
            return f"Connected! Claude says: {out.say}"
        except BrainError as err:
            return {
                "not_installed": "Claude Code isn't installed.",
                "not_logged_in": "Claude Code isn't logged in. Open a terminal, run `claude`, and log in once.",
                "timeout": "Claude took too long to answer.",
            }.get(err.reason, f"Something went wrong: {err}")

    # -- expressive voice pack (GPU), installed on demand ------------------------

    def voice_pack_status(self) -> dict[str, Any]:
        return {**self._pack, "log": self._pack["log"][-6:], "installed": expressive_available()}

    def install_voice_pack(self) -> dict[str, Any]:
        if self._pack["state"] != "installing":
            self._pack = {"state": "installing", "log": ["Starting..."], "message": ""}
            threading.Thread(target=self._install_pack, daemon=True).start()
        return self.voice_pack_status()

    def _install_pack(self) -> None:
        from .. import voicepack

        def progress(line: str) -> None:
            self._pack["log"].append(line.strip()[:160])
            del self._pack["log"][:-40]

        try:
            voicepack.install(progress, whisper=self._app.store.config.get("gpu_whisper_model", "large-v3-turbo"))
        except voicepack.VoicePackError as exc:
            self._pack.update(state="error", message=str(exc))
            return
        except Exception as exc:  # network hiccups, disk full...
            log.exception("voice pack install failed")
            self._pack.update(state="error", message=f"Something went wrong: {exc}")
            return
        self._pack.update(state="done", message="Installed! Switching to my new voice...")
        if self._a.ready.is_set():
            self._swap_voice()

    def talk_now(self) -> None:
        self._a.talk_now.set()

    def preview_voice(self, text: str) -> None:
        if self._a.ready.is_set():
            threading.Thread(target=self._a.speak, args=(text,), daemon=True).start()

    # -- frameless settings window chrome (custom title bar buttons + resize grip) --

    def minimize_settings(self) -> None:
        if self._app.settings is not None:
            self._app.settings.minimize()

    def hide_settings(self) -> None:
        """The title bar's close button: hide only, Touff keeps running in the tray."""
        if self._app.settings is not None:
            self._app.settings.hide()

    def resize_settings(self, width: int, height: int) -> None:
        if self._app.settings is not None:
            self._app.settings.resize(max(SETTINGS_MIN[0], int(width)), max(SETTINGS_MIN[1], int(height)))


class DesktopApp:
    def __init__(self, assistant: "Assistant", show_settings: bool = False):
        self.assistant = assistant
        self.store = assistant.store
        self.popup = None
        self.settings = None
        self.tray = None
        self.ui = PopupUI(self)
        self.show_settings_on_start = show_settings  # a manual launch: open the window she lives in
        self.ready = threading.Event()  # the GUI loop is running and the windows exist
        self._opening = threading.Lock()
        assistant.ui = self.ui
        assistant.executor.on_open_settings = self.open_settings  # "open your settings" by voice

    # -- windows ---------------------------------------------------------------

    def place_popup(self) -> None:
        try:
            screen = webview.screens[0]
            self.popup.move(screen.width - POPUP_W - 16, screen.height - POPUP_H - 60)
        except Exception:
            pass

    def open_settings(self) -> None:
        """Show settings in front of the user: on the monitor under the mouse, restored, focused.
        Safe from any thread (tray, voice loop, a second launch)."""
        if not self.ready.wait(60) or self.settings is None:
            return
        with self._opening:
            hwnd = self._settings_hwnd()  # 0 until the first show: WinForms creates the window lazily
            was_visible = bool(hwnd) and win32.is_visible(hwnd)
            self.settings.show()
            try:
                self.settings.restore()  # in case it was minimized from the custom title bar
            except Exception:
                pass
            for _ in range(20):
                hwnd = hwnd or self._settings_hwnd()
                if hwnd:
                    break
                time.sleep(0.05)
            if hwnd:
                try:
                    # Already open on the monitor she's looking at? Leave it where she put it.
                    win32.center_under_cursor(hwnd, unless_already_there=was_visible)
                    if not win32.focus(hwnd):
                        log.info("Windows wouldn't let the settings window come to the front")
                except Exception:
                    log.exception("couldn't place the settings window")
            self._round_corners()
            try:
                self.settings.evaluate_js("reload()")
            except Exception:
                pass

    def open_settings_async(self) -> None:
        threading.Thread(target=self.open_settings, name="open-settings", daemon=True).start()

    @staticmethod
    def _settings_hwnd() -> int:
        try:
            return win32.find_own_window(SETTINGS_TITLE)
        except Exception:
            return 0

    def _keep_settings(self) -> bool:
        """Closing settings just hides it; the assistant keeps running in the tray."""
        threading.Thread(target=self.settings.hide, daemon=True).start()
        return False

    def run(self) -> None:
        api = Api(self)
        self.popup = webview.create_window(
            "Touff", url=str(WEB / "popup.html"), js_api=api, width=POPUP_W, height=POPUP_H,
            frameless=True, transparent=True, on_top=True, hidden=True, focus=False,
            resizable=False, shadow=False, easy_drag=False, background_color="#000000",
        )
        # Frameless: the page draws its own title bar (drag region + minimize/close buttons).
        self.settings = webview.create_window(
            SETTINGS_TITLE, url=str(WEB / "settings.html"), js_api=api, width=980, height=720,
            min_size=SETTINGS_MIN, hidden=True, background_color="#0b0a12",
            frameless=True, easy_drag=False, shadow=True,
        )
        self.settings.events.closing += self._keep_settings
        webview.start(self._boot, debug="--debug" in sys.argv)

    @classmethod
    def _round_corners(cls) -> None:
        """Ask Windows 11 for rounded corners on the frameless settings window (no-op elsewhere)."""
        try:
            import ctypes

            hwnd = cls._settings_hwnd()
            if hwnd:
                pref = ctypes.c_int(2)  # DWMWA_WINDOW_CORNER_PREFERENCE = 33 -> DWMWCP_ROUND
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass

    def _boot(self) -> None:
        self._round_corners()
        self._start_tray()
        self.ready.set()
        threading.Thread(target=self._level_pump, daemon=True).start()
        if self.show_settings_on_start:
            self.open_settings_async()
        self.ui.show("idle")
        self.ui.status("Waking up...")
        try:
            self.assistant.load()
        except Exception as exc:
            log.exception("failed to load models")
            self.ui.show("sassy")
            self.ui.said(f"I couldn't start: {exc}")
            return
        name = self.store.config["name"]
        greeting = random.choice(GREETINGS).format(name=name)
        self.ui.show("speaking")
        self.ui.said(strip_tags(greeting))
        self.assistant.speak(greeting)
        self.ui.hide(1.5)
        self.assistant.run()

    def _level_pump(self) -> None:
        """Feed mic/voice loudness to the blob so it wiggles in time."""
        while not self.assistant.quit.is_set():
            time.sleep(1 / 15)
            if not self.ui.visible:
                continue
            a = self.assistant
            if self.ui.state in ("speaking", "sassy") and a.voice is not None:
                level = a.voice.level
            elif self.ui.state == "listening" and a.mic is not None:
                level = a.mic.level
            else:
                level = 0.0
            self.ui._js(f"lvl({level:.2f})")

    # -- tray ----------------------------------------------------------------

    def _start_tray(self) -> None:
        import pystray

        from .icon import tray_image

        def toggle_mute(icon, item) -> None:
            if self.assistant.paused.is_set():
                self.assistant.paused.clear()
            else:
                self.assistant.paused.set()

        # Left-click runs the default item: opening her is what people expect from a tray icon.
        menu = pystray.Menu(
            pystray.MenuItem("Open Touff", lambda: self.open_settings_async(), default=True),
            pystray.MenuItem("Talk to Touff", lambda: self.assistant.talk_now.set()),
            pystray.MenuItem("Mute mic", toggle_mute, checked=lambda item: self.assistant.paused.is_set()),
            pystray.MenuItem(
                "Silent mode (bubble only)",
                lambda: self.store.update_config({"silent": not self.store.config.get("silent")}),
                checked=lambda item: bool(self.store.config.get("silent")),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.quit()),
        )
        name = self.store.config.get("name") or "Touff"
        self.tray = pystray.Icon("touff", tray_image(), f"Touff: say '{name}' or click to open", menu)
        self.tray.run_detached()

    def quit(self) -> None:
        self.assistant.quit.set()
        if self.assistant.mic:
            self.assistant.mic.stop()
        if self.tray:
            self.tray.stop()
        if hasattr(self.assistant.voice, "close"):
            self.assistant.voice.close()
        self.settings.events.closing -= self._keep_settings
        for win in list(webview.windows):
            win.destroy()
