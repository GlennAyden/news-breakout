import pandas as pd
from news_breakout.data.yfinance_source import fetch_daily_ohlcv


def _mi(per):  # yfinance-style (Ticker, Field) columns
    return pd.concat(per, axis=1)


def _one(n):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 1}, index=idx)


def test_retries_on_empty_then_succeeds():
    calls = []
    good = _mi({"ANTM.JK": _one(3)})

    def flaky(tickers, period, interval, group_by, auto_adjust, progress, threads):
        calls.append(1)
        return pd.DataFrame() if len(calls) == 1 else good

    out = fetch_daily_ohlcv(["ANTM"], 10, downloader=flaky, sleeper=lambda s: None)
    assert len(calls) == 2
    assert "ANTM" in out


def test_gives_up_after_retries():
    calls = []

    def empty(tickers, period, interval, group_by, auto_adjust, progress, threads):
        calls.append(1)
        return pd.DataFrame()

    out = fetch_daily_ohlcv(["ANTM"], 10, downloader=empty, retries=2, sleeper=lambda s: None)
    assert len(calls) == 3
    assert out == {}
