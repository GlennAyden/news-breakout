import pandas as pd

from news_breakout.data.yfinance_source import fetch_daily_ohlcv, report_availability


def _multiindex_frame(per_ticker):
    """Build a yfinance-style multiindex-column frame: columns = (Ticker, Field)."""
    frames = {}
    for jk_ticker, df in per_ticker.items():
        frames[jk_ticker] = df
    return pd.concat(frames, axis=1)


def _one(n, close):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close, "Volume": 100},
        index=idx,
    )


def test_fetch_maps_original_ticker_and_drops_empty():
    combined = _multiindex_frame({"ANTM.JK": _one(3, 100), "BREN.JK": _one(0, 100)})

    def fake_downloader(tickers, period, interval, group_by, auto_adjust, progress, threads):
        return combined

    out = fetch_daily_ohlcv(["ANTM", "BREN"], history_days=10, downloader=fake_downloader)
    assert "ANTM" in out
    assert "BREN" not in out          # empty dropped
    assert list(out["ANTM"].columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out["ANTM"]) == 3


def test_report_availability_classifies():
    data = {"ANTM": _one(30, 100), "BREN": _one(5, 100)}
    report = report_availability(data, ["ANTM", "BREN", "RATU"], min_bars=21)
    assert report["ANTM"] == "ok"
    assert report["BREN"] == "thin"
    assert report["RATU"] == "missing"
