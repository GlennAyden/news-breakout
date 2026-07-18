from __future__ import annotations

import pandas as pd


def make_ohlcv(highs, lows, closes, volumes, opens=None):
    """Build a chronological OHLCV DataFrame (oldest row first)."""
    n = len(closes)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": opens if opens is not None else closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        },
        index=idx,
    )
