"""Общие заглушки для тестов: хранилище в памяти, HTTP-сессия, генераторы данных."""
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

import requests

ITUNES_URL = "https://itunes.apple.com/search"


class FakeStorage:
    """Подмена src.storage.Storage (MinIO) словарём в памяти."""

    def __init__(self) -> None:
        self.objects: Dict[str, bytes] = {}

    def ensure_bucket(self) -> None:
        pass

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.objects[key] = bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    def put_json(self, key: str, obj: Any) -> str:
        return self.put_bytes(key, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key).decode("utf-8"))


class FakeResponse:
    def __init__(self, content: bytes = b"", json_data: Any = None, status: int = 200, json_error: bool = False):
        self.content = content
        self._json = json_data
        self.status_code = status
        self._json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        if self._json_error:
            raise ValueError("not json")
        return self._json

    def iter_content(self, chunk_size: int = 65536):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class FakeSession:
    """routes: url -> FakeResponse | Exception. Неизвестный URL = ConnectionError."""

    def __init__(self, routes: Dict[str, Any]):
        self.routes = routes
        self.calls: List[str] = []

    def get(self, url: str, params: Optional[dict] = None, timeout: Any = None, stream: bool = False) -> FakeResponse:
        self.calls.append(url)
        target = self.routes.get(url)
        if target is None:
            raise requests.ConnectionError(f"no route for {url}")
        if isinstance(target, Exception):
            raise target
        return target


def rfc822(dt: datetime) -> str:
    return format_datetime(dt.astimezone(timezone.utc), usegmt=True)


def make_episode(i: int, base: datetime = datetime(2026, 1, 1, 12, tzinfo=timezone.utc), **overrides: Any) -> Dict:
    ep = {
        "title": f"Выпуск {i}",
        "guid": f"guid-{i}",
        "pub_date": rfc822(base + timedelta(days=i)),
        "duration": str(600 * (i + 1)),
        "description": f"<p>Описание <b>{i}</b></p>",
        "audio_url": f"https://cdn.example.com/{i}.mp3",
    }
    ep.update(overrides)
    return ep


def rss_xml(episodes: List[Dict], language: str = "ru", description: str = "Описание канала") -> bytes:
    items = []
    for ep in episodes:
        parts = []
        if ep.get("title") is not None:
            parts.append(f"<title>{escape(ep['title'])}</title>")
        if ep.get("guid"):
            parts.append(f"<guid>{escape(ep['guid'])}</guid>")
        if ep.get("pub_date"):
            parts.append(f"<pubDate>{ep['pub_date']}</pubDate>")
        if ep.get("duration") is not None:
            parts.append(f"<itunes:duration>{ep['duration']}</itunes:duration>")
        if ep.get("description"):
            parts.append(f"<description>{escape(ep['description'])}</description>")
        if ep.get("audio_url"):
            parts.append(f'<enclosure url="{ep["audio_url"]}" type="audio/mpeg"/>')
        items.append("<item>" + "".join(parts) + "</item>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>'
        f"<title>Канал</title><language>{language}</language><description>{escape(description)}</description>"
        + "".join(items)
        + "</channel></rss>"
    )
    return xml.encode("utf-8")


def make_itunes_podcast(pid: int, feed_url: Optional[str] = None) -> Dict:
    return {
        "collectionId": pid,
        "collectionName": f"Подкаст {pid}",
        "feedUrl": feed_url if feed_url is not None else f"https://feeds.example.com/{pid}.xml",
        "trackCount": 5,
        "artistName": f"Автор {pid}",
        "primaryGenreName": "Technology",
        "country": "USA",
    }


def make_world(n_podcasts: int = 3, n_episodes: int = 5):
    """Возвращает (FakeSession, список_iTunes) с n_podcasts лентами по n_episodes выпусков."""
    podcasts = [make_itunes_podcast(pid) for pid in range(1, n_podcasts + 1)]
    routes: Dict[str, Any] = {ITUNES_URL: FakeResponse(json_data={"resultCount": len(podcasts), "results": podcasts})}
    for p in podcasts:
        eps = [make_episode(i) for i in range(n_episodes)]
        routes[p["feedUrl"]] = FakeResponse(content=rss_xml(eps))
    return FakeSession(routes), podcasts
