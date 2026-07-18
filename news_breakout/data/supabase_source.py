from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger("news_breakout")

WIB = ZoneInfo("Asia/Jakarta")
_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _default_http_get(url: str, headers: dict, params: dict) -> list:
    import httpx

    resp = httpx.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _rows_to_frames(rows: list) -> dict:
    by_ticker: dict = {}
    for r in rows:
        by_ticker.setdefault(r["ticker"], []).append(r)
    out: dict = {}
    for ticker, recs in by_ticker.items():
        idx = pd.to_datetime([r["ts"] for r in recs], utc=True).tz_convert(WIB)
        df = pd.DataFrame(
            {
                "Open": [r["open"] for r in recs],
                "High": [r["high"] for r in recs],
                "Low": [r["low"] for r in recs],
                "Close": [r["close"] for r in recs],
                "Volume": [r["volume"] for r in recs],
            },
            index=idx,
        ).sort_index()
        out[ticker] = df[_COLUMNS]
    return out


def _query(settings, interval: str, tickers: list, http_get, since) -> list:
    if not settings.supabase_url or not settings.supabase_key:
        logger.warning("supabase creds missing; returning no %s bars", interval)
        return []
    if http_get is None:
        http_get = _default_http_get
    params = {
        "interval": f"eq.{interval}",
        "ticker": "in.(" + ",".join(tickers) + ")",
        "order": "ts.asc",
        "select": "ticker,ts,open,high,low,close,volume",
    }
    if since is not None:
        params["ts"] = f"gte.{since.astimezone(WIB).isoformat()}"
    headers = {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
    }
    url = f"{settings.supabase_url}/rest/v1/price_bars"
    try:
        return http_get(url, headers, params) or []
    except Exception as exc:  # noqa: BLE001 — resilience layer: degrade to empty on any failure
        logger.warning("supabase %s query failed: %s", interval, exc)
        return []


def load_daily_bars(settings, tickers, *, http_get=None, since=None) -> dict:
    return _rows_to_frames(_query(settings, "1d", tickers, http_get, since))


def load_intraday_bars(settings, tickers, *, http_get=None, since=None) -> dict:
    return _rows_to_frames(_query(settings, "60m", tickers, http_get, since))


def make_daily_fetcher(settings, *, http_get=None):
    def fetch(tickers, history_days):
        since = datetime.now(WIB) - timedelta(days=history_days)
        return load_daily_bars(settings, tickers, http_get=http_get, since=since)
    return fetch


def make_intraday_fetcher(settings, *, http_get=None):
    def fetch(tickers, period_days, interval="1h"):
        since = datetime.now(WIB) - timedelta(days=period_days)
        return load_intraday_bars(settings, tickers, http_get=http_get, since=since)
    return fetch
