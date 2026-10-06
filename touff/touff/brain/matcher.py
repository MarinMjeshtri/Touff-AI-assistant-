"""Fuzzy matching of what was heard against the user's custom command phrases."""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from .text import normalize, strip_filler

THRESHOLD = 86


def phrase_score(heard: str, phrase: str) -> float:
    heard = strip_filler(normalize(heard))
    phrase = normalize(phrase)
    if not heard or not phrase:
        return 0.0
    score = fuzz.ratio(heard, phrase)
    # Allow extra words around a multi-word phrase ("ok boot up the sack real quick"),
    # but not for one-word phrases, which would otherwise match everything.
    if len(phrase.split()) >= 2:
        score = max(score, fuzz.token_set_ratio(heard, phrase) - 4)
        if f" {phrase} " in f" {heard} ":
            score = max(score, 95)
    return score


def best_command(heard: str, commands: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    best, best_score = None, 0.0
    for cmd in commands:
        for phrase in cmd.get("phrases", []):
            score = phrase_score(heard, phrase)
            if score > best_score:
                best, best_score = cmd, score
    if best_score >= THRESHOLD:
        return best, best_score
    return None, best_score
