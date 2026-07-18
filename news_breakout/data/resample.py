from __future__ import annotations

import pandas as pd

_AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample a chronological OHLCV frame to a coarser bar `rule` (e.g. '4h')."""
    out = df.resample(rule).agg(_AGG)
    # Empty buckets: Volume sums to 0 (not NaN) while OHLC ("first"/"last") stay NaN,
    # so dropna(how="all") wouldn't catch them. Close is NaN only for empty buckets.
    out = out.dropna(subset=["Close"])
    return out[["Open", "High", "Low", "Close", "Volume"]]
