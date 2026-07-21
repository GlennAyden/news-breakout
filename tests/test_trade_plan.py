import pandas as pd
import pytest

from news_breakout.signals.elliott.models import WaveContext
from news_breakout.signals.elliott.trade_plan import _recent_swing_low, structure_stop, trail_plan


def _df(lows: list[float]) -> pd.DataFrame:
    n = len(lows)
    return pd.DataFrame({
        "Open": lows,
        "High": [v + 1 for v in lows],
        "Low": lows,
        "Close": [v + 0.5 for v in lows],
    })


def test_structure_stop_uses_wave_invalidation_when_below_entry():
    df = _df([100, 95, 96, 97, 98, 99, 100, 101, 102])
    ctx = WaveContext(invalidation=90.0)
    assert structure_stop(df, entry=105.0, ctx=ctx) == 90.0


def test_structure_stop_falls_back_to_swing_low_when_ctx_none():
    # crafted so there is a clear fractal swing low below entry
    lows = [110, 108, 106, 90, 104, 106, 108, 110, 112]
    df = _df(lows)
    entry = 111.0
    result = structure_stop(df, entry=entry, ctx=None)
    assert result is not None
    assert result < entry


def test_structure_stop_returns_none_when_all_lows_above_entry():
    lows = [100, 101, 102, 103, 104, 105, 106, 107, 108]
    df = _df(lows)
    result = structure_stop(df, entry=50.0, ctx=None)
    assert result is None


def test_structure_stop_falls_through_to_swing_low_when_invalidation_not_below_entry():
    lows = [110, 108, 106, 90, 104, 106, 108, 110, 112]
    df = _df(lows)
    entry = 111.0
    ctx = WaveContext(invalidation=120.0)  # >= entry, must fall through
    result = structure_stop(df, entry=entry, ctx=ctx)
    assert result is not None
    assert result < entry
    assert result != 120.0


def test_recent_swing_low_finds_local_min():
    lows = [110, 108, 106, 90, 104, 106, 108, 110, 112]
    df = _df(lows)
    assert _recent_swing_low(df, k=3) == 90.0


def test_recent_swing_low_falls_back_to_20_bar_min_when_no_fractal():
    # monotonically increasing lows -> no interior fractal swing low found
    lows = [float(x) for x in range(50, 70)]
    df = _df(lows)
    assert _recent_swing_low(df, k=3) == min(lows)


def test_trail_plan_computes_risk_activate_and_trail_distance():
    plan = trail_plan(entry=3070, stop=2900, atr=80)
    assert plan["risk_pct"] == pytest.approx(5.54, abs=0.01)
    assert plan["activate"] == pytest.approx(3240.0)
    assert plan["trail_dist"] == pytest.approx(200.0)
    assert plan["mult"] == pytest.approx(2.5)
