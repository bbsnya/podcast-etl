import pytest
from src.transform import transform_podcasts, transform_episodes


def test_transform_podcasts_empty():
    """Пустой список -> пустой DataFrame."""
    df = transform_podcasts([])
    assert df.empty


def test_transform_podcasts_basic():
    """Корректный подкаст -> одна строка с нужными полями."""
    raw = [{
        "collectionId": 123,
        "collectionName": "Test Podcast",
        "description": "Desc",
        "feedUrl": "http://example.com/rss",
        "trackCount": 10,
    }]
    df = transform_podcasts(raw)
    assert len(df) == 1
    assert df.iloc[0]["podcast_id"] == 123
    assert df.iloc[0]["title"] == "Test Podcast"
    assert df.iloc[0]["rss_url"] == "http://example.com/rss"


def test_transform_podcasts_drop_invalid():
    """Подкасты без podcast_id или rss_url отбрасываются."""
    raw = [
        {"collectionId": None, "collectionName": "X", "feedUrl": "http://x"},
        {"collectionId": 1, "collectionName": "Valid", "feedUrl": "http://valid"},
    ]
    df = transform_podcasts(raw)
    assert len(df) == 1
    assert df.iloc[0]["podcast_id"] == 1


def test_transform_episodes_duration_hms():
    """Длительность в формате HH:MM:SS парсится в секунды."""
    raw = [{
        "title": "Ep1",
        "pub_date": "Mon, 01 Jan 2026 12:00:00 GMT",
        "duration": "01:02:03",
        "audio_url": "http://x.mp3",
    }]
    df = transform_episodes(raw, 123)
    assert df.iloc[0]["duration_seconds"] == 3723  # 1*3600 + 2*60 + 3


def test_transform_episodes_duration_seconds():
    """Длительность в секундах парсится корректно."""
    raw = [{
        "title": "Ep2",
        "pub_date": "Mon, 01 Jan 2026 12:00:00 GMT",
        "duration": "300",
        "audio_url": None,
    }]
    df = transform_episodes(raw, 123)
    assert df.iloc[0]["duration_seconds"] == 300
