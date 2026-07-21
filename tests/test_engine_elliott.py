import numpy as np
import pandas as pd
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.signals import engine as E
from news_breakout.signals.engine import evaluate_ticker
from news_breakout.signals.scoring import compute_score_components

NOW = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))


def _breakout_daily(n=80):
    # a clean uptrend that ends on a new-high breakout bar with a volume spike
    base = np.linspace(100, 150, n)
    p = base.copy()
    df = pd.DataFrame(
        {"Open": p, "High": p + 0.5, "Low": p - 0.5, "Close": p,
         "Volume": [1000.0] * (n - 1) + [5000.0]},
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )
    df.iloc[-1, df.columns.get_loc("High")] = df["High"].iloc[-2] + 5
    df.iloc[-1, df.columns.get_loc("Close")] = df["High"].iloc[-2] + 4
    return df


def test_evaluate_ticker_attaches_wave_context():
    df = _breakout_daily()
    alert = evaluate_ticker(
        "ANTM", {"1D": df}, donchian_lookback=20, rvol_window=20,
        rvol_threshold=2.5, now=NOW,
    )
    assert alert is not None                      # a breakout fired
    assert hasattr(alert, "wave_context")         # context attached (may be a 'none' ctx)


def test_labeling_failure_is_swallowed(monkeypatch):
    df = _breakout_daily()

    def boom(*a, **k):
        raise ValueError("boom")

    monkeypatch.setattr(E, "label_current", boom)
    alert = evaluate_ticker(
        "ANTM", {"1D": df}, donchian_lookback=20, rvol_window=20,
        rvol_threshold=2.5, now=NOW,
    )
    assert alert is not None                      # scan still succeeds
    assert alert.wave_context is None             # failure degraded to None


def test_elliott_disabled_leaves_context_none():
    df = _breakout_daily()
    alert = evaluate_ticker(
        "ANTM", {"1D": df}, donchian_lookback=20, rvol_window=20,
        rvol_threshold=2.5, now=NOW, elliott_enabled=False,
    )
    assert alert is not None
    assert alert.wave_context is None


def test_from_abc_is_set_without_error():
    # Advisory-only annotation: labeling must set wave_context.from_abc to a bool
    # (or leave wave_context None) without raising, and must not affect the score.
    df = _breakout_daily()
    alert = evaluate_ticker(
        "ANTM", {"1D": df}, donchian_lookback=20, rvol_window=20,
        rvol_threshold=2.5, now=NOW,
    )
    assert alert is not None
    if alert.wave_context is not None:
        assert isinstance(alert.wave_context.from_abc, bool)


def test_score_reflects_wave_context():
    # Robust to whatever wave_context the synthetic df produces: the engine must
    # have fed alert.wave_context into scoring, not scored before labeling.
    df = _breakout_daily()
    alert = evaluate_ticker(
        "ANTM", {"1D": df}, donchian_lookback=20, rvol_window=20,
        rvol_threshold=2.5, now=NOW,
    )
    assert alert is not None
    expected = compute_score_components(
        alert, df, wave_context=alert.wave_context
    ).score
    assert alert.quality_score == pytest.approx(expected)
