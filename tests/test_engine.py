from datetime import datetime
from zoneinfo import ZoneInfo

from tests.fixtures import make_ohlcv
from news_breakout.signals.engine import evaluate_daily

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)


def _breakout_df(last_volume):
    # prior 3 highs max = 110; last close 115 breaks out. prior vols avg 100.
    return make_ohlcv(
        highs=[100, 105, 110, 116],
        lows=[90, 95, 100, 108],
        closes=[100, 100, 100, 115],
        volumes=[100, 100, 100, last_volume],
    )


def test_signal_when_breakout_and_volume_confirmed():
    df = _breakout_df(last_volume=300)  # rvol 3.0 >= 2.0
    sig = evaluate_daily(
        "ANTM", df, lookback=3, rvol_window=3, rvol_threshold=2.0, now=NOW
    )
    assert sig is not None
    assert sig.ticker == "ANTM"
    assert sig.timeframe == "1D"
    assert sig.signal_type == "resistance_breakout"
    assert sig.price == 115
    assert sig.level == 110
    assert sig.rvol == 3.0
    assert round(sig.pct_change, 1) == 15.0  # 100 -> 115
    assert sig.timestamp == NOW


def test_no_signal_when_volume_too_low():
    df = _breakout_df(last_volume=120)  # rvol 1.2 < 2.0
    sig = evaluate_daily(
        "ANTM", df, lookback=3, rvol_window=3, rvol_threshold=2.0, now=NOW
    )
    assert sig is None


def test_no_signal_when_no_breakout():
    df = make_ohlcv(
        highs=[100, 105, 110, 111],
        lows=[90, 95, 100, 101],
        closes=[100, 100, 100, 108],  # no breakout
        volumes=[100, 100, 100, 500],
    )
    sig = evaluate_daily(
        "ANTM", df, lookback=3, rvol_window=3, rvol_threshold=2.0, now=NOW
    )
    assert sig is None
