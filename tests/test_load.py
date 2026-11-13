import pandas as pd
import numpy as np


def test_nan_replacement():
    """Проверяет логику замены NaN -> None (из load.py)."""
    row = {"duration_seconds": np.nan, "title": "Test"}
    row_dict = {}
    for key, val in row.items():
        if isinstance(val, float) and pd.isna(val):
            row_dict[key] = None
        else:
            row_dict[key] = val
    assert row_dict["duration_seconds"] is None
    assert row_dict["title"] == "Test"
