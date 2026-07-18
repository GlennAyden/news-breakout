from tests.fixtures import make_ohlcv
from news_breakout.signals.volume import compute_rvol


def test_rvol_is_last_over_average_of_previous_window():
    # previous 4 volumes average = 100; last = 300 -> rvol 3.0
    df = make_ohlcv(
        highs=[1, 1, 1, 1, 1],
        lows=[1, 1, 1, 1, 1],
        closes=[1, 1, 1, 1, 1],
        volumes=[100, 100, 100, 100, 300],
    )
    assert compute_rvol(df, window=4) == 3.0


def test_rvol_zero_when_not_enough_rows():
    df = make_ohlcv(highs=[1, 1], lows=[1, 1], closes=[1, 1], volumes=[100, 200])
    assert compute_rvol(df, window=20) == 0.0


def test_rvol_zero_when_average_is_zero():
    df = make_ohlcv(
        highs=[1, 1, 1], lows=[1, 1, 1], closes=[1, 1, 1], volumes=[0, 0, 500]
    )
    assert compute_rvol(df, window=2) == 0.0
