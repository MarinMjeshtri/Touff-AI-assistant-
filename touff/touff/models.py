"""Download the speech models on first run. Nothing here is committed to git."""

from __future__ import annotations

import logging
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .store import models_dir

log = logging.getLogger(__name__)

VOSK_MODEL = "vosk-model-small-en-us-0.15"
VOSK_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL}.zip"

# Voices offered in settings: (id, description). All free Piper voices.
VOICES = [
    ("en_GB-jenny_dioco-medium", "Jenny - British, friendly (default)"),
    ("en_GB-cori-high", "Cori - British, clear, high quality"),
    ("en_GB-alba-medium", "Alba - Scottish"),
    ("en_US-amy-medium", "Amy - American"),
    ("en_US-hfc_female-medium", "HFC - American, bright"),
    ("en_US-kristin-medium", "Kristin - American, calm"),
    ("en_US-lessac-medium", "Lessac - American, classic"),
    ("en_GB-alan-medium", "Alan - British man (very butler)"),
    ("en_US-ryan-high", "Ryan - American man"),
]


PIPER_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/{family}/{code}/{name}/{quality}/{voice}{ext}?download=true"

Progress = Callable[[str], None]


def _fetch(url: str, dest: Path, label: str, progress: Progress | None = None) -> Path:
    """Stream a download to disk, reporting progress, and only keep it if it finished."""
    partial = dest.with_name(dest.name + ".partial")
    req = urllib.request.Request(url, headers={"User-Agent": "touff/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp, partial.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last = 0, -1
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            pct = int(done * 100 / total) if total else -1
            if progress and pct != last and pct % 5 == 0:
                progress(f"Downloading {label}... {pct}%" if pct >= 0 else f"Downloading {label}... {done >> 20} MB")
                last = pct
    partial.replace(dest)
    return dest


def vosk_path(progress: Progress | None = None) -> Path:
    target = models_dir() / VOSK_MODEL
    if not target.exists():
        zipped = models_dir() / (VOSK_MODEL + ".zip")
        _fetch(VOSK_URL, zipped, "my ears", progress)
        with zipfile.ZipFile(zipped) as zf:
            tmp = models_dir() / (VOSK_MODEL + ".partial")
            shutil.rmtree(tmp, ignore_errors=True)
            zf.extractall(tmp)
            (tmp / VOSK_MODEL).replace(target)
            shutil.rmtree(tmp, ignore_errors=True)
        zipped.unlink()
    return target


def voice_path(voice: str, progress: Progress | None = None) -> Path:
    m = re.match(r"^(?P<family>[a-z]+)_(?P<region>[A-Z]+)-(?P<name>[^-]+)-(?P<quality>.+)$", voice)
    if not m:
        raise ValueError(f"not a Piper voice id: {voice}")
    folder = models_dir() / "voices"
    folder.mkdir(exist_ok=True)
    onnx = folder / f"{voice}.onnx"
    fields = dict(family=m["family"], code=f'{m["family"]}_{m["region"]}', name=m["name"], quality=m["quality"], voice=voice)
    for ext in (".onnx.json", ".onnx"):
        dest = folder / f"{voice}{ext}"
        if not dest.exists() or dest.stat().st_size == 0:
            _fetch(PIPER_URL.format(ext=ext, **fields), dest, "my voice", progress)
    return onnx


def whisper_path(size: str) -> str:
    from faster_whisper import download_model

    return download_model(size, output_dir=str(models_dir() / f"whisper-{size}"))


def ensure_all(voice: str, whisper: str, progress: Progress | None = None) -> None:
    vosk_path(progress)
    voice_path(voice, progress)
    if progress:
        progress("Downloading speech recognition (~145 MB)...")
    whisper_path(whisper)
