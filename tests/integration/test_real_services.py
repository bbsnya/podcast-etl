"""Интеграционные тесты с РЕАЛЬНЫМИ источниками и сервисами стенда.

Запуск:  RUN_INTEGRATION=1 docker compose exec airflow-webserver pytest tests/integration/test_real_services.py -m integration -s
(нужны интернет и поднятые postgres/minio).
"""
import os
import uuid

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 не задан"),
]


def test_real_itunes_and_rss():
    from src.extract import build_session, fetch_podcasts_from_itunes, fetch_rss_feed, parse_rss_content

    session = build_session()
    podcasts = fetch_podcasts_from_itunes("technology", 5, session)
    assert podcasts, "iTunes вернул пустой результат"
    feeds = [p["feedUrl"] for p in podcasts if str(p.get("feedUrl", "")).startswith("https://")]
    assert feeds, "нет HTTPS-лент"
    parsed = parse_rss_content(fetch_rss_feed(feeds[0], session))
    assert parsed["episodes"], "в ленте нет выпусков"


def test_real_minio_roundtrip():
    from src.storage import Storage

    storage = Storage()
    storage.ensure_bucket()
    key = f"tests/{uuid.uuid4()}.json"
    storage.put_json(key, {"ok": True})
    assert storage.get_json(key) == {"ok": True}


def test_real_postgres_schema_and_views():
    import sqlalchemy as sa

    from src.load import get_engine

    with get_engine().connect() as conn:
        tables = {r[0] for r in conn.execute(sa.text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))}
        assert {"podcasts", "episodes", "podcast_stats", "v_kpi", "v_top_podcasts"} <= tables
        assert conn.execute(sa.text("SELECT COUNT(*) FROM v_kpi")).scalar() == 1


def test_real_end_to_end_pipeline():
    from src import pipeline
    from src.exceptions import DataQualityError  # noqa: F401
    from src.storage import Storage

    ds = f"it-{uuid.uuid4().hex[:8]}"
    storage = Storage()
    manifest = pipeline.stage_extract(ds, "technology", 5, storage=storage)
    transformed = pipeline.stage_transform(ds, manifest, storage=storage)
    pipeline.stage_quality(ds, transformed, storage=storage)
    counts = pipeline.stage_load(ds, transformed, storage=storage, mode="full")
    assert counts["podcasts"] > 0
