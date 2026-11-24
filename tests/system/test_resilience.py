"""Системные тесты отказоустойчивости: недоступность источников, частичные сбои, откат транзакции."""
import pytest
import requests

pytest.importorskip("sqlalchemy")

from src import load, pipeline  # noqa: E402
from src.exceptions import ExtractionError  # noqa: E402
from src.transform import aggregate_podcast_stats, transform_episodes, transform_podcasts  # noqa: E402
from tests.conftest import count_rows  # noqa: E402
from tests.helpers import (  # noqa: E402
    ITUNES_URL, FakeResponse, make_episode, make_itunes_podcast, make_world, rss_xml,
)

pytestmark = pytest.mark.system
DS = "2026-11-23"


def test_itunes_unavailable_fails_task_so_airflow_retries(fake_storage):
    session, _ = make_world(2, 2)
    session.routes[ITUNES_URL] = requests.ConnectionError("down")
    with pytest.raises(ExtractionError):
        pipeline.stage_extract(DS, "x", 5, storage=fake_storage, session=session)


def test_single_feed_failure_does_not_stop_pipeline(fake_storage):
    session, podcasts = make_world(3, 2)
    session.routes[podcasts[1]["feedUrl"]] = FakeResponse(status=500)
    manifest = pipeline.stage_extract(DS, "x", 5, storage=fake_storage, session=session)
    assert manifest["failed_feeds"] == [2]
    assert set(manifest["rss_keys"]) == {"1", "3"}
    transformed = pipeline.stage_transform(DS, manifest, storage=fake_storage)
    assert transformed["podcasts"] == 3 and transformed["episodes"] == 4


def test_all_feeds_unavailable_fails(fake_storage):
    session, podcasts = make_world(2, 2)
    for p in podcasts:
        session.routes[p["feedUrl"]] = requests.Timeout("slow")
    with pytest.raises(ExtractionError):
        pipeline.stage_extract(DS, "x", 5, storage=fake_storage, session=session)


def test_empty_itunes_result_fails(fake_storage):
    session, _ = make_world(1, 1)
    session.routes[ITUNES_URL] = FakeResponse(json_data={"results": []})
    with pytest.raises(ExtractionError):
        pipeline.stage_extract(DS, "x", 5, storage=fake_storage, session=session)


def test_insecure_feed_is_skipped(fake_storage):
    session, _ = make_world(1, 2)
    insecure = make_itunes_podcast(9, "http://old.example.com/feed.xml")
    session.routes[ITUNES_URL] = FakeResponse(json_data={"results": [make_itunes_podcast(1), insecure]})
    manifest = pipeline.stage_extract(DS, "x", 5, storage=fake_storage, session=session)
    assert manifest["skipped_insecure"] == [9]
    assert "9" not in manifest["rss_keys"]


def test_malformed_feed_is_tolerated_in_transform(fake_storage):
    session, podcasts = make_world(2, 2)
    session.routes[podcasts[0]["feedUrl"]] = FakeResponse(content=b"<rss><channel>")      # битый XML
    manifest = pipeline.stage_extract(DS, "x", 5, storage=fake_storage, session=session)
    transformed = pipeline.stage_transform(DS, manifest, storage=fake_storage)
    assert transformed["episodes"] == 2          # эпизоды только из исправной ленты


def test_load_failure_rolls_back_whole_transaction(sqlite_engine, monkeypatch):
    podcasts = transform_podcasts([make_itunes_podcast(1)])
    episodes = transform_episodes([make_episode(i) for i in range(3)], 1)
    stats = aggregate_podcast_stats(episodes)

    def broken(*args, **kwargs):
        raise RuntimeError("БД недоступна посреди загрузки")

    monkeypatch.setattr(load, "_refresh_stats", broken)
    with pytest.raises(RuntimeError):
        load.load_all(podcasts, episodes, stats, engine=sqlite_engine, mode="full")
    assert count_rows(sqlite_engine, "podcasts") == 0
    assert count_rows(sqlite_engine, "episodes") == 0       # частичных данных нет


def test_recovery_after_failure(sqlite_engine, monkeypatch):
    """После сбоя повторный запуск доводит данные до корректного состояния."""
    podcasts = transform_podcasts([make_itunes_podcast(1)])
    episodes = transform_episodes([make_episode(i) for i in range(3)], 1)
    stats = aggregate_podcast_stats(episodes)
    original = load._refresh_stats
    monkeypatch.setattr(load, "_refresh_stats", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        load.load_all(podcasts, episodes, stats, engine=sqlite_engine, mode="full")
    monkeypatch.setattr(load, "_refresh_stats", original)
    load.load_all(podcasts, episodes, stats, engine=sqlite_engine, mode="full")
    assert count_rows(sqlite_engine, "episodes") == 3
