from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass
class VolumeConfig:
    # Rule 2: today's cumulative volume >= this fraction of the previous day's
    # total. Today's daily bar volume is cumulative-so-far during the session.
    min_ratio_prev_day: float = 0.5


@dataclass
class VolumeResult:
    passed: bool
    today_vol: float
    prev_vol: float
    ratio: float  # today_vol / prev_vol (0.0 if prev_vol missing/zero)


def passes_early_volume(
    daily: pd.DataFrame, now: datetime, cfg: VolumeConfig
) -> VolumeResult:
    """Rule-2 pre-filter, OHLCV-only (no API call).

    Compares today's (partial, cumulative) daily-bar volume against the
    previous trading day's total. ``passed`` requires that the latest daily bar
    is actually today's — a stale last bar means we cannot judge today's pace,
    so it fails closed.
    """
    empty = VolumeResult(False, 0.0, 0.0, 0.0)
    if daily is None or len(daily) < 2 or "Volume" not in daily.columns:
        return empty

    last_ts = daily.index[-1]
    last_date = last_ts.date() if hasattr(last_ts, "date") else None
    if last_date != now.date():  # no fresh today bar → cannot judge pace
        today_vol = float(daily["Volume"].iloc[-1] or 0.0)
        prev_vol = float(daily["Volume"].iloc[-2] or 0.0)
        return VolumeResult(False, today_vol, prev_vol, 0.0)

    today_vol = float(daily["Volume"].iloc[-1] or 0.0)
    prev_vol = float(daily["Volume"].iloc[-2] or 0.0)
    if prev_vol <= 0:
        return VolumeResult(False, today_vol, prev_vol, 0.0)
    ratio = today_vol / prev_vol
    return VolumeResult(ratio >= cfg.min_ratio_prev_day, today_vol, prev_vol, ratio)
