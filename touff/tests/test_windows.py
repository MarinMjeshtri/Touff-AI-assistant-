import pytest

from touff.actions import windows as W
from touff.actions.apps import App
from touff.actions.registry import ACTIONS, Executor
from touff.brain.router import _describe


def acts(reply):
    return [(a["type"], a["arg"]) for a in reply.actions]


@pytest.fixture
def chrome(apps):
    apps.apps.append(App("Google Chrome", "start", "Chrome"))
    return apps


# -- intents -> actions ------------------------------------------------------------


@pytest.mark.parametrize(
    "heard,expected",
    [
        ("Move my Chrome window to my second monitor.", [("window", "move:chrome:2")]),
        ("move my chrome screen to the first monitor", [("window", "move:chrome:1")]),
        ("put spotify on the other screen", [("window", "move:spotify:next")]),
        ("send discord to monitor 2", [("window", "move:discord:2")]),
        ("throw vs code over to the left monitor", [("window", "move:vs code:left")]),
        ("drag the steam window to my main display", [("window", "move:steam:1")]),
        ("move isaac to the 2nd screen", [("window", "move:The Binding of Isaac: Rebirth:2")]),
        ("maximize spotify", [("window", "maximize:spotify")]),
        ("full screen chrome", [("window", "maximize:chrome")]),
        ("make discord full screen", [("window", "maximize:discord")]),
        ("minimize discord", [("window", "minimize:discord")]),
        ("close notepad", [("window", "close:notepad")]),
        ("switch to discord", [("window", "focus:discord")]),
        ("go to file explorer", [("window", "focus:file explorer")]),
        ("focus on vs code", [("window", "focus:vs code")]),
        ("show me spotify", [("window", "focus:spotify")]),
        ("snap chrome to the left", [("window", "snap_left:chrome")]),
        ("snap spotify right", [("window", "snap_right:spotify")]),
        ("move chrome to the right side", [("window", "snap_right:chrome")]),
        ("minimize everything", [("window", "minimize_all:")]),
        ("show the desktop", [("window", "minimize_all:")]),
        ("show my desktop", [("window", "minimize_all:")]),
        ("hide everything", [("window", "minimize_all:")]),
        ("maximize this window", [("window", "maximize:active")]),
        ("press control shift escape", [("hotkey", "control shift escape")]),
        ("press ctrl+t", [("hotkey", "ctrl+t")]),
        ("maximize spotify and discord", [("window", "maximize:spotify"), ("window", "maximize:discord")]),
    ],
)
def test_window_intents(router, heard, expected):
    reply = router.handle(heard)
    assert acts(reply) == expected
    assert reply.source == "intent"


def test_open_on_second_monitor(chrome, router):
    reply = router.handle("open chrome on my second monitor")
    assert acts(reply) == [("open_app", "Google Chrome"), ("window", "move:chrome:2")]
    assert "monitor 2" in reply.say


def test_open_on_other_screen(router):
    assert acts(router.handle("launch spotify on the other screen")) == [("open_app", "Spotify"), ("window", "move:spotify:next")]


def test_open_then_move_it(chrome, router):
    reply = router.handle("open chrome and move it to my second monitor")
    assert acts(reply) == [("open_app", "Google Chrome"), ("window", "move:Google Chrome:2")]


@pytest.mark.parametrize("heard", ["open spotify", "turn it up", "next song", "go to sleep", "go back"])
def test_window_intents_dont_steal(router, heard):
    assert not any(a["type"] in ("window", "hotkey") for a in router.handle(heard).actions)


def test_unknown_app_goes_to_brain(brainy):
    router, brain = brainy
    router.handle("move the thingamajig to my second monitor")
    router.handle("close the door")
    router.handle("close youtube")  # a tab, not the whole browser
    router.handle("press play")
    assert len(brain.calls) == 4


def test_blocked_hotkey_is_refused_locally(router):
    reply = router.handle("press win r")
    assert reply.actions == [] and reply.say


def test_describe_reads_naturally():
    assert _describe([{"type": "window", "arg": "move:chrome:2"}]) == "move chrome to monitor 2"
    assert _describe([{"type": "window", "arg": "snap_left:spotify"}]) == "snap spotify to the left"
    assert _describe([{"type": "window", "arg": "minimize_all:"}]) == "show the desktop"
    assert _describe([{"type": "hotkey", "arg": "ctrl+t"}]) == "press ctrl+t"


def test_actions_are_whitelisted_and_not_risky():
    assert not ACTIONS["window"].risky and not ACTIONS["hotkey"].risky
    assert "move:chrome:2" in ACTIONS["window"].arg


# -- arg parsing ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg,expected",
    [
        ("move:chrome:2", ("move", "chrome", "2")),
        ("move:chrome:next", ("move", "chrome", "next")),
        ("move:chrome:second", ("move", "chrome", "2")),
        ("move:chrome", ("move", "chrome", "next")),
        ("move:The Binding of Isaac: Rebirth:2", ("move", "The Binding of Isaac: Rebirth", "2")),
        ("maximize:The Binding of Isaac: Rebirth", ("maximize", "The Binding of Isaac: Rebirth", "")),
        ("maximise:spotify", ("maximize", "spotify", "")),
        ("snap_left:chrome", ("snap_left", "chrome", "")),
        ("minimize_all:", ("minimize_all", "", "")),
        ("minimize_all", ("minimize_all", "", "")),
    ],
)
def test_parse_window_arg(arg, expected):
    assert W.parse_window_arg(arg) == expected


@pytest.mark.parametrize("arg", ["", "teleport:chrome", "maximize:", "close"])
def test_parse_window_arg_rejects(arg):
    with pytest.raises(ValueError):
        W.parse_window_arg(arg)


@pytest.mark.parametrize(
    "combo,mods,key",
    [
        ("ctrl+t", [0x11], 0x54),
        ("win+shift+s", [0x5B, 0x10], 0x53),
        ("alt+tab", [0x12], 0x09),
        ("ctrl+shift+esc", [0x11, 0x10], 0x1B),
        ("control shift escape", [0x11, 0x10], 0x1B),
        ("f5", [], 0x74),
        ("win+d", [0x5B], 0x44),
        ("ctrl+w", [0x11], 0x57),
        ("space", [], 0x20),
        ("Ctrl + Page Up", [0x11], 0x21),
        ("alt+f4", [0x12], 0x73),
    ],
)
def test_parse_hotkey(combo, mods, key):
    assert W.parse_hotkey(combo) == (mods, key)


@pytest.mark.parametrize("combo", ["win+r", "win+x", "Windows R", "ctrl+win+r", "win+shift+x"])
def test_blocked_hotkeys(combo):
    with pytest.raises(PermissionError):
        W.parse_hotkey(combo)


@pytest.mark.parametrize("combo", ["", "banana", "t+ctrl", "ctrl+banana"])
def test_bad_hotkeys(combo):
    with pytest.raises(ValueError):
        W.parse_hotkey(combo)


def test_executor_reports_bad_args_without_touching_windows(store, apps):
    ex = Executor(apps, store, announce=lambda s: None)
    assert ex.run([{"type": "hotkey", "arg": "win+r"}]) == ["win+r is blocked, it opens a run/command menu"]
    assert "unknown window operation" in ex.run([{"type": "window", "arg": "teleport:chrome"}])[0]


# -- monitors --------------------------------------------------------------------------

# A laptop (primary, in the middle), one screen to its left, one to its right.
LEFT, LAPTOP, RIGHT = (-1920, 0, 0, 1080), (0, 0, 1920, 1080), (1920, -200, 4480, 1240)


def test_monitor_numbering_primary_first_then_left_to_right():
    raw = [(RIGHT, False), (LAPTOP, True), (LEFT, False)]
    assert W.order_monitors(raw) == [1, 2, 0]


@pytest.mark.parametrize(
    "word,target",
    [("second", "2"), ("2nd", "2"), ("two", "2"), ("2", "2"), ("the second monitor", "2"), ("other", "next"),
     ("next", "next"), ("main", "1"), ("primary", "1"), ("first", "1"), ("left", "left"), ("right", "right"),
     ("banana", None)],
)
def test_monitor_words(word, target):
    assert W.monitor_word(word) == target


def test_resolve_target():
    mons = [LAPTOP, LEFT, RIGHT]  # already in spoken order
    assert W.resolve_target(mons, 0, "2") == 1
    assert W.resolve_target(mons, 0, "4") is None
    assert W.resolve_target(mons, 0, "next") == 1
    assert W.resolve_target(mons, 2, "next") == 0  # wraps
    assert W.resolve_target(mons, 0, "previous") == 2
    assert W.resolve_target(mons, 0, "left") == 1
    assert W.resolve_target(mons, 0, "right") == 2
    assert W.resolve_target(mons, 1, "left") is None
    assert W.resolve_target(mons, 2, "left") == 0  # the closest one, not the far left
    assert W.resolve_target(mons[:1], 0, "next") == 0


def test_scale_rect_keeps_relative_position():
    src, dst = (0, 0, 1920, 1040), (1920, 0, 4480, 1400)
    assert W.scale_rect((0, 0, 960, 520), src, dst) == (1920, 0, 3200, 700)
    assert W.scale_rect((960, 520, 1920, 1040), src, dst) == (3200, 700, 4480, 1400)


def test_scale_rect_stays_on_target():
    x0, y0, x1, y1 = W.scale_rect((1800, 900, 2600, 1500), (0, 0, 1920, 1080), (-1280, 0, 0, 720))
    assert -1280 <= x0 and x1 <= 0 and 0 <= y0 and y1 <= 720


def test_half_rect():
    assert W.half_rect((0, 0, 1920, 1040), "left") == (0, 0, 960, 1040)
    assert W.half_rect((0, 0, 1920, 1040), "right") == (960, 0, 1920, 1040)


# -- window matching ------------------------------------------------------------------


def _wins():
    return [
        W.Window(1, "Inbox - Gmail - Google Chrome", "chrome", "Chrome_WidgetWin_1", 0),
        W.Window(2, "touff - Visual Studio Code", "code", "Chrome_WidgetWin_1", 1),
        W.Window(3, "Spotify Premium", "spotify", "Chrome_WidgetWin_1", 2),
        W.Window(4, "Downloads", "explorer", "CabinetWClass", 3),
        W.Window(5, "Binding of Isaac: Rebirth", "isaac-ng", "SDL_app", 4),
        W.Window(6, "Old tab - Google Chrome", "chrome", "Chrome_WidgetWin_1", 5),
        W.Window(7, "Claude", "claude", "Chrome_WidgetWin_1", 6),
    ]


@pytest.mark.parametrize(
    "query,hwnd",
    [("chrome", 1), ("google chrome", 1), ("my chrome window", 1), ("vs code", 2), ("Visual Studio Code", 2),
     ("spotify", 3), ("spotfy", 3), ("file explorer", 4), ("downloads", 4), ("The Binding of Isaac: Rebirth", 5),
     ("claude", 7), ("active", 1), ("discord", None), ("notepad", None)],
)
def test_find_window(query, hwnd):
    win = W.find_window(query, _wins())
    assert (win.hwnd if win else None) == hwnd
