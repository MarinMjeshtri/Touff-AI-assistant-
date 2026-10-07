# Touff 🫧

A tiny, slightly dramatic voice sidekick for Windows. Say **"Touff"**, a blob pops up in the corner, and she listens, does things on your PC, and talks back. She can laugh, sigh, shout and fake-cry.

```
"Touff, open Spotify"                    -> opens Spotify
"Touff, boot up the saac"                -> launches The Binding of Isaac (after you teach her)
"Touff, search YouTube for lofi beats"   -> searches YouTube
"Touff, next song" / "turn it up"        -> media keys
"Touff, set a timer for 5 minutes"       -> she shouts when it's done
"Touff, remember that GG means good game" -> learns it (after you say yes)
"Touff, tell claude he's doing a good job" -> tells claude he's doing a cool job 🤯
```

## How she thinks

Every sentence goes through three steps, cheapest first:

1. **Your glossary.** Your own words get rewritten ("the sack" becomes "The Binding of Isaac").
2. **Instant local matching.** Your custom commands, built-ins (open / search / media / timers), plus a scan of your Start Menu and Steam library, so "open binding of isaac" works without any setup.
3. **The big brain.** Only when steps 1–2 aren't sure, she asks Claude through your own **Claude Code** login. No API key and no per-use bill. Claude can only *suggest* actions from a fixed safe list; Touff runs them.

Risky actions (lock, sleep, shutdown) always need a spoken "yes".

## Install

1. Download **`Touff-Setup-<version>.exe`** from the [latest release](https://github.com/MarinMjeshtri/Touff-AI-assistant-/releases/latest) and run it. No admin needed: she installs just for you, in `%LOCALAPPDATA%\Programs\Touff`. (No installer? The `Touff-<version>-portable.zip` works too: unzip anywhere and run `Touff.exe`.)
2. **The first launch downloads her models once** (~600 MB: wake word, speech recognition, lightweight voice) into `%LOCALAPPDATA%\Touff\models`, with progress in the pop-up. She greets you when everything is ready.
3. **Big brain (optional):** install [Claude Code](https://docs.claude.com/en/docs/claude-code), run `claude` once in a terminal and log in. Touff uses that login, no API key.
4. **Expressive voice pack (recommended if you have an NVIDIA GPU):** much faster, sharper ears (Whisper large on the GPU, ~0.3 s per sentence instead of ~2 s on the CPU) and the expressive voice that laughs, sighs and shouts. Press *Install voice pack* in Settings, or run `touff-cli.exe --install-voice-pack` from the install folder. It builds a separate GPU environment (PyTorch + Chatterbox + Whisper large: ~5 GB of packages plus ~5 GB of models) in `%LOCALAPPDATA%\Touff\voice-pack`. Without an NVIDIA card she politely sticks to the lightweight voice.

She lives in the tray: click the tray icon to talk without the wake word, or right-click it for Settings. The installer can start her with Windows; Settings can change that later. Logs: `%APPDATA%\Touff\touff.log`. Uninstalling removes the app, models and voice pack, and asks before deleting your settings and memories.

## Setup from source

Requires Windows 11 and [uv](https://docs.astral.sh/uv/).

```powershell
powershell -ExecutionPolicy Bypass -File touff\scripts\setup.ps1             # lightweight voice
powershell -ExecutionPolicy Bypass -File touff\scripts\setup.ps1 -Expressive # + expressive GPU voice
```

Then double-click **`touff\Touff.cmd`**. She lives in the tray: click the tray icon to talk without the wake word, or right-click it for Settings.

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

### Build the installer

```powershell
cd touff
uv pip install --python .venv\Scripts\python.exe -e ".[dev,build]"
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Output lands in `touff/packaging/dist`: the `Touff` app folder (`Touff.exe` plus `touff-cli.exe` with a console), `Touff-<version>-portable.zip`, and `Touff-Setup-<version>.exe` if [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed. The version comes from `touff/touff/__init__.py`. Pushing a `v*` tag runs the same build on GitHub Actions and attaches both files to a release.

| Where | What |
|---|---|
| `touff/touff/brain/` | glossary, fuzzy matching, intents, router, Claude CLI bridge, personality |
| `touff/touff/actions/` | the safe action list, app and Steam index |
| `touff/touff/audio/` | mic + VAD, Vosk wake word, faster-whisper, Piper, expressive voice client |
| `touff/touff/voice_server.py` | GPU voice worker (runs in `.venv-voice` / the voice pack) |
| `touff/touff/ui/` | pop-up blob, settings app, tray icon |
| `touff/touff/voicepack.py` | installs the optional GPU voice environment |
| `touff/packaging/` | PyInstaller spec, Inno Setup script, build script |

User data (config, commands, memories, history) is plain JSON in `%APPDATA%\Touff`. From source, models live in `touff/models/` (git-ignored); the installed app keeps them in `%LOCALAPPDATA%\Touff\models`.
