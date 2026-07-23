from __future__ import annotations

import logging
import time

import pandas as pd

logger = logging.getLogger("news_breakout")

BASE_URL = "https://ht2.ajaib.co.id/api/v1/stock/detail"
_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _default_get(url: str, headers: dict, params: dict) -> tuple[int, dict]:
    import httpx

    with httpx.Client() as client:
        resp = client.get(url, headers=headers, params=params, timeout=20)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 — non-JSON body still carries the status
            body = {}
        return resp.status_code, body


def parse_candlestick(body: dict) -> pd.DataFrame:
    """Map the candlestick JSON to an OHLCV DataFrame (UTC index, ascending).

    Confirmed shape (2026-07-24): result.points[] with from_time/to_time (epoch
    ms), open/high/low/close/volume. Raises on a shape mismatch so callers can
    degrade to None rather than emit a bad frame."""
    result = body.get("result") if isinstance(body, dict) else None
    points = result.get("points") if isinstance(result, dict) else None
    if not isinstance(points, list):
        raise ValueError(f"candlestick shape unexpected; keys={list(body)[:8]}")
    if not points:
        return pd.DataFrame(columns=_COLUMNS, index=pd.DatetimeIndex([], tz="UTC"))
    idx = pd.to_datetime([p["from_time"] for p in points], unit="ms", utc=True)
    df = pd.DataFrame(
        {
            "Open": [p["open"] for p in points],
            "High": [p["high"] for p in points],
            "Low": [p["low"] for p in points],
            "Close": [p["close"] for p in points],
            "Volume": [p["volume"] for p in points],
        },
        index=idx,
    ).sort_index()
    return df[_COLUMNS]


def fetch_candlestick(ticker, auth, *, resolution: str, countback: int,
                      http_get=_default_get) -> pd.DataFrame | None:
    """Fetch one ticker's candlesticks. Returns None on any failure (never raises)."""
    url = f"{BASE_URL}/{ticker}/candlestick/"
    params = {"resolution": resolution, "countback": countback}
    try:
        status, body = http_get(url, auth.auth_headers(), params)
        if status == 401:  # session token stale -> refresh once, retry once
            auth.refresh()
            status, body = http_get(url, auth.auth_headers(), params)
        if status != 200:
            logger.warning("candlestick %s: HTTP %s", ticker, status)
            return None
        return parse_candlestick(body)
    except Exception as exc:  # noqa: BLE001 — one bad ticker never aborts the run
        logger.warning("candlestick %s failed: %s", ticker, exc)
        return None


def fetch_many(tickers, auth, *, resolution: str, countback: int,
               http_get=None, sleeper=time.sleep, delay: float = 0.5) -> dict:
    get = http_get if http_get is not None else _default_get
    out: dict = {}
    for t in tickers:
        df = fetch_candlestick(t, auth, resolution=resolution, countback=countback, http_get=get)
        if df is not None and not df.empty:
            out[t] = df
        sleeper(delay)  # throttle every API call (Ajaib may rate-limit)
    return out


def countback_for_days(history_days: int, resolution: str) -> int:
    """Bars to request to cover ~history_days. Daily: history_days is already
    >= trading days in the window. Intraday: ~26 x 15M bars per session."""
    if resolution.upper().endswith("M"):
        try:
            minutes = int(resolution[:-1])
        except ValueError:
            minutes = 15
        per_session = max(1, (6 * 60) // minutes)  # ~6h IDX session
        return history_days * per_session
    return max(history_days, 60)
