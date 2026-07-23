# Ajaib data source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Ajaib-backed IDX OHLCV fetch path that fills a parallel Supabase table (Phase 1), so it can later replace yfinance with per-ticker fallback (Phase 2), without touching the VPS scan/read path.

**Architecture:** Two new fetcher-side modules — `ajaib_auth.py` (session-token lifecycle via `/api/v7/refresh/`, refresh token persisted in Supabase) and `ajaib_source.py` (candlestick OHLCV → yfinance-shaped DataFrames). `scripts/fetch_to_supabase.py` gains an Ajaib source path writing to `price_bars_ajaib`. The VPS reader `supabase_source.py` is untouched.

**Tech Stack:** Python 3.12, pandas, httpx, pytest. Runs on GitHub Actions (clean IP). Supabase PostgREST for storage.

## Global Constraints

- Python 3.12; use `py -3.12` / the repo `.venv` for local runs.
- Tests use injected seams only — NO live network in any test (match `tests/test_supabase_source.py`, `tests/test_orderbook_auth.py`).
- Real secrets (Ajaib refresh token, Supabase key) are supplied by the user via env/Supabase — never hardcoded, never printed.
- Ajaib ticker code is the bare IDX code (e.g. `BBCA`), NO `.JK` suffix.
- Candlestick response shape (confirmed live 2026-07-24): `{"err_code","err_message","result":{"points":[{"from_time","to_time","open","high","low","close","volume"}, …]}}`. Times are epoch milliseconds.
- `/api/v7/refresh/` request/response shape is a SEAM (token values were redacted during inspection) — coded tolerantly and confirmed during the auth-durability spike.
- Run the full suite with `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q` (baseline 402 passing on this branch).

---

### Task 1: Supabase schema — parallel table + token store

**Files:**
- Modify: `supabase/schema.sql`

DDL the user applies once in the Supabase SQL editor. No unit test (manual apply); its correctness is exercised by Task 4's upsert against a real project during the spike.

- [ ] **Step 1: Append the two tables to `supabase/schema.sql`**

```sql
-- Phase-1 parallel table: Ajaib OHLCV lands here for accuracy comparison
-- against price_bars (yfinance). Same shape as price_bars.
create table if not exists price_bars_ajaib (
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
create index if not exists price_bars_ajaib_lookup on price_bars_ajaib (ticker, interval, ts desc);

-- Single-row store for the current Ajaib refresh token, so the GitHub Actions
-- fetcher survives token rotation unattended. id is always 1.
create table if not exists ajaib_token (
  id            int primary key default 1,
  refresh_token text not null,
  updated_at    timestamptz not null default now()
);
```

- [ ] **Step 2: Commit**

```bash
git add supabase/schema.sql
git commit -m "feat(schema): price_bars_ajaib + ajaib_token for the Ajaib data source"
```

---

### Task 2: `ajaib_auth.py` — session-token lifecycle

**Files:**
- Create: `news_breakout/data/ajaib_auth.py`
- Test: `tests/test_ajaib_auth.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `class AjaibAuth(refresh_token, *, token_writer=None, http_post=_default_post, clock=time.time, skew_seconds=60)`
  - `AjaibAuth.get_access_token() -> str`
  - `AjaibAuth.refresh() -> str`
  - `AjaibAuth.auth_headers() -> dict`
  - `_extract_tokens(body: dict, now: float) -> tuple[str, str | None, int]` returning `(access_token, new_refresh_token_or_None, expiry_epoch)`.

`token_writer` is an optional `callable(new_refresh_token: str) -> None` used to persist a rotated refresh token (wired to Supabase in Task 4; a no-op/None in tests that don't assert rotation). SEAM: `REFRESH_URL`, request body, and response shape are the two unknowns, isolated here.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ajaib_auth.py
import pytest
from news_breakout.data.ajaib_auth import AjaibAuth, _extract_tokens


def test_extract_tokens_reads_access_refresh_and_ttl():
    body = {"data": {"access": {"token": "AT", "expires_in": 3600}, "refresh_token": "RT2"}}
    at, rt, exp = _extract_tokens(body, now=1000)
    assert at == "AT" and rt == "RT2" and exp == 1000 + 3600


def test_extract_tokens_tolerates_flat_shape_and_absolute_expiry():
    body = {"access_token": "AT", "expired_time": 5000}
    at, rt, exp = _extract_tokens(body, now=1000)
    assert at == "AT" and rt is None and exp == 5000


def test_extract_tokens_raises_when_no_access_token():
    with pytest.raises(ValueError):
        _extract_tokens({"nope": 1}, now=0)


def test_refresh_posts_and_caches_token():
    calls = []
    def post(url, payload, headers):
        calls.append((url, payload))
        return 200, {"access_token": "AT", "expires_in": 3600}
    auth = AjaibAuth("RT", http_post=post, clock=lambda: 1000)
    assert auth.get_access_token() == "AT"
    # cached: second call does not re-post
    assert auth.get_access_token() == "AT"
    assert len(calls) == 1
    assert auth.auth_headers()["Authorization"] == "Bearer AT"


def test_refresh_persists_rotated_refresh_token():
    saved = []
    def post(url, payload, headers):
        return 200, {"access_token": "AT", "refresh_token": "RT2", "expires_in": 3600}
    auth = AjaibAuth("RT", token_writer=saved.append, http_post=post, clock=lambda: 0)
    auth.refresh()
    assert saved == ["RT2"]


def test_refresh_raises_on_non_200():
    def post(url, payload, headers):
        return 401, {}
    auth = AjaibAuth("RT", http_post=post, clock=lambda: 0)
    with pytest.raises(RuntimeError):
        auth.refresh()


def test_get_access_token_refreshes_after_expiry():
    seq = [{"access_token": "A1", "expires_in": 100}, {"access_token": "A2", "expires_in": 100}]
    t = {"now": 0}
    def post(url, payload, headers):
        return 200, seq.pop(0)
    auth = AjaibAuth("RT", http_post=post, clock=lambda: t["now"], skew_seconds=0)
    assert auth.get_access_token() == "A1"
    t["now"] = 200  # past expiry
    assert auth.get_access_token() == "A2"
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_ajaib_auth.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `news_breakout/data/ajaib_auth.py`**

```python
from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger("news_breakout")

# --- SEAMS: confirm against one live capture during the durability spike ---
# The refresh endpoint + request/response shape are the unknowns (token values
# were redacted during inspection). Isolated here so finalizing is one place.
REFRESH_URL = "https://ht2.ajaib.co.id/api/v7/refresh/"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS_BASE = {"User-Agent": _UA, "Origin": "https://trade.ajaib.co.id",
                 "Referer": "https://trade.ajaib.co.id/"}


def _default_post(url: str, payload: dict, headers: dict) -> tuple[int, dict]:
    with httpx.Client() as client:
        resp = client.post(url, json=payload, headers=headers, timeout=15)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 — non-JSON body still carries the status
            body = {}
        return resp.status_code, body


def _extract_tokens(body: dict, now: float) -> tuple[str, str | None, int]:
    """Pull (access_token, new_refresh_token_or_None, expiry_epoch) from a refresh
    response. Tolerant of nested/flat shapes; raises if no access token is present."""
    data = body.get("data", body) if isinstance(body, dict) else {}
    access = data.get("access", data) if isinstance(data, dict) else {}
    token = (
        (access.get("token") if isinstance(access, dict) else None)
        or data.get("access_token")
        or body.get("access_token")
    )
    if not token:
        raise ValueError(f"refresh response missing access token; keys={list(body)[:8]}")
    new_rt = (
        data.get("refresh_token")
        or body.get("refresh_token")
        or (access.get("refresh_token") if isinstance(access, dict) else None)
    )
    now = int(now)
    abs_exp = (access.get("expired_time") if isinstance(access, dict) else None) or data.get("expired_time")
    ttl = data.get("expires_in") or body.get("expires_in")
    if abs_exp is not None:
        abs_exp = int(abs_exp)
        expiry = abs_exp // 1000 if abs_exp > 10_000_000_000 else abs_exp
    elif ttl is not None:
        expiry = now + int(ttl)
    else:
        expiry = now + 3600  # conservative default
    return token, new_rt, expiry


class AjaibAuth:
    """Manages an Ajaib session token from a stored refresh token.

    Refreshes lazily; persists a rotated refresh token via ``token_writer`` so a
    GitHub Actions run survives token rotation. In-memory only (each Actions run
    is a fresh short-lived process)."""

    def __init__(self, refresh_token: str, *, token_writer=None,
                 http_post=_default_post, clock=time.time, skew_seconds: int = 60):
        self._refresh_token = refresh_token
        self._token_writer = token_writer
        self._post = http_post
        self._clock = clock
        self._skew = skew_seconds
        self._token: str | None = None
        self._expiry: float = 0.0

    def get_access_token(self) -> str:
        if self._token and self._clock() < self._expiry - self._skew:
            return self._token
        return self.refresh()

    def refresh(self) -> str:
        if not self._refresh_token:
            raise RuntimeError("AJAIB_REFRESH_TOKEN is not set")
        status, body = self._post(
            REFRESH_URL, {"refresh_token": self._refresh_token}, dict(_HEADERS_BASE)
        )
        if status != 200:
            raise RuntimeError(f"ajaib token refresh failed: HTTP {status}")
        token, new_rt, expiry = _extract_tokens(body, self._clock())
        self._token, self._expiry = token, float(expiry)
        if new_rt and new_rt != self._refresh_token:
            self._refresh_token = new_rt
            if self._token_writer is not None:
                try:
                    self._token_writer(new_rt)
                except Exception as exc:  # noqa: BLE001 — persist failure must be loud, not fatal here
                    logger.warning("could not persist rotated ajaib refresh token: %s", exc)
        return token

    def auth_headers(self) -> dict:
        return {**_HEADERS_BASE, "Authorization": f"Bearer {self.get_access_token()}"}
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_ajaib_auth.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/data/ajaib_auth.py tests/test_ajaib_auth.py
git commit -m "feat(data): AjaibAuth session-token lifecycle with rotation persistence"
```

---

### Task 3: `ajaib_source.py` — candlestick OHLCV fetch

**Files:**
- Create: `news_breakout/data/ajaib_source.py`
- Test: `tests/test_ajaib_source.py`

**Interfaces:**
- Consumes: `AjaibAuth` from Task 2 (`auth.auth_headers()`, `auth.refresh()`).
- Produces:
  - `parse_candlestick(body: dict) -> pd.DataFrame` (columns `Open,High,Low,Close,Volume`, tz-aware UTC index ascending).
  - `fetch_candlestick(ticker, auth, *, resolution, countback, http_get=_default_get) -> pd.DataFrame | None`
  - `fetch_many(tickers, auth, *, resolution, countback, http_get=None, sleeper=time.sleep, delay=0.5) -> dict[str, pd.DataFrame]`
  - `countback_for_days(history_days: int, resolution: str) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ajaib_source.py
import pandas as pd
from news_breakout.data.ajaib_source import (
    parse_candlestick, fetch_candlestick, fetch_many, countback_for_days,
)


class _Auth:
    def auth_headers(self):
        return {"Authorization": "Bearer AT"}
    def refresh(self):
        return "AT"


_BODY = {"err_code": "EC0000000", "err_message": "APPROVED/OK", "result": {"points": [
    {"from_time": 1782276300000, "to_time": 1782277198992, "open": 6075, "high": 6100,
     "low": 6050, "close": 6090, "volume": 2133300},
    {"from_time": 1782282600000, "to_time": 1782283497813, "open": 6090, "high": 6120,
     "low": 6080, "close": 6110, "volume": 1800000},
]}}


def test_parse_candlestick_builds_ohlcv_utc_ascending():
    df = parse_candlestick(_BODY)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 2
    assert str(df.index.tz) == "UTC"
    assert df.index.is_monotonic_increasing
    assert df["Close"].iloc[0] == 6090 and df["Volume"].iloc[1] == 1800000


def test_parse_candlestick_empty_points_is_empty_frame():
    assert parse_candlestick({"result": {"points": []}}).empty


def test_fetch_candlestick_calls_endpoint_with_params_and_bearer():
    seen = {}
    def http_get(url, headers, params):
        seen["url"] = url; seen["headers"] = headers; seen["params"] = params
        return 200, _BODY
    df = fetch_candlestick("BBCA", _Auth(), resolution="1D", countback=800, http_get=http_get)
    assert df is not None and len(df) == 2
    assert seen["url"].endswith("/stock/detail/BBCA/candlestick/")
    assert seen["params"] == {"resolution": "1D", "countback": 800}
    assert seen["headers"]["Authorization"] == "Bearer AT"


def test_fetch_candlestick_retries_once_on_401():
    calls = {"n": 0}
    def http_get(url, headers, params):
        calls["n"] += 1
        return (401, {}) if calls["n"] == 1 else (200, _BODY)
    df = fetch_candlestick("BBCA", _Auth(), resolution="1D", countback=10, http_get=http_get)
    assert df is not None and calls["n"] == 2


def test_fetch_candlestick_returns_none_on_error_status():
    def http_get(url, headers, params):
        return 500, {}
    assert fetch_candlestick("BBCA", _Auth(), resolution="1D", countback=10, http_get=http_get) is None


def test_fetch_candlestick_returns_none_on_bad_shape():
    def http_get(url, headers, params):
        return 200, {"unexpected": True}
    assert fetch_candlestick("BBCA", _Auth(), resolution="1D", countback=10, http_get=http_get) is None


def test_fetch_many_skips_empty_and_throttles():
    slept = []
    def http_get(url, headers, params):
        return (200, _BODY) if "BBCA" in url else (200, {"result": {"points": []}})
    out = fetch_many(["BBCA", "EMPTY"], _Auth(), resolution="1D", countback=10,
                     http_get=http_get, sleeper=slept.append, delay=0.3)
    assert set(out) == {"BBCA"}
    assert slept == [0.3, 0.3]  # throttled once per ticker


def test_countback_for_days_covers_trading_days_with_buffer():
    assert countback_for_days(90, "1D") >= 90
    assert countback_for_days(5, "15M") > 90  # intraday needs many bars per day
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_ajaib_source.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `news_breakout/data/ajaib_source.py`**

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_ajaib_source.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/data/ajaib_source.py tests/test_ajaib_source.py
git commit -m "feat(data): Ajaib candlestick OHLCV fetcher"
```

---

### Task 4: `fetch_to_supabase.py` — Ajaib source path (Phase 1)

**Files:**
- Modify: `scripts/fetch_to_supabase.py`
- Test: `tests/test_fetch_to_supabase.py`

**Interfaces:**
- Consumes: `AjaibAuth` (Task 2), `fetch_many`/`countback_for_days` (Task 3), existing `to_rows`/`upsert`/`load_config`/`load_daily_universe`.
- Produces:
  - `upsert(rows, url, key, *, poster=None, table="price_bars")` — add a `table` kwarg (default keeps current callers working).
  - `read_ajaib_refresh_token(url, key, *, http_get=None) -> str`
  - `write_ajaib_refresh_token(url, key, token, *, poster=None) -> None`
  - `fetch_all_ajaib(tickers, history_days, auth, *, resolution="1D", fetch=fetch_many) -> list` (rows via `to_rows`).
  - `main()` gains `--source {yahoo,ajaib}` (default `yahoo`); `ajaib` writes to `price_bars_ajaib`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_fetch_to_supabase.py`)

```python
def test_upsert_targets_custom_table():
    sent = []
    def poster(url, headers, json):
        sent.append(url); return 201
    fts.upsert([{"ticker": "X", "interval": "1d", "ts": "t", "open": 1, "high": 1,
                 "low": 1, "close": 1, "volume": 1}],
               "https://p.supabase.co", "svc", poster=poster, table="price_bars_ajaib")
    assert sent[0] == "https://p.supabase.co/rest/v1/price_bars_ajaib"


def test_fetch_all_ajaib_builds_rows_from_fetch_many():
    idx = pd.to_datetime([1782276300000], unit="ms", utc=True)
    frame = pd.DataFrame({"Open": [1.0], "High": [2.0], "Low": [0.5],
                          "Close": [1.5], "Volume": [100]}, index=idx)
    def fake_fetch(tickers, auth, *, resolution, countback, **kw):
        return {t: frame for t in tickers}
    rows = fts.fetch_all_ajaib(["BBCA", "ANTM"], 90, auth=object(), fetch=fake_fetch)
    assert {r["ticker"] for r in rows} == {"BBCA", "ANTM"}
    assert all(r["interval"] == "1d" for r in rows)
    assert rows[0]["ts"].endswith("+00:00")


def test_read_ajaib_refresh_token_returns_stored_value():
    def http_get(url, headers, params):
        assert url.endswith("/rest/v1/ajaib_token")
        return [{"refresh_token": "RT"}]
    assert fts.read_ajaib_refresh_token("https://p.supabase.co", "svc", http_get=http_get) == "RT"


def test_write_ajaib_refresh_token_upserts_single_row():
    sent = []
    def poster(url, headers, json):
        sent.append((url, json)); return 201
    fts.write_ajaib_refresh_token("https://p.supabase.co", "svc", "RT2", poster=poster)
    assert sent[0][0].endswith("/rest/v1/ajaib_token")
    assert sent[0][1] == [{"id": 1, "refresh_token": "RT2"}]
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_fetch_to_supabase.py -q`
Expected: FAIL (`table` kwarg / new functions missing).

- [ ] **Step 3: Implement the changes in `scripts/fetch_to_supabase.py`**

Change `upsert` to accept a `table` kwarg (replace the existing `def upsert` and its `endpoint` line):

```python
def upsert(rows: list, url: str, key: str, *, poster=None, table: str = "price_bars") -> bool:
    """Upsert rows in chunks; return True iff every chunk returned 2xx."""
    if poster is None:
        import httpx

        def poster(u, headers, json):
            return httpx.post(u, headers=headers, json=json, timeout=60).status_code
    endpoint = f"{url}/rest/v1/{table}"
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
```

Add the Ajaib helpers and fetch (place after `upsert`):

```python
def read_ajaib_refresh_token(url: str, key: str, *, http_get=None) -> str:
    if http_get is None:
        import httpx

        def http_get(u, headers, params):
            return httpx.get(u, headers=headers, params=params, timeout=30).json()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    params = {"select": "refresh_token", "id": "eq.1"}
    data = http_get(f"{url}/rest/v1/ajaib_token", headers, params) or []
    if not data:
        raise RuntimeError("ajaib_token row is empty — seed the refresh token first")
    return data[0]["refresh_token"]


def write_ajaib_refresh_token(url: str, key: str, token: str, *, poster=None) -> None:
    if poster is None:
        import httpx

        def poster(u, headers, json):
            return httpx.post(u, headers=headers, json=json, timeout=30).status_code
    headers = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates",
    }
    status = poster(f"{url}/rest/v1/ajaib_token", headers, [{"id": 1, "refresh_token": token}])
    if status not in (200, 201, 204):
        print(f"WARNING: ajaib_token write returned HTTP {status}", file=sys.stderr)


def fetch_all_ajaib(tickers: list, history_days: int, auth, *,
                    resolution: str = "1D", fetch=None) -> list:
    from news_breakout.data.ajaib_source import countback_for_days, fetch_many

    fetch = fetch or fetch_many
    store_iv = "1d" if resolution.upper() == "1D" else "60m"
    countback = countback_for_days(history_days, resolution)
    frames = fetch(tickers, auth, resolution=resolution, countback=countback)
    rows: list = []
    for t, df in frames.items():
        rows.extend(to_rows(df[_COLUMNS], t, store_iv))
    return rows
```

Wire `--source ajaib` into `main()` (replace the body from the `url =`/`key =` lines down to the `print(f"[{args.mode}] ...` line):

```python
    ap.add_argument("--source", choices=["yahoo", "ajaib"], default="yahoo")
    args = ap.parse_args()

    url = _normalize_supabase_url(os.environ["SUPABASE_URL"])
    key = os.environ["SUPABASE_KEY"].strip()
    watchlist, history_days, intraday_days, universe_candidates, ds = load_config()

    if args.mode == "daily":
        tickers = load_daily_universe(ds.get("universe_file", "config/idx_all.txt"))
        hist = ds.get("history_days", 90)
    else:
        tickers = list(dict.fromkeys(watchlist + universe_candidates))
        hist = history_days

    if args.source == "ajaib":
        from news_breakout.data.ajaib_auth import AjaibAuth

        rt = read_ajaib_refresh_token(url, key)
        auth = AjaibAuth(rt, token_writer=lambda t: write_ajaib_refresh_token(url, key, t))
        rows = fetch_all_ajaib(tickers, hist, auth, resolution="1D")
        table = "price_bars_ajaib"
    else:
        import yfinance as yf

        if args.mode == "daily":
            rows = fetch_all(tickers, hist, intraday_days, yf.download, mode="daily")
        else:
            rows = fetch_all(tickers, history_days, intraday_days, yf.download)
        table = "price_bars"

    print(f"[{args.mode}/{args.source}] fetched {len(rows)} bars for {len(tickers)} tickers")
    if not rows:
        print("ERROR: 0 bars fetched — aborting upsert", file=sys.stderr)
        sys.exit(1)
    if not upsert(rows, url, key, table=table):
        print("ERROR: one or more upsert chunks failed — see warnings above", file=sys.stderr)
        sys.exit(1)
    print("upsert complete")
```

Move `import yfinance as yf` OUT of the top of `main()` (it now imports lazily only on the yahoo path — delete the existing `import yfinance as yf` line near the top of `main`). Keep `import argparse` at the top of `main`.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_fetch_to_supabase.py -q`
Expected: PASS (existing + 4 new).

- [ ] **Step 5: Run the full suite**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all, no regressions).

- [ ] **Step 6: Commit**

```bash
git add scripts/fetch_to_supabase.py tests/test_fetch_to_supabase.py
git commit -m "feat(fetch): --source ajaib path writing to price_bars_ajaib"
```

---

### Task 5: Phase-1 workflow job + seed docs

**Files:**
- Modify: `.github/workflows/price-fetch.yml`
- Modify: `docs/superpowers/specs/2026-07-24-ajaib-data-source-design.md` (append a short "Operator runbook" section)

No unit test (CI config). Correctness is confirmed by a manual `workflow_dispatch` run during the durability spike.

- [ ] **Step 1: Add a parallel Ajaib job to `.github/workflows/price-fetch.yml`**

Duplicate the existing price-fetch job as `price-fetch-ajaib` that runs `python scripts/fetch_to_supabase.py --source ajaib --mode daily`, on the same triggers, using the same `SUPABASE_URL`/`SUPABASE_KEY` secrets (the Ajaib refresh token lives in Supabase `ajaib_token`, not a GH secret). Keep `timeout-minutes` and `concurrency` mirrored from the existing job. (Read the current file first and match its exact `runs-on`, Python setup, and `pip install` steps; add `requirements.txt` deps only — no ML/torch.)

- [ ] **Step 2: Append the operator runbook to the design doc**

```markdown
## Operator runbook (Phase 1)

1. Apply `supabase/schema.sql` in the Supabase SQL editor (creates
   `price_bars_ajaib` + `ajaib_token`).
2. Seed the refresh token once: in the SQL editor,
   `insert into ajaib_token (id, refresh_token) values (1, '<token>')
   on conflict (id) do update set refresh_token = excluded.refresh_token;`
   (obtain the token from the logged-in Ajaib web session; the assistant never
   handles its value).
3. Trigger `price-fetch-ajaib` via `workflow_dispatch`; confirm it upserts to
   `price_bars_ajaib` and that `ajaib_token.updated_at` advances if the token
   rotates.
4. Durability gate: let the scheduled job run ~1 week unattended; confirm zero
   manual token intervention and that the GitHub (non-Indonesia) IP is not
   geo-blocked. Accuracy gate: run the comparison script (next milestone) over
   `price_bars` vs `price_bars_ajaib`.
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/price-fetch.yml docs/superpowers/specs/2026-07-24-ajaib-data-source-design.md
git commit -m "ci(fetch): parallel Ajaib price-fetch job + Phase-1 operator runbook"
```

---

## Self-Review

**Spec coverage:**
- Fetcher-only change, reader untouched → Tasks 2–4 (no reader change). ✓
- Auth via Supabase-stored refresh token with rotation → Task 2 (`token_writer`) + Task 4 (`read/write_ajaib_refresh_token`, wired in `main`). ✓
- `price_bars_ajaib` + `ajaib_token` tables → Task 1. ✓
- Phase-1 parallel (yfinance untouched, Ajaib to separate table) → Task 4 `--source ajaib`/`table`, Task 5 parallel job. ✓
- Candlestick OHLCV parse (confirmed shape) → Task 3. ✓
- Per-ticker degrade + 401 retry + throttle → Task 3 (`fetch_candlestick`/`fetch_many`). ✓
- Intraday resolution note (15M→resample or native 60M) → `countback_for_days` handles both; resolution is a param, defaulting `1D` for Phase 1 daily. Intraday wiring is deferred to Phase 2 (out of this plan's Phase-1 scope) — noted here so it isn't mistaken for a gap.
- Validation gates (accuracy + durability) → Task 5 runbook; the accuracy comparison script is the next milestone after Phase-1 data accumulates (intentionally not built here — it needs real accumulated data).

**Placeholder scan:** none — every code step is complete; the only SEAMs (refresh URL/shape) are explicitly flagged and coded tolerantly, matching the existing `orderbook/auth.py` precedent.

**Type consistency:** `auth.auth_headers()`/`auth.refresh()` used in Task 3 match Task 2's public methods. `fetch_many(tickers, auth, *, resolution, countback, http_get, sleeper, delay)` signature matches Task 4's `fetch_all_ajaib` call. `upsert(..., table=)` and `to_rows(df, ticker, interval)` match the existing script. `parse_candlestick` returns the same `_COLUMNS` order the reader expects. ✓

**Phase-2 (flip) is intentionally out of scope** — it is a one-line target-table change plus per-ticker fallback, gated on Phase-1 evidence, and gets its own short plan once the gates pass.
