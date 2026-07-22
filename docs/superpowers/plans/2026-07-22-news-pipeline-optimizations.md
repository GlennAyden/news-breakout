# News Pipeline Optimizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 13 news-pipeline improvements from `docs/superpowers/specs/2026-07-22-news-pipeline-optimizations-design.md` (shared disclosure cache, outage alert, market-hours polling, cross-portal near-dup, name-map scaling, keyword precision, watchlist pass-through, parallel extraction, portal proxy, Atom support, Telegram hardening, dedup hygiene, name-map generator).

**Architecture:** All changes live inside the existing `news_breakout` package following its house style: pure functions + injected fakes (`sender`, `fetcher`, `http_get`, `sleeper`), graceful degradation on every network/model failure, config keys all defaulted so old configs stay valid. A new in-memory `DisclosureCache` is the single IDX chokepoint; `serve.py` wires it into both the news job and the scan booster.

**Tech Stack:** Python 3.11+, pydantic Settings, APScheduler, curl_cffi, sqlite3, pytest.

## Global Constraints

- **No network in tests** — every external call goes through an injected fake.
- **Failures degrade, never propagate** — a fetch/model/send failure must not stop the feed (match existing `# noqa: BLE001` idiom).
- **All new config keys have defaults** — an untouched `config.yaml` must keep working (verbatim keys in spec §4).
- **Timezone:** all timestamps WIB (`Asia/Jakarta`), naive-input tolerant.
- **SQLite schema changes are additive only** — existing `data_cache/dedup.sqlite` on the VPS must open unchanged.
- Run tests from the repo root: `python -m pytest tests/<file> -v` (full suite: `python -m pytest -q`).
- Commit after every green task; message style `feat(news): ...` / `fix(news): ...` matching `git log`.

---

### Task 1: Config — new settings keys, off-hours fallback, name_map file merge, example YAML

**Files:**
- Modify: `news_breakout/config.py`
- Modify: `config/config.example.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces (used by later tasks): `Settings.news_booster_page_size: int = 200`, `Settings.news_fetch_cache_ttl_minutes: int = 10`, `Settings.news_outage_max_failures: int = 4`, `Settings.poll_interval_market_minutes: int = 15`, `Settings.poll_interval_offhours_minutes: int = 60`, `Settings.news_watchlist_passthrough: bool = True`, `Settings.news_dedup_retention_days: int = 90`, `Settings.portal_dup_title_threshold: float = 0.6`, `Settings.portal_fetch_workers: int = 4`, `Settings.portal_proxy: str = ""`, `Settings.portal_name_map_file: str = "config/name_map.yaml"`.
- `portal_name_map` now contains the **merged** map (file entries overridden by inline entries).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_config.py`)

```python
def test_new_news_and_portal_keys_load(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(_MINIMAL_YAML.replace(
        "news_poll_interval_minutes: 60",
        "news_poll_interval_minutes: 60, booster_page_size: 300, "
        "fetch_cache_ttl_minutes: 5, news_outage_max_failures: 2, "
        "poll_interval_market_minutes: 10, poll_interval_offhours_minutes: 45, "
        "watchlist_passthrough: false, dedup_retention_days: 30",
    ), encoding="utf-8")
    s = _load(cfg)
    assert s.news_booster_page_size == 300
    assert s.news_fetch_cache_ttl_minutes == 5
    assert s.news_outage_max_failures == 2
    assert s.poll_interval_market_minutes == 10
    assert s.poll_interval_offhours_minutes == 45
    assert s.news_watchlist_passthrough is False
    assert s.news_dedup_retention_days == 30


def test_new_keys_default_and_offhours_falls_back_to_legacy_interval(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(_MINIMAL_YAML, encoding="utf-8")  # legacy config, no new keys
    s = _load(cfg)
    assert s.news_booster_page_size == 200
    assert s.news_fetch_cache_ttl_minutes == 10
    assert s.news_outage_max_failures == 4
    assert s.poll_interval_market_minutes == 15
    assert s.poll_interval_offhours_minutes == 60   # falls back to news_poll_interval_minutes
    assert s.news_watchlist_passthrough is True
    assert s.news_dedup_retention_days == 90
    assert s.portal_dup_title_threshold == 0.6
    assert s.portal_fetch_workers == 4
    assert s.portal_proxy == ""


def test_name_map_file_merges_under_inline(tmp_path):
    nm = tmp_path / "name_map.yaml"
    nm.write_text("aneka tambang: XXXX\nbank rakyat: BBRI\n", encoding="utf-8")
    cfg = tmp_path / "c.yaml"
    cfg.write_text(_MINIMAL_YAML.replace(
        "portal: {enabled: true}",
        "portal: {enabled: true, name_map_file: %s, name_map: {aneka tambang: ANTM}}"
        % nm.as_posix(),
    ), encoding="utf-8")
    s = _load(cfg)
    assert s.portal_name_map["aneka tambang"] == "ANTM"   # inline wins
    assert s.portal_name_map["bank rakyat"] == "BBRI"     # file entry kept


def test_missing_name_map_file_is_fine(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(_MINIMAL_YAML.replace(
        "portal: {enabled: true}",
        "portal: {enabled: true, name_map_file: %s}" % (tmp_path / "absent.yaml").as_posix(),
    ), encoding="utf-8")
    s = _load(cfg)
    assert s.portal_name_map == {}
```

Before these tests, check the top of `tests/test_config.py`: it already builds a minimal YAML string and a loader helper for existing tests (see `test_load_settings_falls_back_to_booster_defaults_when_absent`). Reuse those; if the file has no shared `_MINIMAL_YAML`/`_load` helpers, add them following the pattern of the existing tests in that file (a YAML string containing `news: {curated_keywords: [dividen], disclosure_page_size: 50, news_poll_interval_minutes: 60}` and `portal: {enabled: true}` sections, plus monkeypatched `TELEGRAM_*` env vars).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v -k "new_news or name_map_file or offhours"`
Expected: FAIL (`AttributeError: news_booster_page_size` / assertion errors)

- [ ] **Step 3: Implement**

In `news_breakout/config.py`, add to `Settings` (after `daily_shift_history_days`):

```python
    news_booster_page_size: int = 200
    news_fetch_cache_ttl_minutes: int = 10
    news_outage_max_failures: int = 4
    poll_interval_market_minutes: int = 15
    poll_interval_offhours_minutes: int = 60
    news_watchlist_passthrough: bool = True
    news_dedup_retention_days: int = 90
    portal_dup_title_threshold: float = 0.6
    portal_fetch_workers: int = 4
    portal_proxy: str = ""
    portal_name_map_file: str = "config/name_map.yaml"
```

Add a module-level helper (near `_load_env_file`):

```python
def _load_name_map_file(path: str) -> dict[str, str]:
    """Optional YAML file of lowercase company name -> ticker; missing file -> {}."""
    p = Path(path)
    if not path or not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip().lower(): str(v).strip().upper() for k, v in data.items()}
```

In `load_settings(...)`, replace the `portal_name_map=portal.get("name_map", {}),` line and add the new keys:

```python
        portal_name_map={
            **_load_name_map_file(portal.get("name_map_file", "config/name_map.yaml")),
            **portal.get("name_map", {}),
        },
        portal_name_map_file=portal.get("name_map_file", "config/name_map.yaml"),
        news_booster_page_size=news.get("booster_page_size", 200),
        news_fetch_cache_ttl_minutes=news.get("fetch_cache_ttl_minutes", 10),
        news_outage_max_failures=news.get("news_outage_max_failures", 4),
        poll_interval_market_minutes=news.get("poll_interval_market_minutes", 15),
        poll_interval_offhours_minutes=news.get(
            "poll_interval_offhours_minutes", news["news_poll_interval_minutes"]),
        news_watchlist_passthrough=news.get("watchlist_passthrough", True),
        news_dedup_retention_days=news.get("dedup_retention_days", 90),
        portal_dup_title_threshold=portal.get("dup_title_threshold", 0.6),
        portal_fetch_workers=portal.get("fetch_workers", 4),
        portal_proxy=portal.get("proxy", ""),
```

In `config/config.example.yaml`, extend the `news:` block (after `priority_boost: 3.0`):

```yaml
  booster_page_size: 200            # canonical IDX fetch size (shared cache + booster window)
  fetch_cache_ttl_minutes: 10       # disclosure cache TTL (news job + scan share one fetch)
  news_outage_max_failures: 4       # consecutive fetch failures before a once/day Telegram warning
  poll_interval_market_minutes: 15  # news poll cadence during market hours
  poll_interval_offhours_minutes: 60  # cadence outside market hours
  watchlist_passthrough: true       # watchlist tickers bypass the keyword gate
  dedup_retention_days: 90          # prune sent-news bookkeeping older than this
```

and the `portal:` block (after `max_per_run: 20`):

```yaml
  dup_title_threshold: 0.6  # near-dup Jaccard threshold across portals (0 disables)
  fetch_workers: 4          # parallel article-extraction workers
  proxy: ""                 # global portal proxy; per-source `proxy:` overrides
  name_map_file: config/name_map.yaml  # optional generated map; inline name_map overrides it
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: all PASS (old tests too — new fields are defaulted)

- [ ] **Step 5: Commit**

```bash
git add news_breakout/config.py config/config.example.yaml tests/test_config.py
git commit -m "feat(news): config keys for cache, cadence, dedup, proxy, name-map file"
```

---

### Task 2: Keyword matching — word boundary + `-nya` enclitic

**Files:**
- Modify: `news_breakout/news/curated.py`
- Modify: `news_breakout/news/portal.py` (`has_corp_action`)
- Test: `tests/test_curated.py`

**Interfaces:**
- Produces: `keyword_match(text: str, keywords: list[str]) -> bool` in `news_breakout/news/curated.py`. `is_price_sensitive` and `has_corp_action` delegate to it.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_curated.py`)

```python
from news_breakout.news.curated import keyword_match


def test_keyword_match_word_boundary_rejects_prefix_extension():
    assert keyword_match("Proyek kontraktor tambang", ["kontrak"]) is False


def test_keyword_match_accepts_exact_and_nya_enclitic():
    assert keyword_match("Pembagian dividen final", ["dividen"]) is True
    assert keyword_match("Besaran dividennya naik", ["dividen"]) is True


def test_keyword_match_multiword_and_case_insensitive():
    assert keyword_match("Jadwal RIGHTS ISSUE emiten", ["rights issue"]) is True
    assert keyword_match("Right issue saja", ["rights issue"]) is False


def test_keyword_match_regex_metachars_are_literal():
    assert keyword_match("laba (unaudited) naik", ["(unaudited)"]) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_curated.py -v`
Expected: FAIL (`ImportError: cannot import name 'keyword_match'`)

- [ ] **Step 3: Implement**

Replace the body of `news_breakout/news/curated.py`:

```python
from __future__ import annotations

import re

from news_breakout.news.models import Disclosure


def keyword_match(text: str, keywords: list[str]) -> bool:
    """Word-boundary keyword match, tolerating the Indonesian ``-nya`` enclitic.

    ``kontrak`` must NOT hit ``kontraktor``, but ``dividen`` must still hit
    ``dividennya``. Uses lookarounds instead of ``\\b`` because ``\\b`` never
    matches between two non-word chars — a keyword like ``(unaudited)`` would
    silently stop matching with plain word boundaries.
    """
    low = (text or "").lower()
    for kw in keywords:
        kw = kw.strip().lower()
        if kw and re.search(rf"(?<!\w){re.escape(kw)}(?:nya)?(?!\w)", low):
            return True
    return False


def is_price_sensitive(disclosure: Disclosure, keywords: list[str]) -> bool:
    return keyword_match(disclosure.title, keywords)
```

In `news_breakout/news/portal.py`, replace `has_corp_action`:

```python
def has_corp_action(text: str, keywords: list[str]) -> bool:
    from news_breakout.news.curated import keyword_match
    return keyword_match(text, keywords)
```

(Local import — `curated.py` is dependency-free, so no cycle, but keep the import local to match the file's existing style for cross-module imports.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_curated.py tests/test_portal.py tests/test_news_feed.py -v`
Expected: all PASS (existing keyword fixtures use whole words already; if any legacy test asserted substring behavior, fix the TEST to the new boundary semantics and note it in the commit message)

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/curated.py news_breakout/news/portal.py tests/test_curated.py
git commit -m "feat(news): word-boundary keyword matching with -nya enclitic"
```

---

### Task 3: Watchlist pass-through in `run_news_feed`

**Files:**
- Modify: `news_breakout/news/feed.py`
- Test: `tests/test_news_feed.py`

**Interfaces:**
- Consumes: `Settings.news_watchlist_passthrough` (Task 1).
- Produces: `run_news_feed` keeps a disclosure when `is_price_sensitive(...)` OR (`settings.news_watchlist_passthrough` and `d.ticker` in watchlist).

- [ ] **Step 1: Write the failing test** (append to `tests/test_news_feed.py`; the file's `_settings()` has `watchlist=["ANTM"]` and `_disc()` uses ticker `"BBRI"`)

```python
def test_watchlist_disclosure_bypasses_keyword_gate():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return [Disclosure("ANTM", "Public Expose", NOW, "w1", "url"),   # watchlist, no keyword
                Disclosure("BBRI", "Public Expose", NOW, "n1", "url")]   # neither

    ids = run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher)
    assert ids == ["w1"]
    store.close()


def test_watchlist_passthrough_disabled_keeps_keyword_gate():
    store = DedupStore(":memory:")
    s = _settings().model_copy(update={"news_watchlist_passthrough": False})

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return [Disclosure("ANTM", "Public Expose", NOW, "w1", "url")]

    ids = run_news_feed(s, store, now=NOW,
                        sender=lambda *a, **k: True, fetcher=fetcher)
    assert ids == []
    store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_news_feed.py -v -k watchlist`
Expected: FAIL (`ids == []` on the first test)

- [ ] **Step 3: Implement**

In `news_breakout/news/feed.py`, replace the curation line in `run_news_feed`:

```python
    watchset = set(settings.watchlist) if settings.news_watchlist_passthrough else set()
    curated = [d for d in disclosures
               if is_price_sensitive(d, settings.curated_keywords) or d.ticker in watchset]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_news_feed.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/feed.py tests/test_news_feed.py
git commit -m "feat(news): watchlist disclosures bypass the keyword gate"
```

---

### Task 4: `fetch_disclosures_ex` — distinguish empty-success from failure

**Files:**
- Modify: `news_breakout/news/idx_source.py`
- Test: `tests/test_fetch_retry.py`

**Interfaces:**
- Produces: `fetch_disclosures_ex(page_size: int = 50, *, now, proxy: str = "", retries: int = 3, http_get=None, sleeper=time.sleep) -> tuple[list[Disclosure], bool]` — `ok=True` iff a response parsed to a dict with a `Replies` list (even if empty). `fetch_disclosures(...)` now returns `fetch_disclosures_ex(...)[0]`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_fetch_retry.py`; reuse its existing `NOW`/helpers)

```python
from news_breakout.news.idx_source import fetch_disclosures_ex


def test_ex_ok_true_on_valid_even_empty_payload():
    items, ok = fetch_disclosures_ex(
        50, now=NOW, retries=0, http_get=lambda url, proxy: '{"Replies": []}')
    assert ok is True
    assert items == []


def test_ex_ok_false_on_cloudflare_html():
    calls = []
    items, ok = fetch_disclosures_ex(
        50, now=NOW, retries=1, sleeper=lambda s: calls.append(s),
        http_get=lambda url, proxy: "<html>blocked</html>")
    assert ok is False
    assert items == []
    assert calls == [5]   # existing retry delay table
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch_retry.py -v -k ex_ok`
Expected: FAIL (`ImportError: cannot import name 'fetch_disclosures_ex'`)

- [ ] **Step 3: Implement**

In `news_breakout/news/idx_source.py`, rename the body of `fetch_disclosures` to `fetch_disclosures_ex`, returning tuples, and re-add the thin wrapper:

```python
def fetch_disclosures_ex(page_size: int = 50, *, now, proxy: str = "", retries: int = 3,
                         http_get=None, sleeper=time.sleep) -> tuple[list[Disclosure], bool]:
    """Like fetch_disclosures, but also reports whether the fetch itself succeeded.

    ok=True means a response parsed to {"Replies": [...]} — an empty list of
    disclosures with ok=True is a genuine empty page, not an outage.
    """
    if http_get is None:
        http_get = _default_http_get
    url = _API.format(page_size=page_size)
    _RETRY_DELAYS = [5, 15, 30]
    for attempt in range(retries + 1):
        try:
            text = http_get(url, proxy)
            data = json.loads(text)
        except Exception:  # noqa: BLE001 — Cloudflare HTML / network / decode failure
            data = None
        if isinstance(data, dict) and isinstance(data.get("Replies"), list):
            return parse_disclosures(data, now=now), True
        if attempt < retries:
            sleeper(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
    logger.warning("IDX disclosure fetch failed after %d attempts (Cloudflare/block?)", retries + 1)
    return [], False


def fetch_disclosures(page_size: int = 50, *, now, proxy: str = "", retries: int = 3,
                      http_get=None, sleeper=time.sleep) -> list[Disclosure]:
    return fetch_disclosures_ex(page_size, now=now, proxy=proxy, retries=retries,
                                http_get=http_get, sleeper=sleeper)[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch_retry.py tests/test_news_fetch.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/idx_source.py tests/test_fetch_retry.py
git commit -m "feat(news): fetch_disclosures_ex reports fetch success separately from emptiness"
```

---

### Task 5: `DisclosureCache` — shared TTL cache with stale-while-error

**Files:**
- Create: `news_breakout/news/disclosure_cache.py`
- Test: `tests/test_disclosure_cache.py`

**Interfaces:**
- Consumes: `fetch_disclosures_ex` (Task 4).
- Produces: `DisclosureCache(page_size: int, ttl_minutes: int, *, fetcher=fetch_disclosures_ex)` with `fetch(page_size_ignored, *, now, proxy="", retries=None, **_) -> list[Disclosure]` (signature-compatible with every existing `fetcher`/`disclosure_fetcher` injection point) and attribute `consecutive_failures: int`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.news.disclosure_cache import DisclosureCache
from news_breakout.news.models import Disclosure

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 22, 9, 0, tzinfo=WIB)


def _disc(i):
    return Disclosure("ANTM", f"t{i}", NOW, str(i), "url")


def test_fetch_uses_canonical_page_size_and_caches_within_ttl():
    calls = []

    def fetcher(page_size, *, now, proxy="", retries=3, **_):
        calls.append((page_size, retries))
        return [_disc(1)], True

    cache = DisclosureCache(200, 10, fetcher=fetcher)
    a = cache.fetch(50, now=NOW, proxy="p")            # caller size ignored
    b = cache.fetch(50, now=NOW + timedelta(minutes=9))  # within TTL -> no refetch
    assert a == b == [_disc(1)]
    assert calls == [(200, 3)]                          # one fetch, canonical size


def test_ttl_expiry_refetches_and_retries_forwarded():
    calls = []

    def fetcher(page_size, *, now, proxy="", retries=3, **_):
        calls.append(retries)
        return [_disc(len(calls))], True

    cache = DisclosureCache(200, 10, fetcher=fetcher)
    cache.fetch(50, now=NOW)
    cache.fetch(50, now=NOW + timedelta(minutes=11), retries=0)
    assert calls == [3, 0]   # default forwarded as fetcher default, explicit 0 forwarded


def test_stale_while_error_and_failure_counter():
    state = {"ok": True}

    def fetcher(page_size, *, now, proxy="", retries=3, **_):
        return ([_disc(1)], True) if state["ok"] else ([], False)

    cache = DisclosureCache(200, 10, fetcher=fetcher)
    good = cache.fetch(50, now=NOW)
    state["ok"] = False
    stale = cache.fetch(50, now=NOW + timedelta(minutes=20))
    assert stale == good                       # last good result served
    assert cache.consecutive_failures == 1
    cache.fetch(50, now=NOW + timedelta(minutes=40))
    assert cache.consecutive_failures == 2
    state["ok"] = True
    fresh = cache.fetch(50, now=NOW + timedelta(minutes=60))
    assert fresh == good
    assert cache.consecutive_failures == 0     # success resets the streak


def test_failed_fetch_does_not_extend_ttl():
    calls = []

    def fetcher(page_size, *, now, proxy="", retries=3, **_):
        calls.append(now)
        return [], False

    cache = DisclosureCache(200, 10, fetcher=fetcher)
    cache.fetch(50, now=NOW)
    cache.fetch(50, now=NOW + timedelta(minutes=1))   # still retries: no good cache yet
    assert len(calls) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_disclosure_cache.py -v`
Expected: FAIL (`ModuleNotFoundError: news_breakout.news.disclosure_cache`)

- [ ] **Step 3: Implement** (`news_breakout/news/disclosure_cache.py`)

```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from news_breakout.news.idx_source import fetch_disclosures_ex
from news_breakout.news.models import Disclosure

logger = logging.getLogger("news_breakout")


class DisclosureCache:
    """One canonical IDX disclosure fetch shared by the news feed and scan booster.

    - Always fetches ``page_size`` rows (the caller-passed size is ignored) so the
      48h booster window is fully covered and both consumers share one fetch.
    - Within ``ttl_minutes`` of the last SUCCESSFUL fetch, returns the cached list.
    - On fetch failure: serves the last good list (stale-while-error) and bumps
      ``consecutive_failures``; a success resets it. A failure never refreshes the
      TTL clock, so the next tick tries again.
    """

    def __init__(self, page_size: int, ttl_minutes: int, *, fetcher=fetch_disclosures_ex):
        self._page_size = page_size
        self._ttl = timedelta(minutes=ttl_minutes)
        self._fetcher = fetcher
        self._cached: list[Disclosure] = []
        self._fetched_at: datetime | None = None
        self.consecutive_failures = 0

    def fetch(self, page_size, *, now, proxy: str = "", retries=None, **_) -> list[Disclosure]:
        if self._fetched_at is not None and now - self._fetched_at < self._ttl:
            return self._cached
        kwargs = {"now": now, "proxy": proxy}
        if retries is not None:
            kwargs["retries"] = retries
        try:
            items, ok = self._fetcher(self._page_size, **kwargs)
        except Exception:  # noqa: BLE001 — a fetch crash degrades like a failed fetch
            items, ok = [], False
        if ok:
            self._cached = items
            self._fetched_at = now
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            logger.warning("disclosure cache: fetch failed (%d consecutive); serving %d stale items",
                           self.consecutive_failures, len(self._cached))
        return self._cached if not ok else items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_disclosure_cache.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/disclosure_cache.py tests/test_disclosure_cache.py
git commit -m "feat(news): shared DisclosureCache with TTL and stale-while-error"
```

---

### Task 6: Outage warning in `run_news_feed`

**Files:**
- Modify: `news_breakout/news/feed.py`
- Test: `tests/test_news_feed.py`

**Interfaces:**
- Consumes: `Settings.news_outage_max_failures` (Task 1).
- Produces: `run_news_feed(..., failure_streak=0)` — int **or** zero-arg callable (evaluated after the fetch, so `lambda: cache.consecutive_failures` sees this run's outcome). At/above threshold sends `"⚠️ Feed keterbukaan IDX gagal N kali beruntun — Cloudflare/proxy bermasalah?"` to the news chat, once per day via dedup key `news-outage-YYYY-MM-DD`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_news_feed.py`)

```python
def test_outage_warning_sent_once_per_day_at_threshold():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return []

    for _ in range(2):
        run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher,
                      failure_streak=4)
    warnings = [t for t in sent if "gagal 4 kali" in t]
    assert len(warnings) == 1                      # once/day dedup
    assert store.news_already_sent("news-outage-2026-07-18")
    store.close()


def test_outage_warning_below_threshold_and_callable_streak():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return []

    run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher,
                  failure_streak=3)
    assert sent == []                              # below default threshold 4
    run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher,
                  failure_streak=lambda: 5)        # callable form
    assert any("gagal 5 kali" in t for t in sent)
    store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_news_feed.py -v -k outage`
Expected: FAIL (`TypeError: unexpected keyword argument 'failure_streak'`)

- [ ] **Step 3: Implement**

In `news_breakout/news/feed.py`, change the `run_news_feed` signature and add the check right after the fetch line:

```python
def run_news_feed(settings, store, *, now, sender=send_message, fetcher=fetch_disclosures,
                  failure_streak=0) -> list[str]:
    disclosures = fetcher(settings.disclosure_page_size, now=now, proxy=settings.idx_proxy)
    streak = failure_streak() if callable(failure_streak) else failure_streak
    if streak >= settings.news_outage_max_failures:
        key = f"news-outage-{now:%Y-%m-%d}"
        if not store.news_already_sent(key):
            warn = (f"⚠️ Feed keterbukaan IDX gagal {streak} kali beruntun — "
                    "Cloudflare/proxy bermasalah?")
            if sender(settings.telegram_bot_token, settings.telegram_news_chat_id,
                      warn, dry_run=settings.dry_run):
                store.news_mark_sent(key)   # one outage heads-up per day
```

(The rest of the function is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_news_feed.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/feed.py tests/test_news_feed.py
git commit -m "feat(news): once/day Telegram warning on consecutive IDX fetch failures"
```

---

### Task 7: `should_poll_news` + market-cadence scheduler interval

**Files:**
- Modify: `news_breakout/scheduling/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `Settings.poll_interval_market_minutes`, `Settings.poll_interval_offhours_minutes` (Task 1).
- Produces: `should_poll_news(now, last_run, *, market_open: bool, offhours_minutes: int) -> bool` in `scheduling/scheduler.py`; `build_scheduler` schedules the news job every `poll_interval_market_minutes`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_scheduler.py`; reuse its existing settings fixture/helper for `build_scheduler` tests)

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.scheduling.scheduler import should_poll_news

WIB = ZoneInfo("Asia/Jakarta")
T0 = datetime(2026, 7, 22, 20, 0, tzinfo=WIB)   # evening, off-hours


def test_poll_always_during_market_hours():
    assert should_poll_news(T0, T0 - timedelta(minutes=1),
                            market_open=True, offhours_minutes=60) is True


def test_poll_offhours_gated_by_elapsed_time():
    assert should_poll_news(T0, None, market_open=False, offhours_minutes=60) is True
    assert should_poll_news(T0, T0 - timedelta(minutes=59),
                            market_open=False, offhours_minutes=60) is False
    assert should_poll_news(T0, T0 - timedelta(minutes=60),
                            market_open=False, offhours_minutes=60) is True


def test_news_job_scheduled_at_market_cadence():
    sched = build_scheduler(_sched_settings(), scan_job=lambda: None,
                            weekend_job=lambda: None, news_job=lambda: None)
    news = next(j for j in sched.get_jobs() if j.id == "news")
    assert news.trigger.interval == timedelta(minutes=15)
```

(`_sched_settings()` = whatever helper the existing `build_scheduler` tests in this file use to construct `Settings`; the new `poll_interval_market_minutes` defaults to 15.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL (`ImportError: should_poll_news`; interval still 60)

- [ ] **Step 3: Implement**

In `news_breakout/scheduling/scheduler.py` add:

```python
from datetime import timedelta


def should_poll_news(now, last_run, *, market_open: bool, offhours_minutes: int) -> bool:
    """Elapsed-time gating for the news job (interval ticks are NOT clock-aligned).

    During market hours every tick polls; off-hours a tick only polls once at
    least ``offhours_minutes`` have passed since the last completed poll.
    """
    if market_open or last_run is None:
        return True
    return now - last_run >= timedelta(minutes=offhours_minutes)
```

and change the news line in `build_scheduler`:

```python
    sched.add_job(news_job, "interval", minutes=settings.poll_interval_market_minutes, id="news")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/scheduling/scheduler.py tests/test_scheduler.py
git commit -m "feat(news): market-hours-aware news polling cadence"
```

---

### Task 8: `portal_dedup` module + `sent_news_titles` store table

**Files:**
- Create: `news_breakout/news/portal_dedup.py`
- Modify: `news_breakout/alerts/dedup.py`
- Test: `tests/test_portal_dedup.py`

**Interfaces:**
- Produces: `normalize_title(title: str) -> set[str]`, `jaccard(a: set, b: set) -> float`, `is_duplicate(tokens: set[str], seen: list[set[str]], threshold: float) -> bool` in `news_breakout/news/portal_dedup.py`; `DedupStore.add_title(date_str, ticker, title_norm)` and `DedupStore.titles_for_day(date_str, ticker) -> list[str]` (title_norm = space-joined sorted tokens).

- [ ] **Step 1: Write the failing tests**

```python
from news_breakout.alerts.dedup import DedupStore
from news_breakout.news.portal_dedup import is_duplicate, jaccard, normalize_title


def test_normalize_drops_stopwords_short_tokens_and_punct():
    toks = normalize_title("Laba ANTM naik 20% di kuartal II, ini kata analis")
    assert "yang" not in toks and "di" not in toks and "ini" not in toks
    assert {"laba", "antm", "naik", "kuartal", "analis"} <= toks


def test_jaccard_and_duplicate_threshold():
    a = normalize_title("ANTM bagikan dividen Rp 500 miliar tahun ini")
    b = normalize_title("Dividen ANTM Rp 500 miliar dibagikan")
    assert jaccard(a, b) >= 0.6
    assert is_duplicate(b, [a], 0.6) is True
    c = normalize_title("ANTM ekspansi pabrik feronikel Halmahera")
    assert is_duplicate(c, [a], 0.6) is False


def test_is_duplicate_threshold_zero_disables():
    a = normalize_title("judul sama persis")
    assert is_duplicate(a, [a], 0) is False


def test_store_titles_round_trip_scoped_by_ticker_and_day():
    store = DedupStore(":memory:")
    store.add_title("2026-07-22", "ANTM", "antm dividen miliar")
    store.add_title("2026-07-22", "TINS", "tins laba naik")
    store.add_title("2026-07-21", "ANTM", "antm lama")
    assert store.titles_for_day("2026-07-22", "ANTM") == ["antm dividen miliar"]
    assert store.titles_for_day("2026-07-22", "") == []
    store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_portal_dedup.py -v`
Expected: FAIL (`ModuleNotFoundError` / `AttributeError: add_title`)

- [ ] **Step 3: Implement**

`news_breakout/news/portal_dedup.py`:

```python
from __future__ import annotations

import re

# Small Indonesian function-word list; enough to keep headline token sets meaningful.
_STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "untuk", "pada", "dengan", "ini", "itu",
    "akan", "ada", "adalah", "atau", "dalam", "juga", "tak", "tidak", "bagi",
    "para", "saat", "usai", "kata", "soal",
}


def normalize_title(title: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_duplicate(tokens: set[str], seen: list[set[str]], threshold: float) -> bool:
    if threshold <= 0 or not tokens:
        return False
    return any(jaccard(tokens, s) >= threshold for s in seen)
```

In `news_breakout/alerts/dedup.py` `__init__`, after the `sent_news` CREATE:

```python
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_news_titles (
                date_str TEXT NOT NULL,
                ticker TEXT NOT NULL,
                title_norm TEXT NOT NULL
            )
            """
        )
```

and the two methods (before `close`):

```python
    def add_title(self, date_str: str, ticker: str, title_norm: str) -> None:
        self._conn.execute(
            "INSERT INTO sent_news_titles VALUES (?, ?, ?)", (date_str, ticker, title_norm)
        )
        self._conn.commit()

    def titles_for_day(self, date_str: str, ticker: str) -> list[str]:
        cur = self._conn.execute(
            "SELECT title_norm FROM sent_news_titles WHERE date_str=? AND ticker=?",
            (date_str, ticker),
        )
        return [r[0] for r in cur.fetchall()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_portal_dedup.py tests/test_dedup.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/portal_dedup.py news_breakout/alerts/dedup.py tests/test_portal_dedup.py
git commit -m "feat(news): near-dup title normalization, Jaccard check, and titles store"
```

---

### Task 9: Near-dup integration in `run_portal_feed`

**Files:**
- Modify: `news_breakout/news/feed.py`
- Test: `tests/test_news_dedup.py`

**Interfaces:**
- Consumes: Task 8 (`normalize_title`, `is_duplicate`, `add_title`, `titles_for_day`), `Settings.portal_dup_title_threshold`.
- Behavior: a same-ticker same-day near-dup is marked sent by URL **without** sending; sent items record their normalized title.

- [ ] **Step 1: Write the failing test** (append to `tests/test_news_dedup.py`; reuse that file's existing `_settings()`/`PortalNews` fixtures — if it has none, copy the `_settings()` helper from `tests/test_news_feed.py` and import `PortalNews` from `news_breakout.news.portal`)

```python
from news_breakout.news.portal import PortalNews
from news_breakout.news.feed import run_portal_feed


def _item(url, title, ticker="ANTM"):
    return PortalNews(ticker, title, NOW, url, "src", summary="s")


def test_cross_portal_near_dup_suppressed_same_ticker_only():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot, chat, text, *, dry_run, client=None, parse_mode=None, disable_preview=False):
        sent.append(text)
        return True

    items = [
        _item("u1", "ANTM bagikan dividen Rp 500 miliar tahun ini"),
        _item("u2", "Dividen ANTM Rp 500 miliar dibagikan"),           # near-dup of u1
        _item("u3", "Laba TINS naik 500 miliar dibagikan", ticker="TINS"),  # other ticker: kept
    ]
    s = _settings().model_copy(update={"portal_enabled": True, "sentiment_enabled": False})
    urls = run_portal_feed(s, store, now=NOW, sender=sender,
                           fetcher=lambda *a, **k: items,
                           extractor=lambda url: "", classifier=None)
    assert "u1" in urls and "u3" in urls
    assert "u2" not in urls
    assert store.news_already_sent("u2")     # suppressed, never resurfaces
    assert len(sent) == 2
    store.close()


def test_near_dup_suppressed_across_runs_same_day():
    store = DedupStore(":memory:")
    s = _settings().model_copy(update={"portal_enabled": True, "sentiment_enabled": False})
    kw = dict(sender=lambda *a, **k: True, extractor=lambda url: "", classifier=None)
    run_portal_feed(s, store, now=NOW,
                    fetcher=lambda *a, **k: [_item("u1", "ANTM bagikan dividen Rp 500 miliar tahun ini")], **kw)
    urls = run_portal_feed(s, store, now=NOW,
                           fetcher=lambda *a, **k: [_item("u9", "Dividen ANTM Rp 500 miliar dibagikan")], **kw)
    assert urls == []
    store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_news_dedup.py -v -k near_dup`
Expected: FAIL (`u2`/`u9` are sent)

- [ ] **Step 3: Implement**

In `news_breakout/news/feed.py`, inside `run_portal_feed`, add the import at the top of the file (`from news_breakout.news.portal_dedup import is_duplicate, normalize_title`) and replace the send loop:

```python
    day = f"{now:%Y-%m-%d}"
    threshold = settings.portal_dup_title_threshold
    seen_by_ticker: dict[str, list[set[str]]] = {}

    def _seen(ticker: str) -> list[set[str]]:
        if ticker not in seen_by_ticker:
            seen_by_ticker[ticker] = [set(t.split())
                                      for t in store.titles_for_day(day, ticker)]
        return seen_by_ticker[ticker]

    sent = []
    for it in items:
        if len(sent) >= settings.portal_max_per_run:
            break
        if store.news_already_sent(it.url):
            continue
        tokens = normalize_title(it.title)
        if is_duplicate(tokens, _seen(it.ticker), threshold):
            store.news_mark_sent(it.url)   # suppressed near-dup must not resurface
            logger.info("portal near-dup suppressed: %s", it.title)
            continue
        if not sender(settings.telegram_bot_token, settings.telegram_news_chat_id,
                      format_portal(it), dry_run=settings.dry_run,
                      parse_mode="HTML", disable_preview=True):
            continue
        store.news_mark_sent(it.url)
        store.add_title(day, it.ticker, " ".join(sorted(tokens)))
        _seen(it.ticker).append(tokens)
        sent.append(it.url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_news_dedup.py tests/test_news_feed.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/feed.py tests/test_news_dedup.py
git commit -m "feat(news): suppress cross-portal near-duplicate stories per ticker/day"
```

---

### Task 10: Word-boundary company-name matching in `match_ticker`

**Files:**
- Modify: `news_breakout/news/portal.py`
- Test: `tests/test_portal.py`

**Interfaces:**
- `match_ticker(text, watchlist, name_map)` unchanged signature; the name pass now requires word boundaries.

- [ ] **Step 1: Write the failing test** (append to `tests/test_portal.py`)

```python
def test_name_match_requires_word_boundary():
    name_map = {"timah": "TINS"}
    assert match_ticker("Harga timah dunia naik", [], name_map) == "TINS"
    assert match_ticker("Pertimahan nasional dibahas", [], name_map) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_portal.py -v -k word_boundary`
Expected: FAIL (substring match tags "Pertimahan")

- [ ] **Step 3: Implement**

In `news_breakout/news/portal.py`, replace the name loop in `match_ticker`:

```python
    for name, tk in name_map.items():          # company name first (higher precision)
        if re.search(rf"\b{re.escape(name.lower())}\b", low):
            return tk
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_portal.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/portal.py tests/test_portal.py
git commit -m "fix(news): company-name matching requires word boundaries"
```

---

### Task 11: Atom feed parsing in `parse_rss`

**Files:**
- Modify: `news_breakout/news/portal.py`
- Test: `tests/test_news_parse.py`

**Interfaces:**
- `parse_rss(xml_text, source, *, now)` additionally yields `PortalNews` for Atom `<entry>` elements.

- [ ] **Step 1: Write the failing test** (append to `tests/test_news_parse.py`)

```python
ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Contoh</title>
  <entry>
    <title>ANTM cetak laba</title>
    <link rel="alternate" href="https://ex.com/a"/>
    <summary>Ringkasan &lt;b&gt;laba&lt;/b&gt; ANTM</summary>
    <published>2026-07-22T08:30:00+07:00</published>
  </entry>
  <entry>
    <title>Tanpa link dilewati</title>
    <published>2026-07-22T08:00:00+07:00</published>
  </entry>
</feed>"""


def test_parse_atom_entries():
    items = parse_rss(ATOM, "ex.com", now=NOW)
    assert len(items) == 1
    it = items[0]
    assert it.title == "ANTM cetak laba"
    assert it.url == "https://ex.com/a"
    assert "laba" in it.summary and "<b>" not in it.summary
    assert it.timestamp.hour == 8 and it.timestamp.minute == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_news_parse.py -v -k atom`
Expected: FAIL (`len(items) == 0`)

- [ ] **Step 3: Implement**

In `news_breakout/news/portal.py`, add below `_parse_pubdate`:

```python
_ATOM = "{http://www.w3.org/2005/Atom}"


def _parse_iso(raw: str, now: datetime) -> datetime:
    try:
        dt = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
        return dt.astimezone(WIB) if dt.tzinfo else dt.replace(tzinfo=WIB)
    except ValueError:
        return now


def _atom_link(entry) -> str:
    links = entry.findall(f"{_ATOM}link")
    for ln in links:
        if ln.get("rel", "alternate") == "alternate" and ln.get("href"):
            return ln.get("href").strip()
    return (links[0].get("href", "").strip() if links else "")
```

and extend `parse_rss` (after the existing `root.iter("item")` loop, before `return out`):

```python
    for entry in root.iter(f"{_ATOM}entry"):
        title = (entry.findtext(f"{_ATOM}title") or "").strip()
        link = _atom_link(entry)
        if not title or not link:
            continue
        raw_sum = entry.findtext(f"{_ATOM}summary") or entry.findtext(f"{_ATOM}content") or ""
        summary = re.sub(r"<[^>]+>", " ", raw_sum).strip()
        raw_ts = entry.findtext(f"{_ATOM}published") or entry.findtext(f"{_ATOM}updated") or ""
        out.append(PortalNews("", title, _parse_iso(raw_ts, now), link, source, summary=summary))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_news_parse.py tests/test_portal.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/portal.py tests/test_news_parse.py
git commit -m "feat(news): parse Atom feeds alongside RSS 2.0"
```

---

### Task 12: Portal proxy plumbing (per-source + global)

**Files:**
- Modify: `news_breakout/news/portal.py`
- Modify: `news_breakout/news/feed.py`
- Modify: `config/config.example.yaml`
- Test: `tests/test_portal.py`

**Interfaces:**
- `_default_http_get(url: str, proxy: str = "") -> str`; `fetch_portal_news(..., global_proxy: str = "")` calls `http_get(url, proxy)` with per-source `proxy` → `global_proxy` → `""`.
- `run_portal_feed` forwards `settings.portal_proxy` as `global_proxy` and uses it for article extraction too.

- [ ] **Step 1: Write the failing test** (append to `tests/test_portal.py`)

```python
def test_per_source_proxy_overrides_global():
    calls = []

    def http_get(url, proxy):
        calls.append((url, proxy))
        return "<rss></rss>"

    sources = [{"url": "https://a.com/rss", "proxy": "http://p1"},
               {"url": "https://b.com/rss"}]
    fetch_portal_news(sources, [], {}, now=NOW, http_get=http_get,
                      global_proxy="http://global")
    assert calls == [("https://a.com/rss", "http://p1"),
                     ("https://b.com/rss", "http://global")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_portal.py -v -k proxy`
Expected: FAIL (`TypeError` — `http_get` called with 1 arg / no `global_proxy` kwarg)

- [ ] **Step 3: Implement**

In `news_breakout/news/portal.py`:

```python
def _default_http_get(url: str, proxy: str = "") -> str:
    from curl_cffi import requests as creq
    kwargs = {"impersonate": "chrome120"}
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    return creq.Session(**kwargs).get(url, timeout=30).text
```

In `fetch_portal_news`, add `global_proxy: str = ""` to the signature and change the fetch:

```python
        proxy = (src.get("proxy", "") if isinstance(src, dict) else "") or global_proxy
        try:
            text = http_get(url, proxy)
        except Exception:  # noqa: BLE001
            logger.warning("portal fetch failed: %s", url)
            continue
```

In `news_breakout/news/feed.py` `run_portal_feed`: pass the proxy through both call sites:

```python
        def extractor(url):
            return fetch_article_text(
                url, http_get=lambda u: _default_http_get(u, settings.portal_proxy))
```

```python
    items = fetcher(settings.portal_sources, tickers, settings.portal_name_map, now=now,
                    corp_keywords=settings.curated_keywords, global_proxy=settings.portal_proxy)
```

Update any existing test fakes for `fetch_portal_news`'s `http_get` to the two-arg form, and injected `fetcher` fakes in feed tests to accept `global_proxy=""` (or `**kwargs`).

In `config/config.example.yaml`, under `portal: sources:`, re-add the blocked feeds as comments:

```yaml
    # 403 dari IP datacenter — aktifkan bila ada proxy residensial (isi `proxy:` per sumber
    # atau `portal.proxy` global):
    # - {url: https://www.kontan.co.id/rss, parser: rss}
    # - {url: https://www.bisnis.com/index, parser: bisnis}
    # - {url: https://investor.id/market, parser: investor}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_portal.py tests/test_news_feed.py tests/test_news_dedup.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/portal.py news_breakout/news/feed.py config/config.example.yaml tests/test_portal.py
git commit -m "feat(news): per-source and global proxy support for portal fetches"
```

---

### Task 13: Parallel article extraction

**Files:**
- Modify: `news_breakout/news/feed.py`
- Test: `tests/test_news_feed.py`

**Interfaces:**
- Consumes: `Settings.portal_fetch_workers` (Task 1).
- Produces: `_extract_leads(items, extractor, workers) -> list[str]` in `feed.py` — ordered bodies, per-item failure → `""`; `workers <= 1` runs sequentially (identical to old behavior).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_news_feed.py`)

```python
from news_breakout.news.feed import _extract_leads


class _Item:
    def __init__(self, url):
        self.url = url


def test_extract_leads_preserves_order_and_degrades():
    items = [_Item("a"), _Item("boom"), _Item("c")]

    def extractor(url):
        if url == "boom":
            raise RuntimeError("net down")
        return f"body-{url}"

    for workers in (1, 4):
        assert _extract_leads(items, extractor, workers) == ["body-a", "", "body-c"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_news_feed.py -v -k extract_leads`
Expected: FAIL (`ImportError: _extract_leads`)

- [ ] **Step 3: Implement**

In `news_breakout/news/feed.py`, add at module level:

```python
from concurrent.futures import ThreadPoolExecutor


def _extract_leads(items, extractor, workers: int) -> list[str]:
    """Fetch article bodies for ``items`` (ordered); any failure degrades to ""."""
    def one(it):
        try:
            return extractor(it.url) or ""
        except Exception:  # noqa: BLE001 — a fetch failure must not drop the item
            return ""
    if workers <= 1:
        return [one(it) for it in items]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, items))
```

and replace the sequential loop in `run_portal_feed`:

```python
    # extractive summary from the full article body (fall back to the RSS description)
    bodies = _extract_leads(items, extractor, settings.portal_fetch_workers)
    for it, body in zip(items, bodies):
        body = strip_leading_title(body, it.title)  # avoid echoing the hyperlinked headline
        it.lead = lead_summary(body or it.summary, settings.portal_summary_sentences)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_news_feed.py tests/test_news_dedup.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/feed.py tests/test_news_feed.py
git commit -m "feat(news): parallel article extraction with ordered, degradable results"
```

---

### Task 14: Telegram 429 — honor `retry_after`

**Files:**
- Modify: `news_breakout/alerts/telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- `send_message` on HTTP 429 sleeps `min(max(retry_after, 1), 30)` seconds (from `parameters.retry_after` in the JSON body) before the next attempt; malformed body → existing `_SEND_DELAYS` table. Other codes keep current behavior.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_telegram.py`; follow that file's existing fake-client pattern — a client object whose `post` returns objects with `status_code` and, for this test, a `json()` method)

```python
class _Resp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _SeqClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def post(self, url, json=None, timeout=None):
        return self._responses.pop(0)


def test_429_honors_retry_after_capped_at_30():
    sleeps = []
    client = _SeqClient([
        _Resp(429, {"parameters": {"retry_after": 7}}),
        _Resp(429, {"parameters": {"retry_after": 99}}),
        _Resp(200),
    ])
    ok = send_message("t", "c", "x", dry_run=False, client=client,
                      retries=2, sleeper=sleeps.append)
    assert ok is True
    assert sleeps == [7, 30]


def test_429_malformed_body_falls_back_to_delay_table():
    sleeps = []
    client = _SeqClient([_Resp(429, RuntimeError("no json")), _Resp(200)])
    ok = send_message("t", "c", "x", dry_run=False, client=client,
                      retries=1, sleeper=sleeps.append)
    assert ok is True
    assert sleeps == [2]   # first entry of _SEND_DELAYS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_telegram.py -v -k 429`
Expected: FAIL (`sleeps == [2, 5]`)

- [ ] **Step 3: Implement**

In `news_breakout/alerts/telegram.py`, replace the retry loop body:

```python
        for attempt in range(retries + 1):
            delay = None
            try:
                resp = client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload,
                    timeout=15,
                )
                if resp.status_code == 200:
                    return True
                if resp.status_code == 429:
                    try:
                        retry_after = int(resp.json().get("parameters", {}).get("retry_after", 0))
                        delay = min(max(retry_after, 1), 30)
                    except Exception:  # noqa: BLE001 — malformed body -> default backoff
                        delay = None
            except Exception:  # noqa: BLE001 — network failures are retryable, never propagate
                pass
            if attempt < retries:
                sleeper(delay if delay is not None
                        else _SEND_DELAYS[min(attempt, len(_SEND_DELAYS) - 1)])
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/alerts/telegram.py tests/test_telegram.py
git commit -m "fix(alerts): honor Telegram 429 retry_after with a 30s cap"
```

---

### Task 15: Inter-send spacing in both feed loops

**Files:**
- Modify: `news_breakout/news/feed.py`
- Test: `tests/test_news_feed.py`

**Interfaces:**
- `run_news_feed(..., sleeper=time.sleep)` and `run_portal_feed(..., sleeper=time.sleep)`: sleep `SEND_SPACING_SECONDS = 1.05` **before** every send except the first successful one in the run (so a single-item run never sleeps).

- [ ] **Step 1: Write the failing test** (append to `tests/test_news_feed.py`)

```python
def test_sends_are_spaced_but_not_before_first():
    store = DedupStore(":memory:")
    sleeps = []

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return [_disc("a", "Pembagian Dividen"), _disc("b", "Rencana Akuisisi"),
                _disc("c", "Dividen Interim")]

    run_news_feed(_settings(), store, now=NOW, sender=lambda *a, **k: True,
                  fetcher=fetcher, sleeper=sleeps.append)
    assert sleeps == [1.05, 1.05]   # 3 sends -> 2 gaps
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_news_feed.py -v -k spaced`
Expected: FAIL (`TypeError: unexpected keyword argument 'sleeper'`)

- [ ] **Step 3: Implement**

In `news_breakout/news/feed.py`: add `import time` at the top, module constant `SEND_SPACING_SECONDS = 1.05`, add `sleeper=time.sleep` to both signatures, and in **both** send loops insert before the `sender(...)` call:

```python
        if sent_ids:   # space consecutive sends (Telegram per-chat rate limit)
            sleeper(SEND_SPACING_SECONDS)
```

(in `run_portal_feed` the guard variable is `sent` instead of `sent_ids`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_news_feed.py tests/test_news_dedup.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/feed.py tests/test_news_feed.py
git commit -m "fix(news): space consecutive Telegram sends ~1s apart"
```

---

### Task 16: Dedup hygiene — `sent_at` migration + `prune_news`

**Files:**
- Modify: `news_breakout/alerts/dedup.py`
- Modify: `news_breakout/news/feed.py` (stamp `sent_at`)
- Test: `tests/test_dedup.py`

**Interfaces:**
- `DedupStore.news_mark_sent(disclosure_id, *, sent_at: str | None = None)` (backward compatible — existing callers without the kwarg store NULL).
- `DedupStore.prune_news(older_than_days: int, *, now) -> None` — deletes `sent_news` rows with non-NULL `sent_at < cutoff` and `sent_news_titles` rows with `date_str < cutoff`; NULL `sent_at` rows are never pruned.
- Both feed loops stamp `sent_at=f"{now:%Y-%m-%d}"`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_dedup.py`)

```python
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

NOW = datetime(2026, 7, 22, tzinfo=ZoneInfo("Asia/Jakarta"))


def test_sent_at_migration_on_legacy_db(tmp_path):
    db = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sent_news (disclosure_id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO sent_news VALUES ('old')")
    conn.commit()
    conn.close()
    store = DedupStore(str(db))                    # must not raise
    assert store.news_already_sent("old")
    store.news_mark_sent("new", sent_at="2026-07-22")
    store.prune_news(90, now=NOW)
    assert store.news_already_sent("old")          # NULL sent_at is never pruned
    store.close()


def test_prune_news_drops_old_rows_and_titles():
    store = DedupStore(":memory:")
    store.news_mark_sent("old", sent_at="2026-01-01")
    store.news_mark_sent("fresh", sent_at="2026-07-20")
    store.add_title("2026-01-01", "ANTM", "tua")
    store.add_title("2026-07-20", "ANTM", "baru")
    store.prune_news(90, now=NOW)
    assert store.news_already_sent("old") is False
    assert store.news_already_sent("fresh") is True
    assert store.titles_for_day("2026-01-01", "ANTM") == []
    assert store.titles_for_day("2026-07-20", "ANTM") == ["baru"]
    store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dedup.py -v -k "sent_at or prune"`
Expected: FAIL (`TypeError: unexpected keyword argument 'sent_at'`)

- [ ] **Step 3: Implement**

In `news_breakout/alerts/dedup.py` `__init__`, after the `sent_news` CREATE:

```python
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(sent_news)")]
        if "sent_at" not in cols:   # additive migration for pre-existing VPS databases
            self._conn.execute("ALTER TABLE sent_news ADD COLUMN sent_at TEXT")
```

Replace `news_mark_sent` and add `prune_news`:

```python
    def news_mark_sent(self, disclosure_id: str, *, sent_at: str | None = None) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO sent_news (disclosure_id, sent_at) VALUES (?, ?)",
            (disclosure_id, sent_at),
        )
        self._conn.commit()

    def prune_news(self, older_than_days: int, *, now) -> None:
        from datetime import timedelta

        cutoff = (now - timedelta(days=older_than_days)).strftime("%Y-%m-%d")
        self._conn.execute(
            "DELETE FROM sent_news WHERE sent_at IS NOT NULL AND sent_at < ?", (cutoff,)
        )
        self._conn.execute("DELETE FROM sent_news_titles WHERE date_str < ?", (cutoff,))
        self._conn.commit()
```

In `news_breakout/news/feed.py`, both successful-send markings become:

```python
        store.news_mark_sent(d.disclosure_id, sent_at=f"{now:%Y-%m-%d}")
```

```python
        store.news_mark_sent(it.url, sent_at=f"{now:%Y-%m-%d}")
```

(The near-dup suppression marking in `run_portal_feed` also stamps `sent_at`; the outage-key marking in `run_news_feed` stays unstamped on purpose — date-keyed, self-limiting.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dedup.py tests/test_news_feed.py tests/test_news_dedup.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/alerts/dedup.py news_breakout/news/feed.py tests/test_dedup.py
git commit -m "feat(alerts): sent_at stamping and retention pruning for news dedup"
```

---

### Task 17: `scripts/build_name_map.py` generator

**Files:**
- Create: `scripts/build_name_map.py`
- Test: `tests/test_build_name_map.py`

**Interfaces:**
- Produces: `normalize_name(raw: str) -> str` and `build_map(records: list[dict]) -> dict[str, str]` (importable from `scripts.build_name_map`); CLI `python scripts/build_name_map.py [--input local.json] [--out config/name_map.yaml] [--url <override>]`.

- [ ] **Step 1: Write the failing tests**

```python
from scripts.build_name_map import build_map, normalize_name


def test_normalize_strips_legal_words_and_punct():
    assert normalize_name("PT Aneka Tambang Tbk.") == "aneka tambang"
    assert normalize_name("PT Timah (Persero) Tbk") == "timah"


def test_build_map_skips_short_names_and_missing_tickers():
    records = [
        {"KodeEmiten": "ANTM", "NamaEmiten": "PT Aneka Tambang Tbk"},
        {"KodeEmiten": "ABC", "NamaEmiten": "PT AB Tbk"},        # name < 4 chars after strip
        {"KodeEmiten": "", "NamaEmiten": "PT Tanpa Kode Tbk"},   # no ticker
        {"Kode_Emiten": "TINS", "Nama_Emiten": "PT Timah Tbk"},  # alternate keys
    ]
    m = build_map(records)
    assert m == {"aneka tambang": "ANTM", "timah": "TINS"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_name_map.py -v`
Expected: FAIL (`ModuleNotFoundError: scripts.build_name_map`)

Check first that `scripts/` is importable in tests (`tests/test_fetch_to_supabase.py` already imports from `scripts.fetch_to_supabase`, so the pattern exists — copy whatever path/packaging convention that test uses).

- [ ] **Step 3: Implement** (`scripts/build_name_map.py`)

```python
"""Generate config/name_map.yaml (lowercase company name -> ticker) from IDX profiles.

Run manually on a machine that can reach idx.co.id (or set IDX_PROXY):
    python scripts/build_name_map.py
    python scripts/build_name_map.py --input profiles.json   # offline: pre-downloaded JSON
The endpoint occasionally shifts; --url overrides it without a code change.
Inline `portal.name_map` entries in config.yaml always override this file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_DEFAULT_URL = ("https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles"
                "?emitenType=s&start=0&length=1000")
_LEGAL_WORDS = {"pt", "tbk", "persero", "tbk.", "(persero)"}
_MIN_NAME_LEN = 4


def normalize_name(raw: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", (raw or "").lower())
    kept = [t for t in tokens if t not in _LEGAL_WORDS]
    return " ".join(kept)


def _first(record: dict, keys: list[str]) -> str:
    for k in keys:
        v = record.get(k)
        if v:
            return str(v).strip()
    return ""


def build_map(records: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        ticker = _first(rec, ["KodeEmiten", "Kode_Emiten", "kodeEmiten", "Kode"]).upper()
        name = normalize_name(_first(rec, ["NamaEmiten", "Nama_Emiten", "NamaPerusahaan", "Nama"]))
        if not ticker or len(name) < _MIN_NAME_LEN:
            continue
        out[name] = ticker
    return out


def _fetch(url: str, proxy: str) -> list[dict]:
    from news_breakout.news.idx_source import _HEADERS, _PAGE
    from curl_cffi import requests as creq

    kwargs = {"impersonate": "chrome120"}
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    session = creq.Session(**kwargs)
    try:
        session.get(_PAGE, headers=_HEADERS, timeout=30)  # warm up Cloudflare cookies
    except Exception:  # noqa: BLE001
        pass
    data = json.loads(session.get(url, headers=_HEADERS, timeout=30).text)
    for key in ("data", "Data", "Results", "Replies"):
        if isinstance(data, dict) and isinstance(data.get(key), list):
            return data[key]
    return data if isinstance(data, list) else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="local JSON file instead of hitting the IDX API")
    ap.add_argument("--out", default="config/name_map.yaml")
    ap.add_argument("--url", default=_DEFAULT_URL)
    args = ap.parse_args()

    if args.input:
        raw = json.loads(open(args.input, encoding="utf-8").read())
        records = raw if isinstance(raw, list) else next(
            (v for v in raw.values() if isinstance(v, list)), [])
    else:
        records = _fetch(args.url, os.environ.get("IDX_PROXY", ""))
    mapping = build_map(records)
    if not mapping:
        print("No records parsed — check --url/--input (endpoint may have shifted).")
        return 1
    lines = [f"{name}: {tk}" for name, tk in sorted(mapping.items())]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("# generated by scripts/build_name_map.py — inline name_map overrides this\n")
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {len(mapping)} names -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_name_map.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_name_map.py tests/test_build_name_map.py
git commit -m "feat(news): offline generator for config/name_map.yaml from IDX profiles"
```

---

### Task 18: Serve wiring — cache, gating, streak, prune

**Files:**
- Modify: `serve.py`
- Test: `tests/test_serve_wiring.py`

**Interfaces:**
- Consumes: `DisclosureCache` (Task 5), `should_poll_news` (Task 7), `run_news_feed(failure_streak=...)` (Task 6), `prune_news` (Task 16).
- Produces: `build_news_job(settings, store, log, cache) -> callable` in `serve.py`; `main()` builds one `DisclosureCache` and injects `cache.fetch` into the news job AND the scan/daily jobs' `disclosure_fetcher`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_serve_wiring.py`; reuse that file's existing settings/monkeypatch helpers)

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import serve
from news_breakout.alerts.dedup import DedupStore

WIB = ZoneInfo("Asia/Jakarta")


class _FakeCache:
    def __init__(self):
        self.consecutive_failures = 0
        self.calls = 0

    def fetch(self, page_size, *, now, proxy="", retries=None, **_):
        self.calls += 1
        return []


def test_news_job_gates_offhours_and_wires_cache(monkeypatch):
    settings = _settings()  # this file's existing helper; market_open="09:00", close="16:00"
    store = DedupStore(":memory:")
    cache = _FakeCache()
    seen = {"feed": 0, "portal": 0, "prune": 0}

    def fake_feed(s, st, *, now, fetcher=None, failure_streak=0, **_):
        seen["feed"] += 1
        assert fetcher == cache.fetch
        assert callable(failure_streak)
        return []

    def fake_portal(s, st, *, now, **_):
        seen["portal"] += 1
        return []

    monkeypatch.setattr(serve, "run_news_feed", fake_feed)
    monkeypatch.setattr(serve, "run_portal_feed", fake_portal)
    monkeypatch.setattr(DedupStore, "prune_news",
                        lambda self, days, *, now: seen.__setitem__("prune", seen["prune"] + 1))

    evening = datetime(2026, 7, 22, 20, 0, tzinfo=WIB)
    clock = {"now": evening}
    job = serve.build_news_job(settings, store, _log(), cache,
                               now_fn=lambda: clock["now"])
    job()                                        # first off-hours tick runs
    clock["now"] = evening + timedelta(minutes=15)
    job()                                        # second tick within 60m is gated
    assert seen["feed"] == 1 and seen["portal"] == 1 and seen["prune"] == 1
    clock["now"] = evening + timedelta(minutes=61)
    job()
    assert seen["feed"] == 2
    store.close()
```

(`_log()` = a `logging.getLogger` or whatever logger helper the file already uses; add a trivial one if absent.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_serve_wiring.py -v -k news_job`
Expected: FAIL (`AttributeError: serve.build_news_job`)

- [ ] **Step 3: Implement**

In `serve.py`, add imports:

```python
from news_breakout.news.disclosure_cache import DisclosureCache
from news_breakout.scheduling.scheduler import should_scan_now, build_scheduler, should_poll_news
```

Add `build_news_job` (after `build_scan_job`):

```python
def build_news_job(settings, store, log, cache, *, now_fn=None):
    if now_fn is None:
        now_fn = lambda: datetime.now(WIB)  # noqa: E731
    last_run = {"t": None}

    def news_job() -> None:
        now = now_fn()
        if not should_poll_news(now, last_run["t"],
                                market_open=should_scan_now(now, settings),
                                offhours_minutes=settings.poll_interval_offhours_minutes):
            return
        last_run["t"] = now
        sent = run_news_feed(settings, store, now=now, fetcher=cache.fetch,
                             failure_streak=lambda: cache.consecutive_failures)
        portal_sent = run_portal_feed(settings, store, now=now)
        store.prune_news(settings.news_dedup_retention_days, now=now)
        log.info("news poll complete; sent: %d, portal sent: %d", len(sent), len(portal_sent))

    return news_job
```

In `main()`: build the cache once and wire everything:

```python
    cache = DisclosureCache(settings.news_booster_page_size,
                            settings.news_fetch_cache_ttl_minutes)
    scan_job = build_scan_job(settings, store, log, cache)
    news_job = build_news_job(settings, store, log, cache)
```

Update `build_scan_job(settings, store, log, cache)` to pass `disclosure_fetcher=cache.fetch` into `run.run_scan(...)`, and both daily jobs to pass `disclosure_fetcher=cache.fetch` into `run_daily_scan(...)`. Delete the old inline `def news_job()` from `main()`.

`build_scan_job` gained a parameter — update every existing call site and any existing `build_scan_job` tests in `tests/test_serve_wiring.py` to pass a `_FakeCache()` (or a real `DisclosureCache` with an injected fetcher).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_serve_wiring.py tests/test_run_smoke.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all PASS

```bash
git add serve.py tests/test_serve_wiring.py
git commit -m "feat(news): wire shared disclosure cache, poll gating, and pruning into serve"
```
