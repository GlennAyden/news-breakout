import numpy as np
import pandas as pd

from news_breakout.signals.elliott.corrective import _is_abc, emerges_from_abc


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    p = np.asarray(prices, dtype=float)
    return pd.DataFrame(
        {"Open": p, "High": p + 0.5, "Low": p - 0.5, "Close": p, "Volume": 1000.0},
        index=idx,
    )


def _abc_df(legA_end, legB_end, legC_end, final_end, *, h0=100.0):
    """Warmup rise to h0, then down-A, up-B, down-C, then a final (provisional) up leg."""
    warmup = list(np.linspace(20, h0, 30))
    legA = list(np.linspace(h0, legA_end, 20))
    legB = list(np.linspace(legA_end, legB_end, 20))
    legC = list(np.linspace(legB_end, legC_end, 20))
    legFinal = list(np.linspace(legC_end, final_end, 20))
    prices = warmup + legA[1:] + legB[1:] + legC[1:] + legFinal[1:]
    return _df(prices)


def test_clean_abc_ending_in_up_leg_is_true():
    # down-A (100->80), up-B (80->90, 0.5 retrace), down-C (90->70, ~1x A), then up
    df = _abc_df(80, 90, 70, 110)
    assert emerges_from_abc(df, scale=3.5) is True


def test_b_retrace_too_deep_is_false():
    # B retraces 0.9 of A (too deep, above 0.786 ceiling)
    df = _abc_df(80, 98, 78, 120)
    assert emerges_from_abc(df, scale=3.5) is False


def test_b_exceeds_a_start_is_false():
    # B rallies past A's start (h0)
    df = _abc_df(80, 105, 85, 130)
    assert emerges_from_abc(df, scale=3.5) is False


def test_c_too_long_is_false():
    # C runs 3x the length of A
    df = _abc_df(80, 90, 30, 90)
    assert emerges_from_abc(df, scale=3.5) is False


def test_fewer_than_five_swings_is_false():
    df = _df([10 + i for i in range(40)])  # strictly rising -> single provisional swing
    assert emerges_from_abc(df, scale=3.5) is False


# -- pure geometry checks (avoids fiddly ATR-ZigZag calibration) --------------


def test_is_abc_geometry_true_for_clean_structure():
    assert _is_abc(100.0, 80.0, 90.0, 70.0) is True


def test_is_abc_geometry_false_for_deep_b_retrace():
    assert _is_abc(100.0, 80.0, 98.0, 78.0) is False


def test_is_abc_geometry_false_when_b_exceeds_a_start():
    assert _is_abc(100.0, 80.0, 105.0, 85.0) is False


def test_is_abc_geometry_false_for_long_c():
    assert _is_abc(100.0, 80.0, 90.0, 30.0) is False
