from tests.fixtures import make_ohlcv
from news_breakout.signals.wyckoff import detect_range_breakout


def test_breakout_when_tight_range_then_close_above():
    # prior 4 bars range 100..110 (width 10%), last close 112 breaks above 110
    df = make_ohlcv(
        highs=[110, 108, 109, 110, 112],
        lows=[100, 101, 100, 102, 108],
        closes=[105, 104, 106, 107, 112],
        volumes=[1, 1, 1, 1, 1],
    )
    is_bo, low, high = detect_range_breakout(df, range_lookback=4, max_width_pct=0.15)
    assert is_bo is True
    assert low == 100
    assert high == 110


def test_no_breakout_when_range_too_wide():
    # prior range 100..140 = 40% width, exceeds 15% even though close breaks above
    df = make_ohlcv(
        highs=[140, 120, 130, 140, 145],
        lows=[100, 101, 100, 102, 141],
        closes=[110, 104, 106, 107, 144],
        volumes=[1, 1, 1, 1, 1],
    )
    is_bo, low, high = detect_range_breakout(df, range_lookback=4, max_width_pct=0.15)
    assert is_bo is False


def test_no_breakout_when_close_inside_range():
    df = make_ohlcv(
        highs=[110, 108, 109, 110, 109],
        lows=[100, 101, 100, 102, 103],
        closes=[105, 104, 106, 107, 108],  # 108 < range_high 110
        volumes=[1, 1, 1, 1, 1],
    )
    is_bo, low, high = detect_range_breakout(df, range_lookback=4, max_width_pct=0.15)
    assert is_bo is False


def test_no_breakout_when_not_enough_rows():
    df = make_ohlcv(highs=[110, 108], lows=[100, 101], closes=[105, 104], volumes=[1, 1])
    assert detect_range_breakout(df, range_lookback=30, max_width_pct=0.15) == (False, 0.0, 0.0)
