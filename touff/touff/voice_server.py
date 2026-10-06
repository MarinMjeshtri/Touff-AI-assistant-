"""GPU worker: expressive voice (Chatterbox Turbo) + speech recognition (Whisper large-v3-turbo).

Runs inside the separate GPU environment (.venv-voice). Kept out of the main app on
purpose: PyTorch + models are several GB and need the GPU, while Touff itself should
stay tiny. Talks JSON lines over stdin/stdout:

  <- {"ready": true, "sr": 24000, "tts": true, "stt": true}     once models are loaded
  -> {"id": 1, "text": "[angry] No way!"}                         synthesize a line
  <- {"id": 1, "path": "...wav"}  or  {"id": 1, "error": "..."}
  -> {"id": 2, "cmd": "stt", "pcm": "<base64 int16 16 kHz mono>", "hint": "Touff, open Chrome."}
  <- {"id": 2, "text": "open chrome on my second monitor"}
  -> {"cmd": "clip", "path": "my_voice.wav"}                      clone a voice from a clip ("" = default)

Speech recognition and synthesis run on separate threads, so hearing the user never
waits behind a sentence being generated. Standalone: imports nothing from touff.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import sys
import tempfile
import threading
import traceback

# Libraries print progress bars and warnings to stdout; keep stdout for the protocol.
_proto = sys.stdout
sys.stdout = sys.stderr
_send_lock = threading.Lock()

# Things Whisper famously "hears" in silence or noise.
HALLUCINATIONS = {
    "thank you", "thanks for watching", "thank you for watching", "you", "bye", "",
    "subtitles by the amara.org community", "please subscribe", "thank you very much",
}


def send(msg: dict) -> None:
    with _send_lock:
        _proto.write(json.dumps(msg) + "\n")
        _proto.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["turbo", "original", "none"], default="turbo")
    parser.add_argument("--stt", default="large-v3-turbo", help="Whisper model, or 'none'")
    parser.add_argument("--models", default="", help="folder for Whisper downloads")
    parser.add_argument("--clip", default="")
    args = parser.parse_args()

    import numpy as np
    import torch  # also puts CUDA/cuDNN DLLs on the path for ctranslate2

    device = "cuda" if torch.cuda.is_available() else "cpu"

    tts = None
    if args.engine != "none":
        if args.engine == "turbo":
            from chatterbox.tts_turbo import ChatterboxTurboTTS as Model
        else:
            from chatterbox.tts import ChatterboxTTS as Model
        tts = Model.from_pretrained(device=device)
        if args.clip and os.path.exists(args.clip):
            tts.prepare_conditionals(args.clip)
    default_conds = tts.conds if tts else None

    stt = None
    if args.stt != "none":
        from faster_whisper import WhisperModel

        stt = WhisperModel(
            args.stt, device=device, compute_type="int8_float16" if device == "cuda" else "int8",
            download_root=args.models or None,
        )
        stt.transcribe(np.zeros(16000, dtype=np.float32), language="en")  # warm up

    out_dir = tempfile.mkdtemp(prefix="touff_voice_")
    tts_q: queue.Queue = queue.Queue()
    stt_q: queue.Queue = queue.Queue()

    def tts_worker() -> None:
        import torchaudio

        while True:
            req = tts_q.get()
            rid = req.get("id")
            try:
                if req.get("cmd") == "clip":
                    tts.conds = default_conds
                    if req.get("path"):
                        tts.prepare_conditionals(req["path"])
                    send({"cmd": "clip", "ok": True})
                    continue
                kwargs = {}
                if args.engine == "original":
                    kwargs = {k: req[k] for k in ("exaggeration", "cfg_weight", "temperature") if k in req}
                with torch.inference_mode():
                    wav = tts.generate(req["text"], **kwargs)
                path = os.path.join(out_dir, f"{rid}.wav")
                torchaudio.save(path, wav.cpu(), tts.sr)
                send({"id": rid, "path": path})
            except Exception as exc:
                traceback.print_exc()
                send({"id": rid, "error": str(exc)})

    def stt_worker() -> None:
        while True:
            req = stt_q.get()
            rid = req.get("id")
            try:
                pcm = np.frombuffer(base64.b64decode(req["pcm"]), dtype=np.int16).astype(np.float32) / 32768.0
                segments, _ = stt.transcribe(
                    pcm, language="en", beam_size=5, initial_prompt=req.get("hint") or None,
                    condition_on_previous_text=False, without_timestamps=True,
                )
                text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6).strip()
                if text.lower().strip(" .!?,") in HALLUCINATIONS:
                    text = ""
                send({"id": rid, "text": text})
            except Exception as exc:
                traceback.print_exc()
                send({"id": rid, "error": str(exc)})

    if tts:
        threading.Thread(target=tts_worker, daemon=True).start()
    if stt:
        threading.Thread(target=stt_worker, daemon=True).start()
    send({"ready": True, "sr": tts.sr if tts else 0, "tts": tts is not None, "stt": stt is not None, "device": device})

    for line in sys.stdin:
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        cmd = req.get("cmd")
        if cmd == "quit":
            break
        if cmd == "stt":
            if stt:
                stt_q.put(req)
            else:
                send({"id": req.get("id"), "error": "speech recognition not loaded"})
        elif tts:
            tts_q.put(req)
        else:
            send({"id": req.get("id"), "error": "voice not loaded"})


if __name__ == "__main__":
    main()
