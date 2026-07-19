from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger("news_breakout")

WIB = ZoneInfo("Asia/Jakarta")
_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _rows_to_frames(rows: list) -> dict[str, pd.DataFrame]:
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


def _query_one(settings, interval: str, ticker: str, http_get, since) -> list[dict]:
    params = {
        "interval": f"eq.{interval}",
        "ticker": f"eq.{ticker}",
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
    return http_get(url, headers, params) or []


def _collect_rows(settings, interval: str, tickers: list, http_get, since) -> list[dict]:
    rows: list[dict] = []
    for ticker in tickers:
        try:
            rows.extend(_query_one(settings, interval, ticker, http_get, since))
        except Exception as exc:  # noqa: BLE001 — resilience layer: degrade to empty on any failure
            logger.warning("supabase %s query failed for %s: %s", interval, ticker, exc)
    return rows


def _query(settings, interval: str, tickers: list, http_get, since) -> list[dict]:
    # Supabase PostgREST caps rows-per-request (default 1000); a single
    # in.(...) request across the whole watchlist can silently truncate to
    # the oldest rows and drop the newest bars. Query per ticker instead —
    # each ticker's row count is far under any cap — and isolate failures
    # so one bad ticker doesn't lose the rest.
    if not settings.supabase_url or not settings.supabase_key:
        logger.warning("supabase creds missing; returning no %s bars", interval)
        return []
    if http_get is not None:  # injected (e.g. tests): use as-is
        return _collect_rows(settings, interval, tickers, http_get, since)
    # Production: reuse ONE keep-alive client across all per-ticker requests
    # (~141 tickers x 2 intervals per scan) instead of a fresh TCP+TLS
    # handshake per ticker.
    import httpx

    with httpx.Client(timeout=30) as client:
        def pooled_get(url, headers, params):
            resp = client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()

        return _collect_rows(settings, interval, tickers, pooled_get, since)


def load_daily_bars(
    settings, tickers, *, http_get=None, since=None
) -> dict[str, pd.DataFrame]:
    try:
        return _rows_to_frames(_query(settings, "1d", tickers, http_get, since))
    except Exception as exc:  # noqa: BLE001 — resilience: malformed rows degrade to empty
        logger.warning("supabase daily bars unusable: %s", exc)
        return {}


def load_intraday_bars(
    settings, tickers, *, http_get=None, since=None
) -> dict[str, pd.DataFrame]:
    try:
        return _rows_to_frames(_query(settings, "60m", tickers, http_get, since))
    except Exception as exc:  # noqa: BLE001 — resilience: malformed rows degrade to empty
        logger.warning("supabase intraday bars unusable: %s", exc)
        return {}


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
