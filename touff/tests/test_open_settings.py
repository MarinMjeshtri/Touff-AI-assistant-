"""Opening Touff: the "open your settings" intent, the action, the window placement maths,
autostart's --background flag and the single-instance bits."""

import json
import subprocess
import sys

import pytest

from touff import autostart, instance
from touff.actions import windows as W
from touff.actions.registry import ACTIONS, Executor
from touff.brain import intents
from touff.brain.router import _describe


def acts(reply):
    return [(a["type"], a["arg"]) for a in reply.actions]


# -- intent ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "heard",
    [
        "Open your settings.",
        "open the settings",
        "open settings",
        "show me your settings",
        "show settings",
        "show me the settings",
        "open touff settings",
        "open touff's settings",
        "Touff, open your settings please",
        "can you open your settings window",
        "bring up your settings",
    ],
)
def test_open_settings_intent(router, heard):
    from touff.brain.text import strip_name

    reply = router.handle(strip_name(heard, ["touff"]))
    assert acts(reply) == [("open_settings", "")]
    assert reply.source == "intent"
    assert reply.say


def test_settings_beats_the_windows_settings_app(router, apps):
    from touff.actions.apps import App

    apps.apps.append(App("Settings", "start", "windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel"))
    assert acts(router.handle("open settings")) == [("open_settings", "")]
    assert acts(router.handle("show me your settings")) == [("open_settings", "")]
    # Other settings pages are still the Windows app, not hers.
    assert intents.parse("open windows settings").kind == "open"
    assert intents.parse("open sound settings").kind == "open"


def test_open_settings_action_is_safe_and_described():
    assert "open_settings" in ACTIONS and not ACTIONS["open_settings"].risky
    assert _describe([{"type": "open_settings", "arg": ""}]) == "open my settings"


def test_executor_open_settings_hook(apps, store):
    ex = Executor(apps, store, announce=lambda s: None)
    problems = ex.run([{"type": "open_settings", "arg": ""}])
    assert problems and "settings" in problems[0]  # no window in --text/--console

    calls = []
    ex.on_open_settings = lambda: calls.append(1)
    assert ex.run([{"type": "open_settings", "arg": ""}]) == []
    assert calls == [1]


# -- window placement --------------------------------------------------------------------


def test_center_rect():
    work = (1920, 0, 3840, 1040)  # a second monitor, taskbar at the bottom
    assert W.center_rect((980, 720), work) == (2390, 160, 3370, 880)
    # Bigger than the monitor: shrunk to fit, still inside.
    assert W.center_rect((3000, 2000), (0, 0, 1280, 680)) == (0, 0, 1280, 680)


def test_monitor_at():
    mons = [
        W.Monitor(1, (0, 0, 1920, 1080), (0, 0, 1920, 1040), True),
        W.Monitor(2, (1920, 0, 3840, 1080), (1920, 0, 3840, 1040), False),
    ]
    assert W.monitor_at((2500, 500), mons).number == 2
    assert W.monitor_at((10, 10), mons).number == 1
    assert W.monitor_at((-5000, 10), mons).number == 1  # nowhere: the primary
    assert W.monitor_at((0, 0), []) is None


# -- autostart -------------------------------------------------------------------------


def test_autostart_command_starts_in_background():
    assert autostart._command().endswith(" --background")


@pytest.mark.parametrize(
    "old,new",
    [
        ('"C:\\Program Files\\Touff\\Touff.exe"', '"C:\\Program Files\\Touff\\Touff.exe" --background'),
        ('"C:\\x\\pythonw.exe" -m touff', '"C:\\x\\pythonw.exe" -m touff --background'),
        ('"C:\\x\\pythonw.exe" -m touff --background', '"C:\\x\\pythonw.exe" -m touff --background'),
    ],
)
def test_autostart_upgrade_adds_flag(old, new):
    assert autostart.with_background_flag(old) == new


# -- single instance ----------------------------------------------------------------------


KEY = "ab" * 16


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def test_parse_info_rejects_garbage():
    assert instance.parse_info({"pid": 123, "port": 5000, "key": KEY}) == instance.Info(123, 5000, bytes.fromhex(KEY))
    for bad in (
        None, [], "x", {}, {"pid": 123, "port": 5000},
        {"pid": "123", "port": 5000, "key": KEY}, {"pid": 0, "port": 5000, "key": KEY},
        {"pid": 123, "port": 70000, "key": KEY}, {"pid": 123, "port": 5000, "key": "zz"},
        {"pid": 123, "port": 5000, "key": "abcd"},  # too short to be a real key
    ):
        assert instance.parse_info(bad) is None, bad


def test_read_info_missing_or_corrupt(tmp_path):
    path = tmp_path / instance.INFO_FILE
    assert instance.read_info(path) is None
    path.write_text("{not json", encoding="utf-8")
    assert instance.read_info(path) is None
    path.write_bytes(b"\xff\xfe\x00garbage")
    assert instance.read_info(path) is None


def test_read_info_ignores_a_crashed_instance(tmp_path):
    path = tmp_path / instance.INFO_FILE
    path.write_text(json.dumps({"pid": _dead_pid(), "port": 5000, "key": KEY}), encoding="utf-8")
    assert instance.read_info(path) is None
    import os

    path.write_text(json.dumps({"pid": os.getpid(), "port": 5000, "key": KEY}), encoding="utf-8")
    assert instance.read_info(path) == instance.Info(os.getpid(), 5000, bytes.fromhex(KEY))


def test_pid_alive():
    import os

    assert instance.pid_alive(os.getpid())
    assert not instance.pid_alive(_dead_pid())


def test_write_and_remove_info_only_removes_our_own(tmp_path):
    path = tmp_path / instance.INFO_FILE
    instance.write_info(path, instance.Info(111, 5000, bytes.fromhex(KEY)))
    assert json.loads(path.read_text(encoding="utf-8"))["port"] == 5000
    instance.remove_info(path, pid=222)  # a newer copy owns it now
    assert path.exists()
    instance.remove_info(path, pid=111)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []  # no temp files left behind


def test_mutex_name_depends_on_data_dir(tmp_path):
    a, b = instance.mutex_name(tmp_path / "a"), instance.mutex_name(tmp_path / "b")
    assert a != b and a.startswith("Local\\Touff-")
    assert instance.mutex_name(tmp_path / "a") == a


def test_notify_with_stale_file_gives_up(tmp_path):
    (tmp_path / instance.INFO_FILE).write_text(json.dumps({"pid": _dead_pid(), "port": 5000, "key": KEY}), encoding="utf-8")
    assert instance.notify_show(tmp_path, wait=0.5) is False


def test_server_round_trip(tmp_path):
    import threading

    shown = threading.Event()
    server = instance.Server(tmp_path, shown.set)
    try:
        assert instance.read_info(tmp_path / instance.INFO_FILE) == server.info
        # Someone with the wrong key gets nothing.
        wrong = instance.Info(server.info.pid, server.info.port, b"\x00" * 32)
        assert instance._send(wrong, {"cmd": "show"}, timeout=1) is False
        assert not shown.is_set()
        assert instance.notify_show(tmp_path, wait=3)
        assert shown.wait(3)
    finally:
        server.close()
    assert not (tmp_path / instance.INFO_FILE).exists()
