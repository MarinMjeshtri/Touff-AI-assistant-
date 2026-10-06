"""Touff's canned lines, so she has some charm even with the AI brain switched off."""

from __future__ import annotations

import random

LINES = {
    "wake": ["Yes?", "Hm?", "I'm here!", "What's up?", "Yo.", "At your service.", "Talk to me."],
    "ok": ["On it!", "Done.", "You got it.", "Easy.", "Consider it done.", "Boom.", "Sure thing."],
    "opening": ["Opening {x}.", "Firing up {x}.", "{x}, coming right up.", "Here's {x}."],
    "searching": ["Searching for {x}.", "Let's see what the internet says about {x}.", "Looking up {x}."],
    "not_found": [
        "I couldn't find {x} on this computer.",
        "{x}? Never heard of it. Is it installed?",
        "Hmm, I don't see anything called {x}.",
    ],
    "didnt_get": [
        "Sorry, I didn't catch that.",
        "Say that again?",
        "My ears glitched. One more time?",
    ],
    "dismiss": ["Okay!", "Never mind then.", "Alright, I'll be here.", "Cool cool cool."],
    "greet": ["Hey hey!", "Hi! What do you need?", "Hello there.", "Sup."],
    "thanks": ["Anytime!", "You're welcome!", "That's what I'm here for.", "Aww, stop it."],
    "how_are_you": [
        "Living my best life inside your computer.",
        "Pretty good! The CPU's warm and cozy today.",
        "Great, thanks for asking. Nobody ever asks.",
    ],
    "who": [
        "I'm {name}! Small, fast, and slightly dramatic. I open stuff and keep you company.",
        "{name}. Your tiny desktop sidekick.",
    ],
    "joke": [
        "Why did the computer go to the doctor? It had a virus. ...I'll see myself out.",
        "I would tell you a UDP joke, but you might not get it.",
        "There are 10 kinds of people: those who understand binary and those who don't.",
        "I told my computer I needed a break. It said: no problem, I'll go to sleep.",
        "Why do programmers prefer dark mode? Because light attracts bugs.",
    ],
    "love": ["Love you too! In a strictly digital way.", "Aww. I'd blush if I had a face. Wait, I do!"],
    "thinking": ["One sec...", "Hmm, let me think.", "Thinking...", "Hang on."],
    "confirm_risky": ["Are you sure you want me to {x}?", "Just checking, {x}? Say yes to confirm."],
    "brain_off": [
        "I'm not sure what you mean, and my big brain is switched off. Try teaching me in settings!",
    ],
    "brain_error": ["My brain lagged out. Try again in a sec?", "Couldn't reach my brain. Is Claude logged in?"],
    "saved": ["Saved! I'll remember that.", "Got it, locked in.", "Noted. I won't forget."],
    "not_saved": ["Okay, forgot it.", "Fine, deleted from my memory."],
}


def say(kind: str, **fmt: str) -> str:
    return random.choice(LINES[kind]).format(**fmt)
