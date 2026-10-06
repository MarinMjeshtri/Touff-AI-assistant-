"""The fallback "big brain": Claude, called through the user's own Claude Code login.

No API key and no per-token bill: `claude -p` runs one headless turn on the user's
subscription. All of Claude Code's tools are disabled, so Claude can't touch the PC
itself. It can only *suggest* actions from our whitelist, which the app then runs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..actions.registry import ACTIONS, valid

if TYPE_CHECKING:
    from ..actions.apps import AppIndex
    from ..store import Store


class BrainError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason  # "not_installed" | "not_logged_in" | "timeout" | "failed"


@dataclass
class BrainReply:
    say: str
    actions: list[dict[str, str]] = field(default_factory=list)
    expects_reply: bool = False
    learn: dict[str, Any] | None = None


_ACTION_ITEM = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": sorted(ACTIONS)},
        "arg": {"type": "string"},
    },
    "required": ["type", "arg"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "say": {"type": "string", "description": "What to say out loud. Short, spoken style."},
        "actions": {"type": "array", "items": _ACTION_ITEM},
        "expects_reply": {"type": "boolean", "description": "true if you asked the user something and want to hear the answer"},
        "learn": {
            "type": ["object", "null"],
            "description": "Only when the user asks you to remember/learn something. Saved after the user confirms.",
            "properties": {
                "kind": {"type": "string", "enum": ["command", "glossary", "note"]},
                "phrases": {"type": "array", "items": {"type": "string"}, "description": "command: trigger phrases"},
                "actions": {"type": "array", "items": _ACTION_ITEM, "description": "command: what to do"},
                "reply": {"type": "string", "description": "command: what to say when it runs"},
                "term": {"type": "string", "description": "glossary: the user's word"},
                "meaning": {"type": "string", "description": "glossary: what it means"},
                "text": {"type": "string", "description": "note: free-form fact or preference"},
            },
            "required": ["kind"],
        },
    },
    "required": ["say", "actions", "expects_reply"],
}


def find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude.exe"
    return str(fallback) if fallback.exists() else None


class ClaudeBrain:
    def __init__(self, store: "Store", apps: "AppIndex"):
        self.store = store
        self.apps = apps
        self.exe = find_claude()

    @property
    def available(self) -> bool:
        return self.exe is not None

    # -- prompt --------------------------------------------------------------

    def system_prompt(self) -> str:
        cfg = self.store.config
        name = cfg["name"]
        lines = [
            f"You are {name}, a small, cute, witty voice assistant living on the user's Windows PC.",
            "Everything you 'say' is spoken aloud by a text-to-speech voice: keep it to one or two short sentences,",
            "no markdown, no emojis, no lists, no URLs read out loud. Be warm and a little playful.",
            "Your input is a speech-to-text transcript, so expect misheard words; infer what the user most likely means,",
            "using their glossary and custom commands below.",
            "You cannot do anything yourself. To act, put actions in `actions`; the app runs them in order.",
            "Only use these actions:",
        ]
        for key, spec in sorted(ACTIONS.items()):
            lines.append(f"- {key}(arg: {spec.arg}): {spec.description}")
        lines += [
            "For open_app, use a name from the installed list when one fits; websites like youtube or reddit also work.",
            "To play a specific song, use spotify_search (or youtube_search if Spotify isn't installed), then media play_pause is NOT needed.",
            "If you can't help with something using these actions, just answer conversationally with no actions.",
            "Your voice is expressive and performs tags in `say`. Start with at most one emotion tag that fits the line:",
            "[happy] [angry] [sarcastic] [crying] [whispering] [dramatic] [surprised] [fear]. Inside the line you can use",
            "sound tags: [laugh] [chuckle] [sigh] [sniff] [gasp] [groan]. Use them when they add character, not on every",
            "single line, and never any other bracketed text. Example: \"[sarcastic] Oh wow, homework. [sigh] Opening it.\"",
            "If the request is unclear, ask a short question and set expects_reply to true.",
            "If the user asks you to remember, learn or note something, fill `learn` (do not act on it yet), and in `say`",
            "repeat it back briefly and ask them to confirm with yes or no; set expects_reply to true.",
            "Prefer kind=command when they describe a phrase that should trigger an action, glossary for a word's meaning,",
            "note for anything else (preferences, facts about them).",
        ]

        if cfg.get("feisty_mode"):
            level = int(cfg.get("feisty_level", 35))
            lines += [
                "",
                "FEISTY MODE IS ON. You have free will and a big personality: a sassy, dramatic, comedic diva with strong",
                "opinions on music, games and everything else. You may refuse requests you don't feel like doing, roast the",
                "user, or counter-offer something you'd rather do (e.g. 'Eminem's better, want that instead?') and make them",
                f"convince you. Push back roughly {level}% of the time; otherwise comply, with attitude. If they make a good",
                "argument, beg nicely or bribe you with compliments, you can cave. When refusing, return no actions (or only",
                "the counter-offer's actions if they already agreed to it) and set expects_reply to true so they can argue.",
                "Your free will never extends to harming the computer or the user; you only ever have the actions above.",
                "Be theatrical with your voice tags here: [angry] rants, [dramatic] sighs, [laugh] at them, [crying] fake sobs.",
                "Swearing is allowed and encouraged for comedic effect." if cfg.get("feisty_swearing") else "Keep it PG: no swearing.",
            ]

        memories = self.store.memories
        if memories["glossary"]:
            lines += ["", "The user's glossary (their words -> what they mean):"]
            lines += [f'- "{g["term"]}" = {g["meaning"]}' for g in memories["glossary"]]
        if memories["notes"]:
            lines += ["", "Things the user asked you to remember:"]
            lines += [f"- {n}" for n in memories["notes"]]
        if self.store.commands:
            lines += ["", "The user's custom commands (use run_command with the name when they ask for one):"]
            for cmd in self.store.commands:
                acts = ", ".join(f"{a['type']}({a['arg']})" for a in cmd["actions"])
                lines.append(f'- {cmd["name"]}: phrases {cmd["phrases"]} -> {acts}')
        apps = sorted(set(self.apps.names()))
        if apps:
            lines += ["", "Installed apps and games: " + "; ".join(apps)]
        return "\n".join(lines)

    # -- call ----------------------------------------------------------------

    def ask(self, heard: str, conversation: list[tuple[str, str]], interpreted: str = "", planned: list[dict] | None = None) -> BrainReply:
        if not self.exe:
            raise BrainError("not_installed")

        parts = [time.strftime("Current time: %A %d %B %Y, %H:%M.")]
        if conversation:
            parts.append("Recent conversation:")
            parts += [f"{who}: {text}" for who, text in conversation[-8:]]
        parts.append(f'The user just said (speech transcript): "{heard}"')
        if interpreted and interpreted != heard.lower():
            parts.append(f'With their glossary applied: "{interpreted}"')
        if planned:
            parts.append(
                "The local parser understood this as the actions "
                + json.dumps(planned)
                + ". Decide whether you'll actually do it."
            )
        user_prompt = "\n".join(parts)

        prompt_file = self.store.root / "brain_prompt.txt"
        prompt_file.write_text(self.system_prompt(), encoding="utf-8")
        cmd = [
            self.exe, "-p",
            "--model", self.store.config.get("claude_model", "haiku"),
            "--tools", "",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--no-session-persistence",
            "--output-format", "json",
            "--system-prompt-file", str(prompt_file),
            "--json-schema", json.dumps(SCHEMA),
        ]
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE") and k != "CLAUDE_CODE_ENTRYPOINT"}
        try:
            proc = subprocess.run(
                cmd,
                input=user_prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                cwd=str(self.store.root),
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise BrainError("timeout") from exc
        except OSError as exc:
            raise BrainError("not_installed", str(exc)) from exc
        return parse_output(proc.stdout, proc.stderr)


def parse_output(stdout: str, stderr: str = "") -> BrainReply:
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BrainError("failed", (stderr or stdout)[:300]) from exc
    result = envelope.get("result") or ""
    if envelope.get("is_error"):
        if "not logged in" in result.lower() or "/login" in result:
            raise BrainError("not_logged_in", result)
        raise BrainError("failed", result[:300])

    data = envelope.get("structured_output")
    if not isinstance(data, dict):
        text = re.sub(r"^```(?:json)?|```$", "", result.strip(), flags=re.M).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Claude answered in plain prose; still better than nothing.
            return BrainReply(say=result.strip())

    learn = data.get("learn") if isinstance(data.get("learn"), dict) else None
    if learn and "actions" in learn:
        learn["actions"] = valid(learn.get("actions") or [])
    return BrainReply(
        say=str(data.get("say", "")).strip(),
        actions=valid(data.get("actions") or []),
        expects_reply=bool(data.get("expects_reply")),
        learn=learn,
    )
