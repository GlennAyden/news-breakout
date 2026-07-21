from __future__ import annotations

import pandas as pd


def _recent_swing_low(df: pd.DataFrame, k: int = 3) -> float:
    """Most recent confirmed fractal swing low (local min over +/-k bars),
    falling back to the min low over the prior 20 bars. Causal: uses only df."""
    lows = df["Low"].to_numpy()
    n = len(df)
    i = n - 1
    for j in range(i - k, k - 1, -1):
        if j + k > i:
            continue
        if lows[j] <= lows[j - k : j].min() and lows[j] <= lows[j + 1 : j + k + 1].min():
            return float(lows[j])
    lo = max(0, i - 20)
    return float(lows[lo : i + 1].min())


def structure_stop(df: pd.DataFrame, entry: float, ctx=None) -> float | None:
    """EW-3 stop: the wave invalidation if valid (< entry), else the most recent
    fractal swing low if it is < entry. None when neither is below entry (caller
    then falls back to the broken-level plan)."""
    if ctx is not None and getattr(ctx, "invalidation", None) is not None and ctx.invalidation < entry:
        return float(ctx.invalidation)
    sl = _recent_swing_low(df)
    return sl if sl < entry else None
