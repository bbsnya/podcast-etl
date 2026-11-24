"""Преобразование DataFrame <-> JSON-совместимые записи (для обмена через MinIO)."""
import math
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np
import pandas as pd


def _py(value: Any) -> Any:
    """Приводит значение pandas/numpy к типу, пригодному для JSON и SQL-драйвера."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        v = float(value)
        return None if math.isnan(v) else v
    return value


def df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """NaN/NaT/pd.NA -> None, Timestamp -> ISO-строка, numpy -> python."""
    if df is None or df.empty:
        return []
    return [{k: _py(v) for k, v in rec.items()} for rec in df.to_dict("records")]


def records_to_df(
    records: Iterable[Dict[str, Any]],
    columns: Sequence[str],
    datetime_cols: Sequence[str] = (),
    int_cols: Sequence[str] = (),
) -> pd.DataFrame:
    """Восстанавливает типизированный DataFrame из записей."""
    df = pd.DataFrame(list(records), columns=list(columns))
    for col in datetime_cols:
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df
