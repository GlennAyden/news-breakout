from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.fixtures import make_ohlcv
from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.signals.scoring import (
    EXT_PCT_CAP,
    W_EXT,
    W_TREND_DOWN,
    W_TREND_UP,
    compute_quality_score,
    compute_score_components,
)

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)


def _signal(price, level, timeframe="1D", rvol=3.0):
    return BreakoutSignal(
        ticker="ANTM", timeframe=timeframe, signal_type="resistance_breakout",
        price=price, pct_change=0.0, level=level, rvol=rvol, timestamp=NOW,
    )


def _alert(signals, priority=3.0):
    return TickerAlert(ticker="ANTM", signals=signals, priority=priority, timestamp=NOW)


def _daily_df(last_close, bars=50):
    """A daily frame whose last close differs from the rest, to drive the SMA50 filter."""
    closes = [100.0] * (bars - 1) + [last_close]
    return make_ohlcv(highs=closes, lows=closes, closes=closes, volumes=[100] * bars)


# --- extension reward: strongest predictor in backtest, must be monotonic ---

def test_extension_rewarded_higher_than_marginal():
    marginal = _alert([_signal(price=101.0, level=100.0)])   # +1% above level
    strong = _alert([_signal(price=108.0, level=100.0)])      # +8% above level
    assert compute_quality_score(strong) > compute_quality_score(marginal)


def test_extension_pct_matches_price_level_distance():
    alert = _alert([_signal(price=105.0, level=100.0)])
    c = compute_score_components(alert)
    assert c.ext_pct == pytest.approx(5.0)
    assert c.score == pytest.approx(alert.priority + W_EXT * 5.0)


def test_extension_clamped_at_cap():
    huge = _alert([_signal(price=150.0, level=100.0)])  # +50%, well past the cap
    c = compute_score_components(huge)
    assert c.ext_pct == pytest.approx(EXT_PCT_CAP)
    assert c.score == pytest.approx(huge.priority + W_EXT * EXT_PCT_CAP)


def test_extension_not_negative_when_price_at_or_below_level():
    alert = _alert([_signal(price=95.0, level=100.0)])
    c = compute_score_components(alert)
    assert c.ext_pct == 0.0
    assert c.score == pytest.approx(alert.priority)


def test_uses_highest_timeframe_signal_for_extension():
    # 1D barely above its level, 1H way above its level -- 1D (TF_WEIGHT) must win.
    alert = _alert([
        _signal(price=101.0, level=100.0, timeframe="1D"),
        _signal(price=150.0, level=100.0, timeframe="1H"),
    ])
    c = compute_score_components(alert)
    assert c.ext_pct == pytest.approx(1.0)


# --- trend filter: below-SMA50 breakouts are net-negative in backtest ---

def test_trend_up_adds_bonus():
    alert = _alert([_signal(price=100.0, level=100.0)])
    c = compute_score_components(alert, _daily_df(last_close=120.0))
    assert c.above_sma50 is True
    assert c.score == pytest.approx(alert.priority + W_TREND_UP)


def test_trend_down_penalizes():
    alert = _alert([_signal(price=100.0, level=100.0)])
    c = compute_score_components(alert, _daily_df(last_close=80.0))
    assert c.above_sma50 is False
    assert c.score == pytest.approx(alert.priority - W_TREND_DOWN)


def test_trend_neutral_when_daily_df_missing():
    alert = _alert([_signal(price=100.0, level=100.0)])
    c = compute_score_components(alert, None)
    assert c.above_sma50 is None
    assert c.score == pytest.approx(alert.priority)


def test_trend_neutral_when_daily_df_too_short_for_sma50():
    alert = _alert([_signal(price=100.0, level=100.0)])
    short_df = _daily_df(last_close=120.0, bars=10)  # fewer than SMA_WINDOW=50 bars
    c = compute_score_components(alert, short_df)
    assert c.above_sma50 is None
    assert c.score == pytest.approx(alert.priority)


# --- RVOL: inverted-U in backtest, must never be added to the score ---

def test_rvol_does_not_change_score_moderate_vs_extreme():
    moderate = _alert([_signal(price=105.0, level=100.0, rvol=4.5)])
    extreme = _alert([_signal(price=105.0, level=100.0, rvol=9.0)])
    assert compute_quality_score(moderate) == compute_quality_score(extreme)


# --- ordering: the point of this whole module ---

def test_high_extension_uptrend_outranks_marginal_downtrend_equal_priority():
    strong = _alert([_signal(price=108.0, level=100.0)], priority=3.0)
    marginal = _alert([_signal(price=100.5, level=100.0)], priority=3.0)
    strong_score = compute_quality_score(strong, _daily_df(last_close=120.0))
    marginal_score = compute_quality_score(marginal, _daily_df(last_close=80.0))
    assert strong_score > marginal_score
