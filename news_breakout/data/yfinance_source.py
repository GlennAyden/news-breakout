from __future__ import annotations

import pandas as pd

_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def fetch_daily_ohlcv(
    tickers: list[str], history_days: int, downloader=None
) -> dict[str, pd.DataFrame]:
    """Download daily OHLCV for `.JK` tickers; return {original_ticker: DataFrame}."""
    if downloader is None:
        import yfinance as yf

        downloader = yf.download

    jk = [f"{t}.JK" for t in tickers]
    raw = downloader(
        jk,
        period=f"{history_days}d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        jk_t = f"{t}.JK"
        try:
            sub = raw[jk_t]
        except (KeyError, TypeError):
            continue
        sub = sub[[c for c in _COLUMNS if c in sub.columns]].dropna(how="all")
        if sub.empty:
            continue
        out[t] = sub[_COLUMNS]
    return out


def report_availability(
    data: dict[str, pd.DataFrame], tickers: list[str], min_bars: int
) -> dict[str, str]:
    report: dict[str, str] = {}
    for t in tickers:
        if t not in data:
            report[t] = "missing"
        elif len(data[t]) < min_bars:
            report[t] = "thin"
        else:
            report[t] = "ok"
    return report
