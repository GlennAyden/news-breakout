import numpy as np
import pandas as pd
from datetime import datetime

from news_breakout.signals.elliott.swings import atr, detect_swings, multi_scale_swings
from news_breakout.signals.elliott.models import Swing


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    p = np.asarray(prices, dtype=float)
    # simple OHLC around the close path: high/low = close +/- 0.5
    return pd.DataFrame(
        {"Open": p, "High": p + 0.5, "Low": p - 0.5, "Close": p, "Volume": 1000.0},
        index=idx,
    )


def test_atr_is_positive_after_window():
    df = _df(list(range(1, 40)))
    a = atr(df, 14)
    assert a.iloc[-1] > 0
    assert a.iloc[:13].isna().all()  # not enough bars before the window


def test_monotonic_series_yields_single_provisional_swing():
    df = _df([10 + i for i in range(40)])  # strictly rising
    sw = detect_swings(df, atr_mult=2.0, atr_window=14)
    assert len(sw) == 1
    assert sw[0].provisional is True
    assert sw[0].kind == "H"
    assert sw[0].i == len(df) - 1  # the last (highest) bar


def test_zigzag_detects_alternating_pivots():
    # rise to ~40, fall to ~20, rise to ~55  -> expect at least H then L confirmed
    up1 = list(np.linspace(20, 40, 20))
    down = list(np.linspace(40, 20, 20))
    up2 = list(np.linspace(20, 55, 20))
    df = _df(up1 + down + up2)
    sw = detect_swings(df, atr_mult=2.0, atr_window=14)
    kinds = [s.kind for s in sw]
    # alternation holds
    assert all(kinds[i] != kinds[i + 1] for i in range(len(kinds) - 1))
    # a confirmed high near the first peak and a confirmed low near the trough exist
    confirmed = [s for s in sw if not s.provisional]
    assert any(s.kind == "H" and s.price >= 39 for s in confirmed)
    assert any(s.kind == "L" and s.price <= 21 for s in confirmed)
    assert sw[-1].provisional is True  # last leg always provisional


def test_multi_scale_returns_one_list_per_scale():
    df = _df(list(np.linspace(20, 40, 30)) + list(np.linspace(40, 25, 30)))
    out = multi_scale_swings(df, scales=(2.0, 4.0), atr_window=14)
    assert set(out.keys()) == {2.0, 4.0}
    assert all(isinstance(v, list) for v in out.values())
