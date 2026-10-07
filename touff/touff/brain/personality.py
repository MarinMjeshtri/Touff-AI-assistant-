"""Touff's canned lines, so she has some charm even with the AI brain switched off."""

from __future__ import annotations

import random

LINES = {
    "wake": ["Yes?", "Hm?", "[happy] I'm here!", "What's up?", "Yo.", "At your service.", "Talk to me."],
    "ok": ["[happy] On it!", "Done.", "You got it.", "Easy.", "Consider it done.", "[happy] Boom.", "Sure thing."],
    "opening": ["Opening {x}.", "Firing up {x}.", "{x}, coming right up.", "Here's {x}."],
    "yt_latest": ["Pulling up {x}'s newest video.", "[happy] Fresh {x} upload, coming up!", "Let's see what {x} posted."],
    "yt_play": ["Playing {x}.", "[happy] {x}, coming right up.", "Putting on {x}."],
    "searching": ["Searching for {x}.", "Let's see what the internet says about {x}.", "Looking up {x}."],
    "not_found": [
        "I couldn't find {x} on this computer.",
        "[surprised] {x}? Never heard of it. Is it installed?",
        "Hmm, I don't see anything called {x}.",
    ],
    "didnt_get": [
        "Sorry, I didn't catch that.",
        "Say that again?",
        "[sigh] My ears glitched. One more time?",
    ],
    "dismiss": ["Okay!", "Never mind then.", "[sigh] Alright, I'll be here.", "[sarcastic] Cool cool cool."],
    "greet": ["[happy] Hey hey!", "[happy] Hi! What do you need?", "Hello there.", "Sup."],
    "thanks": ["[happy] Anytime!", "You're welcome!", "That's what I'm here for.", "[happy] Aww, stop it. [laugh]"],
    "how_are_you": [
        "Living my best life inside your computer.",
        "Pretty good! The CPU's warm and cozy today.",
        "[sniff] Great, thanks for asking. Nobody ever asks.",
    ],
    "who": [
        "I'm {name}! Small, fast, and slightly dramatic. I open stuff and keep you company.",
        "{name}. Your tiny desktop sidekick.",
    ],
    "joke": [
        "Why did the computer go to the doctor? It had a virus. [laugh] I'll see myself out.",
        "I would tell you a UDP joke, but you might not get it. [chuckle]",
        "There are 10 kinds of people: those who understand binary and those who don't. [laugh]",
        "I told my computer I needed a break. It said: no problem, I'll go to sleep. [chuckle]",
        "Why do programmers prefer dark mode? Because light attracts bugs. [laugh]",
    ],
    "love": ["[happy] Love you too! In a strictly digital way.", "[gasp] Aww. I'd blush if I had a face. Wait, I do!"],
    "thinking": ["One sec...", "Hmm, let me think.", "Thinking...", "Hang on."],  # no tags: these must be quick
    "confirm_risky": ["Are you sure you want me to {x}?", "Just checking, {x}? Say yes to confirm."],
    "brain_off": [
        "[sigh] I'm not sure what you mean, and my big brain is switched off. Try teaching me in settings!",
    ],
    "brain_error": ["[groan] My brain lagged out. Try again in a sec?", "Couldn't reach my brain. Is Claude logged in?"],
    "window_move": ["Sliding {x} over to {where}.", "[happy] Whoosh! {x}, off to {where}.", "{x}, moving to {where}."],
    "open_on": ["Opening {x} on {where}.", "[happy] {x}, coming right up on {where}."],
    "window_maximize": ["Making {x} big.", "{x}, full size.", "[happy] Biggest {x} ever."],
    "window_minimize": ["Tucking {x} away.", "{x}, minimized.", "Out of sight, {x}."],
    "window_restore": ["Bringing {x} back.", "{x}, back to normal."],
    "window_close": ["Closing {x}.", "Bye bye, {x}.", "[happy] Poof, {x} is gone."],
    "window_focus": ["Here's {x}.", "Switching to {x}.", "{x}, front and center."],
    "window_snap": ["Snapping {x} to the {side}.", "{x}, {side} side. Snap!"],
    "desktop": ["Clean desktop, coming up.", "[happy] Poof! Everything's hidden.", "Hiding everything."],
    "blocked_key": ["Nope, that shortcut opens a run box. I'm not allowed to press it.", "[sarcastic] Nice try. That combo is blocked."],
    "settings": ["Here are my settings.", "[happy] Welcome to my brain. Don't touch anything weird.", "Settings, coming right up."],
    "saved": ["[happy] Saved! I'll remember that.", "Got it, locked in.", "Noted. I won't forget."],
    "not_saved": ["Okay, forgot it.", "Fine, deleted from my memory."],
}


def say(kind: str, **fmt: str) -> str:
    return random.choice(LINES[kind]).format(**fmt)
