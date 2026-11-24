"""Функции отдельных этапов ETL-конвейера.

Логика этапов отделена от DAG, чтобы её можно было тестировать независимо от Airflow.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from src import config
from src.exceptions import DataQualityError, ExtractionError, InsecureFeedError
from src.extract import build_session, fetch_podcasts_from_itunes, fetch_rss_feed, parse_rss_content
from src.frames import df_to_records, records_to_df
from src.load import load_all
from src.metrics import task_metrics
from src.quality import validate_episodes, validate_podcasts
from src.storage import Storage
from src.transform import (
    EPISODE_COLUMNS,
    SCHEMA,
    aggregate_podcast_stats,
    transform_episodes,
    transform_podcasts,
)

logger = logging.getLogger(__name__)


def _keys(ds: str) -> Dict[str, str]:
    return {
        "itunes": f"raw/itunes/{ds}/search.json",
        "podcasts": f"processed/{ds}/podcasts.json",
        "episodes": f"processed/{ds}/episodes.json",
        "stats": f"processed/{ds}/podcast_stats.json",
        "quality": f"quality/{ds}/report.json",
    }


def _read_frame(storage: Storage, key: str, name: str) -> pd.DataFrame:
    return records_to_df(storage.get_json(key), **SCHEMA[name])


def _write_frame(storage: Storage, key: str, df: pd.DataFrame) -> None:
    storage.put_json(key, df_to_records(df))



def stage_extract(ds: str, search_term: str, limit: int, storage: Optional[Storage] = None, session: Any = None) -> Dict:
    """Получает данные из iTunes и RSS и сохраняет исходные файлы в MinIO."""
    storage = storage or Storage()
    session = session or build_session()
    keys = _keys(ds)

    with task_metrics("extract") as m:
        storage.ensure_bucket()
        raw = fetch_podcasts_from_itunes(search_term, limit, session)
        if not raw:
            raise ExtractionError("iTunes вернул пустой результат")
        storage.put_json(keys["itunes"], raw)

        targets = [(p["collectionId"], p["feedUrl"]) for p in raw if p.get("collectionId") and p.get("feedUrl")]

        def _fetch(target: Tuple[int, str]) -> Tuple[int, Optional[str], str]:
            pid, url = target
            try:
                content = fetch_rss_feed(url, session)
                key = f"raw/rss/{ds}/{pid}.xml"
                storage.put_bytes(key, content, "application/xml")
                return pid, key, "ok"
            except InsecureFeedError:
                logger.warning("Пропущена небезопасная лента (HTTP): подкаст %s", pid)
                return pid, None, "insecure"
            except ExtractionError as exc:
                logger.warning("Лента подкаста %s недоступна: %s", pid, exc)
                return pid, None, "failed"

        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
            results = list(pool.map(_fetch, targets))

        rss_keys = {str(pid): key for pid, key, status in results if status == "ok"}
        failed = [pid for pid, _, status in results if status == "failed"]
        insecure = [pid for pid, _, status in results if status == "insecure"]

        m.set("podcasts_extracted", len(raw))
        m.set("feeds_ok", len(rss_keys))
        m.set("feeds_failed", len(failed))
        m.set("feeds_skipped_insecure", len(insecure))

        if not rss_keys:
            raise ExtractionError("Не удалось загрузить ни одной RSS-ленты")
        logger.info("Extract: подкастов=%d, лент загружено=%d, сбоев=%d, пропущено HTTP=%d",
                    len(raw), len(rss_keys), len(failed), len(insecure))

    return {"ds": ds, "itunes_key": keys["itunes"], "rss_keys": rss_keys,
            "failed_feeds": failed, "skipped_insecure": insecure}



def stage_transform(ds: str, manifest: Dict, storage: Optional[Storage] = None) -> Dict:
    """Обрабатывает исходные данные и сохраняет результаты в MinIO."""
    storage = storage or Storage()
    keys = _keys(ds)

    with task_metrics("transform") as m:
        raw = storage.get_json(manifest["itunes_key"])

        rss_meta: Dict[int, Dict] = {}
        raw_episodes: Dict[int, list] = {}
        parse_failed = 0
        for pid_str, key in manifest["rss_keys"].items():
            pid = int(pid_str)
            try:
                parsed = parse_rss_content(storage.get_bytes(key), config.MAX_EPISODES_PER_FEED)
            except ExtractionError as exc:
                parse_failed += 1
                logger.warning("Лента подкаста %s не разобрана: %s", pid, exc)
                continue
            rss_meta[pid] = parsed["channel"]
            raw_episodes[pid] = parsed["episodes"]

        df_podcasts = transform_podcasts(raw, rss_meta)
        valid_ids = set(df_podcasts["podcast_id"].tolist()) if not df_podcasts.empty else set()

        frames = [transform_episodes(eps, pid) for pid, eps in raw_episodes.items() if pid in valid_ids]
        frames = [f for f in frames if not f.empty]
        df_episodes = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=EPISODE_COLUMNS)
        df_stats = aggregate_podcast_stats(df_episodes)

        _write_frame(storage, keys["podcasts"], df_podcasts)
        _write_frame(storage, keys["episodes"], df_episodes)
        _write_frame(storage, keys["stats"], df_stats)

        m.set("podcasts_transformed", len(df_podcasts))
        m.set("episodes_transformed", len(df_episodes))
        m.set("feeds_parse_failed", parse_failed)

    return {"ds": ds, "podcasts_key": keys["podcasts"], "episodes_key": keys["episodes"], "stats_key": keys["stats"],
            "podcasts": len(df_podcasts), "episodes": len(df_episodes)}



def stage_quality(ds: str, transformed: Dict, storage: Optional[Storage] = None) -> Dict:
    """Проверяет качество данных перед загрузкой в хранилище."""
    storage = storage or Storage()
    keys = _keys(ds)

    with task_metrics("quality") as m:
        df_podcasts = _read_frame(storage, transformed["podcasts_key"], "podcasts")
        df_episodes = _read_frame(storage, transformed["episodes_key"], "episodes")
        reports = [validate_podcasts(df_podcasts), validate_episodes(df_episodes)]

        critical = sum(len(r.critical_failures) for r in reports)
        warnings = sum(len(r.warnings) for r in reports)
        storage.put_json(keys["quality"], [r.to_dict() for r in reports])

        m.set("dq_checks_failed", critical)
        m.set("dq_warnings", warnings)

        if critical:
            details = "; ".join(f for r in reports for f in r.critical_failures)
            raise DataQualityError(f"Критические нарушения качества данных: {details}")

    return {"ds": ds, "report_key": keys["quality"], "warnings": warnings}



def stage_load(
    ds: str,
    transformed: Dict,
    storage: Optional[Storage] = None,
    engine: Any = None,
    mode: Optional[str] = None,
) -> Dict:
    """Загружает данные в PostgreSQL в рамках одной транзакции."""
    storage = storage or Storage()

    with task_metrics("load") as m:
        df_podcasts = _read_frame(storage, transformed["podcasts_key"], "podcasts")
        df_episodes = _read_frame(storage, transformed["episodes_key"], "episodes")
        df_stats = _read_frame(storage, transformed["stats_key"], "stats")

        counts = load_all(df_podcasts, df_episodes, df_stats, engine=engine, mode=mode)

        m.set("podcasts_loaded", counts["podcasts"])
        m.set("episodes_loaded", counts["episodes"])
        m.set("episodes_skipped_incremental", counts["episodes_skipped"])

    logger.info("Load завершён: %s", json.dumps(counts))
    return counts
