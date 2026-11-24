from datetime import datetime, timezone

import pandas as pd
import pytest

from src import transform as t
from src.transform import (
    aggregate_podcast_stats, clean_text, duration_bucket, make_episode_key, parse_duration,
    parse_pub_date, transform_episodes, transform_podcasts,
)
from tests.helpers import make_episode


# ---------- transform_podcasts ----------
def test_transform_podcasts_empty():
    assert transform_podcasts([]).empty


def test_transform_podcasts_basic():
    raw = [{"collectionId": 123, "collectionName": "Test Podcast", "feedUrl": "http://example.com/rss",
            "trackCount": 10, "artistName": "A", "primaryGenreName": "Tech", "country": "USA"}]
    df = transform_podcasts(raw, {123: {"description": "<p>Desc</p>", "language": "en"}})
    assert len(df) == 1
    row = df.iloc[0]
    assert row["podcast_id"] == 123
    assert row["title"] == "Test Podcast"
    assert row["rss_url"] == "http://example.com/rss"
    assert row["description"] == "Desc"          # обогащение из RSS + очистка HTML
    assert row["language"] == "en"
    assert row["genre"] == "Tech"


def test_transform_podcasts_drop_invalid_and_duplicates():
    raw = [
        {"collectionId": None, "collectionName": "X", "feedUrl": "http://x"},
        {"collectionId": 1, "collectionName": "Valid", "feedUrl": "http://valid"},
        {"collectionId": 1, "collectionName": "Valid dup", "feedUrl": "http://valid"},
        {"collectionId": 2, "collectionName": "No feed", "feedUrl": ""},
    ]
    df = transform_podcasts(raw)
    assert df["podcast_id"].tolist() == [1]


# ---------- parse_duration ----------
@pytest.mark.parametrize("value,expected", [
    ("01:02:03", 3723), ("5:30", 330), ("300", 300), ("90.7", 90), (" 45 ", 45), (120, 120),
    ("", None), (None, None), ("abc", None), ("-5", None), ("1:2:3:4", None), ("nan", None),
])
def test_parse_duration(value, expected):
    assert parse_duration(value) == expected


# ---------- parse_pub_date ----------
def test_parse_pub_date_gmt():
    assert parse_pub_date("Mon, 01 Jan 2026 12:00:00 GMT") == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def test_parse_pub_date_offset_converted_to_utc():
    assert parse_pub_date("Thu, 01 Jan 2026 12:00:00 +0300") == datetime(2026, 1, 1, 9, tzinfo=timezone.utc)


def test_parse_pub_date_iso_fallback_assumes_utc():
    assert parse_pub_date("2026-02-03 10:00:00") == datetime(2026, 2, 3, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", [None, "", "   ", "not a date"])
def test_parse_pub_date_invalid(value):
    assert parse_pub_date(value) is None


# ---------- обогащение ----------
@pytest.mark.parametrize("seconds,bucket", [
    (None, t.BUCKET_UNKNOWN), (0, "< 10 мин"), (599, "< 10 мин"), (600, "10-30 мин"), (1800, "30-60 мин"),
    (3600, "60-120 мин"), (7200, "60-120 мин"), (7201, "> 2 ч"),
])
def test_duration_bucket(seconds, bucket):
    assert duration_bucket(seconds) == bucket


def test_clean_text():
    assert clean_text("<p>Hello&nbsp;<b>world</b> &amp; co</p>\n  ok") == "Hello world & co ok"
    assert clean_text("   ") is None
    assert clean_text(None) is None
    assert len(clean_text("x" * 100, max_len=10)) == 10


def test_episode_key_deterministic_and_sensitive():
    d = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert make_episode_key(1, "g", "t", d) == make_episode_key(1, "g", "t", d)
    assert make_episode_key(1, "g", "t", d) != make_episode_key(2, "g", "t", d)
    assert make_episode_key(1, None, "t", None)        # работает без guid и даты


# ---------- transform_episodes ----------
def test_transform_episodes_duration_hms():
    df = transform_episodes([make_episode(0, duration="01:02:03")], 123)
    assert df.iloc[0]["duration_seconds"] == 3723


def test_transform_episodes_duration_seconds_and_missing_audio():
    df = transform_episodes([make_episode(0, duration="300", audio_url=None)], 123)
    assert df.iloc[0]["duration_seconds"] == 300
    assert pd.isna(df.iloc[0]["audio_url"])


def test_transform_episodes_enrichment_columns():
    df = transform_episodes([make_episode(0, duration="900")], 7)
    row = df.iloc[0]
    assert row["duration_bucket"] == "10-30 мин"
    assert row["pub_month"] == "2026-01"
    assert row["pub_year"] == 2026
    assert row["podcast_id"] == 7
    assert row["description"] == "Описание 0"        # HTML очищен


def test_transform_episodes_drops_missing_title_and_dedups():
    raws = [make_episode(0), make_episode(0), make_episode(1, title=None), make_episode(2)]
    df = transform_episodes(raws, 1)
    assert len(df) == 2
    assert df["episode_key"].is_unique


def test_transform_episodes_same_title_different_date_kept():
    raws = [make_episode(0, guid=None, title="Same"), make_episode(1, guid=None, title="Same")]
    assert len(transform_episodes(raws, 1)) == 2


def test_transform_episodes_missing_date_is_idempotent():
    raws = [make_episode(0, pub_date=None)]
    a, b = transform_episodes(raws, 1), transform_episodes(raws, 1)
    assert a.iloc[0]["episode_key"] == b.iloc[0]["episode_key"]
    assert pd.isna(a.iloc[0]["pub_date"])
    assert pd.isna(a.iloc[0]["pub_month"])


def test_transform_episodes_empty():
    assert transform_episodes([], 1).empty


# ---------- агрегация ----------
def test_aggregate_podcast_stats():
    raws = [make_episode(0, duration="600"), make_episode(1, duration="1200"),
            make_episode(2, duration=None), make_episode(3, duration="1800")]
    stats = aggregate_podcast_stats(transform_episodes(raws, 5))
    assert len(stats) == 1
    row = stats.iloc[0]
    assert row["podcast_id"] == 5
    assert row["episodes_loaded"] == 4
    assert row["avg_duration_seconds"] == 1200.0
    assert row["total_duration_seconds"] == 3600
    assert row["activity_segment"] == "high"           # 4 выпуска в пределах месяца
    assert row["first_pub_date"] < row["last_pub_date"]


def test_aggregate_segments_low_activity():
    raws = [make_episode(0), make_episode(400)]
    stats = aggregate_podcast_stats(transform_episodes(raws, 1))
    assert stats.iloc[0]["activity_segment"] == "low"


def test_aggregate_empty():
    assert aggregate_podcast_stats(pd.DataFrame(columns=t.EPISODE_COLUMNS)).empty
