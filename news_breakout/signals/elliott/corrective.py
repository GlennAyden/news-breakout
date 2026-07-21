from __future__ import annotations

import pandas as pd

from news_breakout.signals.elliott.swings import detect_swings


def _is_abc(h0: float, la: float, hb: float, lc: float) -> bool:
    """Pure Fibonacci-geometry check for a completed A-B-C zigzag correction:
    down-A (h0->la), up-B (la->hb, retracing 0.382-0.786 of A, not exceeding
    A's start), down-C (hb->lc, 0.618-1.618 x A)."""
    a = h0 - la
    if a <= 0:
        return False
    b_ret = (hb - la) / a
    c = hb - lc
    return (0.382 <= b_ret <= 0.786) and (hb < h0) and (0.618 * a <= c <= 1.618 * a)


def emerges_from_abc(df: pd.DataFrame, scale: float = 3.5) -> bool:
    """True if the structure just before the current (provisional up) leg is a
    completed A-B-C zigzag correction: down-A, up-B (retraces 0.382-0.786 of A,
    not exceeding A's start), down-C (0.618-1.618 x A). Advisory only — breakouts
    emerging from an ABC historically underperform (backtest: -5.4pp/10d)."""
    sw = detect_swings(df, scale)
    if len(sw) < 5 or not sw[-1].provisional or sw[-1].kind != "H":
        return False
    tail = sw[-5:-1]  # 4 confirmed swings before the provisional up leg
    if [s.kind for s in tail] != ["H", "L", "H", "L"]:
        return False
    h0, la, hb, lc = (s.price for s in tail)
    return _is_abc(h0, la, hb, lc)
