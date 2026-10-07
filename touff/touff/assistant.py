"""The main loop: wait for the name -> listen -> understand -> act -> talk back."""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Protocol

from .actions.apps import AppIndex
from .actions.registry import Executor
from .brain import personality as P
from .brain.claude_cli import ClaudeBrain
from .brain.router import Reply, Router, answer_yes_no
from .brain.text import strip_name, strip_tags
from .store import Store

log = logging.getLogger(__name__)


# Apps whose names speech recognition tends to mangle; hinted when installed.
_COMMON_APPS = [
    "Google Chrome", "Claude", "Spotify", "Discord", "Steam", "Microsoft Edge", "Visual Studio Code", "Notepad",
    "File Explorer", "WhatsApp", "Instagram", "Roblox", "Minecraft Launcher", "League of Legends", "Figma",
    "Blender", "Canva", "CapCut", "Medal", "Google", "YouTube",
]

# Words a sentence rarely ends on: if it does, the speaker probably just paused.
_DANGLING = {
    "the", "a", "an", "to", "my", "on", "in", "into", "of", "for", "with", "and", "or", "but", "at", "from",
    "is", "are", "can", "could", "please", "then", "your", "this", "that", "some", "like", "um", "uh",
    "by", "about", "so", "because", "if", "when", "than", "as", "me", "also",
}


# Allowed before the name in a call: greetings and fillers ("hey Touff", "um, Touff").
_ADDRESS = {"hey", "hi", "ok", "okay", "yo", "hello", "oi", "ey", "so", "um", "uh", "oh", "yeah", "and", "excuse"}
# How Whisper tends to spell a made-up name like "Touff" (TTS voices even say "tooth").
_NAME_SPELLINGS = {"touff", "tuff", "tough", "toff", "toof", "tof", "tuf", "touf", "tuffy", "tooth", "tufe"}


def called_by_name(text: str, names: list[str]) -> bool:
    """Whether a transcript sounds like someone *calling* her, not just containing the word.

    The checked window is the ~2 s that end right after the wake word fired. When
    someone calls her, the name opens what they say ("Touff, open...", "hey Touff")
    and only a couple of words follow before the window ends. In a song the word sits
    mid-line ("when the going gets tough, the tough...").
    """
    from rapidfuzz import fuzz

    names = [n.lower() for n in names if n]
    spellings = set(names) | (_NAME_SPELLINGS if any(n in _NAME_SPELLINGS for n in names) else set())
    # Fuzzy only for custom names; "stuff" is one letter from "tuff".
    custom = [n for n in names if n not in _NAME_SPELLINGS]
    words = re.findall(r"[a-z']+", text.lower())
    for i, word in enumerate(words):
        if word not in spellings and not (len(word) >= 4 and custom and max(fuzz.ratio(word, n) for n in custom) >= 85):
            continue
        before, after = words[:i], words[i + 1 :]
        if len(before) <= 1 and all(b in _ADDRESS for b in before) and len(after) <= 3:
            return True
    return False


def sounds_unfinished(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    if t.endswith(("...", "..", "…", ",", "-")):
        return True
    last = t.rstrip(".!?").split()[-1] if t.rstrip(".!?").split() else ""
    return last in _DANGLING and not t.endswith(("?", "!"))


class UI(Protocol):
    def show(self, state: str) -> None: ...  # idle | listening | thinking | speaking | sassy
    def heard(self, text: str) -> None: ...
    def said(self, text: str) -> None: ...
    def hide(self, delay: float = 0) -> None: ...
    def status(self, text: str) -> None: ...  # loading messages etc.


class ConsoleUI:
    def show(self, state: str) -> None:
        print(f"[{state}]")

    def heard(self, text: str) -> None:
        print(f"  you: {text}")

    def said(self, text: str) -> None:
        print(f"  touff: {text}")

    def hide(self, delay: float = 0) -> None:
        pass

    def status(self, text: str) -> None:
        print(f"* {text}")


class Assistant:
    def __init__(self, store: Store, ui: UI | None = None):
        self.store = store
        self.ui: UI = ui or ConsoleUI()
        self.apps = AppIndex(store.root / "apps.json")
        self.brain = ClaudeBrain(store, self.apps)
        self.router = Router(store, self.apps, self.brain, on_thinking=self._thinking)
        self.executor = Executor(self.apps, store, announce=self.announce)

        self.mic = None
        self.wake = None
        self.stt = None
        self.voice = None
        self.gpu = None
        self.ready = threading.Event()
        self.quit = threading.Event()
        self.paused = threading.Event()  # "mute mic" from the tray
        self.talk_now = threading.Event()  # "talk to Touff" from the tray
        self._mute_count = 0
        self._mute_lock = threading.Lock()
        self.busy = False
        self._last_said = ""
        store.on_change(self._on_store_change)
        threading.Thread(target=self.apps.refresh, daemon=True).start()

    # -- setup -----------------------------------------------------------------

    def load(self) -> None:
        """Download (first run) and load all models. Slow: call from a worker thread."""
        from . import models
        from .audio.mic import Mic
        from .audio.wakeword import WakeWord

        cfg = self.store.config
        # First run: fetch every model now, with progress in the pop-up, so nothing is
        # downloaded later in the middle of a conversation.
        models.ensure_all(cfg["voice"], cfg["whisper_model"], self.ui.status)
        self.ui.status("Waking up my ears...")
        self.wake = WakeWord(models.vosk_path(), self._wake_words())
        threading.Thread(target=self.brain.warm, daemon=True).start()
        self.start_engines()
        self.mic = Mic(cfg.get("mic_device"))
        self.mic.start()
        self.ready.set()
        self.ui.status("Ready")

    def start_engines(self) -> None:
        """(Re)start the voice and the speech recognition according to the config.

        With the GPU environment installed, both live in one GPU worker process:
        expressive Chatterbox voice + Whisper large-v3-turbo. Otherwise (or if the
        worker fails) Piper and CPU Whisper take over.
        """
        from .audio import expressive

        cfg = self.store.config
        if self.gpu is not None:  # free the VRAM before loading again
            self.gpu.close()
            self.gpu = None
        want_tts = cfg.get("voice_engine", "auto") in ("auto", "expressive")
        want_stt = cfg.get("stt_engine", "auto") in ("auto", "gpu")
        if expressive.available() and (want_tts or want_stt):
            self.ui.status("Warming up my GPU voice and ears...")
            try:
                self.gpu = expressive.GpuServer(want_tts, cfg["gpu_whisper_model"] if want_stt else None, cfg.get("voice_clip", ""))
            except Exception:
                log.exception("GPU worker failed, using CPU voice and ears")
        if self.gpu and self.gpu.has_tts:
            self.voice = expressive.ExpressiveVoice(self.gpu, cfg["volume"])
        else:
            self.voice = self._piper()
        if self.gpu and self.gpu.has_stt:
            self.stt = expressive.RemoteSTT(self.gpu)
        else:
            self.stt = self._cpu_stt()

    def _piper(self):
        from . import models
        from .audio.tts import Voice

        cfg = self.store.config
        self.ui.status("Warming up my voice...")
        return Voice(models.voice_path(cfg["voice"], self.ui.status), cfg["speech_speed"], cfg["volume"])

    def _cpu_stt(self):
        from . import models
        from .audio.stt import STT

        self.ui.status("Loading speech recognition...")
        return STT(models.whisper_path(self.store.config["whisper_model"], self.ui.status))

    def _wake_words(self) -> list[str]:
        cfg = self.store.config
        return [cfg["name"].lower()] + [w.lower() for w in cfg.get("wake_words", [])]

    def _on_store_change(self, what: str) -> None:
        if what in ("config", "commands", "memories"):
            # Her instructions changed: restart the brain session now, not mid-question.
            threading.Thread(target=self.brain.warm, daemon=True).start()
        if what != "config" or not self.ready.is_set():
            return
        cfg = self.store.config
        self.wake.set_words(self._wake_words())
        self.voice.speed = cfg["speech_speed"]
        self.voice.volume = cfg["volume"]

    def change_voice(self) -> None:
        """Reload after the voice engine, Piper voice, clip or ears changed in settings."""
        self.start_engines()

    # -- talking ---------------------------------------------------------------

    def speak(self, text: str, force: bool = False) -> None:
        """Say it out loud, unless silent mode is on (then the pop-up bubble is the answer)."""
        if not text or self.voice is None or (self.store.config.get("silent") and not force):
            return
        with self._mute_lock:
            self._mute_count += 1
            self.mic.muted.set()
        try:
            try:
                self.voice.speak(text)
            except Exception:
                # The GPU voice died or choked: say it with Piper instead of going mute.
                log.exception("voice failed")
                self.voice = self._piper()
                self.voice.speak(text)
        finally:
            with self._mute_lock:
                self._mute_count -= 1
                if self._mute_count == 0:
                    time.sleep(0.15)  # let the speaker tail die out
                    self.mic.drain()
                    self.mic.muted.clear()

    def announce(self, text: str) -> None:
        """Speak out of the blue (timers)."""
        self.ui.show("speaking")
        self.ui.said(strip_tags(text))
        self.speak(text)
        if not self.busy:
            self.ui.hide(8.0 if self.store.config.get("silent") else 2.5)

    def _thinking(self) -> None:
        self.ui.show("thinking")
        threading.Thread(target=self.speak, args=(P.say("thinking"),), daemon=True).start()

    # -- understanding -----------------------------------------------------------

    def handle_text(self, heard: str, pending: Reply | None = None) -> Reply:
        """Understand, act, log. Used by the voice loop, --text mode and the settings 'Test' button."""
        reply = None
        if pending is not None and pending.on_yes is not None:
            answer = answer_yes_no(heard)
            if answer is True:
                reply = pending.on_yes()
            elif answer is False:
                reply = Reply(P.say("dismiss"), source="chat")
        if reply is None:
            reply = self.router.handle(heard)

        problems = self.executor.run(reply.actions)
        if problems:
            fix = problems[0][0].upper() + problems[0][1:] + "."
            reply.say = fix if reply.source != "claude" else f"{reply.say} {fix}".strip()
        self.store.log(heard, strip_tags(reply.say), reply.actions, reply.source)
        return reply

    def _hint(self) -> str:
        """Words Whisper should expect, so it spells names and slang the way the user does
        ("Claude", not "cloud"; "Chrome", not "crown")."""
        cfg = self.store.config
        words = [p for c in self.store.commands for p in c["phrases"]][:20]
        words += [g["term"] for g in self.store.memories["glossary"]][:20]
        installed = {a.name.lower() for a in self.apps.apps}
        words += [w for w in _COMMON_APPS if w.lower() in installed or w in ("Google", "YouTube")]
        words += [a.name for a in self.apps.apps if a.kind == "steam"][:12]
        return f"{cfg['name']}, open Chrome on my second monitor. " + ", ".join(dict.fromkeys(words)) + "."

    def _save_recording(self, audio: bytes, text: str) -> None:
        import re
        import wave

        folder = self.store.root / "recordings"
        folder.mkdir(exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S-") + (re.sub(r"[^\w]+", "_", text.lower())[:40] or "silence") + ".wav"
        with wave.open(str(folder / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(audio)
        for old in sorted(folder.glob("*.wav"))[:-30]:
            old.unlink()

    def _transcribe(self, audio: bytes) -> str:
        try:
            return self.stt.transcribe(audio, hint=self._hint())
        except Exception:
            # GPU worker gone? Fall back to the CPU model rather than going deaf.
            log.exception("speech recognition failed, falling back to CPU")
            self.stt = self._cpu_stt()
            return self.stt.transcribe(audio, hint=self._hint())

    # -- the loop ----------------------------------------------------------------

    def run(self) -> None:
        self.ready.wait()
        while not self.quit.is_set():
            if self.talk_now.is_set():
                self.talk_now.clear()
                self.mic.drain()
                self.converse(preroll=[])
                continue
            frame = self.mic.read(timeout=0.3)
            if frame is None or self.paused.is_set():
                continue
            if self.wake.feed(frame):
                if self._really_called():
                    self.converse(preroll=self.wake.take_preroll())
                    self.mic.drain()
                self.wake.reset()

    def _really_called(self) -> bool:
        """Second opinion before popping up: did someone actually *call* her, or did a
        song just say "tough"? Whisper on the GPU checks the last 2 s (~0.3 s). Without
        the GPU ears this would be too slow, so Vosk's confidence has to do."""
        from .audio.expressive import RemoteSTT

        if not isinstance(self.stt, RemoteSTT) or self.store.config.get("wake_check") is False:
            return True
        try:
            text = self.stt.transcribe(b"".join(self.wake.preroll))  # no hint: don't bias it towards the name
        except Exception:
            log.exception("wake check failed")
            return True
        ok = called_by_name(text, self._wake_words())
        log.info("wake %s (vosk %.2f): %r", "accepted" if ok else "ignored", self.wake.last_conf, text)
        return ok

    def converse(self, preroll: list[bytes]) -> None:
        from .audio.mic import record_utterance
        from .audio.tts import chime

        self.busy = True
        cfg = self.store.config
        try:
            self.ui.show("listening")
            if cfg.get("chime") and not cfg.get("silent"):
                chime("wake")
            pending: Reply | None = None
            for turn in range(4):  # a wake-up allows a few back-and-forths
                audio = record_utterance(
                    self.mic, preroll if turn == 0 else None, cfg["silence_ms"], cfg["max_listen_s"],
                    start_timeout=5 if turn == 0 else 6, should_stop=self.quit.is_set,
                )
                if audio is None:
                    break
                self.ui.show("thinking")
                text = self._transcribe(audio)
                # Paused mid-thought ("move chrome to the...")? Keep listening and
                # transcribe the whole thing together.
                for _ in range(2):
                    if not sounds_unfinished(text):
                        break
                    self.ui.heard(text + " ...")
                    self.ui.show("listening")
                    more = record_utterance(self.mic, None, cfg["silence_ms"], cfg["max_listen_s"], start_timeout=2.5, should_stop=self.quit.is_set)
                    if more is None:
                        break
                    audio += more
                    self.ui.show("thinking")
                    text = self._transcribe(audio)
                if cfg.get("save_recordings"):
                    self._save_recording(audio, text)
                heard = strip_name(text, self._wake_words(), fuzzy=turn == 0 and bool(preroll))
                self.ui.heard(text or "...")
                if not heard and turn == 0 and text:
                    # Just the name: "Touff?" -> "Yes?" and keep listening.
                    reply = Reply(P.say("wake"), listen_again=True)
                elif not heard:
                    break
                else:
                    reply = self.handle_text(heard, pending)
                sassy = cfg.get("feisty_mode") and reply.source == "claude" and not reply.actions
                self.ui.show("sassy" if sassy else "speaking")
                self._last_said = strip_tags(reply.say)
                self.ui.said(self._last_said)
                # Toggling silent mode is the one thing she always says out loud (a whisper going in).
                self.speak(reply.say, force=any(a["type"] == "silent_mode" for a in reply.actions))
                if not (reply.listen_again or reply.on_yes):
                    break
                pending = reply if reply.on_yes else None
                self.ui.show("listening")
        except Exception:
            log.exception("conversation failed")
            self.ui.said("Oops, something broke inside me.")
        finally:
            self.busy = False
            # Silent: leave the bubble up long enough to read it.
            self.ui.hide(2.0 + (min(8.0, len(self._last_said) / 14) if cfg.get("silent") else 0))
