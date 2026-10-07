"""Download the speech models on first run. Nothing here is committed to git."""

from __future__ import annotations

import contextlib
import fnmatch
import logging
import os
import re
import shutil
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Iterator

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
            mark = int(done * 20 / total) * 5 if total else (done >> 20) // 10 * 10  # every 5% / 10 MB
            if progress and mark != last:
                progress(f"Downloading {label}... {mark}%" if total else f"Downloading {label}... {mark} MB")
                last = mark
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
            _fetch(PIPER_URL.format(ext=ext, **fields), dest, "my voice", progress if ext == ".onnx" else None)
    return onnx


def folder_size(folder: Path) -> int:
    total = 0
    for f in folder.rglob("*") if folder.exists() else ():
        try:
            if f.is_file() and not f.is_symlink():
                total += _live_size(f)
        except OSError:  # renamed mid-download
            pass
    return total


def _live_size(f: Path) -> int:
    try:  # an open handle knows the real size; path-based stat can lag for files being written
        with f.open("rb") as fh:
            return os.fstat(fh.fileno()).st_size
    except OSError:  # locked by the writer
        return f.stat().st_size


@contextlib.contextmanager
def watch_download(folder: Path, label: str, total: int, progress: Progress | None) -> Iterator[None]:
    """Report progress while a library that has no callback downloads into `folder`."""
    if progress is None:
        yield
        return
    start, stop = folder_size(folder), threading.Event()

    def watch() -> None:
        last = -1
        while not stop.wait(1.0):
            done = folder_size(folder) - start
            mark = min(99, int(done * 100 / total)) if total else (done >> 20) // 100 * 100  # 1% / 100 MB steps
            if mark != last:
                progress(f"Downloading {label}... {mark}%" if total else f"Downloading {label}... {mark} MB")
                last = mark

    progress(f"Downloading {label}...")
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


WHISPER_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]  # as faster-whisper


def hf_size(repo: str, patterns: list[str]) -> int:
    """Download size of the matching files of a Hugging Face repo (0 if unknown)."""
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repo, files_metadata=True, timeout=10)
        return sum(f.size or 0 for f in info.siblings if any(fnmatch.fnmatch(f.rfilename, p) for p in patterns))
    except Exception:
        return 0


HF_URL = "https://huggingface.co/{repo}/resolve/main/{name}?download=true"


def whisper_path(size: str, progress: Progress | None = None) -> str:
    target = models_dir() / f"whisper-{size}"
    if (target / "model.bin").exists():  # already here: don't ping Hugging Face on every start
        return str(target)
    from faster_whisper.utils import _MODELS

    repo = _MODELS.get(size, size)
    try:
        from huggingface_hub import list_repo_files

        names = [n for n in list_repo_files(repo) if any(fnmatch.fnmatch(n, p) for p in WHISPER_FILES)]
    except Exception:
        names = []
    if "model.bin" not in names:  # can't list the repo: let faster-whisper fetch it its own way
        from faster_whisper import download_model

        return download_model(size, output_dir=str(target))
    # Fetched ourselves for real byte progress. The weights go last: they mark it complete.
    target.mkdir(parents=True, exist_ok=True)
    for name in sorted(names, key=lambda n: n == "model.bin"):
        _fetch(HF_URL.format(repo=repo, name=name), target / name, "speech recognition", progress if name == "model.bin" else None)
    return str(target)


def ensure_all(voice: str, whisper: str, progress: Progress | None = None) -> None:
    """Everything the CPU path needs (~550 MB): wake word, Piper voice, Whisper. The Piper
    voice and CPU Whisper are also the fallbacks of the GPU voice pack, so they're always
    fetched up front instead of in the middle of a conversation."""
    vosk_path(progress)
    voice_path(voice, progress)
    whisper_path(whisper, progress)
