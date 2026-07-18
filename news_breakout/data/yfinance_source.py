from __future__ import annotations

import time

import pandas as pd

_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
_RETRY_DELAYS = [5, 15]  # seconds; index by attempt


def _extract(raw, tickers: list[str]) -> dict:
    out = {}
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


def _fetch_ohlcv(
    tickers, period, interval, downloader, retries=2, sleeper=time.sleep
) -> dict:
    jk = [f"{t}.JK" for t in tickers]
    result = {}
    for attempt in range(retries + 1):
        raw = downloader(
            jk,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        result = _extract(raw, tickers)
        if result:
            return result
        if attempt < retries:
            sleeper(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
    return result


def fetch_daily_ohlcv(
    tickers: list[str],
    history_days: int,
    downloader=None,
    retries=2,
    sleeper=time.sleep,
) -> dict[str, pd.DataFrame]:
    """Download daily OHLCV for `.JK` tickers; return {original_ticker: DataFrame}."""
    if downloader is None:
        import yfinance as yf

        downloader = yf.download
    return _fetch_ohlcv(
        tickers, f"{history_days}d", "1d", downloader, retries, sleeper
    )


def fetch_intraday_ohlcv(
    tickers: list[str],
    period_days: int,
    interval: str = "1h",
    downloader=None,
    retries=2,
    sleeper=time.sleep,
) -> dict[str, pd.DataFrame]:
    """Download intraday OHLCV for `.JK` tickers; return {original_ticker: DataFrame}."""
    if downloader is None:
        import yfinance as yf

        downloader = yf.download
    return _fetch_ohlcv(
        tickers, f"{period_days}d", interval, downloader, retries, sleeper
    )


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
