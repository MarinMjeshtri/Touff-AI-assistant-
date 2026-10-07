from touff.actions.apps import App, AppIndex
from touff.assistant import sounds_unfinished
from touff.store import Store


def test_unfinished_sentences_keep_listening():
    assert sounds_unfinished("move my chrome screen to the first..")
    assert sounds_unfinished("Move Chrome to the.")
    assert sounds_unfinished("suggest some")
    assert not sounds_unfinished("open spotify")
    assert not sounds_unfinished("what time is it?")
    assert not sounds_unfinished("")


def test_one_shared_word_does_not_match_an_app():
    index = AppIndex()
    index.apps = [App("Resource Monitor", "start", "x"), App("Claude", "start", "y"), App("Google Chrome", "start", "z")]
    assert index.find("cloud on my second monitor") is None
    assert index.find("claude").name == "Claude"
    assert index.find("my chrome screen").name == "Google Chrome"


def test_old_configs_get_new_listening_defaults(tmp_path):
    (tmp_path / "config.json").write_text('{"silence_ms": 800, "whisper_model": "base.en", "name": "Touff"}')
    cfg = Store(tmp_path).config
    assert cfg["silence_ms"] == 1200
    assert cfg["whisper_model"] == "small.en"
    assert cfg["config_version"] == 2


def test_user_choices_survive_migration(tmp_path):
    (tmp_path / "config.json").write_text('{"silence_ms": 1500, "whisper_model": "medium.en"}')
    cfg = Store(tmp_path).config
    assert cfg["silence_ms"] == 1500 and cfg["whisper_model"] == "medium.en"


def test_wake_needs_someone_calling_her():
    from touff.assistant import called_by_name

    names = ["touff", "tough", "tuff", "toff"]
    for said in ["Touff.", "Touff?", "Hey Tuff, open Spotify", "Tough, open Spotify", "Hey Touff", "okay tough", "so, Touff, play",
                 "Tooth, open spot.", "Hey tooth.", "Toof, what's..."]:
        assert called_by_name(said, names), said
    for lyric in ["times are tough out here", "When the going gets tough the tough get going", "I said tough love",
                  "It is tough. Really tough.", "Stuff happens", "tough the tough get going", "This is getting tough",
                  "When the going gets tough, the tough", "It's tough tough tough tough"]:
        assert not called_by_name(lyric, names), lyric
    assert called_by_name("Jarvis, open chrome", ["jarvis"]) and not called_by_name("jar of peanuts", ["jarvis"])
