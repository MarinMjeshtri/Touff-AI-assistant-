"""The main loop: wait for the name -> listen -> understand -> act -> talk back."""

from __future__ import annotations

import logging
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
        self.ready = threading.Event()
        self.quit = threading.Event()
        self.paused = threading.Event()  # "mute mic" from the tray
        self.talk_now = threading.Event()  # "talk to Touff" from the tray
        self._mute_count = 0
        self._mute_lock = threading.Lock()
        self.busy = False
        store.on_change(self._on_store_change)
        threading.Thread(target=self.apps.refresh, daemon=True).start()

    # -- setup -----------------------------------------------------------------

    def load(self) -> None:
        """Download (first run) and load all models. Slow: call from a worker thread."""
        from . import models
        from .audio.mic import Mic
        from .audio.stt import STT
        from .audio.tts import Voice
        from .audio.wakeword import WakeWord

        cfg = self.store.config
        self.ui.status("Waking up my ears...")
        self.wake = WakeWord(models.vosk_path(), self._wake_words())
        self.voice = self._load_voice()
        self.ui.status("Loading speech recognition...")
        self.stt = STT(models.whisper_path(cfg["whisper_model"]))
        self.mic = Mic(cfg.get("mic_device"))
        self.mic.start()
        self.ready.set()
        self.ui.status("Ready")

    def _load_voice(self):
        from . import models
        from .audio import expressive
        from .audio.tts import Voice

        cfg = self.store.config
        engine = cfg.get("voice_engine", "auto")
        if engine in ("auto", "expressive") and expressive.available():
            self.ui.status("Warming up my expressive voice...")
            try:
                return expressive.ExpressiveVoice(cfg.get("voice_clip", ""), cfg["volume"])
            except Exception:
                log.exception("expressive voice failed, falling back to Piper")
        self.ui.status("Warming up my voice...")
        return Voice(models.voice_path(cfg["voice"]), cfg["speech_speed"], cfg["volume"])

    def _wake_words(self) -> list[str]:
        cfg = self.store.config
        return [cfg["name"].lower()] + [w.lower() for w in cfg.get("wake_words", [])]

    def _on_store_change(self, what: str) -> None:
        if what != "config" or not self.ready.is_set():
            return
        cfg = self.store.config
        self.wake.set_words(self._wake_words())
        self.voice.speed = cfg["speech_speed"]
        self.voice.volume = cfg["volume"]

    def change_voice(self) -> None:
        """Reload the voice after the engine, Piper voice or clip changed in settings."""
        old = self.voice
        self.voice = self._load_voice()
        if old is not None and hasattr(old, "close"):
            old.close()

    # -- talking ---------------------------------------------------------------

    def speak(self, text: str) -> None:
        if not text or self.voice is None:
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
                from . import models
                from .audio.tts import Voice

                cfg = self.store.config
                self.voice = Voice(models.voice_path(cfg["voice"]), cfg["speech_speed"], cfg["volume"])
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
            self.ui.hide(2.5)

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
        """Words Whisper should expect, so it spells names and slang the way the user does."""
        cfg = self.store.config
        words = [cfg["name"]]
        words += [p for c in self.store.commands for p in c["phrases"]][:25]
        words += [g["term"] for g in self.store.memories["glossary"]][:25]
        words += [a.name for a in self.apps.apps if a.kind == "steam"][:15]
        return f"{cfg['name']}, open Spotify. " + ", ".join(dict.fromkeys(words)) + "."

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
                self.converse(preroll=self.wake.take_preroll())
                self.wake.reset()
                self.mic.drain()

    def converse(self, preroll: list[bytes]) -> None:
        from .audio.mic import record_utterance
        from .audio.tts import chime

        self.busy = True
        cfg = self.store.config
        try:
            self.ui.show("listening")
            if cfg.get("chime"):
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
                text = self.stt.transcribe(audio, hint=self._hint())
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
                self.ui.said(strip_tags(reply.say))
                self.speak(reply.say)
                if not (reply.listen_again or reply.on_yes):
                    break
                pending = reply if reply.on_yes else None
                self.ui.show("listening")
        except Exception:
            log.exception("conversation failed")
            self.ui.said("Oops, something broke inside me.")
        finally:
            self.busy = False
            self.ui.hide(2.0)
