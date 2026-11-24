"""NFR-4: обработка 100 000 записей быстрее 5 минут (Transform + Load).

По умолчанию нагрузка идёт в SQLite. Для замера на PostgreSQL из docker-стенда:
    docker compose exec -e POSTGRES_DB=podcast_test_dwh -e RUN_PG_PERF=1 airflow-webserver pytest tests/system/test_performance.py -m system -s --no-cov
(таблицы берутся из sql/init.sql; тест очищает только свои данные с podcast_id >= 900000000).
"""
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("sqlalchemy")

from src import load  # noqa: E402
from src.transform import aggregate_podcast_stats, transform_episodes, transform_podcasts  # noqa: E402
from tests.helpers import make_itunes_podcast, rfc822  # noqa: E402

pytestmark = pytest.mark.system

N_RECORDS = 100_000
N_PODCASTS = 100
LIMIT_SECONDS = 300
BASE_ID = 900_000_000


def build_raw(per_podcast: int):
    base = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        {"title": f"Выпуск {i}", "guid": f"g-{i}", "pub_date": rfc822(base + timedelta(hours=i)),
         "duration": str(300 + i % 5000), "description": f"<p>Описание {i}</p>", "audio_url": f"https://x/{i}.mp3"}
        for i in range(per_podcast)
    ]


def test_transform_and_load_100k_records_under_5_minutes(sqlite_engine):
    import pandas as pd

    per_podcast = N_RECORDS // N_PODCASTS
    raw = build_raw(per_podcast)

    started = time.perf_counter()
    podcasts = transform_podcasts([make_itunes_podcast(BASE_ID + i) for i in range(N_PODCASTS)])
    frames = [transform_episodes(raw, BASE_ID + i) for i in range(N_PODCASTS)]
    episodes = pd.concat(frames, ignore_index=True)
    stats = aggregate_podcast_stats(episodes)
    t_transform = time.perf_counter() - started

    engine = sqlite_engine
    if os.getenv("RUN_PG_PERF") == "1":
        engine = load.get_engine()

    started = time.perf_counter()
    try:
        counts = load.load_all(podcasts, episodes, stats, engine=engine, mode="full")
        t_load = time.perf_counter() - started
    finally:
        if os.getenv("RUN_PG_PERF") == "1":      # не оставляем тестовые данные в DWH
            from sqlalchemy import text

            with engine.begin() as conn:
                for table in ("podcast_stats", "episodes", "podcasts"):
                    conn.execute(text(f"DELETE FROM {table} WHERE podcast_id >= {BASE_ID} AND podcast_id < {BASE_ID + N_PODCASTS}"))

    total = t_transform + t_load
    print(f"\n[perf] records={len(episodes)} transform={t_transform:.1f}s load={t_load:.1f}s total={total:.1f}s "
          f"throughput={len(episodes) / total:.0f} rec/s")
    assert counts["episodes"] == N_RECORDS
    assert total < LIMIT_SECONDS


def test_scalability_2x_load_scales_roughly_linearly():
    """NFR-2: удвоение объёма не приводит к сверхлинейному росту времени Transform."""
    def measure(per_podcast):
        raw = build_raw(per_podcast)
        start = time.perf_counter()
        for i in range(10):
            transform_episodes(raw, i + 1)
        return time.perf_counter() - start

    small, large = measure(1_000), measure(2_000)
    assert large < small * 4        # 2x данных -> заведомо меньше 4x времени
