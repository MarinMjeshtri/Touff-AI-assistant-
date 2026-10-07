"""The optional expressive voice pack: Chatterbox voice + Whisper large on an NVIDIA GPU.

PyTorch and the models are ~10 GB together, so they never ship with the app. The pack is a
separate Python environment that runs voice_server.py (see audio/expressive.py):

  installed app   %LOCALAPPDATA%\\Touff\\voice-pack\\{python,venv}, built on demand with the bundled uv.exe
  source checkout touff\\.venv-voice (scripts\\setup.ps1 -Expressive does the same thing)
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .store import FROZEN, PROJECT_ROOT, local_dir, models_dir

PYTHON_VERSION = "3.12"
TORCH = ["torch==2.6.0", "torchaudio==2.6.0"]
TORCH_INDEX = "https://download.pytorch.org/whl/cu124"
PACKAGES = ["chatterbox-tts", "faster-whisper"]
MARKER = "touff-voice-pack.json"  # written after the packages, so a half-finished install doesn't count
CHATTERBOX_REPO = "ResembleAI/chatterbox-turbo"  # only for the download size estimate
# Run by the pack's own Python, never imported: shipped as a plain file in the build.
SERVER = Path(__file__).resolve().parent / "voice_server.py"

Progress = Callable[[str], None]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class VoicePackError(Exception):
    """Install refused or failed; the message is meant for the user."""


def root() -> Path:
    return local_dir() / "voice-pack" if FROZEN else PROJECT_ROOT


def venv_dir() -> Path:
    return root() / ("venv" if FROZEN else ".venv-voice")


def python_dir() -> Path:
    """Where uv puts the portable Python the pack's venv is built on."""
    return root() / ("python" if FROZEN else ".python")


def python_path() -> Path:
    return venv_dir() / "Scripts" / "python.exe"


def installed() -> bool:
    # A source checkout's .venv-voice predates the marker: there the interpreter is enough.
    return python_path().exists() and (not FROZEN or (venv_dir() / MARKER).exists())


@contextlib.contextmanager
def clean_dll_search():
    """Start child processes without the frozen app's DLL folder in their search path.

    PyInstaller points the DLL search at its bundle folder, and Windows hands that to
    child processes: the voice pack's own Python could then load our bundled DLLs
    (torch / CUDA mismatches). Clear it while spawning, then put it back."""
    if not FROZEN:
        yield
        return
    k32 = ctypes.windll.kernel32
    buf = ctypes.create_unicode_buffer(32768)
    had = k32.GetDllDirectoryW(len(buf), buf)
    k32.SetDllDirectoryW(None)
    try:
        yield
    finally:
        if had:
            k32.SetDllDirectoryW(buf.value)


def gpu_name() -> str | None:
    """Name of the first NVIDIA GPU, or None when there isn't one (or no driver)."""
    exe = shutil.which("nvidia-smi") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    names = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    return names[0] if out.returncode == 0 and names else None


def uv_path() -> Path | None:
    """The uv.exe shipped inside the installed app, else the one on PATH."""
    if FROZEN:
        bundled = PROJECT_ROOT / "uv.exe"  # PROJECT_ROOT is the bundle folder when frozen
        if bundled.exists():
            return bundled
    found = shutil.which("uv")
    return Path(found) if found else None


def install(progress: Progress, dry_run: bool = False, whisper: str = "large-v3-turbo") -> Path:
    """Build the GPU environment and fetch its models (~10 GB download). Returns the pack's python.exe.

    Blocks for a long time: run it on a worker thread. `progress` gets one-line status
    updates (step headers, uv's own output, download percentages). Raises VoicePackError
    with a friendly message when there is no NVIDIA GPU, no uv, or a step fails. With
    dry_run the GPU check is real, but the commands are only reported.
    """
    gpu = gpu_name()
    if not gpu:
        raise VoicePackError(
            "The expressive voice needs an NVIDIA graphics card, and I can't find one here. "
            "No worries, my lightweight voice works everywhere!"
        )
    uv = uv_path()
    if not uv:
        raise VoicePackError("I can't find uv.exe to build the voice pack with. Reinstalling Touff should fix that.")
    progress(f"Found {gpu}. Building the voice pack in {root()}")

    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=str(python_dir()), PYTHONIOENCODING="utf-8")
    env.pop("VIRTUAL_ENV", None)
    py = python_path()

    def run(step: str, *cmd: str | Path, env: dict = env) -> None:
        progress(step)
        cmd = tuple(str(c) for c in cmd)
        if dry_run:
            progress("  would run: " + " ".join(cmd))
            return
        with clean_dll_search():
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", env=env, creationflags=_NO_WINDOW,
            )
        for line in proc.stdout:
            if line.strip():
                progress("  " + line.rstrip())
        if proc.wait():
            raise VoicePackError(f"{step.split(':')[0]} failed (exit code {proc.returncode}). Check your internet and try again.")

    run("1/5: Python " + PYTHON_VERSION, uv, "python", "install", PYTHON_VERSION)
    base = _find_python() or (python_dir() / f"cpython-{PYTHON_VERSION}" / "python.exe")
    if not dry_run and not base.exists():
        raise VoicePackError("Python didn't install properly. Try again?")
    run("2/5: Voice environment", uv, "venv", venv_dir(), "--python", base, "--allow-existing")
    run("3/5: PyTorch for your GPU (about 2.5 GB, grab a snack)", uv, "pip", "install", "--python", py, *TORCH, "--index-url", TORCH_INDEX)
    run("4/5: Chatterbox voice and Whisper ears", uv, "pip", "install", "--python", py, *PACKAGES)
    if not dry_run:
        (venv_dir() / MARKER).write_text(json.dumps({"torch": TORCH, "packages": PACKAGES, "gpu": gpu}), encoding="utf-8")

    # Fetch the weights now, so her first start with the new voice doesn't sit on GBs of downloads.
    from faster_whisper.utils import _MODELS

    from .models import WHISPER_FILES, hf_size, watch_download

    models = models_dir()
    total = 0 if dry_run else hf_size(CHATTERBOX_REPO, ["*.safetensors", "*.json", "*.txt", "*.pt", "*.model"]) + hf_size(_MODELS.get(whisper, whisper), WHISPER_FILES)
    model_env = dict(env, HF_HOME=str(models / "hf"), HF_HUB_DISABLE_PROGRESS_BARS="1")
    try:
        with watch_download(models, "voice models", total, None if dry_run else progress):
            run("5/5: Voice and ears models (about 5 GB)", py, SERVER, "--download-only", "--engine", "turbo",
                "--stt", whisper, "--models", models / "whisper-gpu", env=model_env)
    except VoicePackError:
        progress("Couldn't fetch the voice models now; they'll download the first time she uses the new voice.")
    progress("Dry run: nothing was installed." if dry_run else "Voice pack ready!")
    return py


def _find_python() -> Path | None:
    folder = python_dir()
    if not folder.exists():
        return None
    found = sorted(p for p in folder.glob(f"cpython-{PYTHON_VERSION}*/python.exe"))
    return found[-1] if found else None
