import logging
import pandas as pd
from sqlalchemy import create_engine, text
from src.config import DB_CONFIG

logger = logging.getLogger(__name__)

def get_engine():
    url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    return create_engine(url)

def load_podcasts(df: pd.DataFrame):
    if df.empty:
        logger.warning("Нет данных о подкастах для загрузки.")
        return
    engine = get_engine()
    with engine.begin() as conn:
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            for key, val in row_dict.items():
                if isinstance(val, float) and pd.isna(val):
                    row_dict[key] = None
            conn.execute(
                text("""
                    INSERT INTO podcasts (podcast_id, title, description, rss_url, episode_count)
                    VALUES (:podcast_id, :title, :description, :rss_url, :episode_count)
                    ON CONFLICT (podcast_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        rss_url = EXCLUDED.rss_url,
                        episode_count = EXCLUDED.episode_count
                """),
                row_dict
            )
    logger.info(f"Загружено подкастов: {len(df)}")

def load_episodes(df: pd.DataFrame):
    if df.empty:
        logger.warning("Нет данных о выпусках для загрузки.")
        return
    engine = get_engine()
    with engine.begin() as conn:
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            for key, val in row_dict.items():
                if isinstance(val, float) and pd.isna(val):
                    row_dict[key] = None
            conn.execute(
                text("""
                    INSERT INTO episodes (podcast_id, title, pub_date, description, duration_seconds, audio_url)
                    VALUES (:podcast_id, :title, :pub_date, :description, :duration_seconds, :audio_url)
                    ON CONFLICT (podcast_id, title, pub_date) DO NOTHING
                """),
                row_dict
            )
    logger.info(f"Загружено выпусков: {len(df)}")
