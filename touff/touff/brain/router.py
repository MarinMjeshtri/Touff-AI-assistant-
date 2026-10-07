"""Turns a heard sentence into something to say and things to do.

Tier 1: custom commands (fuzzy phrase match), on the raw text and the glossary-expanded text.
Tier 2: built-in intents (open X, search X, media, timers, ...), resolved locally.
Tier 3: Claude, only when the local tiers aren't confident (or feisty mode wants a say).
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from ..actions import windows
from ..actions.registry import is_risky
from . import glossary, intents, learning, matcher
from . import personality as P
from .claude_cli import BrainError, BrainReply
from .text import normalize, strip_filler

if TYPE_CHECKING:
    from ..actions.apps import AppIndex
    from ..store import Store
    from .claude_cli import ClaudeBrain

_YES = re.compile(r"^(?:yes|yeah|yep|yup|sure|ok|okay|do it|go ahead|confirm|correct|absolutely|of course|please do|ya|yea|affirmative|save it)\b")
_NO = re.compile(r"^(?:no|nope|nah|don't|do not|cancel|stop|never ?mind|negative|forget it)\b")
_SPLIT = re.compile(r"\s+(?:and then|and|then)\s+")


@dataclass
class Reply:
    say: str
    actions: list[dict[str, str]] = field(default_factory=list)
    source: str = "none"  # command | intent | claude | chat | none
    listen_again: bool = False
    # When set, `say` asks a yes/no question and this runs on "yes".
    on_yes: Callable[[], "Reply"] | None = None


def answer_yes_no(text: str) -> bool | None:
    t = strip_filler(normalize(text))
    if _YES.match(t):
        return True
    if _NO.match(t):
        return False
    return None


class Router:
    def __init__(self, store: "Store", apps: "AppIndex", brain: "ClaudeBrain | None", on_thinking: Callable[[], None] | None = None):
        self.store = store
        self.apps = apps
        self.brain = brain
        self.on_thinking = on_thinking or (lambda: None)
        self.conversation: list[tuple[str, str]] = []
        self._last_turn = 0.0

    # -- public ----------------------------------------------------------------

    def handle(self, heard: str) -> Reply:
        # Forget the conversation after a few minutes of silence.
        if time.time() - self._last_turn > 300:
            self.conversation = []
        self._last_turn = time.time()

        reply = self._route(heard)
        self.conversation += [("User", heard), (self.store.config["name"], reply.say)]
        self.conversation = self.conversation[-12:]
        return reply

    # -- routing -------------------------------------------------------------

    def _route(self, heard: str) -> Reply:
        raw = strip_filler(normalize(heard))
        if not raw:
            return Reply(P.say("wake"), source="chat", listen_again=True)

        # "Remember that ..." comes first: the lesson itself usually contains the
        # very phrase it defines, which would otherwise trigger that command.
        lesson = intents.parse(raw)
        if lesson is not None and lesson.kind == "learn":
            reply = self._learn(lesson.arg)
            return reply if reply is not None else self._ask_brain(heard, raw)

        # Tier 1: custom commands. Raw first, so a phrase that contains a glossary
        # term ("boot up the sack") still matches before the term gets rewritten.
        expanded = glossary.expand(raw, self.store.memories["glossary"])
        for text in (raw, expanded):
            cmd, _ = matcher.best_command(text, self.store.commands)
            if cmd:
                return self._maybe_feisty(heard, expanded, self._command_reply(cmd))

        # Tier 2: built-in intents, possibly several joined with "and".
        local = self._local(expanded)
        if local is not None:
            return self._maybe_feisty(heard, expanded, local)

        # Tier 3: the big brain.
        return self._ask_brain(heard, expanded)

    def _local(self, text: str) -> Reply | None:
        intent = intents.parse(text)
        if intent is not None:
            reply = self._intent_reply(intent)
            if reply is not None:
                return reply
        parts = [p for p in _SPLIT.split(text) if p]
        if len(parts) > 1:
            # "open spotify and discord": later parts borrow the first part's verb.
            verb = parts[0].split()[0]
            replies = [self._local(p) or self._local(f"{verb} {p}") for p in parts]
            if all(r is not None and r.actions and not r.on_yes for r in replies):
                actions = _resolve_it([a for r in replies for a in r.actions])
                return Reply(P.say("ok"), actions, source="intent")
        return None

    def _command_reply(self, cmd: dict[str, Any]) -> Reply:
        say = cmd.get("reply") or P.say("ok")
        return self._guard(Reply(say, list(cmd["actions"]), source="command"))

    def _intent_reply(self, intent: intents.Intent) -> Reply | None:
        name = self.store.config["name"]
        k, arg = intent.kind, intent.arg
        if k == "chat":
            return Reply(P.say(arg, name=name), source="chat")
        if k == "dismiss":
            return Reply(P.say("dismiss"), source="chat")
        if k == "time":
            return Reply(time.strftime("It's %I:%M %p.").replace(" 0", " ").lstrip("0"), source="intent")
        if k == "date":
            return Reply(time.strftime("It's %A, %B %d.").replace(" 0", " "), source="intent")
        if k == "timer":
            return Reply(P.say("ok") + " Timer started.", [{"type": "timer", "arg": arg}], source="intent")
        if k == "media":
            return Reply("", [{"type": "media", "arg": arg}], source="intent")
        if k == "volume":
            return Reply("", [{"type": "volume", "arg": arg}], source="intent")
        if k == "system":
            return self._guard(Reply(P.say("ok"), [{"type": arg, "arg": ""}], source="intent"))
        if k == "search":
            engine = intent.extra.get("engine", "google")
            action = {"google": "google_search", "youtube": "youtube_search", "spotify": "spotify_search"}[engine]
            return Reply(P.say("searching", x=arg), [{"type": action, "arg": arg}], source="intent")
        if k == "open":
            app = self.apps.find(arg)
            if app is None:
                return None  # let the brain figure out what they meant
            return Reply(P.say("opening", x=_pretty(app.name)), [{"type": "open_app", "arg": app.name}], source="intent")
        if k == "learn":
            return self._learn(arg)
        if k == "window":
            return self._window_reply(arg, intent.extra.get("app", ""), intent.extra.get("monitor", ""))
        if k == "open_on":
            spoken = windows.clean_app_name(arg)
            app = self.apps.find(spoken)
            monitor = windows.monitor_word(intent.extra.get("monitor", ""))
            if app is None or monitor is None:
                return None
            target = spoken if windows.is_known_alias(spoken) else app.name
            return Reply(
                P.say("open_on", x=_pretty(app.name), where=_where(monitor)),
                [{"type": "open_app", "arg": app.name}, {"type": "window", "arg": f"move:{target}:{monitor}"}],
                source="intent",
            )
        if k == "hotkey":
            keys = re.sub(r"^(?:the|a)\s+", "", arg)
            try:
                windows.parse_hotkey(keys)
            except PermissionError:
                return Reply(P.say("blocked_key"), source="intent")
            except ValueError:
                return None  # "press play"... let the brain work it out
            return Reply("", [{"type": "hotkey", "arg": keys}], source="intent")
        return None

    def _window_reply(self, op: str, spoken: str, monitor_spoken: str) -> Reply | None:
        if op == "minimize_all":
            return Reply(P.say("desktop"), [{"type": "window", "arg": "minimize_all:"}], source="intent")
        target, pretty = self._window_app(spoken, op)
        if target is None:
            return None  # not an app we know: the brain may still make sense of it
        if op == "move":
            monitor = windows.monitor_word(monitor_spoken)
            if monitor is None:
                return None
            action = {"type": "window", "arg": f"move:{target}:{monitor}"}
            return Reply(P.say("window_move", x=pretty, where=_where(monitor)), [action], source="intent")
        line = {"snap_left": "window_snap", "snap_right": "window_snap"}.get(op, f"window_{op}")
        return Reply(P.say(line, x=pretty, side=op[5:]), [{"type": "window", "arg": f"{op}:{target}"}], source="intent")

    def _window_app(self, spoken: str, op: str) -> tuple[str | None, str]:
        """Spoken app -> (name for the window action, name to say). Only apps we actually know."""
        name = windows.clean_app_name(spoken)
        if name == "active":
            return "active", "that window"
        app = self.apps.find(name) if name else None
        if windows.is_known_alias(name):
            return name, _pretty(app.name) if app else name.title()
        if app is None or (op == "close" and app.kind == "url"):
            return None, ""  # "close youtube" means a tab, not the whole browser
        return app.name, _pretty(app.name)

    # -- learning ------------------------------------------------------------

    def _learn(self, body: str) -> Reply | None:
        lesson = learning.parse(body, lambda t: self._local(t) is not None and bool(self._local(t).actions))
        if lesson is None:
            if self.brain and self.store.config["brain"] == "claude":
                return None  # Claude is better at untangling free-form lessons
            return self._confirm_learn(f"I'll remember: {body}. Right?", lambda: self.store.add_note(body))

        if lesson.kind == "command":
            todo = self._local(lesson.meaning)
            actions = todo.actions if todo else []
            what = _describe(actions) or lesson.meaning
            return self._confirm_learn(
                f'Got it. When you say "{lesson.phrase}", I\'ll {what}. Should I save that?',
                lambda: self.store.add_command([lesson.phrase], actions),
            )
        return self._confirm_learn(
            f'So "{lesson.phrase}" means {lesson.meaning}. Save it?',
            lambda: self.store.add_glossary(lesson.phrase, lesson.meaning),
        )

    def _confirm_learn(self, question: str, save: Callable[[], None]) -> Reply:
        def yes() -> Reply:
            save()
            return Reply(P.say("saved"), source="chat")

        return Reply(question, source="chat", listen_again=True, on_yes=yes)

    def _learn_from_brain(self, reply: BrainReply) -> Callable[[], None] | None:
        learn = reply.learn or {}
        kind = learn.get("kind")
        if kind == "command" and learn.get("phrases") and learn.get("actions"):
            return lambda: self.store.add_command(learn["phrases"], learn["actions"], learn.get("reply", ""))
        if kind == "glossary" and learn.get("term") and learn.get("meaning"):
            return lambda: self.store.add_glossary(learn["term"], learn["meaning"])
        if kind == "note" and learn.get("text"):
            return lambda: self.store.add_note(learn["text"])
        return None

    # -- brain ---------------------------------------------------------------

    def _brain_on(self) -> bool:
        return bool(self.brain and self.brain.available and self.store.config.get("brain") == "claude")

    def _ask_brain(self, heard: str, expanded: str, planned: list[dict] | None = None) -> Reply:
        if not self._brain_on():
            return Reply(P.say("brain_off") if self.store.config.get("brain") == "offline" else P.say("didnt_get"), source="none")
        self.on_thinking()
        try:
            out = self.brain.ask(heard, self.conversation, interpreted=expanded, planned=planned)
        except BrainError as err:
            if err.reason == "not_logged_in":
                return Reply("My big brain isn't logged in yet. Run claude in a terminal and log in, then try again.", source="none")
            if err.reason == "not_installed":
                return Reply("I can't find Claude Code on this computer, so I'm running on my small brain only.", source="none")
            return Reply(P.say("brain_error"), source="none")

        save = self._learn_from_brain(out)
        if save is not None:
            return self._confirm_learn(out.say or "Should I remember that?", save)
        return self._guard(Reply(out.say, out.actions, source="claude", listen_again=out.expects_reply))

    def _maybe_feisty(self, heard: str, expanded: str, reply: Reply) -> Reply:
        """In feisty mode, sometimes let Claude decide whether she *feels like* doing it."""
        cfg = self.store.config
        if not (cfg.get("feisty_mode") and reply.actions and self._brain_on()):
            return reply
        if random.random() * 100 >= float(cfg.get("feisty_level", 35)):
            return reply
        return self._ask_brain(heard, expanded, planned=reply.actions)

    @staticmethod
    def _guard(reply: Reply) -> Reply:
        """Risky actions (shutdown, ...) only run after a spoken yes."""
        if not is_risky(reply.actions) or reply.on_yes:
            return reply
        actions = reply.actions
        what = _describe(actions)
        return Reply(
            P.say("confirm_risky", x=what),
            source=reply.source,
            listen_again=True,
            on_yes=lambda: Reply(P.say("ok"), actions, source=reply.source),
        )


def _pretty(name: str) -> str:
    return name if name[:1].isupper() else name.title()


def _where(monitor: str) -> str:
    if monitor == "1":
        return "your main monitor"
    if monitor.isdigit():
        return f"monitor {monitor}"
    return {"left": "the left monitor", "right": "the right monitor"}.get(monitor, "the other monitor")


def _window_phrase(arg: str) -> str:
    try:
        op, app, monitor = windows.parse_window_arg(arg)
    except ValueError:
        return f"manage a window ({arg})"
    if op == "minimize_all":
        return "show the desktop"
    app = "the window in front" if app == "active" else app
    if op == "move":
        return f"move {app} to {_where(monitor)}"
    if op.startswith("snap_"):
        return f"snap {app} to the {op[5:]}"
    return f"{op} {app}"


def _resolve_it(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    """'open chrome and move it to my second monitor': 'it' is the app just opened, not the front window."""
    opened, out = None, []
    for a in actions:
        if a["type"] == "open_app":
            opened = a["arg"]
        elif a["type"] == "window" and opened:
            op, _, rest = a["arg"].partition(":")
            app, sep, monitor = rest.partition(":")
            if app == "active":
                a = {"type": "window", "arg": f"{op}:{opened}{sep}{monitor}"}
        out.append(a)
    return out


_VERBS: dict[str, str | Callable[[str], str]] = {
    "open_app": "open {}",
    "open_steam_game": "launch {}",
    "open_url": "open {}",
    "google_search": "google {}",
    "youtube_search": "search YouTube for {}",
    "spotify_search": "find {} on Spotify",
    "media": "hit {}",
    "volume": "turn the volume {}",
    "timer": "start a {} second timer",
    "run_command": "run {}",
    "window": _window_phrase,
    "hotkey": "press {}",
    "lock_pc": "lock the computer",
    "sleep_pc": "put the computer to sleep",
    "shutdown_pc": "shut the computer down",
}


def _describe(actions: list[dict[str, str]]) -> str:
    bits = []
    for a in actions:
        verb = _VERBS.get(a["type"], a["type"])
        bits.append(verb(a["arg"]) if callable(verb) else verb.format(a["arg"].replace("_", " ")))
    return " and then ".join(bits)
