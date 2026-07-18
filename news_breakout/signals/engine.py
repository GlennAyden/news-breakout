from __future__ import annotations

from datetime import datetime

import pandas as pd

from news_breakout.models import BreakoutSignal
from news_breakout.signals.breakout import detect_donchian_breakout
from news_breakout.signals.volume import compute_rvol
from news_breakout.signals.wyckoff import detect_range_breakout


def _pct_change(df: pd.DataFrame) -> float:
    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    return ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0


def _resistance_signal(
    ticker: str, df: pd.DataFrame, timeframe: str, *,
    donchian_lookback: int, rvol: float, now: datetime,
) -> BreakoutSignal | None:
    is_bo, level = detect_donchian_breakout(df, donchian_lookback)
    if not is_bo:
        return None
    return BreakoutSignal(
        ticker=ticker, timeframe=timeframe, signal_type="resistance_breakout",
        price=float(df["Close"].iloc[-1]), pct_change=_pct_change(df),
        level=level, rvol=rvol, timestamp=now,
    )


def _wyckoff_signal(
    ticker: str, df: pd.DataFrame, timeframe: str, *,
    range_lookback: int, range_max_width_pct: float, rvol: float, now: datetime,
) -> BreakoutSignal | None:
    is_bo, _low, high = detect_range_breakout(df, range_lookback, range_max_width_pct)
    if not is_bo:
        return None
    return BreakoutSignal(
        ticker=ticker, timeframe=timeframe, signal_type="wyckoff_range_breakout",
        price=float(df["Close"].iloc[-1]), pct_change=_pct_change(df),
        level=high, rvol=rvol, timestamp=now,
    )


def evaluate_timeframe(
    ticker: str, df: pd.DataFrame, timeframe: str, *,
    donchian_lookback: int, rvol_window: int, rvol_threshold: float,
    range_lookback: int, range_max_width_pct: float, now: datetime,
) -> list[BreakoutSignal]:
    if len(df) < 2:
        return []
    rvol = compute_rvol(df, rvol_window)
    if rvol < rvol_threshold:
        return []
    signals: list[BreakoutSignal] = []
    res = _resistance_signal(
        ticker, df, timeframe, donchian_lookback=donchian_lookback, rvol=rvol, now=now
    )
    if res is not None:
        signals.append(res)
    wyk = _wyckoff_signal(
        ticker, df, timeframe,
        range_lookback=range_lookback, range_max_width_pct=range_max_width_pct,
        rvol=rvol, now=now,
    )
    if wyk is not None:
        signals.append(wyk)
    return signals


def evaluate_daily(
    ticker: str, df: pd.DataFrame, *,
    lookback: int, rvol_window: int, rvol_threshold: float, now: datetime,
) -> BreakoutSignal | None:
    if len(df) < 2:
        return None
    rvol = compute_rvol(df, rvol_window)
    if rvol < rvol_threshold:
        return None
    return _resistance_signal(
        ticker, df, "1D", donchian_lookback=lookback, rvol=rvol, now=now
    )
