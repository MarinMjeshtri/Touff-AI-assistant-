import pytest

from touff.brain import glossary, intents, matcher
from touff.brain.router import answer_yes_no
from touff.brain.text import strip_name


def acts(reply):
    return [(a["type"], a["arg"]) for a in reply.actions]


# -- the headline example -------------------------------------------------------


def test_boot_up_the_sack_via_glossary(router, store):
    store.add_glossary("the sack", "The Binding of Isaac")
    reply = router.handle("Boot up the sack!")
    assert acts(reply) == [("open_app", "The Binding of Isaac: Rebirth")]


def test_boot_up_the_sack_as_custom_command(router, store):
    store.add_command(["boot up the sack"], [{"type": "open_steam_game", "arg": "250900"}], reply="Sack time!")
    reply = router.handle("ok boot up the sack please")
    assert acts(reply) == [("open_steam_game", "250900")]
    assert reply.say == "Sack time!"
    assert reply.source == "command"


def test_open_binding_of_isaac_without_any_setup(router):
    assert acts(router.handle("open binding of isaac")) == [("open_app", "The Binding of Isaac: Rebirth")]


# -- built-ins -------------------------------------------------------------------


@pytest.mark.parametrize(
    "heard,expected",
    [
        ("Open Spotify.", [("open_app", "Spotify")]),
        ("open spotfy", [("open_app", "Spotify")]),
        ("can you launch discord for me", [("open_app", "Discord")]),
        ("open vs code", [("open_app", "Visual Studio Code")]),
        ("open youtube", [("open_app", "youtube")]),
        ("open my downloads", [("open_app", "downloads")]),
        ("Search Google for cute cats.", [("google_search", "cute cats")]),
        ("google how tall is the eiffel tower", [("google_search", "how tall is the eiffel tower")]),
        ("search youtube for lofi beats", [("youtube_search", "lofi beats")]),
        ("play lose yourself on spotify", [("spotify_search", "lose yourself")]),
        ("look up pancake recipes on youtube", [("youtube_search", "pancake recipes")]),
        ("next song", [("media", "next")]),
        ("pause", [("media", "play_pause")]),
        ("turn it up", [("volume", "up")]),
        ("set a timer for 5 minutes", [("timer", "300")]),
        ("timer for ten seconds", [("timer", "10")]),
        ("open spotify and discord", [("open_app", "Spotify"), ("open_app", "Discord")]),
    ],
)
def test_builtin_intents(router, heard, expected):
    assert acts(router.handle(heard)) == expected


def test_x_does_not_open_xbox_by_accident(apps):
    assert apps.find("x").name == "x"  # the website, exact match


def test_unknown_goes_nowhere_offline(router):
    reply = router.handle("what's the meaning of life")
    assert reply.actions == [] and reply.source == "none"


def test_unknown_goes_to_brain(brainy):
    router, brain = brainy
    reply = router.handle("open spotify and play candy shop by fifty cent")
    assert reply.say == "brain says hi"
    assert brain.calls[0][0] == "open spotify and play candy shop by fifty cent"


def test_unresolvable_app_goes_to_brain(brainy):
    router, brain = brainy
    router.handle("open the thing i was working on yesterday")
    assert len(brain.calls) == 1


def test_risky_action_needs_yes(router):
    reply = router.handle("shut down the computer")
    assert reply.actions == [] and reply.on_yes is not None
    assert acts(reply.on_yes()) == [("shutdown_pc", "")]


def test_chat_and_time(router):
    assert router.handle("thank you").source == "chat"
    assert router.handle("what time is it").say.startswith("It's")


# -- learning --------------------------------------------------------------------


def test_learn_command_by_voice(router, store):
    reply = router.handle("remember that when I say boot up the sack I mean open binding of isaac")
    assert reply.on_yes is not None and "boot up the sack" in reply.say
    assert store.commands[-1]["phrases"] != ["boot up the sack"]  # not saved before yes
    reply.on_yes()
    saved = store.commands[-1]
    assert saved["phrases"] == ["boot up the sack"]
    assert saved["actions"] == [{"type": "open_app", "arg": "The Binding of Isaac: Rebirth"}]
    assert acts(router.handle("boot up the sack")) == [("open_app", "The Binding of Isaac: Rebirth")]


def test_learn_glossary_by_voice(router, store):
    reply = router.handle("remember that gg means good game")
    reply.on_yes()
    assert store.memories["glossary"] == [{"term": "gg", "meaning": "good game"}]


def test_learn_note_offline(router, store):
    router.handle("remember my favourite rapper is eminem").on_yes()
    assert store.memories["notes"] == ["my favourite rapper is eminem"]


# -- feisty mode ---------------------------------------------------------------


def test_feisty_mode_lets_brain_argue(brainy, store):
    router, brain = brainy
    store.update_config({"feisty_mode": True, "feisty_level": 100})
    reply = router.handle("open spotify")
    assert reply.say == "brain says hi"
    assert brain.calls[0][2] == [{"type": "open_app", "arg": "Spotify"}]


def test_feisty_off_never_asks_brain(brainy):
    router, brain = brainy
    router.handle("open spotify")
    assert brain.calls == []


# -- pieces ----------------------------------------------------------------------


def test_strip_name():
    assert strip_name("Hey Touff, open Spotify.", ["touff", "tough"]) == "open spotify"
    assert strip_name("Tough.", ["touff", "tough"]) == ""


def test_glossary_whole_words_only():
    g = [{"term": "cs", "meaning": "Counter-Strike 2"}]
    assert glossary.expand("open cs", g) == "open counter-strike 2"
    assert glossary.expand("open discs", g) == "open discs"


def test_single_word_phrase_needs_close_match():
    cmds = [{"phrases": ["music"], "actions": []}]
    assert matcher.best_command("play some music from the eighties", cmds)[0] is None
    assert matcher.best_command("music", cmds)[0] is not None


def test_yes_no():
    assert answer_yes_no("Yeah, do it.") is True
    assert answer_yes_no("nah") is False
    assert answer_yes_no("purple") is None


def test_intents_dont_eat_learning():
    assert intents.parse("when i say lights out lock the computer").kind == "learn"
