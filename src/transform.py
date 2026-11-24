"""Transform: очистка, нормализация, дедупликация, обогащение и агрегация."""
import hashlib
import html
import logging
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)

PODCAST_COLUMNS = [
    "podcast_id", "title", "description", "rss_url", "episode_count",
    "artist_name", "genre", "country", "language",
]
EPISODE_COLUMNS = [
    "episode_key", "podcast_id", "guid", "title", "pub_date", "description",
    "duration_seconds", "audio_url", "duration_bucket", "pub_month", "pub_year",
]
STATS_COLUMNS = [
    "podcast_id", "episodes_loaded", "avg_duration_seconds", "total_duration_seconds",
    "first_pub_date", "last_pub_date", "episodes_per_month", "activity_segment",
]

# Типы данных, используемые при чтении промежуточных файлов.
SCHEMA = {
    "podcasts": {"columns": PODCAST_COLUMNS, "datetime_cols": [], "int_cols": ["podcast_id", "episode_count"]},
    "episodes": {
        "columns": EPISODE_COLUMNS,
        "datetime_cols": ["pub_date"],
        "int_cols": ["podcast_id", "duration_seconds", "pub_year"],
    },
    "stats": {
        "columns": STATS_COLUMNS,
        "datetime_cols": ["first_pub_date", "last_pub_date"],
        "int_cols": ["podcast_id", "episodes_loaded", "total_duration_seconds"],
    },
}

BUCKET_UNKNOWN = "нет данных"
DURATION_BUCKETS = ["< 10 мин", "10-30 мин", "30-60 мин", "60-120 мин", "> 2 ч", BUCKET_UNKNOWN]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(value: Any, max_len: int = 5000) -> Optional[str]:
    """Удаляет HTML-теги, декодирует сущности, схлопывает пробелы; пустое - None."""
    if value is None:
        return None
    text = html.unescape(_TAG_RE.sub(" ", str(value)))
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_len] if text else None


def parse_duration(value: Any) -> Optional[int]:
    """'HH:MM:SS', 'MM:SS' или секунды - int секунд; некорректное - None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parts = [float(p) for p in text.split(":")]
    except ValueError:
        return None
    if len(parts) > 3 or any((not math.isfinite(p)) or p < 0 for p in parts):
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return int(seconds)


def parse_pub_date(value: Any) -> Optional[datetime]:
    """Дата RSS (RFC 822 и др.) - tz-aware datetime в UTC; некорректное - None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            dt = dateutil_parser.parse(text)
        except (ValueError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def duration_bucket(seconds: Optional[int]) -> str:
    """Обогащение: диапазон длительности выпуска."""
    if seconds is None:
        return BUCKET_UNKNOWN
    if seconds < 600:
        return "< 10 мин"
    if seconds < 1800:
        return "10-30 мин"
    if seconds < 3600:
        return "30-60 мин"
    if seconds <= 7200:
        return "60-120 мин"
    return "> 2 ч"


def make_episode_key(podcast_id: Any, guid: Optional[str], title: Optional[str], pub_date: Optional[datetime]) -> str:
    """Формирует постоянный идентификатор выпуска."""
    ident = guid or title or ""
    stamp = pub_date.isoformat() if pub_date else ""
    return hashlib.sha1(f"{podcast_id}|{ident}|{stamp}".encode("utf-8")).hexdigest()


def transform_podcasts(raw_podcasts: List[Dict], rss_meta: Optional[Dict[int, Dict]] = None) -> pd.DataFrame:
    """Очистка метаданных подкастов; обогащение описанием и языком из RSS-канала."""
    rss_meta = rss_meta or {}
    records = []
    for p in raw_podcasts:
        pid = p.get("collectionId")
        meta = rss_meta.get(pid) or {}
        records.append(
            {
                "podcast_id": pid,
                "title": clean_text(p.get("collectionName"), 500),
                "description": clean_text(p.get("description") or meta.get("description")),
                "rss_url": (p.get("feedUrl") or "").strip() or None,
                "episode_count": p.get("trackCount"),
                "artist_name": clean_text(p.get("artistName"), 500),
                "genre": clean_text(p.get("primaryGenreName"), 200),
                "country": clean_text(p.get("country"), 10),
                "language": clean_text(meta.get("language"), 20),
            }
        )
    df = pd.DataFrame(records, columns=PODCAST_COLUMNS)
    if df.empty:
        logger.info("Нет данных о подкастах после трансформации.")
        return df

    df = df.dropna(subset=["podcast_id", "title", "rss_url"])
    df = df.drop_duplicates(subset=["podcast_id"]).reset_index(drop=True)
    df["podcast_id"] = df["podcast_id"].astype("int64")
    df["episode_count"] = pd.to_numeric(df["episode_count"], errors="coerce").astype("Int64")
    logger.info("После трансформации подкастов: %d", len(df))
    return df


def transform_episodes(raw_episodes: List[Dict], podcast_id: int) -> pd.DataFrame:
    """Очистка выпусков, нормализация дат/длительности, дедупликация, обогащение."""
    records = []
    for ep in raw_episodes:
        pub = parse_pub_date(ep.get("pub_date"))
        title = clean_text(ep.get("title"), 1000)
        guid = (ep.get("guid") or "").strip() or None
        duration = parse_duration(ep.get("duration"))
        audio = (ep.get("audio_url") or "").strip() or None
        records.append(
            {
                "episode_key": make_episode_key(podcast_id, guid, title, pub),
                "podcast_id": podcast_id,
                "guid": guid,
                "title": title,
                "pub_date": pub,
                "description": clean_text(ep.get("description")),
                "duration_seconds": duration,
                "audio_url": audio,
                "duration_bucket": duration_bucket(duration),
                "pub_month": pub.strftime("%Y-%m") if pub else None,
                "pub_year": pub.year if pub else None,
            }
        )

    df = pd.DataFrame(records, columns=EPISODE_COLUMNS)
    if not df.empty:
        df = df.dropna(subset=["title"])
        df = df.drop_duplicates(subset=["episode_key"]).reset_index(drop=True)
        df["pub_date"] = pd.to_datetime(df["pub_date"], utc=True)
        for col in ("duration_seconds", "pub_year"):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    logger.info("После трансформации выпусков для подкаста %s: %d", podcast_id, len(df))
    return df


def _activity_segment(per_month: float) -> str:
    if per_month >= 4:
        return "high"
    if per_month >= 1:
        return "medium"
    return "low"


def aggregate_podcast_stats(df_episodes: pd.DataFrame) -> pd.DataFrame:
    if df_episodes.empty:
        return pd.DataFrame(columns=STATS_COLUMNS)

    stats = (
        df_episodes.groupby("podcast_id")
        .agg(
            episodes_loaded=("episode_key", "count"),
            avg_duration_seconds=("duration_seconds", "mean"),
            total_duration_seconds=("duration_seconds", "sum"),
            first_pub_date=("pub_date", "min"),
            last_pub_date=("pub_date", "max"),
        )
        .reset_index()
    )
    span_days = (stats["last_pub_date"] - stats["first_pub_date"]).dt.total_seconds() / 86400
    months = (span_days / 30.44).fillna(1).clip(lower=1)
    stats["episodes_per_month"] = (stats["episodes_loaded"] / months).round(2)
    stats["avg_duration_seconds"] = stats["avg_duration_seconds"].astype("float64").round(1)
    stats["activity_segment"] = stats["episodes_per_month"].map(_activity_segment)
    stats["episodes_loaded"] = stats["episodes_loaded"].astype("Int64")
    stats["total_duration_seconds"] = stats["total_duration_seconds"].astype("Int64")
    return stats[STATS_COLUMNS]
