"""Built-in commands that are understood instantly, with no AI involved."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import strip_filler

_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "couple": 2, "a couple": 2, "a couple of": 2, "three": 3,
    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "twenty five": 25, "thirty": 30, "forty": 40,
    "forty five": 45, "fifty": 50, "sixty": 60, "ninety": 90,
}
_UNITS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600}


@dataclass
class Intent:
    kind: str
    arg: str = ""
    extra: dict = field(default_factory=dict)


_OPEN = re.compile(
    r"^(?:open|launch|start|run|boot|boot up|fire up|load up|load|pull up|bring up|put on|get)\s+(?:up\s+)?(?P<target>.+)$"
)
_SEARCH_ON = re.compile(
    r"^(?:search|look up|look for|find)\s+(?:for\s+)?(?P<q>.+?)\s+on\s+(?P<engine>google|youtube|spotify)$"
)
_SEARCH = re.compile(
    r"^(?:search|google|look up|find)(?:\s+(?:on|in))?(?:\s+(?P<engine>google|youtube|spotify))?(?:\s+for)?\s+(?P<q>.+)$"
)
_PLAY_ON = re.compile(r"^play\s+(?P<q>.+?)\s+on\s+(?P<engine>youtube|spotify)$")
_MEDIA = {
    "play_pause": re.compile(r"^(?:play|pause|resume|unpause|stop the music|pause the music|play the music|pause it|play it|resume the music|hit play|hit pause)$"),
    "next": re.compile(r"^(?:next|skip|next song|next track|skip (?:this |the )?(?:song|track)|skip it)$"),
    "previous": re.compile(r"^(?:previous|previous song|previous track|go back|last song|play the last song|back)$"),
}
_VOLUME = {
    "up": re.compile(r"^(?:volume up|louder|turn (?:it|the volume|the music) up|turn up the (?:volume|music)|crank it(?: up)?|pump it up)$"),
    "down": re.compile(r"^(?:volume down|quieter|softer|turn (?:it|the volume|the music) down|turn down the (?:volume|music))$"),
    "mute": re.compile(r"^(?:mute|unmute|mute (?:it|the sound|the volume)|unmute (?:it|the sound))$"),
}
_TIME = re.compile(r"^(?:what time is it|what's the time|whats the time|what is the time|time|tell me the time)$")
_DATE = re.compile(r"^(?:what(?:'s| is) the date|what day is it|what's today|what is today|today's date|whats the date)$")
_TIMER = re.compile(
    r"^(?:set\s+)?(?:a\s+)?(?:timer|countdown|alarm)\s+(?:for\s+)?(?P<n>[\w ]+?)\s+(?P<unit>second|sec|minute|min|hour)s?$"
    r"|^(?:remind me in|wake me in|timer)\s+(?P<n2>[\w ]+?)\s+(?P<unit2>second|sec|minute|min|hour)s?$"
)
_HALF_HOUR = re.compile(r"^(?:set\s+)?(?:a\s+)?timer for half an hour$")
_LEARN = re.compile(r"^(?:remember|learn|note|memorize|save)(?:\s+that)?\s+(?P<body>.+)$")
_WHEN_I_SAY = re.compile(r"^when i say\s+.+")
_DISMISS = re.compile(r"^(?:never ?mind|cancel|nothing|forget it|stop|shut up|be quiet|go away|nvm|no|nah)$")
_SYSTEM = {
    "lock_pc": re.compile(r"^lock (?:the |my )?(?:computer|pc|screen|laptop)$"),
    "sleep_pc": re.compile(r"^(?:go to sleep|put (?:the |my )?(?:computer|pc|laptop) to sleep|sleep mode)$"),
    "shutdown_pc": re.compile(r"^(?:shut ?down|shut down (?:the |my )?(?:computer|pc|laptop)|turn off (?:the |my )?(?:computer|pc|laptop))$"),
}
_CHAT = {
    "greet": re.compile(r"^(?:hi|hello|hey|yo|sup|what's up|whats up|good morning|good evening|good afternoon)$"),
    "thanks": re.compile(r"^(?:thanks|thank you|thx|cheers|good job|nice|well done|good girl|you're the best|youre the best)$"),
    "how_are_you": re.compile(r"^(?:how are you|how are you doing|how's it going|hows it going|you good)$"),
    "who": re.compile(r"^(?:who are you|what are you|what's your name|whats your name|introduce yourself)$"),
    "joke": re.compile(r"^(?:tell me a joke|say something funny|make me laugh|joke)$"),
    "love": re.compile(r"^(?:i love you|love you)$"),
}


def _seconds(n: str, unit: str) -> int | None:
    n = n.strip()
    if n.replace(".", "", 1).isdigit():
        value = float(n)
    elif n in _NUMBERS:
        value = _NUMBERS[n]
    else:
        return None
    return int(value * _UNITS[unit])


def parse(text: str) -> Intent | None:
    """Recognise a built-in command in already-normalized (and glossary-expanded) text."""
    t = strip_filler(text)
    if not t:
        return None

    if _LEARN.match(t) or _WHEN_I_SAY.match(t):
        body = _LEARN.match(t).group("body") if _LEARN.match(t) else t
        return Intent("learn", body)
    if _DISMISS.match(t):
        return Intent("dismiss")
    for kind, pattern in _CHAT.items():
        if pattern.match(t):
            return Intent("chat", kind)
    if _TIME.match(t):
        return Intent("time")
    if _DATE.match(t):
        return Intent("date")
    if _HALF_HOUR.match(t):
        return Intent("timer", "1800")
    if m := _TIMER.match(t):
        n, unit = (m.group("n"), m.group("unit")) if m.group("n") else (m.group("n2"), m.group("unit2"))
        secs = _seconds(n, unit)
        if secs:
            return Intent("timer", str(secs))
    for action, pattern in _SYSTEM.items():
        if pattern.match(t):
            return Intent("system", action)
    for what, pattern in _MEDIA.items():
        if pattern.match(t):
            return Intent("media", what)
    for what, pattern in _VOLUME.items():
        if pattern.match(t):
            return Intent("volume", what)
    if m := _PLAY_ON.match(t):
        return Intent("search", m.group("q"), {"engine": m.group("engine")})
    if m := _SEARCH_ON.match(t):
        return Intent("search", m.group("q"), {"engine": m.group("engine")})
    if m := _SEARCH.match(t):
        return Intent("search", m.group("q"), {"engine": m.group("engine") or "google"})
    if m := _OPEN.match(t):
        return Intent("open", m.group("target"))
    return None
