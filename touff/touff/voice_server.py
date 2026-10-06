"""Expressive voice worker. Runs inside the separate GPU environment (.venv-voice).

Kept out of the main app on purpose: PyTorch + Chatterbox are ~3 GB and need the
GPU, while Touff itself should stay tiny. Talks JSON lines over stdin/stdout:

  <- {"ready": true, "sr": 24000}                      once the model is loaded
  -> {"id": 1, "text": "[angry] No way!"}              synthesize a line
  <- {"id": 1, "path": "...wav"}  or  {"id": 1, "error": "..."}
  -> {"cmd": "clip", "path": "my_voice.wav"}           clone a voice from a clip ("" = default)
  <- {"cmd": "clip", "ok": true}

Standalone on purpose: it must not import anything from the touff package.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback

# Libraries print progress bars and warnings to stdout; keep stdout for the protocol.
_proto = sys.stdout
sys.stdout = sys.stderr


def send(msg: dict) -> None:
    _proto.write(json.dumps(msg) + "\n")
    _proto.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["turbo", "original"], default="turbo")
    parser.add_argument("--clip", default="")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    import torch
    import torchaudio

    device = args.device if (args.device != "cuda" or torch.cuda.is_available()) else "cpu"
    if args.engine == "turbo":
        from chatterbox.tts_turbo import ChatterboxTurboTTS as Model
    else:
        from chatterbox.tts import ChatterboxTTS as Model
    model = Model.from_pretrained(device=device)
    if args.clip and os.path.exists(args.clip):
        model.prepare_conditionals(args.clip)
    default_conds = model.conds

    out_dir = tempfile.mkdtemp(prefix="touff_voice_")
    send({"ready": True, "sr": model.sr, "device": device, "engine": args.engine})

    for line in sys.stdin:
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if req.get("cmd") == "quit":
            break
        if req.get("cmd") == "clip":
            try:
                if req.get("path"):
                    model.prepare_conditionals(req["path"])
                else:
                    model.conds = default_conds
                send({"cmd": "clip", "ok": True})
            except Exception as exc:
                send({"cmd": "clip", "ok": False, "error": str(exc)})
            continue
        rid = req.get("id")
        try:
            kwargs = {}
            if args.engine == "original":
                kwargs = {k: req[k] for k in ("exaggeration", "cfg_weight", "temperature") if k in req}
            with torch.inference_mode():
                wav = model.generate(req["text"], **kwargs)
            path = os.path.join(out_dir, f"{rid}.wav")
            torchaudio.save(path, wav.cpu(), model.sr)
            send({"id": rid, "path": path})
        except Exception as exc:
            traceback.print_exc()
            send({"id": rid, "error": str(exc)})


if __name__ == "__main__":
    main()
