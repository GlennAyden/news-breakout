from __future__ import annotations

import pandas as pd

from news_breakout.signals.elliott.models import Swing


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Wilder's ATR."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def detect_swings(df: pd.DataFrame, atr_mult: float, atr_window: int = 14) -> list[Swing]:
    """Causal ATR-ZigZag. A reversal of >= atr_mult*ATR from the running extreme
    confirms that extreme as a pivot and flips direction. The final still-extending
    leg is returned as one provisional=True swing. Uses only bars up to the end."""
    n = len(df)
    if n < atr_window + 2:
        return []
    a = atr(df, atr_window).to_numpy()
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    idx = list(df.index)
    start = atr_window

    swings: list[Swing] = []
    hi_i, hi = start, high[start]
    lo_i, lo = start, low[start]
    trend = 0  # 0 until first confirmed pivot, then +1 (up leg) / -1 (down leg)

    for i in range(start + 1, n):
        thr = atr_mult * a[i]
        if not (thr > 0):
            continue
        if high[i] > hi:
            hi_i, hi = i, high[i]
        if low[i] < lo:
            lo_i, lo = i, low[i]

        if trend == 0:
            # No trend established yet: the start-of-tracking bar is a warm-up
            # artifact (both hi and lo are anchored there), not a genuine
            # turning point. The first threshold breach only establishes the
            # initial direction; it must not confirm a pivot at that anchor.
            if (hi - low[i]) >= thr:
                trend = -1
                lo_i, lo = i, low[i]
            elif (high[i] - lo) >= thr:
                trend = 1
                hi_i, hi = i, high[i]
        elif trend > 0 and (hi - low[i]) >= thr:
            if not swings or swings[-1].kind != "H":
                swings.append(Swing(hi_i, idx[hi_i], float(hi), "H", provisional=False))
            trend = -1
            lo_i, lo = i, low[i]
        elif trend < 0 and (high[i] - lo) >= thr:
            if not swings or swings[-1].kind != "L":
                swings.append(Swing(lo_i, idx[lo_i], float(lo), "L", provisional=False))
            trend = 1
            hi_i, hi = i, high[i]

    # provisional last leg (always present)
    if trend > 0:
        swings.append(Swing(hi_i, idx[hi_i], float(hi), "H", provisional=True))
    elif trend < 0:
        swings.append(Swing(lo_i, idx[lo_i], float(lo), "L", provisional=True))
    else:
        # never reversed: single provisional pivot at the overall extreme
        if high[n - 1] - low[start] >= low[start] - low[n - 1]:
            swings.append(Swing(hi_i, idx[hi_i], float(hi), "H", provisional=True))
        else:
            swings.append(Swing(lo_i, idx[lo_i], float(lo), "L", provisional=True))
    return swings


def multi_scale_swings(
    df: pd.DataFrame, scales: tuple[float, ...] = (2.0, 3.5, 5.0), atr_window: int = 14
) -> dict[float, list[Swing]]:
    return {s: detect_swings(df, s, atr_window) for s in scales}
