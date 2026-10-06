"""Speech-to-text with faster-whisper, running locally on the CPU."""

from __future__ import annotations

import os

import numpy as np


class STT:
    def __init__(self, model_path: str):
        from faster_whisper import WhisperModel

        threads = max(2, min(4, (os.cpu_count() or 4) // 2))
        self.model = WhisperModel(model_path, device="cpu", compute_type="int8", cpu_threads=threads)

    def transcribe(self, pcm16: bytes, hint: str = "") -> str:
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=2,
            initial_prompt=hint or None,  # biases spelling towards names/phrases it should know
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
        )
        text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.7).strip()
        return "" if _is_hallucination(text) else text


# Things Whisper famously "hears" in silence or noise.
_HALLUCINATIONS = {
    "thank you", "thanks for watching", "thank you for watching", "you", "bye", ".", "",
    "subtitles by the amara.org community", "please subscribe",
}


def _is_hallucination(text: str) -> bool:
    return text.lower().strip(" .!?,") in _HALLUCINATIONS
