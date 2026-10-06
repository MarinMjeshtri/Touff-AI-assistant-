"""Text clean-up shared by every matching step."""

from __future__ import annotations

import re

_PUNCT = re.compile(r"[^\w\s'&+.:/-]")
_SPACES = re.compile(r"\s+")

# Filler that carries no meaning for command matching.
_LEADING_FILLER = re.compile(
    r"^(?:(?:hey|hi|ok|okay|yo|um+|uh+|so|and|please|could you|can you|would you|will you|"
    r"i want you to|i need you to|go ahead and|just)\s+)+"
)
_TRAILING_FILLER = re.compile(r"(?:\s+(?:please|for me|thanks|thank you|now))+$")


def normalize(text: str) -> str:
    """Lowercase, drop punctuation Whisper likes to add, collapse spaces."""
    text = text.lower().replace("’", "'")
    text = _PUNCT.sub(" ", text)
    # Sentence-ending dots/colons are punctuation; keep them only inside words (google.com).
    text = re.sub(r"[.:](?=\s|$)", " ", text)
    return _SPACES.sub(" ", text).strip()


def strip_name(text: str, names: list[str]) -> str:
    """Remove the assistant's name (and sound-alikes) from the start of a sentence."""
    t = normalize(text)
    for _ in range(2):  # "hey touff, touff open spotify"
        t = _LEADING_FILLER.sub("", t)
        for name in sorted({n.lower() for n in names if n}, key=len, reverse=True):
            if t == name:
                return ""
            if t.startswith(name + " "):
                t = t[len(name) + 1 :]
    return t.strip()


def strip_filler(text: str) -> str:
    t = _LEADING_FILLER.sub("", text)
    return _TRAILING_FILLER.sub("", t).strip()
