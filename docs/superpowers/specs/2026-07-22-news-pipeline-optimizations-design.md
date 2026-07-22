# News Pipeline Optimizations — Design Spec

- **Date:** 2026-07-22
- **Status:** Approved (design) — pending spec review
- **Owner:** news-breakout
- **Scope:** 13 improvements to the news subsystem (disclosure feed, portal feed, booster, Telegram delivery, dedup hygiene). Sentiment model unchanged by explicit decision.

## 1. Problem & Goal

The news pipeline works but leaves recall, latency, and reliability on the table:

1. The scan booster only sees the latest 50 disclosures for a 48-hour catalyst window — catalysts silently fall off the end.
2. An IDX/Cloudflare outage silences the news channel with only a log line as evidence.
3. The same story syndicated across portals is sent multiple times (URL-exact dedup only).
4. Company-name matching covers ~30 hand-curated names out of 900+ listed issuers.
5. A flat 60-minute poll delays intraday disclosures for a breakout trader.
6. Assorted smaller gaps: duplicate IDX fetches per cycle, sequential article fetches, blind Telegram retries on 429, no proxy support for blocked portals, RSS-2.0-only parsing, substring keyword false positives, keyword-gated watchlist disclosures, unbounded dedup table growth.

**Goal:** close all of the above without infrastructure changes, keeping every new behavior config-defaulted (old configs stay valid), degradable (failures never stop the feed), and testable via injected fakes (no network in tests).

## 2. Key Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Shared in-memory `DisclosureCache`** feeds both `news_job` and the scan booster; no SQLite persistence. | The APScheduler process is single, long-running; in-memory TTL is enough and far simpler. Standalone `run.py`/`run_news.py` keep today's direct-fetch behavior. |
| D2 | **One canonical fetch at `booster_page_size` (default 200)** serves both consumers. | Fixes the booster's 50-row blind spot and halves IDX hits in one move. The feed path is insensitive to page size (keyword filter + dedup). |
| D3 | **Stale-while-error:** a failed fetch returns the last good result and increments a failure counter. | The booster and feed degrade to slightly-old data instead of nothing; the counter powers the outage alert. |
| D4 | **Outage alert reuses the price-staleness pattern** (once/day dedup key in the store, sent to the news channel). | Proven pattern already in `run.py`; no new alert framework. |
| D5 | **Market-hours-aware polling via one interval job + internal gating**, not two cron jobs. | Interval at the fast cadence (15 min); outside market hours the job self-skips to an hourly effective cadence. No scheduler edge cases. |
| D6 | **Near-dup = same WIB day + token-set Jaccard ≥ threshold (default 0.6)** against sent titles persisted per day. | Cross-portal headlines are never byte-identical; exact normalized keys have zero recall. Jaccard on normalized tokens is cheap and deterministic. |
| D7 | **`name_map` file merged under inline config; generation is an offline script.** | Runtime stays network-free and deterministic; the generator (IDX company profiles) runs manually, with legal-word stripping and a min-length guard. |
| D8 | **Keyword match = left word boundary + optional `-nya` enclitic + right boundary.** | Kills `kontrak`→`kontraktor` false positives while keeping legitimate `dividennya`-style inflections. |
| D9 | **Sentiment model stays local** (`w11wo/indonesian-roberta-base-sentiment-classifier`). | User decision 2026-07-22: no API cost/credentials for now. |
| D10 | **Watchlist disclosures bypass the keyword gate** (config-switchable, default on). | Official news about a held stock is worth seeing regardless of title wording. |

## 3. Design by Area

### 3.1 `news/disclosure_cache.py` (NEW)

```python
class DisclosureCache:
    def __init__(self, page_size: int, ttl_minutes: int, *, fetcher=fetch_disclosures): ...
    def fetch(self, page_size_ignored: int, *, now, proxy: str = "", retries: int | None = None) -> list[Disclosure]: ...
    @property
    def consecutive_failures(self) -> int: ...
```

- `fetch()` is signature-compatible with the existing `fetcher`/`disclosure_fetcher` injection points in `run_news_feed` and `run.run_scan`; the caller-supplied page size is ignored in favor of the canonical `page_size` (documented). A caller-supplied `retries` is forwarded to the underlying fetcher when a real fetch happens (`None` → the fetcher's default), so the scan path keeps its fast `retries=0` behavior on cache misses.
- Within `ttl_minutes` of the last successful fetch, returns the cached list without hitting IDX.
- On underlying fetch failure (empty result from `fetch_disclosures`): returns the last good list (any age), increments `consecutive_failures`, logs. On success: caches and resets the counter to 0.
- An **empty-but-successful** fetch cannot be distinguished from failure today (`fetch_disclosures` returns `[]` for both). `idx_source` gains `fetch_disclosures_ex(...) -> tuple[list[Disclosure], bool]` (ok flag = parse succeeded); `fetch_disclosures` delegates to it. The cache consumes `_ex`.
- `serve.py` constructs one cache and passes `cache.fetch` into both `news_job` (as `run_news_feed(..., fetcher=...)`) and the scan job (as `run.run_scan(..., disclosure_fetcher=...)` — parameter already exists, [run.py:61](../../run.py)).

### 3.2 Outage alert (in `news/feed.py`)

- `run_news_feed` gains an optional `failure_streak: int = 0` input (serve passes `cache.consecutive_failures`) plus `outage_threshold` and breakout-style sender wiring.
- When `failure_streak >= news_outage_max_failures` (config, default 4): send `"⚠️ Feed keterbukaan IDX gagal N kali beruntun — Cloudflare/proxy bermasalah?"` to the **news** chat, guarded by dedup key `news-outage-YYYY-MM-DD` (`store.news_already_sent`/`news_mark_sent`), exactly like the price-staleness warning in `run.py`.

### 3.3 Market-hours-aware polling (`scheduling/scheduler.py`, `serve.py`)

- Scheduler interval for the news job becomes `poll_interval_market_minutes` (default 15).
- Inside `news_job`: if `is_market_open(now, ...)` → always run. Else → run only when at least `poll_interval_offhours_minutes` have elapsed since the last completed news run (elapsed-time gating, **not** wall-clock minute checks — APScheduler interval ticks are not clock-aligned). Off-hours cadence defaults to the legacy `news_poll_interval_minutes`, keeping old configs meaningful.
- Gating lives in a pure helper `should_poll_news(now, last_run, *, market_open: bool, offhours_minutes: int) -> bool` (True when `market_open`, or when `last_run` is None, or when `now - last_run >= offhours_minutes`); `serve.py`'s job closure tracks `last_run`.

### 3.4 Cross-portal near-dup (`news/portal_dedup.py` NEW + `alerts/dedup.py`)

```python
def normalize_title(title: str) -> list[str]      # lowercase, strip punct, drop tokens len<3 and stopwords
def is_duplicate(tokens, seen_token_sets, threshold) -> bool   # max Jaccard >= threshold
```

- `DedupStore` gains table `sent_news_titles(date_str TEXT, ticker TEXT, title_norm TEXT)` with `add_title(date_str, ticker, title_norm)` and `titles_for_day(date_str, ticker) -> list[str]` (title_norm = space-joined sorted tokens; parsed back to sets on read).
- **Comparison is scoped per ticker** (empty-ticker corp-action items form their own group): otherwise near-identical headline templates about different issuers ("Laba ANTM naik 20%" vs "Laba TINS naik 20%") would false-positive at Jaccard 0.6.
- In `run_portal_feed`, before sending each item: compute tokens; compare against (a) same-ticker titles already sent today from the store, (b) same-ticker titles sent earlier in this run. If duplicate → `news_mark_sent(url)` **without** sending (so it never resurfaces), log at info.
- `portal.dup_title_threshold` (default 0.6; `0` disables the stage entirely).
- Stopword list: small built-in Indonesian function-word list (`yang`, `dan`, `di`, `ke`, `dari`, `untuk`, `pada`, `dengan`, `ini`, `itu`, …) — constant in `portal_dedup.py`, not config.

### 3.5 Emiten matching (`news/portal.py`, `config.py`, `scripts/build_name_map.py` NEW)

- **File-based name_map:** `portal.name_map_file` (default `config/name_map.yaml`, optional — missing file is fine). Loaded at `load_settings` time; inline `portal.name_map` entries override file entries on key collision.
- **Word-boundary name match:** `match_ticker` name pass becomes `re.search(rf"\b{re.escape(name)}\b", low)` instead of substring.
- **Generator script:** `scripts/build_name_map.py` fetches IDX company profiles (same curl_cffi + Cloudflare warm-up + optional proxy treatment as `idx_source`), normalizes names (strip `PT`, `Tbk`, `(Persero)`, punctuation; lowercase), skips names shorter than 4 chars, writes YAML sorted by name. Pure parsing/normalizing functions are unit-tested; the network entry point is not.

### 3.6 Keyword matching (`news/curated.py`, `news/portal.py`)

- New shared helper `keyword_match(text, keywords) -> bool` using `\b<kw>(?:nya)?\b` per keyword (case-insensitive, `re.escape`d, multi-word keywords supported).
- `is_price_sensitive` and `has_corp_action` both delegate to it.

### 3.7 Watchlist pass-through (`news/feed.py`)

- `run_news_feed` curation becomes: keep if `is_price_sensitive(d, keywords)` **or** (`news.watchlist_passthrough` and `d.ticker in watchlist_set`). Default `true`.

### 3.8 Parallel article extraction (`news/feed.py`)

- Replace the sequential extractor loop with `ThreadPoolExecutor(max_workers=portal.fetch_workers)` (default 4) via `executor.map`-style ordered results; per-item exceptions degrade to `""` exactly as today. `fetch_workers: 1` must behave identically to the current sequential path.

### 3.9 Portal proxy support (`news/portal.py`, config)

- `_default_http_get(url, proxy="")` gains proxy plumbing (same curl_cffi `proxies` dict as idx_source).
- Source entries accept optional `proxy:`; fallback chain: per-source `proxy` → `portal.proxy` (global, default `""`) → direct.
- `config.example.yaml`: restore Kontan RSS + Bisnis/Investor entries **commented out**, annotated "aktifkan bila ada proxy residensial (403 dari IP datacenter)".

### 3.10 Atom feed support (`news/portal.py`)

- `parse_rss` additionally iterates Atom `{http://www.w3.org/2005/Atom}entry`: `title`, `link[rel=alternate or first]/@href`, `summary` or `content`, `published` or `updated` (ISO-8601 parsing alongside RFC-2822).

### 3.11 Telegram hardening (`alerts/telegram.py`, `news/feed.py`)

- `send_message`: on HTTP 429, read `parameters.retry_after` from the JSON body, sleep `min(retry_after, 30)` seconds, and retry (counts toward the existing retry budget; malformed body → fall back to the standard delay table).
- Both send loops in `feed.py` sleep `~1.05 s` between consecutive **successful** sends (injectable `sleeper` for tests; no sleep after the last item).

### 3.12 Dedup hygiene (`alerts/dedup.py`)

- Migration on `DedupStore.__init__`: `ALTER TABLE sent_news ADD COLUMN sent_at TEXT` when the column is missing (existing rows keep `NULL`); `news_mark_sent` stamps `sent_at` with the ISO date.
- `prune_news(older_than_days)` deletes `sent_news` rows with non-NULL `sent_at` older than the cutoff and `sent_news_titles` rows older than the cutoff; called once per `news_job` with `news.dedup_retention_days` (default 90). NULL-`sent_at` legacy rows are never pruned.

## 4. Config Additions (all defaulted; old configs stay valid)

```yaml
news:
  booster_page_size: 200            # canonical IDX fetch size (cache + booster)
  fetch_cache_ttl_minutes: 10       # shared disclosure cache TTL
  news_outage_max_failures: 4       # consecutive failures before a once/day Telegram warning
  poll_interval_market_minutes: 15  # news poll cadence during market hours
  poll_interval_offhours_minutes: 60  # cadence outside market hours (fallback: news_poll_interval_minutes)
  watchlist_passthrough: true       # watchlist tickers bypass the keyword gate
  dedup_retention_days: 90          # prune sent_news / sent_news_titles rows older than this

portal:
  dup_title_threshold: 0.6          # near-dup Jaccard threshold (0 disables)
  fetch_workers: 4                  # parallel article-extraction workers
  proxy: ""                         # global portal proxy (per-source `proxy:` overrides)
  name_map_file: config/name_map.yaml  # optional; inline name_map overrides file entries
```

## 5. Testing

Every area follows the existing house style — pure functions + injected fakes, no network:

- `test_disclosure_cache.py`: TTL reuse, stale-while-error, failure counter reset, page-size canonicalization, `fetch_disclosures_ex` ok-flag plumbing.
- `test_news_feed.py` (extend): outage warning threshold + once/day dedup, watchlist pass-through, inter-send sleeper, parallel extractor ordering & degradation (workers=1 equivalence).
- `test_scheduler.py` (extend) + new `should_poll_news` tests: market-hours vs off-hours gating, legacy-config fallback.
- `test_portal_dedup.py`: normalization, Jaccard duplicate/non-duplicate, threshold 0 disable, same-day store round-trip.
- `test_portal.py` (extend): word-boundary name matching, Atom parsing, per-source/global proxy plumbing.
- `test_curated.py` (extend): boundary + enclitic keyword cases (`kontraktor` rejected, `dividennya` accepted, multi-word keywords).
- `test_build_name_map.py`: profile-record parsing, legal-word stripping, min-length skip, YAML output shape.
- `test_telegram.py` (extend): 429 retry_after honored, cap at 30 s, malformed-body fallback.
- `test_dedup.py` (extend): `sent_at` migration on legacy DB file, pruning cutoffs, NULL rows retained, titles table round-trip.
- `test_config.py` (extend): all new keys with defaults + legacy fallback for poll intervals.

## 6. Out of Scope

- Sentiment model change (D9 — user decision to keep local model).
- Running `build_name_map.py` against the live IDX API (network; run manually on demand).
- Backfilling `sent_at` for existing `sent_news` rows.
- Any change to the breakout/Elliott scan logic beyond consuming the shared cache.

## 7. Rollout

Single deploy to `hermes-vps` (git pull + restart scheduler). No `.env` changes required. Optional post-deploy step: run `python scripts/build_name_map.py` once on a machine that can reach IDX (or via the existing `idx_proxy`) and commit `config/name_map.yaml`.
