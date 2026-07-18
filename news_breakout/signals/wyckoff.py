from __future__ import annotations

import pandas as pd


def detect_range_breakout(
    df: pd.DataFrame, range_lookback: int, max_width_pct: float
) -> tuple[bool, float, float]:
    """Wyckoff-style breakout: a tight prior consolidation range, then a close above it."""
    if len(df) < range_lookback + 1:
        return (False, 0.0, 0.0)
    window = df.iloc[-(range_lookback + 1):-1]
    range_high = float(window["High"].max())
    range_low = float(window["Low"].min())
    if range_low <= 0:
        return (False, range_low, range_high)
    width = (range_high - range_low) / range_low
    is_tight = width <= max_width_pct
    breaks_out = float(df["Close"].iloc[-1]) > range_high
    return (is_tight and breaks_out, range_low, range_high)
