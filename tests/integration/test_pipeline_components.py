"""Интеграционные тесты взаимодействия компонентов: Extract → Transform → Quality → Load.

Внешние сервисы заменены заглушками (MinIO → память, HTTP → FakeSession, PostgreSQL → SQLite),
поэтому тесты выполняются без Docker.
"""
import pytest

pytest.importorskip("sqlalchemy")

from src import pipeline  # noqa: E402
from tests.conftest import count_rows  # noqa: E402
from tests.helpers import FakeResponse, make_world, rss_xml, make_episode  # noqa: E402

DS = "2026-11-23"


def run_until_transform(storage, session):
    manifest = pipeline.stage_extract(DS, "technology", 3, storage=storage, session=session)
    transformed = pipeline.stage_transform(DS, manifest, storage=storage)
    return manifest, transformed


def test_extract_stores_raw_data_in_lake(fake_storage):
    session, _ = make_world(3, 4)
    manifest = pipeline.stage_extract(DS, "technology", 3, storage=fake_storage, session=session)
    assert fake_storage.get_json(manifest["itunes_key"])[0]["collectionId"] == 1
    assert set(manifest["rss_keys"]) == {"1", "2", "3"}
    assert fake_storage.get_bytes("raw/rss/2026-11-23/1.xml").startswith(b"<?xml")


def test_transform_writes_processed_layer(fake_storage):
    session, _ = make_world(3, 4)
    _, transformed = run_until_transform(fake_storage, session)
    assert transformed["podcasts"] == 3 and transformed["episodes"] == 12
    assert len(fake_storage.get_json(transformed["stats_key"])) == 3


def test_full_pipeline_loads_dwh(fake_storage, sqlite_engine):
    pytest.importorskip("great_expectations")
    session, _ = make_world(3, 4)
    _, transformed = run_until_transform(fake_storage, session)
    quality = pipeline.stage_quality(DS, transformed, storage=fake_storage)
    assert fake_storage.get_json(quality["report_key"])[0]["passed"] is True
    counts = pipeline.stage_load(DS, transformed, storage=fake_storage, engine=sqlite_engine, mode="full")
    assert counts["podcasts"] == 3 and counts["episodes"] == 12
    assert count_rows(sqlite_engine, "episodes") == 12
    assert count_rows(sqlite_engine, "podcast_stats") == 3


def test_repeated_runs_do_not_duplicate_data(fake_storage, sqlite_engine):
    session, _ = make_world(2, 5)
    _, transformed = run_until_transform(fake_storage, session)
    for mode in ("full", "full", "incremental"):
        pipeline.stage_load(DS, transformed, storage=fake_storage, engine=sqlite_engine, mode=mode)
    assert count_rows(sqlite_engine, "episodes") == 10
    assert count_rows(sqlite_engine, "podcasts") == 2


def test_incremental_run_picks_up_only_new_episodes(fake_storage, sqlite_engine):
    session, podcasts = make_world(1, 3)
    _, transformed = run_until_transform(fake_storage, session)
    pipeline.stage_load(DS, transformed, storage=fake_storage, engine=sqlite_engine, mode="incremental")
    assert count_rows(sqlite_engine, "episodes") == 3

    feed = podcasts[0]["feedUrl"]
    session.routes[feed] = FakeResponse(content=rss_xml([make_episode(i) for i in range(5)]))   # +2 выпуска
    _, transformed = run_until_transform(fake_storage, session)
    counts = pipeline.stage_load(DS, transformed, storage=fake_storage, engine=sqlite_engine, mode="incremental")
    assert counts["episodes"] == 3 and counts["episodes_skipped"] == 2     # граничный + 2 новых
    assert count_rows(sqlite_engine, "episodes") == 5


def test_quality_gate_blocks_load(fake_storage):
    pytest.importorskip("great_expectations")
    from src.exceptions import DataQualityError

    session, _ = make_world(1, 3)
    _, transformed = run_until_transform(fake_storage, session)
    records = fake_storage.get_json(transformed["episodes_key"])
    records[0]["duration_seconds"] = -10
    fake_storage.put_json(transformed["episodes_key"], records)
    with pytest.raises(DataQualityError):
        pipeline.stage_quality(DS, transformed, storage=fake_storage)
