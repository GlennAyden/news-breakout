from __future__ import annotations

import pandas as pd


def detect_donchian_breakout(df: pd.DataFrame, lookback: int) -> tuple[bool, float]:
    """Detect a new-high breakout: last Close above the max High of the prior `lookback` bars."""
    if len(df) < lookback + 1:
        return (False, 0.0)
    prior_high = float(df["High"].iloc[-(lookback + 1):-1].max())
    last_close = float(df["Close"].iloc[-1])
    return (last_close > prior_high, prior_high)
