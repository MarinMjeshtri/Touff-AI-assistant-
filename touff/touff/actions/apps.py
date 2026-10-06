"""Index of everything Touff can open: Start Menu apps, Steam games, known folders, websites."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import winreg
from dataclasses import asdict, dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

from ..brain.text import normalize

MATCH_THRESHOLD = 80

# Start Menu entries nobody wants to open by voice.
_JUNK = re.compile(r"uninstall|readme|read me|help|documentation|release notes|license|website|manual|setup|repair", re.I)
_STEAM_JUNK = re.compile(r"redistributable|steamworks|proton|steam linux runtime|spacewar", re.I)

WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv",
    "reddit": "https://www.reddit.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "instagram": "https://www.instagram.com",
    "tiktok": "https://www.tiktok.com",
    "amazon": "https://www.amazon.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "wikipedia": "https://www.wikipedia.org",
}

# What people say -> what the Start Menu calls it.
NICKNAMES = {
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "code": "visual studio code",
    "explorer": "file explorer",
    "files": "file explorer",
    "my files": "file explorer",
    "edge": "microsoft edge",
    "word": "microsoft word",
    "excel": "microsoft excel",
    "powerpoint": "microsoft powerpoint",
    "teams": "microsoft teams",
    "store": "microsoft store",
    "cmd": "command prompt",
    "terminal": "windows terminal",
    "calc": "calculator",
    "cs": "counter-strike 2",
    "cs2": "counter-strike 2",
    "isaac": "the binding of isaac: rebirth",
    "bloons": "bloons td 6",
    "btd6": "bloons td 6",
}

FOLDERS = {
    "downloads": "Downloads",
    "documents": "Documents",
    "desktop": "Desktop",
    "pictures": "Pictures",
    "photos": "Pictures",
    "music": "Music",
    "videos": "Videos",
}


@dataclass
class App:
    name: str
    kind: str  # "start" (shell:AppsFolder id), "steam" (appid), "url", "folder"
    target: str


class AppIndex:
    def __init__(self, cache_file: Path | None = None):
        self.cache_file = cache_file
        self.apps: list[App] = []
        self._lock = threading.Lock()
        if cache_file and cache_file.exists():
            try:
                self.apps = [App(**a) for a in json.loads(cache_file.read_text(encoding="utf-8"))]
            except (OSError, json.JSONDecodeError, TypeError):
                self.apps = []
        if not self.apps:
            self.apps = self._static_entries()

    # -- building ------------------------------------------------------------

    def refresh(self) -> int:
        """Rescan the system. Takes a second or two (PowerShell), so run it off the UI thread."""
        apps = self._static_entries() + _steam_games() + _start_apps()
        # Steam games also show up as Start Menu shortcuts; keep the Steam entry.
        seen: set[str] = set()
        unique: list[App] = []
        for app in sorted(apps, key=lambda a: {"steam": 0, "start": 1}.get(a.kind, 2)):
            key = normalize(app.name)
            if key and key not in seen:
                seen.add(key)
                unique.append(app)
        with self._lock:
            self.apps = unique
        if self.cache_file:
            self.cache_file.write_text(json.dumps([asdict(a) for a in unique], indent=1), encoding="utf-8")
        return len(unique)

    @staticmethod
    def _static_entries() -> list[App]:
        home = Path.home()
        return [App(name, "url", url) for name, url in WEBSITES.items()] + [
            App(name, "folder", str(home / sub)) for name, sub in FOLDERS.items()
        ]

    # -- lookup --------------------------------------------------------------

    def names(self, kinds: tuple[str, ...] = ("start", "steam")) -> list[str]:
        return [a.name for a in self.apps if a.kind in kinds]

    def find(self, query: str) -> App | None:
        query = normalize(query)
        query = re.sub(r"^(?:the|my|up)\s+", "", query)
        query = re.sub(r"\s+(?:app|application|game|program|folder|website|site)$", "", query)
        if not query:
            return None
        query = NICKNAMES.get(query, query)
        with self._lock:
            apps = list(self.apps)
        names = [normalize(a.name) for a in apps]
        # Exact name wins outright ("x" must not fuzzy-match "xbox").
        if query in names:
            return apps[names.index(query)]
        for name, score, idx in process.extract(query, names, scorer=fuzz.WRatio, score_cutoff=MATCH_THRESHOLD, limit=5):
            # WRatio's partial matching is generous: "spotify and play candy shop" scores 90
            # against "spotify", and 3-letter queries match half the Start Menu.
            if len(query) > len(name) * 1.6 + 4:
                continue
            if len(query) <= 3 and score < 95:
                continue
            return apps[idx]
        return None


# -- scanners -----------------------------------------------------------------


def _start_apps() -> list[App]:
    """Everything in the Start Menu, including Microsoft Store apps (e.g. Spotify from the Store)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        rows = json.loads(out or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []
    if isinstance(rows, dict):
        rows = [rows]
    return [
        App(r["Name"], "start", r["AppID"])
        for r in rows
        if r.get("Name") and r.get("AppID") and not _JUNK.search(r["Name"])
    ]


def steam_root() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        default = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"
        return default if default.exists() else None


def _steam_games() -> list[App]:
    root = steam_root()
    if not root:
        return []
    libraries = {root}
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        for path in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
            libraries.add(Path(path.replace("\\\\", "\\")))
    games = []
    for lib in libraries:
        for manifest in (lib / "steamapps").glob("appmanifest_*.acf"):
            text = manifest.read_text(encoding="utf-8", errors="ignore")
            appid = re.search(r'"appid"\s+"(\d+)"', text)
            name = re.search(r'"name"\s+"([^"]+)"', text)
            if appid and name and not _STEAM_JUNK.search(name.group(1)):
                games.append(App(name.group(1), "steam", appid.group(1)))
    return games
