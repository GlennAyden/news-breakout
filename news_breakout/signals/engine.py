from __future__ import annotations

from datetime import datetime

import pandas as pd

from news_breakout.models import BreakoutSignal
from news_breakout.signals.breakout import detect_donchian_breakout
from news_breakout.signals.volume import compute_rvol


def evaluate_daily(
    ticker: str,
    df: pd.DataFrame,
    *,
    lookback: int,
    rvol_window: int,
    rvol_threshold: float,
    now: datetime,
) -> BreakoutSignal | None:
    if len(df) < 2:
        return None
    is_bo, level = detect_donchian_breakout(df, lookback)
    if not is_bo:
        return None
    rvol = compute_rvol(df, rvol_window)
    if rvol < rvol_threshold:
        return None

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    pct_change = ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0

    return BreakoutSignal(
        ticker=ticker,
        timeframe="1D",
        signal_type="resistance_breakout",
        price=last_close,
        pct_change=pct_change,
        level=level,
        rvol=rvol,
        timestamp=now,
    )
