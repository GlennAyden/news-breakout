from tests.fixtures import make_ohlcv
from news_breakout.signals.breakout import detect_donchian_breakout


def test_breakout_true_when_close_exceeds_prior_high():
    # prior 3 highs max = 110; last close = 115 -> breakout, level 110
    df = make_ohlcv(
        highs=[100, 105, 110, 116],
        lows=[90, 95, 100, 108],
        closes=[95, 100, 105, 115],
        volumes=[1, 1, 1, 1],
    )
    is_bo, level = detect_donchian_breakout(df, lookback=3)
    assert is_bo is True
    assert level == 110


def test_no_breakout_when_close_below_prior_high():
    df = make_ohlcv(
        highs=[100, 105, 110, 111],
        lows=[90, 95, 100, 101],
        closes=[95, 100, 105, 108],  # 108 < 110
        volumes=[1, 1, 1, 1],
    )
    is_bo, level = detect_donchian_breakout(df, lookback=3)
    assert is_bo is False
    assert level == 110


def test_no_breakout_when_not_enough_rows():
    df = make_ohlcv(highs=[100, 105], lows=[90, 95], closes=[95, 100], volumes=[1, 1])
    is_bo, level = detect_donchian_breakout(df, lookback=20)
    assert is_bo is False
    assert level == 0.0
