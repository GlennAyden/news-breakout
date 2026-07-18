from datetime import datetime
from zoneinfo import ZoneInfo

from tests.fixtures import make_ohlcv
from news_breakout.signals.engine import evaluate_ticker

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)

PARAMS = dict(
    donchian_lookback=3, rvol_window=3, rvol_threshold=2.0,
    range_lookback=3, range_max_width_pct=0.15,
)


def _breakout_df():
    return make_ohlcv(
        highs=[110, 108, 110, 116],
        lows=[100, 101, 102, 108],
        closes=[105, 104, 107, 115],
        volumes=[100, 100, 100, 300],  # rvol 3.0
    )


def _flat_df():
    return make_ohlcv(
        highs=[110, 110, 110, 110],
        lows=[100, 100, 100, 100],
        closes=[105, 105, 105, 105],
        volumes=[100, 100, 100, 100],  # rvol 1.0, no breakout
    )


def test_evaluate_ticker_aggregates_and_scores():
    frames = {"1D": _breakout_df(), "1H": _breakout_df()}
    alert = evaluate_ticker("ANTM", frames, now=NOW, **PARAMS)
    assert alert is not None
    assert alert.ticker == "ANTM"
    fired_tfs = {s.timeframe for s in alert.signals}
    assert fired_tfs == {"1D", "1H"}
    # 1D weight 3 + 1H weight 1, counted once per fired signal on each TF
    assert alert.priority >= 4.0
    assert alert.max_rvol == 3.0


def test_evaluate_ticker_none_when_nothing_fires():
    frames = {"1D": _flat_df(), "1H": _flat_df()}
    assert evaluate_ticker("ANTM", frames, now=NOW, **PARAMS) is None


def test_priority_higher_tf_outranks_lower():
    a = evaluate_ticker("A", {"1D": _breakout_df()}, now=NOW, **PARAMS)
    b = evaluate_ticker("B", {"1H": _breakout_df()}, now=NOW, **PARAMS)
    assert a.priority > b.priority
