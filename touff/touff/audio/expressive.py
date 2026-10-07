"""Client for the GPU worker (voice_server.py running in the voice pack's Python, see voicepack.py).

GpuServer owns the process. ExpressiveVoice and RemoteSTT sit on top of it with the
same interfaces as the CPU versions (tts.Voice / stt.STT), so the assistant doesn't
care where the work happens.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import subprocess
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

from .. import voicepack
from ..store import models_dir

SERVER = voicepack.SERVER

# Tags the Turbo model performs. Everything else in [brackets] gets stripped
# so it isn't read out loud.
EMOTION_TAGS = ["happy", "angry", "sarcastic", "crying", "whispering", "dramatic", "surprised", "fear"]
SOUND_TAGS = ["laugh", "chuckle", "sigh", "sniff", "gasp", "groan", "cough", "clear throat", "shush"]
_KNOWN = set(EMOTION_TAGS + SOUND_TAGS)
_TAG = re.compile(r"\[([a-z ]+)\]")
_SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=\S)")


def available() -> bool:
    return voicepack.installed()


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


class GpuServer:
    def __init__(self, tts: bool, stt_model: str | None, clip: str = ""):
        env = dict(os.environ, HF_HOME=str(models_dir() / "hf"), HF_HUB_DISABLE_PROGRESS_BARS="1", PYTHONIOENCODING="utf-8")
        cmd = [
            str(voicepack.python_path()), str(SERVER),
            "--engine", "turbo" if tts else "none",
            "--stt", stt_model or "none",
            "--models", str(models_dir() / "whisper-gpu"),
        ]
        if clip:
            cmd += ["--clip", clip]
        with voicepack.clean_dll_search():
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        hello = self.proc.stdout.readline()  # blocks while models load (~20 s; first run downloads several GB)
        if not hello:
            raise RuntimeError("GPU voice server failed to start")
        info = json.loads(hello)
        self.rate = int(info.get("sr") or 0)
        self.has_tts = bool(info.get("tts"))
        self.has_stt = bool(info.get("stt"))
        self._next_id = 0
        self._id_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._results: dict[int, queue.Queue] = {}
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            q = self._results.pop(msg.get("id"), None)
            if q is not None:
                q.put(msg)

    def request(self, payload: dict) -> queue.Queue:
        with self._id_lock:
            self._next_id += 1
            rid = self._next_id
        q: queue.Queue = queue.Queue()
        self._results[rid] = q
        self.send({**payload, "id": rid})
        return q

    def send(self, payload: dict) -> None:
        with self._write_lock:
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            self.send({"cmd": "quit"})
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


class RemoteSTT:
    """Whisper large-v3-turbo on the GPU: much better ears than the small CPU model."""

    def __init__(self, server: GpuServer):
        self.server = server

    def transcribe(self, pcm16: bytes, hint: str = "") -> str:
        msg = self.server.request({"cmd": "stt", "pcm": base64.b64encode(pcm16).decode("ascii"), "hint": hint}).get(timeout=30)
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg["text"]


class ExpressiveVoice:
    """Same interface as tts.Voice: speak(text), stop(), .level, .speed, .volume.

    Sentences are synthesized one after another while earlier ones already play,
    so she starts talking after the first sentence, not the whole reply.
    """

    def __init__(self, server: GpuServer, volume: float = 1.0):
        self.server = server
        self.volume = volume
        self.speed = 1.0  # Turbo has no speed control; kept for interface parity
        self.level = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._stop.set()

    def speak(self, text: str) -> None:
        text = clean_tags(text)
        if not _TAG.sub("", text).strip():
            return
        with self._lock:
            self._stop.clear()
            pending = [self.server.request({"text": s}) for s in split_sentences(text)]  # worked through in order
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
        self.server.send({"cmd": "clip", "path": path})
