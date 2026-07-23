from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from news_breakout.orderbook.volume_filter import VolumeConfig, passes_early_volume

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 20, 10, 0, tzinfo=WIB)
CFG = VolumeConfig(min_ratio_prev_day=0.5)


def _daily(volumes, dates=("2026-07-17", "2026-07-20")):
    idx = pd.to_datetime(list(dates))
    return pd.DataFrame({"Close": [100] * len(volumes), "Volume": list(volumes)}, index=idx)


def test_passes_when_today_at_least_half_prev():
    r = passes_early_volume(_daily([1000, 600]), NOW, CFG)  # ratio 0.6
    assert r.passed
    assert r.ratio == 0.6


def test_fails_when_today_below_half():
    r = passes_early_volume(_daily([1000, 400]), NOW, CFG)  # ratio 0.4
    assert not r.passed


def test_boundary_exactly_half_passes():
    assert passes_early_volume(_daily([1000, 500]), NOW, CFG).passed


def test_fails_when_last_bar_is_not_today():
    # last bar dated 2026-07-17, but now is 2026-07-20 -> cannot judge pace
    r = passes_early_volume(_daily([1000, 900], dates=("2026-07-16", "2026-07-17")), NOW, CFG)
    assert not r.passed
    assert r.ratio == 0.0


def test_fails_on_insufficient_history():
    one = pd.DataFrame({"Close": [100], "Volume": [1000]}, index=pd.to_datetime(["2026-07-20"]))
    assert not passes_early_volume(one, NOW, CFG).passed


def test_fails_when_prev_day_zero():
    assert not passes_early_volume(_daily([0, 500]), NOW, CFG).passed
