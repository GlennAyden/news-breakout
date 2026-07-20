# Two-Shift Universe — Design Spec

- **Date:** 2026-07-20
- **Status:** Approved (design) — pending spec review
- **Owner:** news-breakout

## 1. Problem & Goal

The breakout scanner covers only ~141 tickers (watchlist + LQ45/IDX80 candidates), scanned intraday every 30 min. IDX has ~960 listed stocks; the current universe misses breakouts forming in the broader (still-tradeable) market. Scanning all ~960 intraday every 30 min is infeasible (yfinance rate limits, intraday noise on illiquid names, alert flooding).

**Goal:** add a second **daily shift** — a broad, liquidity-filtered universe scanned once per day on daily bars only — alongside the existing intraday shift, so coverage expands without noise or data-pipeline strain.

## 2. Key Decisions (from brainstorming)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Two shifts.** Intraday (existing 141, 1D/4H/1H, every 30 min) unchanged. Add a **daily shift** (broad, 1D-only, once/day). | Intraday only meaningful for liquid names; a daily breakout is the meaningful signal for the broader market. Also reduces per-30-min fetch load. |
| D2 | **Broad list = static committed file** `config/idx_all.txt` (~960 IDX tickers), seeded once + refreshed quarterly. | Most reliable; no scraping fragility. IDX adds ~30–40/yr. |
| D3 | **Intraday tier stays explicit** (watchlist + curated candidates = 141). **Daily tier = broad list, auto liquidity-filtered, minus the intraday tier.** | Intraday stable/predictable; daily auto-adapts; no double coverage. |
| D4 | **Liquidity floor for daily = avg daily value ≥ Rp2 B, price ≥ Rp50** → ~300–350 names. | Tradeable for retail; drops truly thin stocks. |
| D5 | **Daily detect (16:30 WIB, after close):** individual alerts (same format as intraday, score + trade plan), ranked by `quality_score`, capped **top 15**, deduped per day. | Detailed detection when the daily bar is final. |
| D6 | **Daily reminder (08:00 WIB, pre-open):** **one digest** message recapping the same shortlist. | Morning watch reminder without re-firing 15 alerts. |
| D7 | Reminder **re-computes** the shortlist (no stored state) — the daily bar is frozen overnight, so the result is identical. | YAGNI; avoids a state file. |

## 3. Architecture & Data Flow

```
INTRADAY shift (unchanged)              DAILY shift (new)
─────────────────────────              ─────────────────
Universe: watchlist ∪ candidates = 141  Universe: config/idx_all.txt (~960)
Fetch (GitHub, VPS-cron every 30 min):  Fetch (GitHub, VPS-cron 16:15 WIB):
  fetch_to_supabase --mode intraday       fetch_to_supabase --mode daily
  → 1d + 60m for the 141                   → 1d only for the ~960
Scan (VPS APScheduler, every 30 min):   Scan (VPS APScheduler):
  run_scan → 1D/4H/1H → individual         • 16:30 WIB detect:
                                             read 1d ← Supabase; liquidity-filter
                                             (≥Rp2B, ≥Rp50) MINUS intraday tier;
                                             evaluate 1D; rank; top 15;
                                             individual alerts (dedup per day)
                                           • 08:00 WIB reminder:
                                             same compute → one digest message
```

Loose coupling via Supabase: the GitHub daily fetch (16:15) lands 1d bars; the VPS daily-detect scan (16:30) reads them. The 15-min gap covers fetch time. If the fetch is late/failed, the scan reads whatever is present and degrades (fewer tickers); the existing staleness alert is the safety net.

## 4. Components & Interfaces

Small units, each testable via dependency injection.

### `news_breakout/signals/scan_core.py` (refactor — extract from run.py)
```python
def evaluate_scan(settings, daily_data, intraday_data, *, now, catalysts, tickers) -> list[TickerAlert]:
    """Evaluate `tickers` over the given frames, return alerts sorted by
       (quality_score, max_rvol) desc. No sending, no dedup. Pure-ish."""
```
- `run.scan_once` is refactored to = `evaluate_scan(...)` + the existing send/dedup loop, and gains an optional `max_alerts: int | None = None` (cap sends to the top N after sort). Intraday passes `None`; daily passes 15. Existing behavior unchanged when `max_alerts=None`.

### `news_breakout/signals/daily_shift.py` (NEW)
```python
def load_daily_universe(path: str) -> list[str]:
    """Read config/idx_all.txt (one ticker per line, '#' comments), de-duped."""

def run_daily_scan(settings, store, *, now, mode,             # mode: "detect" | "reminder"
                   daily_fetcher, sender=send_message,
                   disclosure_fetcher=fetch_disclosures) -> list[str]:
    """Broad daily-only breakout scan.
       1. broad = load_daily_universe(settings.daily_shift_universe_file)
       2. daily = daily_fetcher(broad, settings.daily_shift_history_days)
       3. intraday_set = set(watchlist ∪ universe_candidates)
          daily_tickers = [t for t in resolve_scan_tickers([], broad, daily,
                           settings.daily_shift_min_price, settings.daily_shift_min_daily_value)
                           if t not in intraday_set]
       4. mode 'detect'  → return scan_once(settings, daily, {}, store, now=now, sender=sender,
                             catalysts=catalysts, tickers=daily_tickers,
                             max_alerts=settings.daily_shift_max_alerts)
                             — scan_once does evaluate + rank + cap + per-day dedup + individual send.
          mode 'reminder'→ alerts = evaluate_scan(settings, daily, {}, now=now, catalysts=catalysts,
                             tickers=daily_tickers)[: settings.daily_shift_max_alerts]
                             if alerts and not store.news_already_sent('daily-digest-{date}'):
                                 send format_daily_digest(alerts); mark the key (fires once/day)."""
```

### `news_breakout/alerts/formatter.py` (MODIFY)
```python
def format_daily_digest(alerts: list[TickerAlert], *, now) -> str:
    """One HTML-free message: '🗓️ Watchlist Pagi — EOD Breakout ({date})' + a ranked
       list of the top alerts (ticker · 🏅score · price/level · trend arrow), most-material first."""
```

### `scripts/fetch_to_supabase.py` (MODIFY)
- Add `--mode {intraday,daily}` (default `intraday`).
  - `intraday`: current behavior — `watchlist ∪ candidates`, plan `[1d + 60m]`.
  - `daily`: tickers = `load_daily_universe(config/idx_all.txt)`, plan `[1d only]`, `history_days = daily_shift.history_days`.
- Chunk the yfinance batch (~200 tickers/call) so a ~960 download doesn't fail as one giant request.

### `config/idx_all.txt` (NEW)
- ~960 IDX tickers (bare codes, one per line, `#` comments allowed). Seeded once from the IDX listed-companies list during implementation (count sanity-checked ~950+); refreshed quarterly.

### `.github/workflows/price-fetch.yml` (MODIFY)
- Add a `workflow_dispatch` input `mode` (default `intraday`), passed to `python scripts/fetch_to_supabase.py --mode ${{ inputs.mode }}`.
- Keep the schedule cron as a backup; the reliable trigger is the VPS cron.

### `scripts/trigger_fetch.sh` (MODIFY) + VPS crontab
- Accept a mode arg; include `"inputs": {"mode": "<mode>"}` in the dispatch body.
- New VPS crontab line (CST): `15 17 * * 1-5 …/trigger_fetch.sh daily` (16:15 WIB) — triggers the broad daily fetch. Existing `*/30 10-17 …` stays (intraday).

### `serve.py` + `news_breakout/scheduling/scheduler.py` (MODIFY)
- `build_scheduler` registers two new cron jobs when `daily_shift.enabled`:
  - `daily_detect` — cron 16:30 WIB → `run_daily_scan(mode="detect")`.
  - `daily_reminder` — cron 08:00 WIB Mon–Fri → `run_daily_scan(mode="reminder")`.

### `config.py` + `config/config.example.yaml` (MODIFY)
```yaml
daily_shift:
  enabled: true
  universe_file: config/idx_all.txt
  min_daily_value: 2000000000   # Rp2 B avg daily value floor
  min_price: 50
  max_alerts: 15
  history_days: 90              # enough for SMA50 + Donchian20 + RVOL20
```
Mirrored as `Settings` fields with these defaults.

## 5. Signal

The daily scan calls `evaluate_scan` with `intraday_data={}` and `frames={"1D": df}` per ticker — `evaluate_ticker` already handles daily-only frames and computes `quality_score` from the 1D frame (SMA50 trend, extension, priority). No signal-logic change; the daily shift reuses the exact breakout engine on 1D bars.

## 6. Dedup & Overlap

- Daily detect uses the existing per-(ticker, "aggregated", "MULTI", daily-date) dedup — a daily-tier breakout fires once per day.
- The daily tier **excludes** the 141 intraday tickers, so no ticker is scanned by both shifts; the per-day dedup is a second guard.
- The reminder digest uses a single `daily-digest-{date}` dedup key so it sends once per morning.

## 7. Error Handling / Degradation

| Failure | Behavior |
|---------|----------|
| Broad daily fetch late/failed | Daily scan reads whatever 1d bars exist; liquidity filter drops tickers with no recent bar; scan proceeds on the rest. Staleness alert is the net. |
| A ticker has no/thin data | Dropped by the liquidity filter or skipped in `evaluate_scan`. |
| `idx_all.txt` missing/empty | `load_daily_universe` returns `[]` → daily scan no-ops (logged); intraday unaffected. |
| Telegram send fails | Existing retry; not marked sent → retried next run. |
| `daily_shift.enabled: false` | No daily jobs registered; system behaves exactly as today. |

## 8. Testing

- `evaluate_scan`: returns sorted alerts, no send (extracted logic keeps existing `scan_once` tests green; add a direct test).
- `scan_once` `max_alerts`: caps sends to top N; `None` = unchanged.
- `load_daily_universe`: parses file, strips comments/blanks, de-dupes.
- `run_daily_scan` (inject `daily_fetcher`/`sender`/`disclosure_fetcher`): liquidity filter + intraday exclusion; `detect` sends capped individual alerts + dedups; `reminder` sends exactly one digest and dedups per day; degrades on empty universe/fetch.
- `format_daily_digest`: ranked list, key fields, top-N.
- `fetch_to_supabase --mode daily`: uses the daily universe + 1d-only plan + chunking (inject downloader).
- Scheduler wiring: two new jobs registered only when enabled.
- Full suite stays green.

## 9. Defaults Chosen (user may veto at review)

1. Reminder re-computes the shortlist (no stored state).
2. Daily `history_days = 90`.
3. Daily alerts + morning digest go to the **breakout** channel, clearly labeled.
4. Cap = 15.
5. `idx_all.txt` seeded from the IDX listed list during implementation.

## 10. Out of Scope / Future

- Dynamic (liquidity-ranked) tier promotion between shifts.
- A separate Telegram channel for the daily shift.
- Auto-refreshing `idx_all.txt` (stays a manual quarterly update).
- Intraday-tier expansion (unchanged at 141).
