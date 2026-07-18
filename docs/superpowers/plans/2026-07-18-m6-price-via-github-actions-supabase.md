# M6 — Price via GitHub Actions → Supabase → VPS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed IDX price data (OHLCV) to the always-on VPS breakout scanner without touching Yahoo from the VPS — by fetching prices on GitHub Actions (whose runner IPs Yahoo serves), storing them in Supabase, and having the VPS read Supabase instead of yfinance.

**Architecture:** A scheduled GitHub Actions workflow runs `yfinance` during IDX market hours (Azure runner IP = not blocked) and upserts 1d + 60m bars into a Supabase `price_bars` table via the PostgREST REST API. On the VPS, a new `supabase_source` reader returns per-ticker DataFrames in the exact same shape the old yfinance fetchers produced, so the breakout logic (Donchian/RVOL/Wyckoff/multi-TF) is unchanged — only the data source swaps. 4H bars keep being resampled from 60m on the VPS via the existing `data/resample.py`.

**Tech Stack:** Python 3.12, yfinance, pandas, httpx (PostgREST calls — no `supabase-py` dep), PyYAML, GitHub Actions (cron), Supabase (Postgres + PostgREST), pytest.

## Global Constraints

- Python 3.12 only. On Windows dev, the venv is created with `py -3.12` (default `python` is 3.13). Run scripts with `PYTHONPATH=. .venv/Scripts/python.exe ...`; the VPS uses `.venv/bin/python`.
- **No new runtime dependencies.** Reuse what the project already pins: `yfinance`, `pandas`, `httpx`, `PyYAML`. Do NOT add `supabase-py`.
- **Secrets are never committed and never typed by the agent.** `SUPABASE_URL` / `SUPABASE_KEY` live only in GitHub repo secrets and the VPS `.env`; the user sets both. Use the Supabase **service_role** key (server-side only, both fetcher and reader).
- DataFrame contract (must match the old yfinance output exactly): one entry per ticker keyed by the bare ticker (no `.JK`), value = `pd.DataFrame` with columns `["Open","High","Low","Close","Volume"]` and a chronological `DatetimeIndex`. Daily index = one row per trading day; intraday index = 60-minute bars.
- Store timestamps as tz-aware UTC (`timestamptz`); the reader converts to `Asia/Jakarta` so 60m→4H resampling and the daily date string stay session-aligned.
- The breakout logic is FROZEN. Only `serve.py`'s `scan_job` wiring and a new data module change. `run.py`'s defaults stay on yfinance (local dev where Yahoo works); `run.py` is not used on the VPS.
- Keep the VPS process light (<300 MB); the reader must filter to a bounded window (`history_days` / `intraday_period_days`) rather than reading the whole table.
- Tests: `pytest`, all existing 119 tests must keep passing. New tests use injected fakes (no network, no live Supabase).

---

## File Structure

- **Create** `news_breakout/data/supabase_source.py` — VPS-side reader. Queries PostgREST, rebuilds yfinance-shaped DataFrames, exposes drop-in fetcher closures `make_daily_fetcher(settings)` / `make_intraday_fetcher(settings)`.
- **Create** `scripts/fetch_to_supabase.py` — standalone fetcher run by GitHub Actions. Reads watchlist from `config/config.example.yaml`, downloads 1d + 60m via yfinance, upserts to `price_bars`.
- **Create** `.github/workflows/price-fetch.yml` — cron + manual workflow that runs the fetcher.
- **Create** `supabase/schema.sql` — the `price_bars` DDL (reference; user pastes into Supabase SQL editor).
- **Modify** `news_breakout/config.py` — add env-sourced `supabase_url` / `supabase_key` to `Settings` and `load_settings`.
- **Modify** `serve.py:24-29` — `scan_job` injects the Supabase fetchers into `run.run_scan`.
- **Modify** `config/config.example.yaml` — add a short commented note documenting the two required env vars (no secret values).
- **Create** `tests/test_supabase_source.py`, `tests/test_fetch_to_supabase.py` — unit tests with injected fakes.

---

### Task 1: Supabase credentials in config

**Files:**
- Modify: `news_breakout/config.py:10-40` (Settings), `:55-97` (load_settings)
- Modify: `config/config.example.yaml` (doc note only)
- Test: `tests/test_config_supabase.py`

**Interfaces:**
- Produces: `Settings.supabase_url: str` and `Settings.supabase_key: str`, both defaulting to `""`, sourced from env `SUPABASE_URL` / `SUPABASE_KEY` (empty when unset — used by Task 2's reader).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_supabase.py
import os
from news_breakout.config import load_settings


def test_supabase_creds_read_from_env(tmp_path, monkeypatch):
    # minimal valid config + env, reusing the example config
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "svc-key")
    s = load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))
    assert s.supabase_url == "https://proj.supabase.co"
    assert s.supabase_key == "svc-key"


def test_supabase_creds_default_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    s = load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))
    assert s.supabase_url == ""
    assert s.supabase_key == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_config_supabase.py -v`
Expected: FAIL — `Settings` has no field `supabase_url`.

- [ ] **Step 3: Write minimal implementation**

In `news_breakout/config.py`, add two fields to `Settings` (after `portal_name_map`):

```python
    supabase_url: str = ""
    supabase_key: str = ""
```

In `load_settings(...)`, add to the `Settings(...)` constructor call (alongside `idx_proxy=...`):

```python
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_key=os.environ.get("SUPABASE_KEY", ""),
```

In `config/config.example.yaml`, append a documentation note (no secrets):

```yaml

# Price data (M6): the VPS reads OHLCV from Supabase, filled by a GitHub Actions
# fetcher. Set these in the environment / VPS .env (never commit real values):
#   SUPABASE_URL=https://<project>.supabase.co
#   SUPABASE_KEY=<service_role key>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_config_supabase.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: all previously-passing tests + 2 new pass.

- [ ] **Step 6: Commit**

```bash
git add news_breakout/config.py config/config.example.yaml tests/test_config_supabase.py
git commit -m "feat(m6): add Supabase creds (url/key) to Settings from env"
```

---

### Task 2: VPS-side Supabase reader (`supabase_source.py`)

**Files:**
- Create: `news_breakout/data/supabase_source.py`
- Test: `tests/test_supabase_source.py`

**Interfaces:**
- Consumes: `Settings.supabase_url`, `Settings.supabase_key`, `Settings.history_days`, `Settings.intraday_period_days` (Task 1).
- Produces:
  - `load_daily_bars(settings, tickers, *, http_get=None, since=None) -> dict[str, pd.DataFrame]`
  - `load_intraday_bars(settings, tickers, *, http_get=None, since=None) -> dict[str, pd.DataFrame]`
  - `make_daily_fetcher(settings) -> Callable[[list[str], int], dict[str, pd.DataFrame]]` — drop-in for `fetch_daily_ohlcv(tickers, history_days)`.
  - `make_intraday_fetcher(settings) -> Callable[..., dict[str, pd.DataFrame]]` — drop-in for `fetch_intraday_ohlcv(tickers, period_days, interval="1h")`.
  - `http_get` fake signature: `http_get(url: str, headers: dict, params: dict) -> list[dict]` returning PostgREST rows `{"ticker","ts","open","high","low","close","volume"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_supabase_source.py
import pandas as pd
from news_breakout.config import load_settings
from news_breakout.data import supabase_source as ss


def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "svc")
    return load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))


def test_rows_become_yfinance_shaped_frames(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)
    rows = [
        {"ticker": "ANTM", "ts": "2026-07-16T02:00:00+00:00", "open": 1, "high": 3, "low": 1, "close": 2, "volume": 100},
        {"ticker": "ANTM", "ts": "2026-07-17T02:00:00+00:00", "open": 2, "high": 4, "low": 2, "close": 3, "volume": 200},
        {"ticker": "BUMI", "ts": "2026-07-17T02:00:00+00:00", "open": 5, "high": 6, "low": 4, "close": 5, "volume": 50},
    ]
    captured = {}

    def fake_get(url, headers, params):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return rows

    out = ss.load_daily_bars(s, ["ANTM", "BUMI"], http_get=fake_get)

    # correct endpoint + auth + filters
    assert captured["url"] == "https://proj.supabase.co/rest/v1/price_bars"
    assert captured["headers"]["apikey"] == "svc"
    assert captured["headers"]["Authorization"] == "Bearer svc"
    assert captured["params"]["interval"] == "eq.1d"
    assert captured["params"]["ticker"] == "in.(ANTM,BUMI)"

    # shape contract
    assert set(out) == {"ANTM", "BUMI"}
    df = out["ANTM"]
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "Asia/Jakarta"
    assert len(df) == 2
    assert df["Close"].tolist() == [2.0, 3.0]
    # chronological
    assert df.index.is_monotonic_increasing


def test_missing_creds_returns_empty(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)
    object.__setattr__(s, "supabase_url", "")
    called = {"n": 0}

    def fake_get(url, headers, params):
        called["n"] += 1
        return []

    out = ss.load_intraday_bars(s, ["ANTM"], http_get=fake_get)
    assert out == {}
    assert called["n"] == 0  # never hits the network without creds


def test_http_error_degrades_to_empty(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)

    def boom(url, headers, params):
        raise RuntimeError("network down")

    assert ss.load_daily_bars(s, ["ANTM"], http_get=boom) == {}


def test_make_daily_fetcher_has_dropin_signature(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)

    def fake_get(url, headers, params):
        return [{"ticker": "ANTM", "ts": "2026-07-17T02:00:00+00:00",
                 "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]

    fetch = ss.make_daily_fetcher(s, http_get=fake_get)
    out = fetch(["ANTM"], 120)  # same (tickers, history_days) call as run_scan uses
    assert "ANTM" in out and list(out["ANTM"].columns) == ["Open", "High", "Low", "Close", "Volume"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_supabase_source.py -v`
Expected: FAIL — module `news_breakout.data.supabase_source` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# news_breakout/data/supabase_source.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_supabase_source.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/data/supabase_source.py tests/test_supabase_source.py
git commit -m "feat(m6): Supabase price reader with yfinance-shaped output + drop-in fetchers"
```

---

### Task 3: GitHub Actions fetcher script (`scripts/fetch_to_supabase.py`)

**Files:**
- Create: `scripts/fetch_to_supabase.py`
- Test: `tests/test_fetch_to_supabase.py`

**Interfaces:**
- Consumes: watchlist + `data.history_days` + `data.intraday_period_days` from `config/config.example.yaml`.
- Produces:
  - `load_config(path=...) -> tuple[list[str], int, int]` → `(watchlist, history_days, intraday_period_days)`
  - `to_rows(df: pd.DataFrame, ticker: str, interval: str) -> list[dict]` — one dict per non-NaN bar with UTC ISO `ts` and floats.
  - `fetch_all(watchlist, history_days, intraday_days, downloader) -> list[dict]` — 1d + 60m rows.
  - `upsert(rows, url, key, *, poster=None)` — POSTs chunks of ≤500 to `{url}/rest/v1/price_bars` with `Prefer: resolution=merge-duplicates`.
  - `poster` fake signature: `poster(url: str, headers: dict, json: list) -> int` (HTTP status).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch_to_supabase.py
import pandas as pd
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "fetch_to_supabase", Path("scripts/fetch_to_supabase.py")
)
fts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fts)


def _frame(tz):
    idx = pd.to_datetime(["2026-07-17 09:00", "2026-07-17 10:00"])
    if tz:
        idx = idx.tz_localize("Asia/Jakarta")
    return pd.DataFrame(
        {"Open": [1.0, 2.0], "High": [2.0, 3.0], "Low": [1.0, 2.0],
         "Close": [2.0, 3.0], "Volume": [10, 20]}, index=idx)


def test_to_rows_serializes_utc_iso_and_floats():
    rows = fts.to_rows(_frame(tz=True), "ANTM", "60m")
    assert len(rows) == 2
    r = rows[0]
    assert r["ticker"] == "ANTM" and r["interval"] == "60m"
    assert r["ts"].endswith("+00:00")           # tz-aware UTC
    assert r["ts"].startswith("2026-07-17T02")  # 09:00 WIB -> 02:00 UTC
    assert r["close"] == 2.0 and r["volume"] == 10


def test_to_rows_localizes_naive_daily_index():
    rows = fts.to_rows(_frame(tz=False), "ANTM", "1d")
    # naive index is treated as WIB then converted to UTC (no crash, tz-aware out)
    assert rows[0]["ts"].endswith("+00:00")


def test_to_rows_skips_nan_close():
    df = _frame(tz=True)
    df.loc[df.index[1], "Close"] = float("nan")
    rows = fts.to_rows(df, "ANTM", "60m")
    assert len(rows) == 1


def test_fetch_all_covers_both_intervals():
    def fake_downloader(jk, **kw):
        # emulate yfinance group_by="ticker": columns MultiIndex (ticker, field)
        frames = {}
        for sym in jk:
            f = _frame(tz=True)
            f.columns = pd.MultiIndex.from_product([[sym], f.columns])
            frames[sym] = f
        return pd.concat(frames.values(), axis=1)

    rows = fts.fetch_all(["ANTM", "BUMI"], 120, 60, fake_downloader)
    intervals = {r["interval"] for r in rows}
    assert intervals == {"1d", "60m"}
    assert {r["ticker"] for r in rows} == {"ANTM", "BUMI"}


def test_upsert_chunks_and_sets_merge_header():
    sent = []

    def poster(url, headers, json):
        sent.append((url, headers, len(json)))
        return 201

    rows = [{"ticker": "ANTM", "interval": "1d", "ts": "x", "open": 1, "high": 1,
             "low": 1, "close": 1, "volume": 1} for _ in range(1200)]
    fts.upsert(rows, "https://proj.supabase.co", "svc", poster=poster)
    assert sent[0][0] == "https://proj.supabase.co/rest/v1/price_bars"
    assert sent[0][1]["Prefer"] == "resolution=merge-duplicates"
    assert sent[0][1]["Authorization"] == "Bearer svc"
    assert [n for _, _, n in sent] == [500, 500, 200]  # chunked by 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_fetch_to_supabase.py -v`
Expected: FAIL — `scripts/fetch_to_supabase.py` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fetch_to_supabase.py
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


def load_config(path: str = _CONFIG):
    raw = yaml.safe_load(open(path, encoding="utf-8"))
    data = raw.get("data", {})
    return raw["watchlist"], data["history_days"], data["intraday_period_days"]


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
            all_rows.extend(to_rows(sub[_COLUMNS], t, store_iv))
    return all_rows


def upsert(rows: list, url: str, key: str, *, poster=None) -> None:
    if poster is None:
        import httpx

        def poster(u, headers, json):
            return httpx.post(u, headers=headers, json=json, timeout=60).status_code
    endpoint = f"{url}/rest/v1/price_bars"
    headers = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates",
    }
    for i in range(0, len(rows), _CHUNK):
        status = poster(endpoint, headers, rows[i:i + _CHUNK])
        if status not in (200, 201, 204):
            print(f"WARNING: upsert chunk {i}-{i + _CHUNK} returned HTTP {status}", file=sys.stderr)


def main() -> None:
    import yfinance as yf

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    watchlist, history_days, intraday_days = load_config()
    rows = fetch_all(watchlist, history_days, intraday_days, yf.download)
    print(f"fetched {len(rows)} bars for {len(watchlist)} tickers")
    if not rows:
        print("ERROR: 0 bars fetched — aborting upsert (likely a Yahoo outage)", file=sys.stderr)
        sys.exit(1)
    upsert(rows, url, key)
    print("upsert complete")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_fetch_to_supabase.py -v`
Expected: PASS (all 5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_to_supabase.py tests/test_fetch_to_supabase.py
git commit -m "feat(m6): GitHub Actions fetcher — yfinance OHLCV -> Supabase upsert"
```

---

### Task 4: Wire the VPS to Supabase + workflow + schema

**Files:**
- Modify: `serve.py:24-29` (`scan_job`)
- Create: `.github/workflows/price-fetch.yml`
- Create: `supabase/schema.sql`
- Test: `tests/test_serve_wiring.py`

**Interfaces:**
- Consumes: `make_daily_fetcher` / `make_intraday_fetcher` (Task 2), `run.run_scan` injection points `daily_fetcher` / `intraday_fetcher` (existing `run.py:68-72`).
- Produces: `serve.build_scan_job(settings, store, log) -> Callable[[], None]` — extracted so the wiring is unit-testable (the fetchers it injects are the Supabase ones).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_serve_wiring.py
import serve
from news_breakout.config import load_settings


def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "svc")
    return load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))


def test_scan_job_injects_supabase_fetchers(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)
    captured = {}

    # capture what run_scan is called with, and force the scan to actually run
    def fake_run_scan(settings, store, *, now, daily_fetcher, intraday_fetcher, **kw):
        captured["daily"] = daily_fetcher
        captured["intraday"] = intraday_fetcher
        return []

    monkeypatch.setattr(serve.run, "run_scan", fake_run_scan)
    monkeypatch.setattr(serve, "should_scan_now", lambda now, settings: True)

    class _Log:
        def info(self, *a, **k): pass

    job = serve.build_scan_job(s, store=object(), log=_Log())
    job()
    # the injected fetchers are callables with the drop-in (tickers, N) signature
    assert callable(captured["daily"]) and callable(captured["intraday"])
    # and they are the Supabase-backed ones (closures over settings), not yfinance
    assert captured["daily"].__qualname__.startswith("make_daily_fetcher")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_serve_wiring.py -v`
Expected: FAIL — `serve.build_scan_job` does not exist.

- [ ] **Step 3: Write minimal implementation**

In `serve.py`, add the import near the top:

```python
from news_breakout.data.supabase_source import make_daily_fetcher, make_intraday_fetcher
```

Extract the scan job into a module-level factory (replacing the inline `scan_job` closure). Add this function above `main()`:

```python
def build_scan_job(settings, store, log):
    daily_fetcher = make_daily_fetcher(settings)
    intraday_fetcher = make_intraday_fetcher(settings)

    def scan_job() -> None:
        now = datetime.now(WIB)
        if not should_scan_now(now, settings):
            return
        alerted = run.run_scan(
            settings, store, now=now,
            daily_fetcher=daily_fetcher, intraday_fetcher=intraday_fetcher,
        )
        log.info("scan complete; alerted: %s", alerted or "none")

    return scan_job
```

Then in `main()`, replace the inline `def scan_job(): ...` block with:

```python
    scan_job = build_scan_job(settings, store, log)
```

(Leave `weekend_job` and `news_job` unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_serve_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Create the Supabase schema reference file**

```sql
-- supabase/schema.sql — paste into Supabase SQL Editor once.
create table if not exists price_bars (
  ticker   text        not null,
  interval text        not null,   -- '1d' or '60m'
  ts       timestamptz not null,
  open     double precision,
  high     double precision,
  low      double precision,
  close    double precision,
  volume   bigint,
  primary key (ticker, interval, ts)
);
create index if not exists price_bars_lookup on price_bars (ticker, interval, ts desc);
```

- [ ] **Step 6: Create the GitHub Actions workflow**

```yaml
# .github/workflows/price-fetch.yml
name: price-fetch
on:
  schedule:
    - cron: "*/30 2-9 * * 1-5"   # every 30 min, 02:00-09:00 UTC = 09:00-16:00 WIB, Mon-Fri
    - cron: "0 3 * * 6"          # Sat 10:00 WIB — refresh 1d bars for the weekend deep-scan
  workflow_dispatch: {}
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install --quiet yfinance httpx pandas pyyaml
      - name: Fetch prices to Supabase
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: python scripts/fetch_to_supabase.py
```

- [ ] **Step 7: Run the full suite**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass (119 prior + new).

- [ ] **Step 8: Commit**

```bash
git add serve.py supabase/schema.sql .github/workflows/price-fetch.yml tests/test_serve_wiring.py
git commit -m "feat(m6): VPS scan_job reads Supabase; add price-fetch workflow + schema"
```

---

## Deployment Runbook (executed WITH the user — gated on their Supabase keys)

> Not a TDD task. These steps touch the live repo, GitHub secrets, Supabase, and the VPS. The agent never types the secret values — the user sets them.

- [ ] **1. User: create Supabase project**, then SQL Editor → paste `supabase/schema.sql` → Run. Grab `Project URL` + `service_role` key (Settings → API).
- [ ] **2. User: set GitHub repo secrets** (Settings → Secrets and variables → Actions, or `gh secret set SUPABASE_URL` / `gh secret set SUPABASE_KEY` which prompt for the value so it never hits the shell history).
- [ ] **3. User: add the same two lines to the VPS `.env`** via `scp` (as with the Telegram token). Confirm with `grep -c '^SUPABASE_' .env` == 2 on the VPS.
- [ ] **4. Merge M6 to `main`** (fast-forward) and push. Nothing runs until secrets exist.
- [ ] **5. Seed Supabase once:** `gh workflow run price-fetch.yml`, then watch it (`gh run watch`). Verify rows landed: in Supabase, `select interval, count(*) from price_bars group by interval;` should show both `1d` and `60m`.
- [ ] **6. Deploy VPS:** `ssh -i ~/.ssh/glenn.pem ubuntu@43.156.128.91`, `cd ~/news-breakout && git pull --ff-only`, `.venv/bin/python -m pytest -q`, then `sudo systemctl restart news-breakout.service`. Journal should still show `jobs: ['scan','weekend','news']`.
- [ ] **7. Verify read path from the VPS** (one-shot, respects market-hours gate is bypassed for the check):
  `.venv/bin/python -c "from news_breakout.config import load_settings; from news_breakout.data.supabase_source import make_daily_fetcher as m; s=load_settings(); print({k: len(v) for k,v in m(s)(s.watchlist, s.history_days).items()})"`
  Expected: a dict of tickers → bar counts (non-empty).
- [ ] **8. Monday market-hours check:** `journalctl -u news-breakout.service --since "09:00"` — scans should log real `alerted:` results instead of the 0-tickers WARNING. Confirm the GitHub Actions `price-fetch` runs are green in the Actions tab.

---

## Self-Review

**Spec coverage:** GitHub Actions fetch on a served IP (Task 3 + Task 4 workflow) ✅; Supabase store (Task 4 schema) ✅; VPS reads Supabase in yfinance shape (Task 2) ✅; breakout logic unchanged / only wiring swapped (Task 4 `serve.py`) ✅; 1d + 60m with 4H resampled on VPS (reader returns 60m; existing `resample.py` untouched) ✅; secrets user-managed, no new deps (Global Constraints) ✅; bounded query window (Task 2 `since`) ✅; deployment gated on user keys (Runbook) ✅.

**Placeholder scan:** No TBD/TODO; every code step is complete and runnable.

**Type consistency:** `make_daily_fetcher(settings, *, http_get=None)` returns `fetch(tickers, history_days)` matching `run.run_scan`'s `daily_fetcher(settings.watchlist, settings.history_days)` call (`run.py:73`). `make_intraday_fetcher` returns `fetch(tickers, period_days, interval="1h")` matching `intraday_fetcher(settings.watchlist, settings.intraday_period_days)` (`run.py:74`). PostgREST row keys (`ticker/ts/open/high/low/close/volume`) are identical between the fetcher's `to_rows` (Task 3) and the reader's `_rows_to_frames` (Task 2). Store interval labels `"1d"`/`"60m"` agree across fetcher (`fetch_all` plan) and reader (`_query`).
