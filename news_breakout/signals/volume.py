from __future__ import annotations

import pandas as pd


def compute_rvol(df: pd.DataFrame, window: int) -> float:
    """Relative volume: last bar's volume / mean of the previous `window` bars."""
    if len(df) < window + 1:
        return 0.0
    prev = df["Volume"].iloc[-(window + 1):-1]
    avg = float(prev.mean())
    if avg <= 0:
        return 0.0
    return float(df["Volume"].iloc[-1]) / avg
