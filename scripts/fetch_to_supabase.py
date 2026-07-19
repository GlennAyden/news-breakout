#!/usr/bin/env python3
"""Fetch IDX OHLCV from Yahoo and upsert into Supabase `price_bars`.

Runs on GitHub Actions (runner IPs are served by Yahoo, unlike the VPS
datacenter IP). Reads the committed watchlist from config/config.example.yaml.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import yaml

_CONFIG = "config/config.example.yaml"
_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
_CHUNK = 500


def _normalize_supabase_url(raw: str) -> str:
    """Tolerate a bare project ref or a scheme-less host in SUPABASE_URL.

    Mirrors news_breakout.config._normalize_supabase_url (kept standalone so
    this script needs no package import when run by GitHub Actions).
    """
    u = (raw or "").strip().rstrip("/")
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    host = u.split("://", 1)[-1]
    if "." not in host:  # bare project ref -> full supabase host
        u = f"https://{host}.supabase.co"
    return u


def load_config(path: str = _CONFIG):
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    data = raw.get("data", {})
    universe_candidates = raw.get("universe", {}).get("candidates", [])
    return raw["watchlist"], data["history_days"], data["intraday_period_days"], universe_candidates


def _f(v):
    return None if pd.isna(v) else float(v)


def to_rows(df: pd.DataFrame, ticker: str, interval: str) -> list:
    idx = df.index
    idx = idx.tz_localize("Asia/Jakarta") if idx.tz is None else idx
    idx = idx.tz_convert("UTC")
    rows = []
    for ts, (_, r) in zip(idx, df.iterrows()):
        if pd.isna(r["Close"]):
            continue
        vol = r["Volume"]
        rows.append({
            "ticker": ticker, "interval": interval, "ts": ts.isoformat(),
            "open": _f(r["Open"]), "high": _f(r["High"]), "low": _f(r["Low"]),
            "close": _f(r["Close"]), "volume": 0 if pd.isna(vol) else int(vol),
        })
    return rows


def fetch_all(watchlist: list, history_days: int, intraday_days: int, downloader) -> list:
    plan = [("1d", f"{history_days}d", "1d"), ("60m", f"{intraday_days}d", "60m")]
    jk = [f"{t}.JK" for t in watchlist]
    all_rows: list = []
    for store_iv, period, yf_iv in plan:
        raw = downloader(
            jk, period=period, interval=yf_iv, group_by="ticker",
            auto_adjust=False, progress=False, threads=True,
        )
        for t in watchlist:
            try:
                sub = raw[f"{t}.JK"]
            except (KeyError, TypeError):
                continue
            sub = sub[[c for c in _COLUMNS if c in sub.columns]].dropna(how="all")
            if sub.empty:
                continue
            # yfinance's still-forming last intraday bar can repeat a
            # timestamp; a duplicate (ticker, interval, ts) in the upsert
            # batch makes PostgREST's ON CONFLICT DO UPDATE raise "cannot
            # affect row a second time". Keep the latest observation.
            sub = sub[~sub.index.duplicated(keep="last")]
            all_rows.extend(to_rows(sub[_COLUMNS], t, store_iv))
    return all_rows


def upsert(rows: list, url: str, key: str, *, poster=None) -> bool:
    """Upsert rows in chunks; return True iff every chunk returned 2xx."""
    if poster is None:
        import httpx

        def poster(u, headers, json):
            return httpx.post(u, headers=headers, json=json, timeout=60).status_code
    endpoint = f"{url}/rest/v1/price_bars"
    headers = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates",
    }
    ok = True
    for i in range(0, len(rows), _CHUNK):
        status = poster(endpoint, headers, rows[i:i + _CHUNK])
        if status not in (200, 201, 204):
            ok = False
            print(f"WARNING: upsert chunk {i}-{i + _CHUNK} returned HTTP {status}", file=sys.stderr)
    return ok


def main() -> None:
    import yfinance as yf

    url = _normalize_supabase_url(os.environ["SUPABASE_URL"])
    key = os.environ["SUPABASE_KEY"].strip()
    watchlist, history_days, intraday_days, universe_candidates = load_config()
    tickers = list(dict.fromkeys(watchlist + universe_candidates))
    rows = fetch_all(tickers, history_days, intraday_days, yf.download)
    print(f"fetched {len(rows)} bars for {len(tickers)} tickers")
    if not rows:
        print("ERROR: 0 bars fetched — aborting upsert (likely a Yahoo outage)", file=sys.stderr)
        sys.exit(1)
    if not upsert(rows, url, key):
        print("ERROR: one or more upsert chunks failed — see warnings above", file=sys.stderr)
        sys.exit(1)
    print("upsert complete")


if __name__ == "__main__":
    main()
