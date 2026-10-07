import pytest

from touff.actions import youtube
from touff.actions.registry import Executor


def acts(reply):
    return [(a["type"], a["arg"]) for a in reply.actions]


@pytest.mark.parametrize(
    "heard,expected",
    [
        ("Touff open the newest Lazy Mattman video", [("youtube_play", "latest:lazy mattman")]),
        ("play the latest video from mrbeast", [("youtube_play", "latest:mrbeast")]),
        ("play markiplier's newest video", [("youtube_play", "latest:markiplier")]),
        ("show me the newest video by lazy mattman on youtube", [("youtube_play", "latest:lazy mattman")]),
        ("play lose yourself on youtube", [("youtube_play", "lose yourself")]),
        ("search youtube for lofi beats", [("youtube_search", "lofi beats")]),
        ("play candy shop on spotify", [("spotify_search", "candy shop")]),
    ],
)
def test_youtube_intents(router, heard, expected):
    from touff.brain.text import strip_name

    assert acts(router.handle(strip_name(heard, ["touff"]))) == expected


def test_youtube_play_opens_the_video(store, apps, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    monkeypatch.setattr(youtube, "latest_video", lambda ch: youtube.Video("Godhead Aura", "https://www.youtube.com/watch?v=abc", ch))
    monkeypatch.setattr(youtube, "top_video", lambda q: youtube.Video("Lose Yourself", "https://www.youtube.com/watch?v=xyz"))
    ex = Executor(apps, store, announce=lambda s: None)
    assert ex.run([{"type": "youtube_play", "arg": "latest:lazy mattman"}, {"type": "youtube_play", "arg": "lose yourself"}]) == []
    assert opened == ["https://www.youtube.com/watch?v=abc", "https://www.youtube.com/watch?v=xyz"]


def test_youtube_play_falls_back_to_search_when_offline(store, apps, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)

    def boom(_):
        raise youtube.NotFound("offline")

    monkeypatch.setattr(youtube, "latest_video", boom)
    Executor(apps, store, announce=lambda s: None).run([{"type": "youtube_play", "arg": "latest:lazy mattman"}])
    assert opened == ["https://www.youtube.com/results?search_query=lazy+mattman+newest+video"]
