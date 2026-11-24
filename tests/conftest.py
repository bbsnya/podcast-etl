import pytest

from tests.helpers import FakeStorage

SQLITE_SCHEMA = """
CREATE TABLE podcasts (
    podcast_id BIGINT PRIMARY KEY, title TEXT NOT NULL, description TEXT, rss_url TEXT NOT NULL,
    episode_count INT, artist_name TEXT, genre TEXT, country TEXT, language TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE episodes (
    episode_key TEXT PRIMARY KEY, podcast_id BIGINT NOT NULL REFERENCES podcasts(podcast_id),
    guid TEXT, title TEXT NOT NULL, pub_date TIMESTAMP, description TEXT, duration_seconds INT,
    audio_url TEXT, duration_bucket TEXT, pub_month TEXT);
CREATE TABLE podcast_stats (
    podcast_id BIGINT PRIMARY KEY REFERENCES podcasts(podcast_id), episodes_loaded INT,
    avg_duration_seconds NUMERIC, total_duration_seconds BIGINT, first_pub_date TIMESTAMP,
    last_pub_date TIMESTAMP, episodes_per_month NUMERIC, activity_segment TEXT)
"""


@pytest.fixture
def fake_storage():
    return FakeStorage()


@pytest.fixture
def sqlite_engine():
    """In-memory SQLite: синтаксис ON CONFLICT совместим с PostgreSQL, схема упрощена."""
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        for statement in SQLITE_SCHEMA.split(";"):
            if statement.strip():
                conn.exec_driver_sql(statement)
    return engine


def count_rows(engine, table: str) -> int:
    import sqlalchemy as sa

    with engine.connect() as conn:
        return conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
