"""One always-open microphone stream, shared by the wake word and the recorder."""

from __future__ import annotations

import collections
import queue
import threading

import numpy as np
import sounddevice as sd
import webrtcvad

RATE = 16000
FRAME = 480  # 30 ms, a frame size webrtcvad accepts
FRAME_MS = 30


class Mic:
    def __init__(self, device: int | str | None = None):
        self.device = device
        self.frames: queue.Queue[bytes] = queue.Queue(maxsize=400)
        self.level = 0.0  # 0..1, for the pop-up animation
        self.muted = threading.Event()  # set while Touff talks, so she doesn't hear herself
        self.stream: sd.RawInputStream | None = None

    def start(self) -> None:
        self.stream = sd.RawInputStream(
            samplerate=RATE, blocksize=FRAME, dtype="int16", channels=1, device=self.device, callback=self._callback
        )
        self.stream.start()

    def stop(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def _callback(self, indata, _frames, _time, _status) -> None:
        data = bytes(indata)
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0
        self.level = min(1.0, rms * 12)
        if self.muted.is_set():
            return
        try:
            self.frames.put_nowait(data)
        except queue.Full:  # nobody is reading; drop the oldest audio
            try:
                self.frames.get_nowait()
                self.frames.put_nowait(data)
            except queue.Empty:
                pass

    def read(self, timeout: float = 0.5) -> bytes | None:
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        while not self.frames.empty():
            try:
                self.frames.get_nowait()
            except queue.Empty:
                break


def record_utterance(
    mic: Mic,
    preroll: list[bytes] | None = None,
    silence_ms: int = 800,
    max_seconds: float = 12,
    start_timeout: float = 5,
    should_stop=lambda: False,
) -> bytes | None:
    """Record until the speaker pauses. Returns None if nobody said anything."""
    vad = webrtcvad.Vad(2)
    audio = list(preroll or [])
    # Speech in the pre-roll (e.g. "Touff, open..." said in one breath) counts.
    voiced = sum(1 for f in audio[-10:] if _is_speech(vad, f))
    heard_speech = voiced >= 3
    silent_frames = 0
    max_frames = int(max_seconds * 1000 / FRAME_MS)
    start_frames = int(start_timeout * 1000 / FRAME_MS)
    needed_silence = int(silence_ms / FRAME_MS)
    ring = collections.deque(maxlen=8)

    for i in range(max_frames):
        if should_stop():
            return None
        frame = mic.read(timeout=1.0)
        if frame is None:
            continue
        audio.append(frame)
        speech = _is_speech(vad, frame)
        ring.append(speech)
        if not heard_speech:
            if sum(ring) >= 4:  # ~120 ms of speech in the last 240 ms
                heard_speech = True
            elif i > start_frames:
                return None
            continue
        silent_frames = 0 if speech else silent_frames + 1
        if silent_frames >= needed_silence:
            break
    return b"".join(audio) if heard_speech else None


def _is_speech(vad: webrtcvad.Vad, frame: bytes) -> bool:
    try:
        return vad.is_speech(frame, RATE)
    except Exception:
        return False


def list_devices() -> list[dict]:
    out = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and dev["hostapi"] == sd.default.hostapi:
            out.append({"id": idx, "name": dev["name"]})
    return out
