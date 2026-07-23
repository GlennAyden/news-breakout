# Orderbook Bid/Offer-Phase Alert ("Ready Markup" playbook) — Design

**Date:** 2026-07-23
**Status:** Design approved (Sections 1–2 by user; Section 3 + playbook incorporation decided by author on user's "implement now" instruction).

## Goal

Add a **standalone Telegram alert** that fires when a stock's orderbook enters
the **Ready Markup (RM)** phase — total BID lot ≈ total OFFER lot ("bid/offer
setara") — per the user's Wyckoff-style orderbook playbook. Data comes from
**Stockbit's internal API** using the user's own logged-in session
(refresh-token auth).

## User playbook (source of truth for the signal)

Phases classified from **total BID lot vs total OFFER lot** in the orderbook:

| Phase | Example (bid/offer) | ratio bid/offer | Meaning |
|---|---|---|---|
| **A — Akumulasi** | 300k / 700k | offer-dominant (~0.43) | supply overhead; not ready |
| **RM — Ready Markup** | 300k / 300k | ~balanced (~1.0) | **entry trigger** |
| **BM — Before Markdown** | 500k / 300k | bid-dominant (~1.67) | ⚠️ trap; can revert to A |

**Rules:** (1) universe = stocks in *or* out of the core universe; (2) ~30 min
after market open, today's volume ≥ ½ of the previous day; (3) enter at RM;
(4) beware the BM "trap" that can bounce back to A.

## Decisions (from brainstorming + playbook)

| Question | Decision |
|---|---|
| Data source | Stockbit internal API (`exodus.stockbit.com`) — grey-area (ToS), brittle, free & complete |
| Freshness | Snapshot once per scan cycle (~1–5 min); no streaming |
| **Population** | **Broad universe (in/out) that passes the rule-2 early-volume filter** — computed from OHLCV already loaded (no extra API calls). Supersedes the earlier "breakout candidates" answer. |
| Integration | **Standalone** alert path (own format, own dedup, own/opt chat) |
| Trigger | Phase == **RM** (bid ≈ offer), with prior-phase context (A→RM good, BM→RM caution) |
| Auth | **Refresh-token**: store `refresh_token`, mint & cache `access_token`, refresh on expiry/401 |

## Discovery findings (confirmed live)

- Orderbook: `GET https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{SYMBOL}` → 200. One call = one symbol, full depth.
- Session: `GET .../company-price-feed/market-time/session` → skip when market closed.
- Auth: bearer token required (unauthenticated fetch is CORS/401-rejected).

### Confirmed orderbook JSON shape (live TLKM capture, 2026-07-23)

```json
{ "data": {
    "symbol": "TLKM", "lastprice": 2700,
    "bid":   [ {"price":"2690","que_num":"1","volume":"1200"}, ... ],   // 36 levels
    "offer": [ {"price":"2700","que_num":"94","volume":"3001300"}, ... ] // 74 levels
}}
```

- All values are **strings**. `volume` is in **shares** → `lot = volume / 100`
  (IDX 1 lot = 100 shares). `que_num` = order **frequency**.
- `bid`/`offer` carry the **full depth** (every level, not just the visible 10).
  Summing level lots reproduces Stockbit's total row exactly (verified: TLKM
  bid 248,163 / offer 267,892 lots, freq 5,287 / 4,282 → ratio 0.926 = RM).
- Parser finalized in `stockbit_source.py`; real-shape fixture in `test_orderbook_source.py`.

## Architecture

New package `news_breakout/orderbook/`:

| Module | Responsibility |
|---|---|
| `models.py` | `OrderbookLevel(price, lot, freq)`, `OrderbookSnapshot(symbol, ts, bids[], offers[], total_bid_lot, total_offer_lot, total_bid_freq, total_offer_freq, best_bid, best_offer, last_price)` |
| `volume_filter.py` | `passes_early_volume(daily_df, now, cfg) -> VolumeResult(passed, today_vol, prev_vol, ratio)` — rule-2, OHLCV-only (no API) |
| `phase.py` | `classify_phase(snapshot, cfg) -> PhaseResult(phase∈{A,RM,BM}, bid_lot, offer_lot, ratio)` — RM when `min(bid,offer)/max(bid,offer) >= rm_balance_min_ratio` |
| `state.py` | `PhaseStore` (sqlite `data_cache/orderbook.sqlite`): `get_last_phase / set_phase` per (ticker, date) for A→RM vs BM→RM context |
| `auth.py` | `StockbitAuth`: refresh_token → cached access_token (+expiry, persisted `data_cache/stockbit_token.json`) |
| `stockbit_source.py` | `fetch_orderbook(symbol, auth, http_get)` → `OrderbookSnapshot`; 401 → refresh once → retry once; `_parse_orderbook` (JSON seam) |
| `formatter.py` | `format_orderbook_alert(snapshot, phase_result, prev_phase, volume_result) -> str` |
| `scan.py` | `run_orderbook_scan(settings, daily_data, store, phase_store, *, now, auth, sender, fetcher, is_open)` → alerted list |

### Per-cycle flow (called from `run.py::run_scan`, market hours only)

1. `is_open()` false (session endpoint / clock) → skip entirely.
2. `now` before `open + window_after_open_minutes` → skip (too early for rule-2).
3. For each ticker in `daily_data`: `passes_early_volume(...)` → candidate set (cheap, no API).
4. Cap candidates to `max_symbols_per_scan` (highest volume ratio first; log dropped).
5. For each candidate: `fetch_orderbook` → `classify_phase`; read `prev_phase`; store current phase. If phase == RM and not deduped → send alert (annotate prior phase); sleep `request_delay_seconds`.

### Resilience

Any failure in the orderbook path (network, token, parse) skips only that
ticker and is logged — it never aborts the main breakout scan (matches the
existing `# noqa: BLE001` degrade-to-empty pattern).

## Auth (refresh-token)

- `STOCKBIT_REFRESH_TOKEN` env (secret, `.env`), like the Telegram/Supabase tokens.
- Access token + expiry persisted to `data_cache/stockbit_token.json`.
- Browser-like headers (User-Agent, Referer `https://stockbit.com`).
- On 401 from a data fetch: force `refresh()` once, retry once.

## Dedup, chat, config

- **Dedup:** reuse `sent_alerts` via `already_sent(ticker, "ready_markup", "ORDERBOOK", date_str)` — at most one RM alert per ticker per trading day.
- **Chat:** new env `TELEGRAM_ORDERBOOK_CHAT_ID`; falls back to `telegram_breakout_chat_id` if unset.
- **Config** (`config.yaml` → `orderbook:` block; defaults so absent = disabled):
  ```yaml
  orderbook:
    enabled: false
    max_symbols_per_scan: 15
    request_delay_seconds: 0.7
    window_after_open_minutes: 30      # rule-2 timing gate
    early_volume:
      min_ratio_prev_day: 0.5          # today cumulative vol >= 0.5 * prev day total
    phase:
      rm_balance_min_ratio: 0.85       # RM if min(bid,offer)/max(bid,offer) >= this
  ```

## Alert format (RM)

Symbol, phase (RM), bid vs offer lot + ratio, prior phase (A→RM ✅ / BM→RM ⚠️),
today-vs-prev volume ratio + minutes-after-open, last price, best bid/offer,
timestamp WIB.

## Testing (no live network)

- `volume_filter` — passes/fails around threshold; missing prev day; today-only.
- `phase.classify_phase` — A / RM / BM from the playbook example numbers; boundary at `rm_balance_min_ratio`.
- `state.PhaseStore` — set/get, per-day isolation.
- `stockbit_source._parse_orderbook` — from a saved real-response fixture (finalized after capture).
- `formatter` — RM text contains phase, ratio, prior-phase note.
- `scan.run_orderbook_scan` (injected fetcher/sender/store/is_open): early gate, volume filter, cap+drop-log, RM-only alert, prior-phase annotation, dedup, throttle, per-ticker failure isolation.
- `auth` (mock refresh): cache hit, expiry refresh, 401 retry.

## Status of the seams

1. ✅ **Orderbook JSON field names** — RESOLVED (confirmed live 2026-07-23; parser + real-shape fixture done; verified against Stockbit's own totals).
2. ⏳ **Refresh endpoint** URL/payload + refresh-token reusability (rotation?) — still a best-guess default (`/login/refresh`, `{"refresh_token": …}`) isolated in `auth.py`. Verified on first real refresh. Meanwhile `STOCKBIT_ACCESS_TOKEN` bootstrap lets the data path run now without it.
3. ⏳ **VPS IP block risk** ⚠️ (user-side) — OHLCV fetch already had to move to GitHub Actions because Yahoo blocks the VPS IP. Test `exodus.stockbit.com` from `hermes-vps`; if blocked: relay via GitHub Actions (refresh_token → GH secret) — fallback only.
4. ⏳ **Rule-2 exact semantics** — assumed: today daily-bar cumulative volume vs previous daily-bar total, ratio ≥ 0.5. Isolated in `volume_filter`; swap if a specific 30-min window is meant.

## Verification harness

`scripts/check_orderbook.py`:
- `--demo` — runs classify + formatter with no credentials (proves the signal pipeline).
- `--live SYMBOL` — fetches a real orderbook (needs `STOCKBIT_ACCESS_TOKEN` or `STOCKBIT_REFRESH_TOKEN`), classifies, prints the alert. This is the end-to-end confirmation and surfaces any seam-2 error without exposing token values.

## Verification performed (2026-07-23)

- **Functional (local):** full suite 347 passing; `--live BBCA` → HTTP 200,
  parsed, phase=ACCUMULATION; `--scan BBCA,TLKM,ANTM,BBRI,ASII` (full
  `run_orderbook_scan` orchestration, dry-run) → only TLKM = READY_MARKUP
  (bid 252,428 / offer 265,059, ratio 0.95) alerted. Live data confirmed moving.
- **Stockbit reachability from VPS (seam #3):** ✅ from `ubuntu@43.156.128.91`,
  `curl` to `exodus.stockbit.com` orderbook + session endpoints returned **HTTP 401**
  (0.07 s) — reachable, NOT IP-blocked (unlike Yahoo/IDX-price from this datacenter IP).
  **No GitHub-Actions relay needed** — the VPS can hit Stockbit directly with a token.
- **Wiring:** `serve.py::scan_job` calls `run.run_scan`, which calls
  `_maybe_run_orderbook` — so the feature runs on every scheduled 30-min scan
  once enabled; no `serve.py` change.

## Deploy to VPS (runbook)

Follows the project's standard flow (VPS runs `main`; `config/config.yaml` is the
git-ignored live copy — never re-`cp` from example or `dry_run` resets to true).

1. Push branch, merge to `main` (PR or ff-merge), so `origin/main` has this work.
2. On VPS (short, spaced SSH commands — fail2ban): `cd ~/news-breakout && git fetch && git merge --ff-only origin/main`.
3. Enable in the VPS `config/config.yaml` — append the `orderbook:` block with
   `enabled: true` (absent block = disabled by default). Do NOT re-cp the example.
4. **User** adds to VPS `.env` (assistant never writes VPS secrets):
   `STOCKBIT_REFRESH_TOKEN=...` (for unattended) and/or `STOCKBIT_ACCESS_TOKEN=...`
   (quick start, ~24 h), optional `TELEGRAM_ORDERBOOK_CHAT_ID=...`.
5. `sudo -n systemctl restart news-breakout.service` (passwordless on the box).
6. Verify: `journalctl -u news-breakout --since "-2min"` (scheduler clean) and,
   with a token in place, `PYTHONPATH=. .venv/bin/python scripts/check_orderbook.py --live BBCA` → HTTP 200.

**Caveat before relying on unattended runs:** the refresh endpoint (seam #2) is
still a best-guess. With only `STOCKBIT_ACCESS_TOKEN` the feature works until the
token's `exp` (~24 h) then stops; confirm the refresh flow (set
`STOCKBIT_REFRESH_TOKEN`, watch for a refresh error in the journal) before
depending on 24/7 operation.

## Out of scope (YAGNI)

Websocket/streaming, full-universe *orderbook* scanning (volume filter gates it),
historical orderbook storage, multi-broker sources.
