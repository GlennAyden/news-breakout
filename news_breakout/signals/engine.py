from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from news_breakout.models import TF_WEIGHT, BreakoutSignal, TickerAlert
from news_breakout.signals.breakout import detect_donchian_breakout
from news_breakout.signals.elliott.trade_plan import structure_stop
from news_breakout.signals.elliott.waves import label_current
from news_breakout.signals.scoring import compute_score_components
from news_breakout.signals.volume import compute_rvol

logger = logging.getLogger(__name__)


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


def evaluate_timeframe(
    ticker: str, df: pd.DataFrame, timeframe: str, *,
    donchian_lookback: int, rvol_window: int, rvol_threshold: float,
    now: datetime,
) -> list[BreakoutSignal]:
    if len(df) < 2:
        return []
    rvol = compute_rvol(df, rvol_window)
    if rvol < rvol_threshold:
        return []
    res = _resistance_signal(
        ticker, df, timeframe, donchian_lookback=donchian_lookback, rvol=rvol, now=now
    )
    return [res] if res is not None else []


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


_TF_ORDER = ["1D", "4H", "1H"]


def evaluate_ticker(
    ticker: str, frames: dict[str, pd.DataFrame], *,
    donchian_lookback: int, rvol_window: int, rvol_threshold: float,
    now: datetime, elliott_enabled: bool = True,
    elliott_scales: tuple[float, ...] = (2.0, 3.5, 5.0),
    elliott_atr_window: int = 14, elliott_max_pivots: int = 9,
    elliott_fib_tolerance: float = 0.06,
) -> TickerAlert | None:
    signals: list[BreakoutSignal] = []
    for tf in _TF_ORDER:
        df = frames.get(tf)
        if df is None:
            continue
        signals.extend(evaluate_timeframe(
            ticker, df, tf,
            donchian_lookback=donchian_lookback, rvol_window=rvol_window,
            rvol_threshold=rvol_threshold, now=now,
        ))
    if not signals:
        return None
    priority = sum(TF_WEIGHT[s.timeframe] for s in signals)
    alert = TickerAlert(ticker=ticker, signals=signals, priority=priority, timestamp=now)
    if elliott_enabled and (daily := frames.get("1D")) is not None:
        try:
            alert.wave_context = label_current(
                daily, scales=elliott_scales, atr_window=elliott_atr_window,
                max_pivots=elliott_max_pivots, fib_tol=elliott_fib_tolerance,
            )
        except Exception:
            logger.warning("elliott labeling failed for %s", ticker, exc_info=True)
            alert.wave_context = None
        try:
            entry_px = float(daily["Close"].iloc[-1])
            alert.structure_stop = structure_stop(daily, entry_px, alert.wave_context)
        except Exception:
            logger.warning("elliott structure_stop failed for %s", ticker, exc_info=True)
            alert.structure_stop = None
    components = compute_score_components(
        alert, frames.get("1D"), wave_context=alert.wave_context
    )
    alert.quality_score = components.score
    alert.ext_pct = components.ext_pct
    alert.above_sma50 = components.above_sma50
    return alert
