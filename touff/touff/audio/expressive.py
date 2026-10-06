"""Client for the expressive GPU voice (voice_server.py in .venv-voice).

Same interface as tts.Voice: speak(text), stop(), .level, .speed, .volume.
Sentences are synthesized one after another while earlier ones already play,
so she starts talking after the first sentence is ready, not the whole reply.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

from ..store import PROJECT_ROOT, models_dir

VOICE_PYTHON = PROJECT_ROOT / ".venv-voice" / "Scripts" / "python.exe"
SERVER = Path(__file__).resolve().parents[1] / "voice_server.py"

# Tags the Turbo model performs. Everything else in [brackets] gets stripped
# so it isn't read out loud.
EMOTION_TAGS = ["happy", "angry", "sarcastic", "crying", "whispering", "dramatic", "surprised", "fear"]
SOUND_TAGS = ["laugh", "chuckle", "sigh", "sniff", "gasp", "groan", "cough", "clear throat", "shush"]
_KNOWN = set(EMOTION_TAGS + SOUND_TAGS)
_TAG = re.compile(r"\[([a-z ]+)\]")
_SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=\S)")


def available() -> bool:
    return VOICE_PYTHON.exists()


def clean_tags(text: str) -> str:
    """Drop tags the model doesn't know (and fix spacing)."""
    text = _TAG.sub(lambda m: m.group(0) if m.group(1) in _KNOWN else "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    """Split for streaming, carrying the opening emotion tag onto every sentence."""
    text = text.strip()
    lead = _TAG.match(text)
    emotion = lead.group(0) if lead and lead.group(1) in EMOTION_TAGS else ""
    chunks: list[str] = []
    for part in (p.strip() for p in _SENTENCE.split(text)):
        if not part:
            continue
        # Tiny fragments ("No!") sound odd alone: glue them to the next sentence.
        if chunks and len(_TAG.sub("", chunks[-1]).strip()) < 12:
            chunks[-1] += " " + part
        else:
            chunks.append(part)
    return [c if i == 0 or not emotion or c.startswith("[") else f"{emotion} {c}" for i, c in enumerate(chunks)]


class ExpressiveVoice:
    def __init__(self, clip: str = "", volume: float = 1.0, status: Callable[[str], None] | None = None):
        self.volume = volume
        self.speed = 1.0  # Turbo has no speed control; kept for interface parity
        self.level = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._next_id = 0
        self._results: dict[int, queue.Queue] = {}
        env = dict(os.environ, HF_HOME=str(models_dir() / "hf"), HF_HUB_DISABLE_PROGRESS_BARS="1", PYTHONIOENCODING="utf-8")
        cmd = [str(VOICE_PYTHON), str(SERVER), "--engine", "turbo"]
        if clip:
            cmd += ["--clip", clip]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        hello = self.proc.stdout.readline()  # blocks while the model loads (~15 s, first run downloads ~1.5 GB)
        if not hello:
            raise RuntimeError("expressive voice failed to start")
        self.rate = int(json.loads(hello)["sr"])
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            q = self._results.get(msg.get("id"))
            if q is not None:
                q.put(msg)

    def _request(self, text: str) -> queue.Queue:
        self._next_id += 1
        q: queue.Queue = queue.Queue()
        self._results[self._next_id] = q
        self.proc.stdin.write(json.dumps({"id": self._next_id, "text": text}) + "\n")
        self.proc.stdin.flush()
        return q

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self) -> None:
        self._stop.set()

    def speak(self, text: str) -> None:
        text = clean_tags(text)
        if not _TAG.sub("", text).strip():
            return
        with self._lock:
            self._stop.clear()
            pending = [self._request(s) for s in split_sentences(text)]  # server works through them in order
            for q in pending:
                msg = q.get(timeout=60)
                if self._stop.is_set():
                    continue
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                audio, rate = sf.read(msg["path"], dtype="float32")
                os.remove(msg["path"])
                self._play(audio * self.volume, rate)
            self.level = 0.0

    def _play(self, audio: np.ndarray, rate: int) -> None:
        if audio.ndim > 1:
            audio = audio[:, 0]
        with sd.OutputStream(samplerate=rate, channels=1, dtype="float32") as out:
            for i in range(0, len(audio), 1024):
                if self._stop.is_set():
                    return
                block = np.clip(audio[i : i + 1024], -1, 1)
                self.level = min(1.0, float(np.sqrt(np.mean(block * block))) * 6)
                out.write(block.reshape(-1, 1))

    def set_clip(self, path: str) -> None:
        self.proc.stdin.write(json.dumps({"cmd": "clip", "path": path}) + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        try:
            self.proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            self.proc.stdin.flush()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
