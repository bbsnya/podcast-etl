"""Пакетная загрузка данных в PostgreSQL с обновлением существующих записей."""
import logging
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine

from src import config
from src.frames import df_to_records

logger = logging.getLogger(__name__)

PODCAST_DB_COLUMNS = [
    "podcast_id", "title", "description", "rss_url", "episode_count",
    "artist_name", "genre", "country", "language",
]
EPISODE_DB_COLUMNS = [
    "episode_key", "podcast_id", "guid", "title", "pub_date", "description",
    "duration_seconds", "audio_url", "duration_bucket", "pub_month",
]
STATS_DB_COLUMNS = [
    "podcast_id", "episodes_loaded", "avg_duration_seconds", "total_duration_seconds",
    "first_pub_date", "last_pub_date", "episodes_per_month", "activity_segment",
]

UPSERT_PODCASTS = text("""
    INSERT INTO podcasts (podcast_id, title, description, rss_url, episode_count,
                          artist_name, genre, country, language)
    VALUES (:podcast_id, :title, :description, :rss_url, :episode_count,
            :artist_name, :genre, :country, :language)
    ON CONFLICT (podcast_id) DO UPDATE SET
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        rss_url = EXCLUDED.rss_url,
        episode_count = EXCLUDED.episode_count,
        artist_name = EXCLUDED.artist_name,
        genre = EXCLUDED.genre,
        country = EXCLUDED.country,
        language = EXCLUDED.language
""")

UPSERT_EPISODES = text("""
    INSERT INTO episodes (episode_key, podcast_id, guid, title, pub_date, description,
                          duration_seconds, audio_url, duration_bucket, pub_month)
    VALUES (:episode_key, :podcast_id, :guid, :title, :pub_date, :description,
            :duration_seconds, :audio_url, :duration_bucket, :pub_month)
    ON CONFLICT (episode_key) DO UPDATE SET
        guid = EXCLUDED.guid,
        title = EXCLUDED.title,
        pub_date = EXCLUDED.pub_date,
        description = EXCLUDED.description,
        duration_seconds = EXCLUDED.duration_seconds,
        audio_url = EXCLUDED.audio_url,
        duration_bucket = EXCLUDED.duration_bucket,
        pub_month = EXCLUDED.pub_month
""")

UPSERT_STATS = text("""
    INSERT INTO podcast_stats (podcast_id, episodes_loaded, avg_duration_seconds, total_duration_seconds,
                               first_pub_date, last_pub_date, episodes_per_month, activity_segment)
    VALUES (:podcast_id, :episodes_loaded, :avg_duration_seconds, :total_duration_seconds,
            :first_pub_date, :last_pub_date, :episodes_per_month, :activity_segment)
    ON CONFLICT (podcast_id) DO UPDATE SET
        episodes_loaded = EXCLUDED.episodes_loaded,
        avg_duration_seconds = EXCLUDED.avg_duration_seconds,
        total_duration_seconds = EXCLUDED.total_duration_seconds,
        first_pub_date = EXCLUDED.first_pub_date,
        last_pub_date = EXCLUDED.last_pub_date,
        episodes_per_month = EXCLUDED.episodes_per_month,
        activity_segment = EXCLUDED.activity_segment
""")


def get_engine(db_config: Optional[Dict[str, str]] = None) -> Engine:
    cfg = db_config or config.DB_CONFIG

    url = URL.create(
        "postgresql+psycopg2",
        username=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=int(cfg["port"]),
        database=cfg["dbname"],
    )

    connect_args = {
        "sslmode": cfg.get("sslmode", "prefer")
    }

    if cfg.get("sslrootcert"):
        connect_args["sslrootcert"] = cfg["sslrootcert"]

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def _rows(df: pd.DataFrame, columns: List[str]) -> List[Dict]:
    return [{c: rec.get(c) for c in columns} for rec in df_to_records(df)]


def _execute_chunked(conn: Connection, statement, rows: List[Dict], chunk_size: int) -> int:
    for start in range(0, len(rows), chunk_size):
        conn.execute(statement, rows[start:start + chunk_size])
    return len(rows)


def _upsert_podcasts(conn: Connection, df: pd.DataFrame, chunk_size: int) -> int:
    if df.empty:
        logger.warning("Нет данных о подкастах для загрузки.")
        return 0
    return _execute_chunked(conn, UPSERT_PODCASTS, _rows(df, PODCAST_DB_COLUMNS), chunk_size)


def _upsert_episodes(conn: Connection, df: pd.DataFrame, chunk_size: int) -> int:
    if df.empty:
        logger.warning("Нет данных о выпусках для загрузки.")
        return 0
    return _execute_chunked(conn, UPSERT_EPISODES, _rows(df, EPISODE_DB_COLUMNS), chunk_size)



def _refresh_stats(conn: Connection) -> int:
    if conn.dialect.name == "sqlite":
        stats_sql = """
            INSERT INTO podcast_stats (
                podcast_id, episodes_loaded, avg_duration_seconds,
                total_duration_seconds, first_pub_date, last_pub_date,
                episodes_per_month, activity_segment
            )
            SELECT
                podcast_id,
                COUNT(*),
                ROUND(AVG(duration_seconds), 1),
                COALESCE(SUM(duration_seconds), 0),
                MIN(pub_date),
                MAX(pub_date),
                ROUND(
                    COUNT(*) / MAX(
                        1.0,
                        (julianday(MAX(pub_date)) -
                         julianday(MIN(pub_date))) / 30.44
                    ),
                    2
                ),
                CASE
                    WHEN COUNT(*) / MAX(
                        1.0,
                        (julianday(MAX(pub_date)) -
                         julianday(MIN(pub_date))) / 30.44
                    ) >= 4 THEN 'high'
                    WHEN COUNT(*) / MAX(
                        1.0,
                        (julianday(MAX(pub_date)) -
                         julianday(MIN(pub_date))) / 30.44
                    ) >= 1 THEN 'medium'
                    ELSE 'low'
                END
            FROM episodes
            GROUP BY podcast_id
            ON CONFLICT (podcast_id) DO UPDATE SET
                episodes_loaded = excluded.episodes_loaded,
                avg_duration_seconds = excluded.avg_duration_seconds,
                total_duration_seconds = excluded.total_duration_seconds,
                first_pub_date = excluded.first_pub_date,
                last_pub_date = excluded.last_pub_date,
                episodes_per_month = excluded.episodes_per_month,
                activity_segment = excluded.activity_segment
        """
    else:
        stats_sql = """
            INSERT INTO podcast_stats (
                podcast_id, episodes_loaded, avg_duration_seconds,
                total_duration_seconds, first_pub_date, last_pub_date,
                episodes_per_month, activity_segment
            )
            SELECT
                podcast_id,
                COUNT(*),
                ROUND(AVG(duration_seconds), 1),
                COALESCE(SUM(duration_seconds), 0),
                MIN(pub_date),
                MAX(pub_date),
                ROUND(
                    COUNT(*)::NUMERIC /
                    GREATEST(
                        EXTRACT(EPOCH FROM (MAX(pub_date) - MIN(pub_date)))
                        / 86400 / 30.44,
                        1
                    ),
                    2
                ),
                CASE
                    WHEN COUNT(*)::NUMERIC /
                        GREATEST(
                            EXTRACT(EPOCH FROM (MAX(pub_date) - MIN(pub_date)))
                            / 86400 / 30.44,
                            1
                        ) >= 4 THEN 'high'
                    WHEN COUNT(*)::NUMERIC /
                        GREATEST(
                            EXTRACT(EPOCH FROM (MAX(pub_date) - MIN(pub_date)))
                            / 86400 / 30.44,
                            1
                        ) >= 1 THEN 'medium'
                    ELSE 'low'
                END
            FROM episodes
            GROUP BY podcast_id
            ON CONFLICT (podcast_id) DO UPDATE SET
                episodes_loaded = EXCLUDED.episodes_loaded,
                avg_duration_seconds = EXCLUDED.avg_duration_seconds,
                total_duration_seconds = EXCLUDED.total_duration_seconds,
                first_pub_date = EXCLUDED.first_pub_date,
                last_pub_date = EXCLUDED.last_pub_date,
                episodes_per_month = EXCLUDED.episodes_per_month,
                activity_segment = EXCLUDED.activity_segment
        """

    conn.execute(text(stats_sql))

    return conn.execute(
        text("SELECT COUNT(*) FROM podcast_stats")
    ).scalar_one()

def _read_watermarks(conn: Connection) -> Dict[int, pd.Timestamp]:
    rows = conn.execute(text("SELECT podcast_id, MAX(pub_date) FROM episodes GROUP BY podcast_id")).fetchall()
    result = {}
    for pid, last in rows:
        if last is not None:
            result[int(pid)] = pd.to_datetime(last, utc=True)
    return result


def get_watermarks(engine: Optional[Engine] = None) -> Dict[int, pd.Timestamp]:
    """Возвращает дату последнего выпуска для каждого подкаста."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        return _read_watermarks(conn)


def filter_new_episodes(df: pd.DataFrame, watermarks: Dict[int, pd.Timestamp]) -> pd.DataFrame:
    """Отбирает выпуски с учётом даты последней загрузки."""
    if df.empty or not watermarks:
        return df
    pub = pd.to_datetime(df["pub_date"], utc=True)
    wm = pd.to_datetime(df["podcast_id"].map(watermarks), utc=True)
    keep = wm.isna() | pub.isna() | (pub >= wm)
    return df[keep].reset_index(drop=True)


def load_podcasts(df: pd.DataFrame, engine: Optional[Engine] = None) -> int:
    engine = engine or get_engine()
    with engine.begin() as conn:
        return _upsert_podcasts(conn, df, config.LOAD_CHUNK_SIZE)


def load_episodes(df: pd.DataFrame, engine: Optional[Engine] = None, mode: str = "full") -> int:
    engine = engine or get_engine()
    with engine.begin() as conn:
        if mode == "incremental":
            df = filter_new_episodes(df, _read_watermarks(conn))
        return _upsert_episodes(conn, df, config.LOAD_CHUNK_SIZE)


def load_all(
    podcasts: pd.DataFrame,
    episodes: pd.DataFrame,
    stats: pd.DataFrame,
    engine: Optional[Engine] = None,
    mode: Optional[str] = None,
    chunk_size: Optional[int] = None,
) -> Dict[str, int]:
    """Загружает данные в DWH одной транзакцией."""
    mode = mode or config.LOAD_MODE
    if mode not in {"full", "incremental"}:
        raise ValueError(f"Неизвестный режим загрузки: {mode}")
    chunk_size = chunk_size or config.LOAD_CHUNK_SIZE
    engine = engine or get_engine()

    with engine.begin() as conn:
        n_podcasts = _upsert_podcasts(conn, podcasts, chunk_size)
        to_load = filter_new_episodes(episodes, _read_watermarks(conn)) if mode == "incremental" else episodes
        n_episodes = _upsert_episodes(conn, to_load, chunk_size)
        n_stats = _refresh_stats(conn)

    skipped = len(episodes) - len(to_load)
    logger.info("Загружено: подкастов=%d, выпусков=%d (пропущено как неновые: %d), статистик=%d",
                n_podcasts, n_episodes, skipped, n_stats)
    return {"podcasts": n_podcasts, "episodes": n_episodes, "episodes_skipped": skipped, "stats": n_stats}
