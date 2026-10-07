import pytest

from touff.actions.registry import Executor


def acts(reply):
    return [(a["type"], a["arg"]) for a in reply.actions]


@pytest.mark.parametrize("heard", ["please stay silent", "Stay quiet for a while", "silent mode on", "turn on silent mode",
                                   "mute yourself", "be silent", "don't talk out loud anymore", "go quiet"])
def test_silent_on(router, heard):
    reply = router.handle(heard)
    assert acts(reply) == [("silent_mode", "on")]
    assert "[whispering]" in reply.say


@pytest.mark.parametrize("heard", ["you can talk again", "silent mode off", "turn off silent mode", "unmute yourself", "talk again"])
def test_silent_off(router, heard):
    assert acts(router.handle(heard)) == [("silent_mode", "off")]


def test_plain_be_quiet_still_just_dismisses(router):
    assert router.handle("be quiet").actions == []
    assert router.handle("shut up").actions == []


def test_silent_action_flips_config(store, apps):
    ex = Executor(apps, store, announce=lambda s: None)
    ex.run([{"type": "silent_mode", "arg": "on"}])
    assert store.config["silent"] is True
    ex.run([{"type": "silent_mode", "arg": "off"}])
    assert store.config["silent"] is False


def test_silent_mode_skips_the_voice(store):
    from touff.assistant import Assistant

    a = Assistant(store)
    spoken = []

    class FakeVoice:
        def speak(self, text):
            spoken.append(text)

    class FakeMic:
        class muted:
            set = clear = staticmethod(lambda: None)
        drain = staticmethod(lambda: None)

    a.voice, a.mic = FakeVoice(), FakeMic()
    store.update_config({"silent": True})
    a.speak("hello")
    a.speak("[whispering] okay, going quiet", force=True)
    assert spoken == ["[whispering] okay, going quiet"]
