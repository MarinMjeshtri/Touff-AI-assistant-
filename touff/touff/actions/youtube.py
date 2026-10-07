"""Find a specific YouTube video without clicking around: a channel's newest upload,
or the top result for a search. No API key: YouTube's public search page and the
channel RSS feed are enough.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
       "Accept-Language": "en-US,en;q=0.9"}
_FILTER_VIDEOS = "EgIQAQ%3D%3D"
_FILTER_CHANNELS = "EgIQAg%3D%3D"


@dataclass
class Video:
    title: str
    url: str
    channel: str = ""


class NotFound(Exception):
    pass


def _get(url: str, timeout: float = 8) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _initial_data(html: str) -> dict:
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise NotFound("YouTube changed its page layout")
    return json.loads(m.group(1))


def _walk(node, key: str):
    """Yield every value stored under `key` anywhere in a nested JSON structure."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            yield from _walk(v, key)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item, key)


def _text(runs: dict | None) -> str:
    if not runs:
        return ""
    if "simpleText" in runs:
        return runs["simpleText"]
    return "".join(r.get("text", "") for r in runs.get("runs", []))


def search_url(query: str, kind: str = _FILTER_VIDEOS) -> str:
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}&sp={kind}"


def top_video(query: str) -> Video:
    """The first real video (no ads, shorts shelves or playlists) for a search."""
    data = _initial_data(_get(search_url(query)))
    for vr in _walk(data, "videoRenderer"):
        vid = vr.get("videoId")
        if vid:
            return Video(_text(vr.get("title")), f"https://www.youtube.com/watch?v={vid}", _text(vr.get("ownerText")))
    raise NotFound(f"no videos found for {query}")


def find_channel(name: str) -> tuple[str, str]:
    """(channel id, channel title) for a spoken channel name like "lazy mattman"."""
    data = _initial_data(_get(search_url(name, _FILTER_CHANNELS)))
    for cr in _walk(data, "channelRenderer"):
        if cr.get("channelId"):
            return cr["channelId"], _text(cr.get("title"))
    # Channel filter came back empty: fall back to the uploader of the top video.
    for vr in _walk(_initial_data(_get(search_url(name))), "videoRenderer"):
        for run in (vr.get("ownerText") or {}).get("runs", []):
            browse = run.get("navigationEndpoint", {}).get("browseEndpoint", {})
            if browse.get("browseId", "").startswith("UC"):
                return browse["browseId"], run.get("text", name)
    raise NotFound(f"couldn't find a channel called {name}")


def latest_video(channel: str) -> Video:
    """The newest upload of a channel, via its public RSS feed."""
    channel_id, title = find_channel(channel)
    feed = ET.fromstring(_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"))
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    entry = feed.find("a:entry", ns)
    if entry is None:
        raise NotFound(f"{title} hasn't uploaded anything")
    vid = entry.findtext("yt:videoId", default="", namespaces=ns)
    return Video(entry.findtext("a:title", default="", namespaces=ns), f"https://www.youtube.com/watch?v={vid}", title)
