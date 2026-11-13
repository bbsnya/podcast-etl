import logging
import pandas as pd

logger = logging.getLogger(__name__)

def validate_podcasts(df: pd.DataFrame) -> bool:
    if df.empty:
        logger.warning("Пустой DataFrame для валидации подкастов.")
        return False
    
    errors = []
    if df["podcast_id"].isnull().any():
        errors.append("Есть пропущенные podcast_id")
    if df["title"].isnull().any():
        errors.append("Есть пропущенные title")
    if df["rss_url"].isnull().any():
        errors.append("Есть пропущенные rss_url")
    if df.duplicated(subset=["podcast_id"]).any():
        errors.append("Есть дубликаты podcast_id")
    
    if errors:
        logger.error(f"Ошибки валидации подкастов: {errors}")
        return False
    
    logger.info("Валидация подкастов пройдена.")
    return True

def validate_episodes(df: pd.DataFrame) -> bool:
    if df.empty:
        logger.warning("Пустой DataFrame для валидации выпусков.")
        return True
    
    errors = []
    if df["title"].isnull().any():
        errors.append("Есть пропущенные title")
    if df["podcast_id"].isnull().any():
        errors.append("Есть пропущенные podcast_id")
    if df.duplicated(subset=["podcast_id", "title", "pub_date"]).any():
        errors.append("Есть дубликаты выпусков")
    
    if errors:
        logger.error(f"Ошибки валидации выпусков: {errors}")
        return False
    
    logger.info("Валидация выпусков пройдена.")
    return True
