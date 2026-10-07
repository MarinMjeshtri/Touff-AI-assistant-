"""Listens for the assistant's name with a tiny offline Vosk model.

The recognizer gets a grammar of just the wake words plus "[unk]", which makes it
cheap (a few % of one core) and lets the name be changed without any training.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import vosk

vosk.SetLogLevel(-1)


# Weak floor only: "tough" and "tuff" sound identical, so Vosk splits its confidence
# between them (~0.5 each even for a clear call). The Whisper check does the real filtering.
MIN_CONF = 0.3
GREETINGS = ("hey", "hi", "ok", "okay", "yo", "hello")
SETTLE_FRAMES = 8  # after a partial hit, listen ~240 ms more before judging


class WakeWord:
    def __init__(self, model_dir: Path, words: list[str]):
        self.model = vosk.Model(str(model_dir))
        self.preroll: collections.deque[bytes] = collections.deque(maxlen=67)  # last 2 s
        self.last_conf = 0.0
        self._candidate = -1  # frames left before judging a partial hit, -1 = none
        self.set_words(words)

    def set_words(self, words: list[str]) -> None:
        cleaned = {w.lower().strip() for w in words if w and w.strip()}
        known = sorted(w for w in cleaned if self.knows(w))
        self.words = set(known)
        self.unknown = sorted(cleaned - self.words)
        # Vosk matches whole phrases, so "hey touff" must be its own phrase or it turns into [unk].
        grammar = known + [f"{g} {w}" for w in known for g in GREETINGS if self.knows(g)] + ["[unk]"]
        self.rec = vosk.KaldiRecognizer(self.model, 16000, json.dumps(grammar))
        self.rec.SetWords(True)  # per-word confidence in final results
        self._candidate = -1

    def knows(self, phrase: str) -> bool:
        """Whether every word of `phrase` is in the model's vocabulary (otherwise Vosk ignores it)."""
        return all(self.model.vosk_model_find_word(w) >= 0 for w in phrase.split())

    def feed(self, frame: bytes) -> bool:
        """Feed 30 ms of audio. True when the name was heard *confidently*.

        A partial hit only makes a candidate; ~240 ms later the recognizer is forced to
        finalize, and the name word must come back with high confidence. Music full of
        "tough"-ish syllables mostly fails here; the assistant double-checks the rest."""
        self.preroll.append(frame)
        if not self.words:
            return False
        if self.rec.AcceptWaveform(frame):
            return self._judge(json.loads(self.rec.Result()))
        if self._candidate > 0:
            self._candidate -= 1
            if self._candidate == 0:
                return self._judge(json.loads(self.rec.FinalResult()))
            return False
        partial = json.loads(self.rec.PartialResult()).get("partial", "")
        if any(w in self.words for w in partial.split()):
            self._candidate = SETTLE_FRAMES
        return False

    def _judge(self, result: dict) -> bool:
        self._candidate = -1
        confs = [w.get("conf", 0.0) for w in result.get("result", []) if w.get("word") in self.words]
        self.last_conf = max(confs, default=0.0)
        if self.last_conf >= MIN_CONF:
            self.rec.Reset()
            return True
        return False

    def take_preroll(self) -> list[bytes]:
        frames = list(self.preroll)
        self.preroll.clear()
        return frames

    def reset(self) -> None:
        self.rec.Reset()
        self.preroll.clear()
        self._candidate = -1


    def suggest(self, name: str, limit: int = 4) -> list[str]:
        """Sound-alike spellings of `name` that the model does know ("touff" -> tough, tuff, toff)."""
        return [w for w in soundalikes(name) if self.knows(w)][:limit]


_SWAPS = [
    ("ough", "uff"), ("ou", "u"), ("ou", "oo"), ("oo", "u"), ("u", "oo"), ("ff", "f"), ("f", "ff"),
    ("uff", "ough"), ("ph", "f"), ("f", "ph"), ("c", "k"), ("k", "c"), ("ck", "k"), ("y", "ie"),
    ("ie", "y"), ("i", "y"), ("y", "i"), ("ee", "ea"), ("ea", "ee"), ("z", "s"), ("s", "z"),
    ("x", "ks"), ("qu", "kw"), ("o", "a"), ("a", "o"), ("e", ""), ("", "e"),
]


def soundalikes(name: str) -> list[str]:
    """Cheap spelling variants for a made-up name. Not phonetics, but good enough to find neighbours."""
    base = name.lower().strip()
    seen = [base]
    frontier = [base]
    for _ in range(2):  # variants of variants
        nxt = []
        for word in frontier:
            for old, new in _SWAPS:
                if old == "":
                    cand = word + new
                elif old in word:
                    cand = word.replace(old, new, 1)
                else:
                    continue
                if cand and cand not in seen:
                    seen.append(cand)
                    nxt.append(cand)
        frontier = nxt
    return seen
