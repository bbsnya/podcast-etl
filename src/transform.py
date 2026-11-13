import logging
import pandas as pd
from dateutil import parser
from typing import List, Dict

logger = logging.getLogger(__name__)

def transform_podcasts(raw_podcasts: List[Dict]) -> pd.DataFrame:
    records = []
    for p in raw_podcasts:
        records.append({
            "podcast_id": p.get("collectionId"),
            "title": p.get("collectionName"),
            "description": p.get("description"),
            "rss_url": p.get("feedUrl"),
            "episode_count": p.get("trackCount"),
        })
    df = pd.DataFrame(records)
    if df.empty:
        logger.info("Нет данных о подкастах после трансформации.")
        return df
    df = df.dropna(subset=["podcast_id", "title", "rss_url"])
    df = df.drop_duplicates(subset=["podcast_id"])
    logger.info(f"После трансформации подкастов: {len(df)}")
    return df

def transform_episodes(raw_episodes: List[Dict], podcast_id: int) -> pd.DataFrame:
    records = []
    for ep in raw_episodes:
        pub_date = None
        if ep.get("pub_date"):
            try:
                pub_date = parser.parse(ep["pub_date"])
            except Exception:
                pub_date = None
        
        duration_sec = None
        if ep.get("duration"):
            try:
                parts = str(ep["duration"]).split(":")
                if len(parts) == 3:
                    duration_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif len(parts) == 2:
                    duration_sec = int(parts[0]) * 60 + int(parts[1])
                else:
                    duration_sec = int(float(ep["duration"]))
            except Exception:
                duration_sec = None
        
        records.append({
            "podcast_id": podcast_id,
            "title": ep.get("title"),
            "pub_date": pub_date,
            "description": ep.get("description"),
            "duration_seconds": duration_sec,
            "audio_url": ep.get("audio_url"),
        })
    
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.dropna(subset=["title"])
        df = df.drop_duplicates(subset=["podcast_id", "title", "pub_date"])
    logger.info(f"После трансформации выпусков для подкаста {podcast_id}: {len(df)}")
    return df
