"""Persistent user data: config, custom commands, memories and history.

Everything is plain JSON in %APPDATA%\\Touff so it can be edited by hand too.
Set TOUFF_HOME to point the whole data directory somewhere else (tests do this).
In the installed app (PyInstaller build) big models go to %LOCALAPPDATA%\\Touff instead.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

DEFAULT_CONFIG: dict[str, Any] = {
    "name": "Touff",
    # Words the wake-word engine listens for. The name itself is often not in the
    # speech model's vocabulary, so sound-alike words are listened for as well.
    "wake_words": ["tough", "tuff", "toff"],
    "voice_engine": "auto",  # "auto" | "expressive" (GPU, Chatterbox Turbo) | "piper" (light, CPU)
    "voice_clip": "",  # wav to clone for the expressive voice; "" = built-in voice
    "voice": "en_GB-jenny_dioco-medium",  # Piper voice
    "speech_speed": 1.0,
    "volume": 1.0,
    "brain": "claude",  # "claude" (Claude Code CLI) or "offline"
    "claude_model": "haiku",
    "stt_engine": "auto",  # "auto"/"gpu" (Whisper large-v3-turbo in the GPU worker) or "cpu"
    "gpu_whisper_model": "large-v3-turbo",
    "whisper_model": "small.en",  # CPU fallback
    "mic_device": None,
    "silence_ms": 1200,
    "max_listen_s": 12,
    "chime": True,
    "popup": True,
    "start_with_windows": False,
    # Developer settings
    "feisty_mode": False,
    "feisty_level": 35,  # % of locally understood requests she gets to argue about
    "feisty_swearing": False,
    "dev_unlocked": False,
    "save_recordings": False,  # keep the last 30 utterances as .wav in %APPDATA%\Touff\recordings
    "config_version": 2,
}

DEFAULT_COMMANDS: list[dict[str, Any]] = [
    {
        "id": "example-music",
        "name": "Music time",
        "phrases": ["music time", "drop the beat"],
        "actions": [{"type": "open_app", "arg": "Spotify"}, {"type": "media", "arg": "play_pause"}],
        "reply": "Music time!",
    },
]

DEFAULT_MEMORIES: dict[str, Any] = {
    "glossary": [],  # [{"term": "the sack", "meaning": "The Binding of Isaac"}]
    "notes": [],  # ["I prefer YouTube over Spotify for podcasts"]
}

HISTORY_LIMIT = 200


def data_dir() -> Path:
    base = os.environ.get("TOUFF_HOME") or os.path.join(os.environ.get("APPDATA", str(Path.home())), "Touff")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


# Installed app (PyInstaller build) vs. running from a source checkout.
FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # frozen: the bundle folder (sys._MEIPASS)


def local_dir() -> Path:
    """%LOCALAPPDATA%\\Touff: machine-local bulk data of the installed app (models, voice pack)."""
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Touff"


def models_dir() -> Path:
    """Big downloaded models. Running from source they live next to the code (git-ignored),
    which also keeps them out of AppData folders that sandboxed launchers redirect."""
    if os.environ.get("TOUFF_HOME"):
        path = Path(os.environ["TOUFF_HOME"]) / "models"
    elif not FROZEN and (PROJECT_ROOT / "pyproject.toml").exists():
        path = PROJECT_ROOT / "models"
    else:
        path = local_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_id() -> str:
    return uuid.uuid4().hex[:10]


class Store:
    """Thread-safe owner of all user data. Listeners fire after every save."""

    def __init__(self, root: Path | None = None):
        self.root = root or data_dir()
        self._lock = threading.RLock()
        self._listeners: list[Callable[[str], None]] = []
        self.config = self._load("config.json", DEFAULT_CONFIG)
        # Fill in keys added in newer versions without clobbering user values.
        self._migrate()
        for key, value in DEFAULT_CONFIG.items():
            self.config.setdefault(key, copy.deepcopy(value))
        self.commands = self._load("commands.json", DEFAULT_COMMANDS)
        self.memories = self._load("memories.json", DEFAULT_MEMORIES)
        for key, value in DEFAULT_MEMORIES.items():
            self.memories.setdefault(key, copy.deepcopy(value))
        self.history = self._load("history.json", [])

    def _migrate(self) -> None:
        """Move old installs onto new defaults, but only where the user never changed them."""
        version = self.config.get("config_version", 1)
        if version < 2:
            if self.config.get("silence_ms") == 800:  # cut people off mid-sentence
                self.config["silence_ms"] = 1200
            if self.config.get("whisper_model") == "base.en":  # too weak
                self.config["whisper_model"] = "small.en"
        self.config["config_version"] = DEFAULT_CONFIG["config_version"]

    # -- persistence -------------------------------------------------------

    def _load(self, filename: str, default: Any) -> Any:
        path = self.root / filename
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # Keep the broken file around instead of silently losing it.
                path.replace(path.with_suffix(".broken.json"))
        return copy.deepcopy(default)

    def _save(self, filename: str, data: Any) -> None:
        path = self.root / filename
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def on_change(self, listener: Callable[[str], None]) -> None:
        self._listeners.append(listener)

    def _changed(self, what: str) -> None:
        for listener in list(self._listeners):
            try:
                listener(what)
            except Exception:  # a broken listener must not break saving
                pass

    # -- config --------------------------------------------------------------

    def update_config(self, changes: dict[str, Any]) -> None:
        with self._lock:
            self.config.update({k: v for k, v in changes.items() if k in DEFAULT_CONFIG})
            self._save("config.json", self.config)
        self._changed("config")

    # -- commands ------------------------------------------------------------

    def set_commands(self, commands: list[dict[str, Any]]) -> None:
        with self._lock:
            cleaned = []
            for cmd in commands:
                phrases = [p.strip() for p in cmd.get("phrases", []) if p and p.strip()]
                if not phrases:
                    continue
                cleaned.append(
                    {
                        "id": cmd.get("id") or new_id(),
                        "name": (cmd.get("name") or phrases[0]).strip(),
                        "phrases": phrases,
                        "actions": [
                            {"type": a["type"], "arg": str(a.get("arg", ""))}
                            for a in cmd.get("actions", [])
                            if a.get("type")
                        ],
                        "reply": (cmd.get("reply") or "").strip(),
                    }
                )
            self.commands = cleaned
            self._save("commands.json", self.commands)
        self._changed("commands")

    def add_command(self, phrases: list[str], actions: list[dict[str, str]], reply: str = "", name: str = "") -> dict:
        cmd = {"id": new_id(), "name": name or phrases[0], "phrases": phrases, "actions": actions, "reply": reply}
        self.set_commands(self.commands + [cmd])
        return cmd

    # -- memories ------------------------------------------------------------

    def set_memories(self, memories: dict[str, Any]) -> None:
        with self._lock:
            glossary = [
                {"term": g["term"].strip(), "meaning": g["meaning"].strip()}
                for g in memories.get("glossary", [])
                if g.get("term", "").strip() and g.get("meaning", "").strip()
            ]
            notes = [n.strip() for n in memories.get("notes", []) if n and n.strip()]
            self.memories = {"glossary": glossary, "notes": notes}
            self._save("memories.json", self.memories)
        self._changed("memories")

    def add_glossary(self, term: str, meaning: str) -> None:
        glossary = [g for g in self.memories["glossary"] if g["term"].lower() != term.lower()]
        glossary.append({"term": term, "meaning": meaning})
        self.set_memories({**self.memories, "glossary": glossary})

    def add_note(self, text: str) -> None:
        self.set_memories({**self.memories, "notes": self.memories["notes"] + [text]})

    # -- history -------------------------------------------------------------

    def log(self, heard: str, said: str, actions: list[dict[str, str]], source: str) -> None:
        with self._lock:
            self.history.append(
                {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "heard": heard, "said": said, "actions": actions, "source": source}
            )
            self.history = self.history[-HISTORY_LIMIT:]
            self._save("history.json", self.history)
        self._changed("history")
