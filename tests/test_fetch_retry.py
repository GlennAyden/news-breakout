import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.data.yfinance_source import fetch_daily_ohlcv
from news_breakout.news.idx_source import fetch_disclosures_ex

NOW = datetime(2026, 7, 18, 9, 0, tzinfo=ZoneInfo("Asia/Jakarta"))


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


def test_retries_on_exception_then_succeeds():
    calls = []
    good = _mi({"ANTM.JK": _one(3)})

    def raising(tickers, period, interval, group_by, auto_adjust, progress, threads):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("rate limited")
        return good

    out = fetch_daily_ohlcv(["ANTM"], 10, downloader=raising, sleeper=lambda s: None)
    assert len(calls) == 2
    assert "ANTM" in out


def test_all_exceptions_returns_empty():
    def always_raise(*a, **k):
        raise RuntimeError("boom")

    out = fetch_daily_ohlcv(["ANTM"], 10, downloader=always_raise, retries=1, sleeper=lambda s: None)
    assert out == {}


def test_ex_ok_true_on_valid_even_empty_payload():
    items, ok = fetch_disclosures_ex(
        50, now=NOW, retries=0, http_get=lambda url, proxy: '{"Replies": []}')
    assert ok is True
    assert items == []


def test_ex_ok_false_on_cloudflare_html():
    calls = []
    items, ok = fetch_disclosures_ex(
        50, now=NOW, retries=1, sleeper=lambda s: calls.append(s),
        http_get=lambda url, proxy: "<html>blocked</html>")
    assert ok is False
    assert items == []
    assert calls == [5]   # existing retry delay table
