import pandas as pd

from news_breakout.data.yfinance_source import fetch_intraday_ohlcv


def _one(n):
    idx = pd.date_range("2026-01-01 09:00", periods=n, freq="1h")
    return pd.DataFrame(
        {"Open": 100, "High": 100, "Low": 100, "Close": 100, "Volume": 100}, index=idx
    )


def test_fetch_intraday_maps_ticker_and_drops_empty():
    combined = pd.concat({"ANTM.JK": _one(4), "BREN.JK": _one(0)}, axis=1)

    def fake_downloader(tickers, period, interval, group_by, auto_adjust, progress, threads):
        assert period == "60d" and interval == "1h"
        return combined

    out = fetch_intraday_ohlcv(["ANTM", "BREN"], period_days=60, downloader=fake_downloader)
    assert "ANTM" in out and "BREN" not in out
    assert list(out["ANTM"].columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out["ANTM"]) == 4
