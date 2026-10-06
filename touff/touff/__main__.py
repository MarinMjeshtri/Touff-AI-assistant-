"""Run Touff.

    python -m touff                 tray + pop-up + voice (the real thing)
    python -m touff --settings      same, and open the settings window
    python -m touff --console       voice only, logs to the terminal
    python -m touff --text "..."    one request typed instead of spoken
    python -m touff --download      fetch the speech models and exit
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="touff", description="Tiny desktop voice sidekick.")
    parser.add_argument("--text", help="handle one typed request and exit")
    parser.add_argument("--dry-run", action="store_true", help="with --text: don't actually run the actions")
    parser.add_argument("--speak", action="store_true", help="with --text: say the answer out loud")
    parser.add_argument("--console", action="store_true", help="no windows, just the voice loop")
    parser.add_argument("--download", action="store_true", help="download speech models and exit")
    parser.add_argument("--settings", action="store_true", help="open the settings window on start")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s %(name)s: %(message)s")

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

    from .ui.app import DesktopApp

    DesktopApp(assistant).run()
    sys.exit(0)


if __name__ == "__main__":
    main()
