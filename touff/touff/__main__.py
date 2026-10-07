"""Run Touff.

    python -m touff                 tray + pop-up + voice, opens the settings window (the real thing)
    python -m touff --background    same, but stays in the tray (how Windows starts her at login)
    python -m touff --settings      open the settings window (already the default without --background)
    python -m touff --console       voice only, logs to the terminal
    python -m touff --text "..."    one request typed instead of spoken
    python -m touff --download      fetch the speech models and exit
    python -m touff --install-voice-pack   build the expressive GPU voice (NVIDIA, ~10 GB)

Only one windowed Touff runs at a time (per data folder): launching her again just brings
up the running one's settings window, see instance.py.

Logs also go to %APPDATA%\\Touff\\touff.log.
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
import threading
import time


def _setup_logging(debug: bool) -> None:
    # The windowed build has no console: sys.stdout/stderr are None there, and libraries
    # that print (progress bars, warnings) would crash on them.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    from .store import data_dir

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handlers: list[logging.Handler] = [console]
    try:
        logfile = logging.handlers.RotatingFileHandler(data_dir() / "touff.log", maxBytes=1 << 20, backupCount=2, encoding="utf-8")
        logfile.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handlers.append(logfile)
    except OSError:
        pass
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, handlers=handlers)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per model download request
    log = logging.getLogger("touff")
    sys.excepthook = lambda *exc: log.critical("Crashed", exc_info=exc)
    threading.excepthook = lambda a: log.error("Thread %s crashed", a.thread and a.thread.name, exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def _already_running(show: bool) -> bool:
    """If another Touff (same data folder) is running, ask it to show settings and say so."""
    from . import instance
    from .store import data_dir

    log = logging.getLogger("touff")
    try:
        if instance.acquire(data_dir()):
            return False
    except Exception:
        log.exception("single-instance check failed; starting anyway")
        return False
    if not show:
        log.info("Touff is already running; nothing to do")
        return True
    if instance.notify_show(data_dir()):
        log.info("Touff is already running: showed her settings instead of starting a second copy")
        return True
    # No answer: usually the old copy is still shutting down (quit, then reopened right away).
    # Wait for it to let go of the lock, then start normally.
    for _ in range(30):
        time.sleep(0.5)
        if instance.acquire(data_dir()):
            log.info("previous Touff finished closing; starting")
            return False
    log.warning("Touff is already running but didn't answer; not starting a second copy")
    return True


def _listen_for_second_launches(app):
    from . import instance
    from .store import data_dir

    try:
        return instance.Server(data_dir(), app.open_settings)
    except Exception:
        logging.getLogger("touff").exception("couldn't listen for second launches")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(prog="touff", description="Tiny desktop voice sidekick.")
    parser.add_argument("--text", help="handle one typed request and exit")
    parser.add_argument("--dry-run", action="store_true", help="with --text / --install-voice-pack: don't actually do it")
    parser.add_argument("--speak", action="store_true", help="with --text: say the answer out loud")
    parser.add_argument("--console", action="store_true", help="no windows, just the voice loop")
    parser.add_argument("--download", action="store_true", help="download speech models and exit")
    parser.add_argument("--install-voice-pack", action="store_true", help="install the expressive GPU voice and exit")
    parser.add_argument("--settings", action="store_true", help="open the settings window on start (the default)")
    parser.add_argument("--background", action="store_true", help="start in the tray without opening any window")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.debug)

    windowed = not (args.install_voice_pack or args.download or args.text or args.console)
    show_settings = args.settings or not args.background
    if windowed and _already_running(show=show_settings):
        return

    if args.install_voice_pack:
        from . import voicepack

        try:
            voicepack.install(lambda line: print(line, flush=True), dry_run=args.dry_run)
        except voicepack.VoicePackError as exc:
            print(exc)
            sys.exit(1)
        return

    from .store import Store

    store = Store()

    if args.download:
        from . import models

        models.ensure_all(store.config["voice"], store.config["whisper_model"], progress=print)
        print("All models downloaded.")
        return

    from .assistant import Assistant

    if args.text:
        assistant = Assistant(store)
        assistant.apps.refresh()
        if args.dry_run:
            assistant.executor.run = lambda actions, depth=0: []  # type: ignore[method-assign]
        reply = assistant.handle_text(args.text)
        print(f"{store.config['name']}: {reply.say}")
        for action in reply.actions:
            print(f"  -> {action['type']}({action['arg']})")
        print(f"  [{reply.source}]")
        if args.speak:
            assistant.load()
            assistant.speak(reply.say)
        return

    assistant = Assistant(store)
    if args.console:
        assistant.load()
        print(f"Say '{store.config['name']}' to wake me. Ctrl+C to quit.")
        try:
            assistant.run()
        except KeyboardInterrupt:
            pass
        return

    from . import autostart
    from .ui.app import DesktopApp

    if store.config["start_with_windows"] != autostart.is_enabled():  # the installer may have set it
        store.update_config({"start_with_windows": autostart.is_enabled()})
    autostart.upgrade()  # older Run entries lack --background and would pop the window up at login
    app = DesktopApp(assistant, show_settings=show_settings)
    server = _listen_for_second_launches(app)
    try:
        app.run()
    finally:
        if server is not None:
            server.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
