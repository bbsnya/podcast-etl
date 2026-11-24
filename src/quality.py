"""Проверки полноты, уникальности и корректности данных.

Критические ошибки останавливают конвейер, предупреждения записываются в отчёт.
"""
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, NamedTuple

import pandas as pd

from src.transform import DURATION_BUCKETS

logger = logging.getLogger(__name__)

CRITICAL = "critical"
WARNING = "warning"


class Check(NamedTuple):
    method: str
    kwargs: Dict[str, Any]
    severity: str
    description: str


@dataclass
class QualityReport:
    dataset: str
    rows: int = 0
    checked: int = 0
    critical_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.critical_failures

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["passed"] = self.passed
        return data


def podcast_checks() -> List[Check]:
    return [
        # Проверка обязательных полей.
        Check("expect_column_values_to_not_be_null", {"column": "podcast_id"}, CRITICAL, "FR-5.1: podcast_id заполнен"),
        Check("expect_column_values_to_not_be_null", {"column": "title"}, CRITICAL, "FR-5.1: title заполнен"),
        Check("expect_column_values_to_not_be_null", {"column": "rss_url"}, CRITICAL, "FR-5.1: rss_url заполнен"),
        # Проверка уникальности записей.
        Check("expect_column_values_to_be_unique", {"column": "podcast_id"}, CRITICAL, "FR-5.2: podcast_id уникален"),
        # Проверка допустимых значений.
        Check("expect_column_values_to_match_regex", {"column": "rss_url", "regex": r"^https?://\S+$"},
              CRITICAL, "FR-5.3: rss_url — корректный URL"),
        Check("expect_column_value_lengths_to_be_between", {"column": "title", "min_value": 1, "max_value": 500},
              CRITICAL, "FR-5.3: длина title 1..500"),
        Check("expect_column_values_to_be_between", {"column": "episode_count", "min_value": 0, "max_value": 1_000_000},
              WARNING, "FR-5.3: episode_count в диапазоне 0..1 000 000"),
    ]


def episode_checks() -> List[Check]:
    current_year = datetime.now(timezone.utc).year
    return [
        Check("expect_column_values_to_not_be_null", {"column": "episode_key"}, CRITICAL, "FR-5.1: episode_key заполнен"),
        Check("expect_column_values_to_not_be_null", {"column": "podcast_id"}, CRITICAL, "FR-5.1: podcast_id заполнен"),
        Check("expect_column_values_to_not_be_null", {"column": "title"}, CRITICAL, "FR-5.1: title заполнен"),
        Check("expect_column_values_to_not_be_null", {"column": "pub_date", "mostly": 0.9},
              WARNING, "FR-5.1: pub_date заполнен у ≥ 90% выпусков"),
        Check("expect_column_values_to_not_be_null", {"column": "audio_url", "mostly": 0.8},
              WARNING, "FR-5.1: audio_url заполнен у ≥ 80% выпусков"),
        Check("expect_column_values_to_be_unique", {"column": "episode_key"}, CRITICAL, "FR-5.2: episode_key уникален"),
        Check("expect_column_values_to_be_between",
              {"column": "duration_seconds", "min_value": 0, "max_value": 172_800},
              CRITICAL, "FR-5.3: длительность 0..48 ч"),
        Check("expect_column_values_to_be_between",
              {"column": "pub_year", "min_value": 1990, "max_value": current_year, "mostly": 0.99},
              WARNING, "FR-5.3: год публикации 1990..текущий (нет дат из будущего)"),
        Check("expect_column_values_to_be_in_set",
              {"column": "duration_bucket", "value_set": DURATION_BUCKETS},
              CRITICAL, "FR-5.3: duration_bucket — допустимое значение"),
    ]


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Преобразует типы pandas перед проверками качества."""
    out = df.copy()
    for col in out.columns:
        dtype = out[col].dtype
        if str(dtype) in {"Int64", "Int32", "Float64"}:
            out[col] = out[col].astype("float64")
        elif isinstance(dtype, pd.StringDtype) or str(dtype) == "str":
            out[col] = out[col].astype(object)
    return out


def run_checks(df: pd.DataFrame, checks: List[Check], dataset: str) -> QualityReport:
    report = QualityReport(dataset=dataset, rows=len(df))
    if df.empty:
        report.critical_failures.append(f"{dataset}: набор данных пуст")
        return report

    import great_expectations as ge  # отложенный импорт: тяжёлая зависимость

    gdf = ge.from_pandas(_prepare(df))
    for check in checks:
        column = check.kwargs.get("column")
        if column not in df.columns:
            report.critical_failures.append(f"{check.description}: колонка {column} отсутствует")
            continue
        try:
            result = getattr(gdf, check.method)(**check.kwargs)
        except Exception as exc:  # noqa: BLE001
            report.critical_failures.append(f"{check.description}: ошибка выполнения проверки ({type(exc).__name__})")
            continue
        report.checked += 1
        if result.success:
            continue
        unexpected = (result.result or {}).get("unexpected_count")
        message = check.description + (f" (нарушений: {unexpected})" if unexpected is not None else "")
        (report.critical_failures if check.severity == CRITICAL else report.warnings).append(message)

    level = logging.INFO if report.passed else logging.ERROR
    logger.log(level, "Качество %s: проверок=%d, критических=%d, предупреждений=%d",
               dataset, report.checked, len(report.critical_failures), len(report.warnings))
    return report


def validate_podcasts(df: pd.DataFrame) -> QualityReport:
    return run_checks(df, podcast_checks(), "podcasts")


def validate_episodes(df: pd.DataFrame) -> QualityReport:
    return run_checks(df, episode_checks(), "episodes")
