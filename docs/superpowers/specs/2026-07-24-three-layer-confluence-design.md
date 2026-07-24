# Three-Layer Confluence Engine (News → Breakout → Orderbook) — Design

**Date:** 2026-07-24
**Status:** Design approved via brainstorming (all sections + the two flagged
defaults confirmed by user). Ready for implementation plan.

## Goal

Add a **fourth, additive alert path** that ties the three existing layers into a
single high-conviction funnel for a time-poor long/markup trader:

> **News (catalyst)** → **Breakout (sign of strength)** → **Orderbook (markup-ready timing)**

A positive news catalyst promotes a symbol onto a **confluence watchlist**. The
engine then follows up **on its own**: it re-scans that symbol for a breakout
(any time, even outside market hours) and, once breakout confirms, for an
orderbook Ready-Markup phase (market hours only). Alerts fire **in stages** to a
**new dedicated channel**; the three existing streams are untouched.

## Core principle: additive, zero change to existing functions

The engine is a **consumer** of existing pure functions, never a modifier of
them. `run.py`, `run_news.py`, and the three existing Telegram channels behave
**exactly as today**. The only wiring touch is **one new, additive job
registration** in `serve.py` (existing jobs unchanged).

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Integration shape | **Active, news-triggered staged pipeline** (not a passive coincidence-aggregator). News is the trigger; the engine actively follows up. |
| Output | **New dedicated channel** "Confluence / A+ Setup" (`TELEGRAM_CONFLUENCE_CHAT_ID`). The 3 raw channels stay as-is (noise/research streams). |
| Staged alerts | `news + breakout` → **2/3 heads-up** immediately (even off-hours). `+ orderbook Ready-Markup` → **3/3 confirmed** upgrade (market hours). |
| Breakout timing | Evaluated **any time** (latest daily/intraday bars) — re-checked each cycle while the symbol is on the watchlist. |
| Orderbook timing | **Market hours only** (bid/offer is live-only). Deferred until the next session if the catalyst broke after close. |
| News trigger (long-bias) | Portal item `sentiment == "positif"` **OR** a material `pick_catalyst` disclosure **not** flagged ⚠️ corp-action caution (dilutive right-issues do **not** trigger a long watch). |
| Watchlist TTL | **5 trading days** — gives the week for breakout to catch up to the news. |
| Runtime | Standalone `run_confluence.py` entry point + an additive `confluence_job` in `serve.py` (Option A). Isolated: its failures never touch the other jobs. |

## Architecture

New package `news_breakout/confluence/`:

| Module | Responsibility |
|---|---|
| `trigger.py` | `positive_news_triggers(settings, *, now, portal_items, catalysts) -> list[Trigger]` — long-bias filter: portal `sentiment=="positif"` OR material non-caution disclosure catalyst. Returns `(ticker, source, headline, ts)`. Pure; no fetch. |
| `store.py` | `ConfluenceStore` (sqlite `data_cache/confluence.sqlite`): per-symbol watch row — `ticker, news_ts, catalyst_text, breakout_at, breakout_payload, orderbook_at, stage_alerted∈{none,2of3,3of3}, expires_at`. `upsert_watch / active_watches / mark_breakout / mark_orderbook / mark_stage_alerted / prune_expired`. |
| `engine.py` | `run_confluence_cycle(settings, store, *, now, auth, daily_fetcher, intraday_fetcher, portal_fetcher, disclosure_fetcher, sender, is_open)` — the 4-step orchestration + state machine below. Returns alerts sent this cycle. |
| `formatter.py` | `format_confluence_alert(watch, stage, *, breakout, orderbook, now) -> str` — the 2/3 and 3/3 message bodies (HTML, tappable links, WIB timestamps). |

Root: `run_confluence.py` — standalone entry (mirrors `run_news.py`): load
settings, open stores, run one cycle, print summary.

### Reused unchanged (the whole point)

| Need | Reused function | From |
|---|---|---|
| Breakout eval (pure, no send) | `evaluate_scan(settings, daily, intraday, now, catalysts, tickers)` | `signals/scan_core.py` |
| Orderbook fetch + phase | `fetch_orderbook`, `classify_phase`, `is_market_open` | `orderbook/` |
| Stockbit auth | `StockbitAuth` | `orderbook/auth.py` |
| Price data (VPS-safe) | `make_daily_fetcher`, `make_intraday_fetcher` (Supabase) | `data/supabase_source.py` |
| News + sentiment | `run_portal_feed` sentiment tagging, `pick_catalyst` | `news/` |
| Send | `send_message` | `alerts/telegram.py` |

## State machine (per symbol)

```
[positive news] ──► WATCHING
     │  (every cycle, any hour: evaluate_scan on latest bars)
     ▼
  breakout alert (quality_score ≥ min_quality_score)?
     │ yes → mark_breakout ─► ALERT 2/3 (news+breakout) ─► WAIT_ORDERBOOK
     ▼                                                        │ (market hours + open+window only)
  (stay WATCHING, re-check next cycle)                        ▼
                                             classify_phase == Ready-Markup?
                                                  │ yes → mark_orderbook ─► ALERT 3/3 ─► DONE
  TTL (5 trading days) elapsed in ANY state ──► EXPIRED (drop from watchlist, silent)
```

`stage_alerted` is the dedup: 2/3 sends once, 3/3 sends once. No new signal
logic — the engine only *sequences* signals the existing layers already produce.

## Per-cycle flow (`run_confluence_cycle`)

1. **Ingest triggers.** Fetch fresh portal news + disclosures (reuse existing
   fetchers), run `positive_news_triggers(...)`, `upsert_watch` each new symbol
   with `expires_at = now + 5 trading days` (reuse `market_calendar` for the
   trading-day math). Re-triggering an active watch refreshes its catalyst, not
   its stage.
2. **Prune** expired watches (`prune_expired`).
3. **Breakout pass** (any hour). For symbols still at `stage_alerted==none`:
   fetch daily+intraday for just those tickers, `evaluate_scan(... tickers=[t],
   catalysts={t: catalyst})`. If an alert clears `min_quality_score` →
   `mark_breakout(payload)` and **send 2/3**, `mark_stage_alerted("2of3")`.
4. **Orderbook pass** (market hours only). If `not is_open()` or before
   `open + orderbook_window_after_open_minutes` → skip step. For symbols at
   `stage_alerted=="2of3"`: `fetch_orderbook → classify_phase`; if Ready-Markup →
   `mark_orderbook` and **send 3/3**, `mark_stage_alerted("3of3")`. Throttle with
   the existing `orderbook_request_delay_seconds`.
5. Return the list of `(ticker, stage)` sent.

Every step is wrapped so a per-symbol failure (network/token/parse) skips only
that symbol and is logged — matching the repo's `# noqa: BLE001` degrade pattern.
The whole cycle is isolated from the other scheduler jobs.

## Alert format

**2/3 heads-up** (news + breakout aligned; orderbook pending):

```
🔸 CONFLUENCE 2/3 — BBRI
📰 NEWS ✅ · 📈 BREAKOUT ✅ · 📊 ORDERBOOK ⏳ (menunggu jam bursa / ready markup)

📰 08:12  Kontrak baru senilai Rp2,1T   (Aksi Korporasi · sentimen +)
📈 Donchian-20 break · RVOL 3.2× · Wyckoff SOS · Elliott wave-3
   Entry 4.850 · Stop 4.720 · Target 5.100
```

**3/3 confirmed** (orderbook Ready-Markup fired during market hours):

```
⭐ CONFLUENCE 3/3 — BBRI   (upgrade dari 2/3)
📰 NEWS ✅ · 📈 BREAKOUT ✅ · 📊 ORDERBOOK ✅ READY MARKUP
📊 10:32  bid/offer 300k/295k (0.98) · vol ✅ · +32m after open
```

Content is assembled from the stored breakout payload + the live orderbook
result — no new computation. Because the alert already carries all three layers'
context, it stands alone (a key reason the dedicated channel loses no context).

## Runtime & scheduling

- **Standalone** `run_confluence.py` for manual/CI/test runs (like `run_news.py`).
- **Unattended:** an additive `confluence_job` in `serve.py`, registered with the
  existing scheduler, cadence = `scan_interval_minutes` (30m). Off-hours it does
  steps 1–3 (news + breakout); in-hours it adds step 4 (orderbook). Registering a
  new job leaves the existing `scan_job`/`news_job`/weekend/daily jobs unchanged.
- Price data via the Supabase fetchers (Yahoo is IP-blocked from the VPS).

## Config

New `confluence:` block in `config/config.yaml` (defaults so an absent block =
disabled), plus one env for the channel id:

```yaml
confluence:
  enabled: false
  ttl_trading_days: 5
  require_orderbook: true          # true → 3/3 target; false would make 2/3 terminal
  orderbook_require_volume: true   # reuse rule-2 early-volume gate for the OB stage
  # breakout/orderbook thresholds are reused from the existing signal config
```

- `TELEGRAM_CONFLUENCE_CHAT_ID` — env (secret-adjacent, like
  `TELEGRAM_ORDERBOOK_CHAT_ID`); no silent fallback (unset + enabled → warn+skip,
  so confluence never leaks into another channel).
- New `Settings` fields mirror the `orderbook_*` loading pattern in `config.py`.

## Dedup

The `stage_alerted` column in `ConfluenceStore` is the source of truth — at most
one 2/3 and one 3/3 per watch. No reliance on `DedupStore`; the watch row *is*
the per-symbol state, and TTL/prune bounds table growth.

## What stays unchanged (guarantee)

`run.py`, `run_news.py`, all three existing channels, and every module under
`signals/`, `news/`, `orderbook/` receive **zero edits**. New surface = the
`confluence/` package, `run_confluence.py`, one additive `serve.py` job, new
config keys, and a new sqlite file.

## Testing (no live network)

Follows the repo's TDD pattern; all with injected fetchers/sender/stores:

- `trigger.positive_news_triggers` — positive portal item triggers; negative/
  neutral does not; material non-caution disclosure triggers; ⚠️ caution
  (dilutive) disclosure does **not**; de-dupe same ticker from two sources.
- `store.ConfluenceStore` — upsert/refresh, stage transitions, `active_watches`
  filtering by stage, TTL prune, per-ticker isolation, `:memory:` DB.
- `engine.run_confluence_cycle` — the full state machine: news→2/3 (off-hours ok),
  2/3→3/3 (market hours), 2/3 does **not** re-send, orderbook step skipped when
  market closed / before window, TTL expiry drops silently, per-symbol failure
  isolation, `require_orderbook=false` makes 2/3 terminal.
- `formatter` — 2/3 vs 3/3 bodies contain the right layer marks and payload fields.

## Deploy to VPS (runbook)

Standard project flow (VPS runs `main`; `config/config.yaml` is the git-ignored
live copy — never re-`cp` from example or `dry_run` resets to true):

1. Push branch → merge to `main`.
2. On VPS (short, spaced SSH — fail2ban): `git fetch && git merge --ff-only origin/main`.
3. Append the `confluence:` block with `enabled: true` to the VPS
   `config/config.yaml` (absent = disabled).
4. **User** creates the new Telegram channel, gets its chat id, adds
   `TELEGRAM_CONFLUENCE_CHAT_ID=...` to the VPS `.env` (assistant never writes VPS
   secrets). Reuses the existing `STOCKBIT_*` token for the orderbook stage.
5. `sudo -n systemctl restart news-breakout.service`.
6. Verify: `journalctl -u news-breakout --since "-2min"` shows `confluence_job`
   registered; `PYTHONPATH=. .venv/bin/python run_confluence.py` (dry-run) prints
   a clean cycle.

## Out of scope (YAGNI)

Short/markdown-side confluence, per-symbol position sizing, backtesting the
funnel's win-rate (the dedicated channel's clean history enables this *later*),
multi-catalyst weighting, and any change to the three existing layers' own
signal logic or channels.

## Open items to confirm at spec review

1. **Breakout-pass definition** — default: `evaluate_scan` returns an alert with
   `quality_score ≥ min_quality_score` (same floor `scan_once` uses). Alt: a
   softer "near-breakout" gate — not chosen; would add new logic.
2. **`require_orderbook`** default `true` (3/3 is the real target). Flip to
   `false` only if you later want news+breakout to be a terminal alert on its own.
3. **Off-hours breakout cadence** — runs every 30m like in-hours. If off-hours
   30m polling is noisier than wanted on the VPS, we can widen it to the news
   off-hours cadence (`poll_interval_offhours_minutes`).
