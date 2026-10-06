"""Touff's voice: Piper neural TTS, offline. Plus a little wake-up chime."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd


class Voice:
    def __init__(self, onnx_path: Path, speed: float = 1.0, volume: float = 1.0):
        from piper import PiperVoice

        self.voice = PiperVoice.load(str(onnx_path))
        self.rate = self.voice.config.sample_rate
        self.speed = speed
        self.volume = volume
        self.level = 0.0  # loudness of what's being said right now, for the pop-up's mouth
        self._stop = threading.Event()
        self._lock = threading.Lock()  # one sentence at a time

    def stop(self) -> None:
        self._stop.set()

    def speak(self, text: str, on_level: Callable[[float], None] | None = None) -> None:
        from piper import SynthesisConfig

        from ..brain.text import strip_tags

        text = strip_tags(text)  # Piper would read "[laugh]" out loud
        if not text:
            return
        config = SynthesisConfig(length_scale=1.0 / max(0.5, min(2.0, self.speed)), volume=self.volume)
        with self._lock:
            self._stop.clear()
            with sd.OutputStream(samplerate=self.rate, channels=1, dtype="float32") as out:
                for chunk in self.voice.synthesize(text, config):
                    audio = chunk.audio_float_array.astype(np.float32)
                    for i in range(0, len(audio), 1024):  # small blocks: interruptible + level for the blob
                        if self._stop.is_set():
                            return
                        block = audio[i : i + 1024]
                        self.level = min(1.0, float(np.sqrt(np.mean(block * block))) * 6)
                        if on_level:
                            on_level(self.level)
                        out.write(block.reshape(-1, 1))
        self.level = 0.0
        if on_level:
            on_level(0.0)


def chime(kind: str = "wake", volume: float = 0.25) -> None:
    """Two soft bell notes: up for wake, down for 'done listening'."""
    rate = 24000
    notes = (880.0, 1318.5) if kind == "wake" else (1046.5, 784.0)
    parts = []
    for freq in notes:
        t = np.linspace(0, 0.11, int(rate * 0.11), endpoint=False)
        env = np.exp(-t * 18)  # plucky decay
        tone = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t)
        parts.append((tone * env).astype(np.float32))
    sd.play(np.concatenate(parts) * volume, rate)
