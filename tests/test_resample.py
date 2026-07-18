import pandas as pd

from news_breakout.data.resample import resample_ohlcv


def test_resample_1h_to_4h_aggregates_correctly():
    idx = pd.date_range("2026-01-01 08:00", periods=8, freq="1h")
    df = pd.DataFrame(
        {
            "Open": [10, 11, 12, 13, 20, 21, 22, 23],
            "High": [15, 16, 17, 18, 25, 26, 27, 28],
            "Low": [5, 6, 7, 8, 15, 16, 17, 18],
            "Close": [11, 12, 13, 14, 21, 22, 23, 24],
            "Volume": [1, 2, 3, 4, 5, 6, 7, 8],
        },
        index=idx,
    )
    out = resample_ohlcv(df, "4h")
    assert len(out) == 2
    first = out.iloc[0]
    assert first["Open"] == 10 and first["High"] == 18
    assert first["Low"] == 5 and first["Close"] == 14 and first["Volume"] == 10
    second = out.iloc[1]
    assert second["Open"] == 20 and second["High"] == 28
    assert second["Low"] == 15 and second["Close"] == 24 and second["Volume"] == 26


def test_resample_drops_empty_buckets():
    idx = pd.DatetimeIndex(["2026-01-01 08:00", "2026-01-01 20:00"])
    df = pd.DataFrame(
        {"Open": [10, 20], "High": [15, 25], "Low": [5, 15], "Close": [11, 21], "Volume": [1, 2]},
        index=idx,
    )
    out = resample_ohlcv(df, "4h")
    assert len(out) == 2  # the empty 4h buckets between are dropped
