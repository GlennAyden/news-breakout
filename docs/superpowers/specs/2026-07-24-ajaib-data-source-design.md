# Ajaib as the IDX price data source — design

Date: 2026-07-24
Status: Design (approved in brainstorming; pending spec review)

## Problem

The breakout scanner's price backbone is yfinance (fetched on GitHub Actions,
stored in Supabase, read by the VPS). yfinance has two weaknesses that surfaced
during the 2026-07 signal/data review:

- ~15-minute delay and inconsistent IDX small-cap coverage.
- Small-cap volume is unreliable, which feeds the thin-name false positives seen
  in the daily-shift digest (e.g. WMUU/YELO breakouts that were one-bandar pumps).

A browser inspection of the user's own logged-in Ajaib Trade session (2026-07-24)
found a usable IDX-native data API (see `reference-ajaib-data-api` memory). Gate-1
(data completeness) passed: `stock/detail/{TICKER}/candlestick/?resolution=&countback=`
returns full OHLCV **with volume**. Gate-2 (auth durability) is promising but
unproven: a dedicated `/api/v7/refresh/` endpoint works (HTTP 200), but the refresh
token's unattended lifetime is not yet tested.

## Goal

Replace yfinance with Ajaib as the price backbone **without** touching the VPS
scan/read path, gated by evidence (accuracy + auth durability) before any flip,
with yfinance retained as an automatic fallback.

## Non-goals

- No change to signal logic, scoring, or the VPS reader (`supabase_source.py`).
- Bandarmology gate (`broker/top-brokers`), IHSG-regime filter (`COMPOSITE`), and
  the exchange-calendar swap (`trading-day/non-holiday`) are separate follow-ups,
  NOT part of this migration. This spec is the OHLCV swap only.
- No order/portfolio API use. Read-only market data only.

## Approach: phased, not big-bang

Chosen because the auth durability is unproven and this is a private, undocumented
API that can change without notice.

- **Phase 1 (parallel validation):** the Ajaib fetcher writes to a *separate*
  Supabase table alongside the untouched yfinance path. The VPS scan keeps reading
  the yfinance table. We accumulate data to run two gates.
- **Phase 2 (flip):** once both gates pass, the fetcher writes Ajaib → the
  production table with per-ticker yfinance fallback. The VPS reader is unchanged.

Rejected alternatives: full replacement (a broken Ajaib/token blanks the whole scan)
and Ajaib-only with no fallback (too fragile for a private API).

## Architecture

The migration lives **entirely in the fetcher**. The VPS reader
(`supabase_source.py`) keeps reading the `price_bars` table as-is. Only *who fills
that table* changes, which makes the Phase 1→2 flip nearly risk-free on the
production side.

### Components

| Component | Status | Role |
|---|---|---|
| `news_breakout/data/ajaib_auth.py` | new | Manage the Ajaib session token: read the refresh token, call `/api/v7/refresh/`, cache token + expiry, write back a rotated refresh token. Mirrors the existing `orderbook/auth.py` pattern. |
| `news_breakout/data/ajaib_source.py` | new | Fetch `candlestick/?resolution=&countback=` per ticker → a yfinance-shaped OHLCV DataFrame; throttle; degrade to `None` per ticker. Provides `make_daily_fetcher`/`make_intraday_fetcher` closures matching the `supabase_source.py` fetcher signature. |
| `scripts/fetch_to_supabase.py` | modified | Add an Ajaib fetch path. Phase 1: write to `price_bars_ajaib`. Phase 2: write to `price_bars` with per-ticker yfinance fallback. |
| `.github/workflows/price-fetch.yml` | modified | Add Ajaib secret(s); same job/cron. |
| `supabase/schema.sql` | modified | `price_bars_ajaib` (Phase 1 comparison) + `ajaib_token` (single-row store for the current refresh token). |
| `supabase_source.py` (reader) | unchanged | Reads `price_bars` as today. |

### Auth handling (the durability crux)

The fetcher runs on GitHub Actions, which cannot easily write back to a GitHub
secret. So the refresh token is stored in Supabase (`ajaib_token`, one row):

1. Fetcher reads the current refresh token from `ajaib_token`.
2. `POST https://ht2.ajaib.co.id/api/v7/refresh/` → session token (Bearer) and,
   if Ajaib rotates it, a new refresh token.
3. If a new refresh token is returned, upsert it back to `ajaib_token`.
4. Use the session token as `Authorization: Bearer` for candlestick calls; on a
   401 mid-fetch, refresh once and retry once.

The user seeds the initial refresh token once. This handles token rotation and
stays unattended. Real secrets (refresh token, Supabase key) are supplied by the
user via env/secret stores — the assistant never handles their values.

### Data flow (Phase 1)

Per GitHub Actions run (existing schedule):

- yfinance keeps filling `price_bars` (production untouched).
- Ajaib fills `price_bars_ajaib`: `resolution=1D`, `countback` sized to need
  (≈800 once to seed the backtest, then ≈100 for the daily refresh), for
  watchlist ∪ candidates (141) + the broad daily list (~900). Per-ticker throttle
  ≈0.4–0.7 s (900 × 0.4 s ≈ 6 min, fine for once/day).
- VPS scan keeps reading `price_bars` (yfinance) — zero live behavior change.

Intraday (1H/4H): confirm in Phase 1 whether a native `60M` resolution exists;
otherwise fetch `15M` and resample via the existing `data/resample.py`. The daily
tier uses `1D`.

### Data flow (Phase 2, after gates pass)

`fetch_to_supabase` writes Ajaib → `price_bars` with per-ticker yfinance fallback;
`price_bars_ajaib` is retired. The VPS reader is unchanged.

## Validation gates (go/no-go for the flip)

- **Accuracy gate:** compare `price_bars` vs `price_bars_ajaib` — close match %,
  volume match, coverage (how many of the ~900 daily names Ajaib serves, especially
  thin ones), then re-run the signal-edge backtest on Ajaib daily data — does the
  edge hold or improve with accurate small-cap volume? This is a scratch analysis
  script (not a unit test), run on accumulated real data.
- **Auth durability gate:** run the Ajaib GH Actions fetch on schedule for ~1 week;
  confirm `/api/v7/refresh/` keeps working unattended (rotation persisted), zero
  manual intervention. This also tests whether Ajaib geo-blocks/flags the GitHub
  (non-Indonesia) IP. If it fails here, move the fetch to the VPS or a residential
  machine (re-decide).

## Error handling

Principle: the scan is never blinded by a single failure.

- `ajaib_auth`: refresh non-200 → raise; 401 mid-fetch → refresh once, retry once.
  Phase 2: a whole-run auth failure → the fetcher falls back to yfinance for that
  run. Token write-back is a single-row upsert; if it fails, log loudly (stale
  refresh token risks the next run).
- `ajaib_source`: per-ticker try/except → `None`; the Phase 2 caller fills that
  ticker from yfinance. One bad ticker never aborts the run.
- The existing staleness net (warns when Supabase price data is stale) is unchanged
  and protects both sources.

## Testing (TDD)

All seams injected; no live network (matches `supabase_source`/`orderbook` tests).

- `test_ajaib_auth`: refresh response shape, token cache + expiry skew, rotation
  write-back invoked, 401 → refresh → retry, empty/missing token raises.
- `test_ajaib_source`: candlestick JSON → OHLCV DataFrame (yfinance-shaped,
  `from_time`-ascending index), empty/malformed → `None`, throttle sleeper called,
  correct `resolution`/`countback` params.
- `test_fetch_to_supabase` (Ajaib path): writes to the correct table (Phase 1
  `price_bars_ajaib`), per-ticker yfinance fallback (Phase 2), whole-run degrade on
  auth failure.

## Risks & open questions

- **GitHub IP geo-block/flag:** Ajaib may restrict to Indonesia IPs or tie tokens to
  a device/IP. Directly tested by the auth durability gate; fallback plan is VPS or
  residential fetch.
- **Refresh-token rotation behavior:** whether `/api/v7/refresh/` returns a new
  refresh token each call is confirmed during the durability gate; the design
  already persists a rotated token to `ajaib_token`.
- **Daily history depth:** `countback` supports arbitrary counts and `1D` resolution
  is standard, but the max daily history returned is confirmed during the accuracy
  gate (need ~3y for the backtest and ≥55 bars for the long-channel score).
- **ToS / account standing:** private/undocumented API, automated use is against
  Ajaib's ToS, and it's the user's personal brokerage account. Mitigations: read-only
  market data, batch (not HFT), never touch order/portfolio endpoints, fetch from a
  clean IP (GitHub Actions pattern).

## References

- `reference-ajaib-data-api` (memory) — endpoint map.
- `project-news-breakout` (memory) — pipeline history (yfinance → Supabase → VPS).
