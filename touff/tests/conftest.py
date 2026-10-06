import pytest

from touff.actions.apps import App, AppIndex
from touff.brain.router import Router
from touff.store import Store


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("TOUFF_HOME", str(tmp_path))
    s = Store(tmp_path)
    s.update_config({"brain": "offline"})
    return s


@pytest.fixture
def apps():
    index = AppIndex()
    index.apps = index._static_entries() + [
        App("Spotify", "start", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"),
        App("Steam", "start", "Valve.Steam"),
        App("The Binding of Isaac: Rebirth", "steam", "250900"),
        App("Counter-Strike 2", "steam", "730"),
        App("Discord", "start", "com.squirrel.Discord.Discord"),
        App("Visual Studio Code", "start", "Microsoft.VisualStudioCode"),
        App("Xbox", "start", "Microsoft.GamingApp_8wekyb3d8bbwe!Microsoft.Xbox.App"),
    ]
    return index


class FakeBrain:
    available = True

    def __init__(self):
        self.calls = []

    def ask(self, heard, conversation, interpreted="", planned=None):
        from touff.brain.claude_cli import BrainReply

        self.calls.append((heard, interpreted, planned))
        return BrainReply(say="brain says hi")


@pytest.fixture
def router(store, apps):
    return Router(store, apps, brain=None)


@pytest.fixture
def brainy(store, apps):
    store.update_config({"brain": "claude"})
    brain = FakeBrain()
    return Router(store, apps, brain=brain), brain
