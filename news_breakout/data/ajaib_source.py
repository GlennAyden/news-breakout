from __future__ import annotations

import logging
import time

import pandas as pd

logger = logging.getLogger("news_breakout")

BASE_URL = "https://ht2.ajaib.co.id/api/v1/stock/detail"
_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# Ajaib's data API sits behind a Cloudflare-style WAF that 403s plain httpx, and
# its data endpoints authenticate with `Authorization: jwt <access_token>` (NOT
# Bearer). Both confirmed live 2026-07-24. The access token is short-lived
# (~1h) and cannot be refreshed unattended, so this is an ON-DEMAND puller: a
# caller supplies a freshly-exported access token. See
# docs/superpowers/specs/2026-07-24-ajaib-data-source-design.md.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_ORIGIN = {"Origin": "https://trade.ajaib.co.id", "Referer": "https://trade.ajaib.co.id/"}


def _default_get(url: str, headers: dict, params: dict) -> tuple[int, dict]:
    # curl_cffi impersonates a real browser's TLS/JA3 fingerprint to pass the WAF
    # (plain httpx gets a 403 challenge page). Same dependency the news fetcher uses.
    from curl_cffi import requests as cffi

    resp = cffi.get(url, headers=headers, params=params, impersonate="chrome120", timeout=20)
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 — non-JSON body still carries the status
        body = {}
    return resp.status_code, body


def _auth_headers(access_token: str) -> dict:
    return {"User-Agent": _UA, **_ORIGIN, "Authorization": f"jwt {access_token}"}


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
    # Ajaib can repeat a from_time (a still-forming bar or a glitch); a duplicate
    # (ticker, interval, ts) would break the Supabase upsert's ON CONFLICT.
    df = df[~df.index.duplicated(keep="last")]
    return df[_COLUMNS]


def fetch_candlestick(ticker, access_token: str, *, resolution: str, countback: int,
                      http_get=_default_get) -> pd.DataFrame | None:
    """Fetch one ticker's candlesticks with a fresh access token. Returns None on
    any failure (never raises). A 401 means the token has expired — the caller
    must supply a freshly-exported token (there is no unattended refresh)."""
    url = f"{BASE_URL}/{ticker}/candlestick/"
    params = {"resolution": resolution, "countback": countback}
    try:
        status, body = http_get(url, _auth_headers(access_token), params)
        if status == 401:
            logger.warning("candlestick %s: 401 — access token expired; export a fresh one", ticker)
            return None
        if status != 200:
            logger.warning("candlestick %s: HTTP %s", ticker, status)
            return None
        return parse_candlestick(body)
    except Exception as exc:  # noqa: BLE001 — one bad ticker never aborts the run
        logger.warning("candlestick %s failed: %s", ticker, exc)
        return None


def fetch_many(tickers, access_token: str, *, resolution: str, countback: int,
               http_get=None, sleeper=time.sleep, delay: float = 0.5) -> dict:
    get = http_get if http_get is not None else _default_get
    out: dict = {}
    for t in tickers:
        df = fetch_candlestick(t, access_token, resolution=resolution, countback=countback, http_get=get)
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
