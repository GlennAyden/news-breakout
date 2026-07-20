from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.signals.elliott.models import WaveContext
from news_breakout.signals.scoring import (
    W_IMPULSE_MID,
    W_WAVE3_START,
    W_WAVE5_EXHAUSTION,
    compute_score_components,
)

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)


def _signal(price=105.0, level=100.0, timeframe="1D", rvol=3.0):
    return BreakoutSignal(
        ticker="ANTM", timeframe=timeframe, signal_type="resistance_breakout",
        price=price, pct_change=0.0, level=level, rvol=rvol, timestamp=NOW,
    )


def _alert(priority=3.0):
    return TickerAlert(ticker="ANTM", signals=[_signal()], priority=priority, timestamp=NOW)


def test_wave3_start_boosts_score_scaled_by_confidence():
    alert = _alert()
    base = compute_score_components(alert, None).score
    ctx = WaveContext(position="wave_3_start", confidence=0.8)
    c = compute_score_components(alert, None, wave_context=ctx)
    assert c.score == pytest.approx(base + W_WAVE3_START * 0.8)
    assert c.wave_adjust == pytest.approx(1.6)


def test_impulse_mid_penalizes_score():
    alert = _alert()
    base = compute_score_components(alert, None).score
    ctx = WaveContext(position="impulse_mid", confidence=0.5)
    c = compute_score_components(alert, None, wave_context=ctx)
    assert c.score == pytest.approx(base - W_IMPULSE_MID)
    assert c.wave_adjust == pytest.approx(-1.5)


def test_wave5_exhaustion_penalizes():
    alert = _alert()
    base = compute_score_components(alert, None).score
    ctx = WaveContext(position="wave_5_possible_exhaustion", confidence=0.9)
    c = compute_score_components(alert, None, wave_context=ctx)
    assert c.score == pytest.approx(base - W_WAVE5_EXHAUSTION)
    assert c.wave_adjust == pytest.approx(-1.0)


@pytest.mark.parametrize("position", ["ambiguous", "none", "corrective_or_unresolved",
                                       "wave_2_pullback", "wave_4_pullback"])
def test_neutral_positions_and_none_no_change(position):
    alert = _alert()
    base = compute_score_components(alert, None).score

    ctx = WaveContext(position=position, confidence=0.7)
    c = compute_score_components(alert, None, wave_context=ctx)
    assert c.wave_adjust == pytest.approx(0.0)
    assert c.score == pytest.approx(base)

    c_none = compute_score_components(alert, None, wave_context=None)
    assert c_none.wave_adjust == pytest.approx(0.0)
    assert c_none.score == pytest.approx(base)
