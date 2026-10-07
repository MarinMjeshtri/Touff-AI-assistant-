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

With --download-only it just fetches the model weights and exits (voice pack install).

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


def _cached_snapshot(repo_id: str) -> str | None:
    """Local folder of an already-downloaded Hugging Face model, if complete enough to load."""
    home = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    snaps = os.path.join(home, "hub", "models--" + repo_id.replace("/", "--"), "snapshots")
    if not os.path.isdir(snaps):
        return None
    for name in sorted(os.listdir(snaps), key=lambda n: os.path.getmtime(os.path.join(snaps, n)), reverse=True):
        path = os.path.join(snaps, name)
        if any(f.endswith(".safetensors") for f in os.listdir(path)) and os.path.exists(os.path.join(path, "conds.pt")):
            return path
    return None


def send(msg: dict) -> None:
    with _send_lock:
        _proto.write(json.dumps(msg) + "\n")
        _proto.flush()


def download(args: argparse.Namespace) -> None:
    """Fetch the weights the next real start will load, so that start doesn't wait for GBs."""
    if args.engine == "turbo":
        from chatterbox.tts_turbo import REPO_ID
        from huggingface_hub import snapshot_download

        print("Downloading Chatterbox Turbo...", flush=True)
        snapshot_download(repo_id=REPO_ID, allow_patterns=["*.safetensors", "*.json", "*.txt", "*.pt", "*.model"])
    if args.stt != "none":
        from faster_whisper import download_model

        print(f"Downloading Whisper {args.stt}...", flush=True)
        download_model(args.stt, cache_dir=args.models or None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["turbo", "original", "none"], default="turbo")
    parser.add_argument("--stt", default="large-v3-turbo", help="Whisper model, or 'none'")
    parser.add_argument("--models", default="", help="folder for Whisper downloads")
    parser.add_argument("--clip", default="")
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    if args.download_only:
        download(args)
        return

    import numpy as np
    import torch  # also puts CUDA/cuDNN DLLs on the path for ctranslate2

    device = "cuda" if torch.cuda.is_available() else "cpu"

    def load_tts():
        if args.engine == "none":
            return None
        if args.engine == "turbo":
            from chatterbox.tts_turbo import REPO_ID, ChatterboxTurboTTS as Model
        else:
            from chatterbox.tts import REPO_ID, ChatterboxTTS as Model
        # Already downloaded? Load straight from disk instead of asking Hugging Face first.
        local = _cached_snapshot(REPO_ID)
        model = Model.from_local(local, device) if local and hasattr(Model, "from_local") else Model.from_pretrained(device=device)
        if args.clip and os.path.exists(args.clip):
            model.prepare_conditionals(args.clip)
        return model

    def load_stt():
        if args.stt == "none":
            return None
        from faster_whisper import WhisperModel

        kwargs = dict(device=device, compute_type="int8_float16" if device == "cuda" else "int8", download_root=args.models or None)
        try:
            model = WhisperModel(args.stt, local_files_only=True, **kwargs)
        except Exception:  # not downloaded yet
            model = WhisperModel(args.stt, **kwargs)
        model.transcribe(np.zeros(16000, dtype=np.float32), language="en")  # warm up
        return model

    # Load the voice and the ears side by side: startup is the slower of the two, not the sum.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(2) as pool:
        tts_job, stt_job = pool.submit(load_tts), pool.submit(load_stt)
        tts, stt = tts_job.result(), stt_job.result()
    default_conds = tts.conds if tts else None

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
