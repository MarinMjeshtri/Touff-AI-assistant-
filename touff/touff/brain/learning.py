"""Parse "remember that ..." sentences without needing the AI brain."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

_WHEN_I_SAY = re.compile(
    r"^(?:that\s+)?(?:when(?:ever)?|if)\s+i\s+say\s+(?P<a>.+?)\s*,?\s+"
    r"(?:i\s+mean|it\s+means|that\s+means|you\s+should|i\s+want\s+you\s+to|then|do)\s+(?P<b>.+)$"
)
_WHEN_I_SAY_BARE = re.compile(r"^(?:that\s+)?(?:when(?:ever)?|if)\s+i\s+say\s+(?P<rest>.+)$")
_MEANS = re.compile(r"^(?:that\s+)?(?:by\s+)?(?P<a>.+?)\s+(?:means|is short for|stands for|is what i call)\s+(?P<b>.+)$")
_BY_I_MEAN = re.compile(r"^(?:that\s+)?by\s+(?P<a>.+?)\s+i\s+mean\s+(?P<b>.+)$")


@dataclass
class Lesson:
    kind: str  # "command" (phrase -> do something) | "glossary" (word -> meaning)
    phrase: str
    meaning: str


def parse(body: str, looks_like_command: Callable[[str], bool]) -> Lesson | None:
    """`looks_like_command(text)` says whether some text is something to *do* rather than a definition."""
    body = body.strip().strip("\"'")

    for pattern in (_WHEN_I_SAY, _BY_I_MEAN, _MEANS):
        m = pattern.match(body)
        if m:
            a, b = m.group("a").strip("\"' ,"), m.group("b").strip("\"' ")
            if a and b:
                return Lesson("command" if looks_like_command(b) else "glossary", a, b)

    # "when I say lights out lock the computer": no connector word, so find where
    # the action starts.
    m = _WHEN_I_SAY_BARE.match(body)
    if m:
        words = m.group("rest").split()
        for i in range(1, len(words)):
            b = " ".join(words[i:])
            if looks_like_command(b):
                return Lesson("command", " ".join(words[:i]).strip(","), b)
    return None
