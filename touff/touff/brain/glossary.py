"""Rewrite the user's own slang into what they mean before matching."""

from __future__ import annotations

import re

from .text import normalize


def expand(text: str, glossary: list[dict[str, str]]) -> str:
    """Replace every glossary term (whole words, longest first) with its meaning.

    "boot up the sack" + {"the sack": "The Binding of Isaac"} -> "boot up the binding of isaac"
    """
    result = normalize(text)
    entries = sorted(glossary, key=lambda g: len(g["term"]), reverse=True)
    for entry in entries:
        term = normalize(entry["term"])
        if not term:
            continue
        pattern = re.compile(rf"(?<![\w']){re.escape(term)}(?![\w'])")
        # A lambda keeps backslashes in the meaning from being read as group refs.
        result = pattern.sub(lambda _m, m=normalize(entry["meaning"]): m, result)
    return result
