# Touff 🫧

A tiny, slightly dramatic voice sidekick for Windows. Say **"Touff"**, a blob pops up in the corner, and she listens, does things on your PC, and talks back. She can laugh, sigh, shout and fake-cry.

```
"Touff, open Spotify"                    -> opens Spotify
"Touff, boot up the sack"                -> launches The Binding of Isaac (after you teach her)
"Touff, search YouTube for lofi beats"   -> searches YouTube
"Touff, next song" / "turn it up"        -> media keys
"Touff, set a timer for 5 minutes"       -> she shouts when it's done
"Touff, remember that GG means good game" -> learns it (after you say yes)
```

## How she thinks

Every sentence goes through three steps, cheapest first:

1. **Your glossary.** Your own words get rewritten ("the sack" becomes "The Binding of Isaac").
2. **Instant local matching.** Your custom commands, built-ins (open / search / media / timers), plus a scan of your Start Menu and Steam library, so "open binding of isaac" works without any setup.
3. **The big brain.** Only when steps 1–2 aren't sure, she asks Claude through your own **Claude Code** login. No API key and no per-use bill. Claude can only *suggest* actions from a fixed safe list; Touff runs them.

Risky actions (lock, sleep, shutdown) always need a spoken "yes".

## Setup

Requires Windows 11 and [uv](https://docs.astral.sh/uv/).

```powershell
powershell -ExecutionPolicy Bypass -File touff\scripts\setup.ps1             # lightweight voice
powershell -ExecutionPolicy Bypass -File touff\scripts\setup.ps1 -Expressive # + expressive GPU voice
```

Then double-click **`Touff.cmd`**. She lives in the tray: click the tray icon to talk without the wake word, or right-click it for Settings.

For the big brain, run `claude` once in a terminal and log in.

### Developer mode 😈

Poke the blob in the Settings sidebar five times. You get **feisty mode**: she has free will, can refuse, roast you and counter-offer, and you have to argue with her. Optional swearing.

## Voices

| Engine | What it sounds like | Needs |
|---|---|---|
| **Expressive** (Chatterbox Turbo) | Emotions and sounds: `[angry]`, `[crying]`, `[whispering]`, `[laugh]`, `[sigh]`... The brain picks them per line. | NVIDIA GPU with ~3 GB free VRAM. ~3.8 GB of weights on first start. |
| **Lightweight** (Piper) | Clear, calm, instant. Several voices to pick from. | Nothing special, ~60 MB per voice. |

Give her a custom voice: put a clean 10–20 s `.wav` path in Settings → Voice clip. Only use voices you have the right to use.

## Dev

```powershell
cd touff
.venv\Scripts\python -m pytest
.venv\Scripts\python -m touff --text "open spotify" --dry-run   # test without a mic
.venv\Scripts\python -m touff --console                         # voice loop, logs in terminal
```

| Where | What |
|---|---|
| `touff/brain/` | glossary, fuzzy matching, intents, router, Claude CLI bridge, personality |
| `touff/actions/` | the safe action list, app and Steam index |
| `touff/audio/` | mic + VAD, Vosk wake word, faster-whisper, Piper, expressive voice client |
| `touff/voice_server.py` | GPU voice worker (runs in `.venv-voice`) |
| `touff/ui/` | pop-up blob, settings app, tray icon |

User data (config, commands, memories, history) is plain JSON in `%APPDATA%\Touff`. Models live in `touff/models/` (git-ignored).
