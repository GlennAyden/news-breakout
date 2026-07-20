# Two-Shift Universe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily-shift breakout scan — a broad, liquidity-filtered IDX universe scanned once/day on daily bars — alongside the unchanged intraday shift.

**Architecture:** A static `config/idx_all.txt` (~960 tickers) is fetched 1D-only once/day into Supabase (GitHub Actions `--mode daily`), then a VPS daily scan reads it, liquidity-filters (≥Rp2B, ≥Rp50) minus the intraday tier, evaluates 1D breakouts via the existing engine, and alerts: 16:30 WIB = top-15 individual alerts (deduped); 08:00 WIB = one digest. A small refactor extracts `evaluate_scan` (+ a `max_alerts` cap on `scan_once`) so both shifts share the breakout engine.

**Tech Stack:** Python 3.12, pytest (TDD), pandas, APScheduler, yfinance (GitHub side), Supabase reader (VPS side), Telegram Bot API.

## Global Constraints

- Run tests: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`.
- TDD: failing test first, watch it fail, minimal implementation, watch it pass, commit.
- No network in tests — inject `daily_fetcher` / `sender` / `disclosure_fetcher` / `downloader`.
- Liquidity floor daily: `min_daily_value = 2_000_000_000` (Rp2B), `min_price = 50`. Daily cap `max_alerts = 15`. Daily `history_days = 90`.
- Daily tier EXCLUDES the intraday tier (`watchlist ∪ universe_candidates`).
- Reminder recomputes (no stored state); digest deduped once/day via `daily-digest-{YYYY-MM-DD}`.
- Daily alerts + morning digest go to the **breakout** channel (`telegram_breakout_chat_id`).
- Branch: `feat/two-shift-universe` (already checked out; baseline `2d2004d`).
- Existing signatures: `resolve_scan_tickers(watchlist, candidates, daily_data, min_price, min_daily_value)`; `filter_liquid_universe(candidates, daily_data, min_price, min_daily_value, value_window=20)`; `evaluate_ticker(ticker, frames, *, donchian_lookback, rvol_window, rvol_threshold, now)`; `make_daily_fetcher(settings) -> (tickers, history_days) -> dict`; `recent_by_ticker(disclosures, *, now, window_hours)`; `DedupStore.news_already_sent/news_mark_sent`, `.already_sent/.mark_sent`.

---

### Task 1: Config — daily_shift settings

**Files:**
- Modify: `news_breakout/config.py`
- Modify: `config/config.example.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces on `Settings`: `daily_shift_enabled: bool = True`, `daily_shift_universe_file: str = "config/idx_all.txt"`, `daily_shift_min_daily_value: float = 2_000_000_000`, `daily_shift_min_price: float = 50`, `daily_shift_max_alerts: int = 15`, `daily_shift_history_days: int = 90`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:
```python
def test_load_settings_reads_daily_shift(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n"
        "daily_shift: {enabled: false, universe_file: config/x.txt, min_daily_value: 3000000000, "
        "min_price: 100, max_alerts: 10, history_days: 60}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=a:b\nTELEGRAM_BREAKOUT_CHAT_ID=-1\nTELEGRAM_NEWS_CHAT_ID=-2\n",
                   encoding="utf-8")
    s = load_settings(str(cfg), str(env))
    assert s.daily_shift_enabled is False
    assert s.daily_shift_universe_file == "config/x.txt"
    assert s.daily_shift_min_daily_value == 3000000000
    assert s.daily_shift_min_price == 100
    assert s.daily_shift_max_alerts == 10
    assert s.daily_shift_history_days == 60


def test_load_settings_daily_shift_defaults_when_absent(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=a:b\nTELEGRAM_BREAKOUT_CHAT_ID=-1\nTELEGRAM_NEWS_CHAT_ID=-2\n",
                   encoding="utf-8")
    s = load_settings(str(cfg), str(env))
    assert s.daily_shift_enabled is True
    assert s.daily_shift_universe_file == "config/idx_all.txt"
    assert s.daily_shift_min_daily_value == 2_000_000_000
    assert s.daily_shift_min_price == 50
    assert s.daily_shift_max_alerts == 15
    assert s.daily_shift_history_days == 90
```

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL — `Settings` has no `daily_shift_enabled`.

- [ ] **Step 3: Add Settings fields + loader wiring**

In `news_breakout/config.py`, add to `Settings` (after `sentiment_min_confidence`):
```python
    daily_shift_enabled: bool = True
    daily_shift_universe_file: str = "config/idx_all.txt"
    daily_shift_min_daily_value: float = 2_000_000_000
    daily_shift_min_price: float = 50
    daily_shift_max_alerts: int = 15
    daily_shift_history_days: int = 90
```
In `load_settings`, after `sentiment = raw.get("sentiment", {})` add:
```python
    daily_shift = raw.get("daily_shift", {})
```
and add these keyword args to the `Settings(...)` construction (after `sentiment_min_confidence=...`):
```python
        daily_shift_enabled=daily_shift.get("enabled", True),
        daily_shift_universe_file=daily_shift.get("universe_file", "config/idx_all.txt"),
        daily_shift_min_daily_value=daily_shift.get("min_daily_value", 2_000_000_000),
        daily_shift_min_price=daily_shift.get("min_price", 50),
        daily_shift_max_alerts=daily_shift.get("max_alerts", 15),
        daily_shift_history_days=daily_shift.get("history_days", 90),
```

- [ ] **Step 4: Update the example config**

In `config/config.example.yaml`, add a new top-level section (after the `sentiment:` block):
```yaml
daily_shift:
  enabled: true
  universe_file: config/idx_all.txt   # broad IDX list (one ticker/line), scanned 1D-only once/day
  min_daily_value: 2000000000         # Rp2 B avg daily value floor
  min_price: 50
  max_alerts: 15                      # top-N individual alerts at 16:30 WIB
  history_days: 90                    # daily bars fetched for the broad tier
```

- [ ] **Step 5: Run to verify pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add news_breakout/config.py config/config.example.yaml tests/test_config.py
git commit -m "feat(config): daily_shift settings"
```

---

### Task 2: `load_daily_universe`

**Files:**
- Create: `news_breakout/signals/daily_shift.py`
- Test: `tests/test_daily_shift.py`

**Interfaces:**
- Produces: `load_daily_universe(path: str) -> list[str]` — reads one ticker per line, ignores blank lines and `#` comments, uppercases, de-dupes order-preserving. Missing file → `[]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_daily_shift.py`:
```python
from news_breakout.signals.daily_shift import load_daily_universe


def test_load_daily_universe_parses_and_dedupes(tmp_path):
    f = tmp_path / "idx.txt"
    f.write_text("# header comment\nANTM\nbbri\n\nANTM\n  TLKM  \n# trailing\n", encoding="utf-8")
    assert load_daily_universe(str(f)) == ["ANTM", "BBRI", "TLKM"]


def test_load_daily_universe_missing_file_returns_empty(tmp_path):
    assert load_daily_universe(str(tmp_path / "nope.txt")) == []
```

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_daily_shift.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `news_breakout/signals/daily_shift.py`:
```python
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("news_breakout")


def load_daily_universe(path: str) -> list[str]:
    """Read the broad daily-shift ticker list (one code per line; '#' comments
    and blanks ignored). Uppercased, de-duped, order-preserving. Missing file -> []."""
    p = Path(path)
    if not p.exists():
        logger.warning("daily shift: universe file not found: %s", path)
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().upper()
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_daily_shift.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news_breakout/signals/daily_shift.py tests/test_daily_shift.py
git commit -m "feat(scan): load_daily_universe"
```

---

### Task 3: Extract `evaluate_scan` + `scan_once` cap (refactor)

**Files:**
- Create: `news_breakout/signals/scan_core.py`
- Modify: `run.py` (remove `scan_once` body; import from scan_core; keep `run_scan`/`main`)
- Test: `tests/test_scan_core.py`, existing `tests/test_run_smoke.py` (must stay green)

**Interfaces:**
- Consumes: `evaluate_ticker` (signals.engine), `resample_ohlcv` (data.resample), `send_message`, `format_ticker_alert`, `DedupStore`, `TickerAlert`.
- Produces:
  - `evaluate_scan(settings, daily_data, intraday_data, *, now, catalysts, tickers) -> list[TickerAlert]` (sorted by `(quality_score, max_rvol)` desc; no send).
  - `scan_once(settings, daily_data, intraday_data, store, *, now, sender=send_message, catalysts=None, tickers=None, max_alerts=None) -> list[str]` (moved here; `max_alerts` caps sends to the top N; `run.scan_once` re-exports it).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scan_core.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.fixtures import make_ohlcv
from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
from news_breakout.signals.scan_core import evaluate_scan, scan_once

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)


def _settings(**over):
    base = dict(
        watchlist=["ANTM"], donchian_lookback=3, rvol_threshold=2.0, rvol_window=3,
        history_days=120, range_lookback=3, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[], universe_candidates=[], min_price=50,
        min_daily_value=1e9, telegram_news_chat_id="-2", curated_keywords=["dividen"],
        disclosure_page_size=50, news_poll_interval_minutes=60, idx_proxy="",
    )
    base.update(over)
    return Settings(**base)


def _breakout(close):
    return make_ohlcv(highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
                      closes=[100, 100, 100, close], volumes=[100, 100, 100, 300])


def test_evaluate_scan_returns_sorted_alerts_without_sending():
    daily = {"HIGHX": _breakout(121), "LOWX": _breakout(111)}
    alerts = evaluate_scan(_settings(), daily, {}, now=NOW, catalysts={},
                           tickers=["LOWX", "HIGHX"])
    assert [a.ticker for a in alerts] == ["HIGHX", "LOWX"]  # higher extension ranks first


def test_scan_once_max_alerts_caps_sends():
    daily = {"A": _breakout(121), "B": _breakout(120), "C": _breakout(119)}
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    out = scan_once(_settings(), daily, {}, store, now=NOW, sender=sender,
                    tickers=["A", "B", "C"], max_alerts=2)
    assert len(out) == 2 and len(sent) == 2
    store.close()
```

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_scan_core.py -q`
Expected: FAIL — module `news_breakout.signals.scan_core` not found.

- [ ] **Step 3: Create scan_core.py (move + extend)**

Create `news_breakout/signals/scan_core.py`:
```python
from __future__ import annotations

from news_breakout.config import Settings
from news_breakout.data.resample import resample_ohlcv
from news_breakout.signals.engine import evaluate_ticker
from news_breakout.alerts.dedup import DedupStore
from news_breakout.alerts.formatter import format_ticker_alert
from news_breakout.alerts.telegram import send_message


def evaluate_scan(settings: Settings, daily_data, intraday_data, *, now, catalysts, tickers):
    """Evaluate `tickers` over available frames; return alerts sorted by
    (quality_score, max_rvol) desc. No sending, no dedup."""
    alerts = []
    for ticker in tickers:
        frames = {}
        if ticker in daily_data:
            frames["1D"] = daily_data[ticker]
        if ticker in intraday_data:
            frames["1H"] = intraday_data[ticker]
            frames["4H"] = resample_ohlcv(intraday_data[ticker], "4h")
        if not frames:
            continue
        alert = evaluate_ticker(
            ticker, frames,
            donchian_lookback=settings.donchian_lookback, rvol_window=settings.rvol_window,
            rvol_threshold=settings.rvol_threshold, now=now,
        )
        if alert is not None:
            if alert.ticker in catalysts:
                alert.priority += settings.news_priority_boost
                alert.quality_score += settings.news_priority_boost
            alerts.append(alert)
    alerts.sort(key=lambda a: (a.quality_score, a.max_rvol), reverse=True)
    return alerts


def scan_once(settings: Settings, daily_data, intraday_data, store: DedupStore,
              *, now, sender=send_message, catalysts=None, tickers=None,
              max_alerts=None) -> list[str]:
    if catalysts is None:
        catalysts = {}
    scan_list = settings.watchlist if tickers is None else tickers
    alerts = evaluate_scan(settings, daily_data, intraday_data, now=now,
                           catalysts=catalysts, tickers=scan_list)
    if max_alerts is not None:
        alerts = alerts[:max_alerts]

    alerted: list[str] = []
    for alert in alerts:
        if "1D" in {s.timeframe for s in alert.signals}:
            date_str = daily_data[alert.ticker].index[-1].strftime("%Y-%m-%d")
        else:
            date_str = now.strftime("%Y-%m-%d")
        if store.already_sent(alert.ticker, "aggregated", "MULTI", date_str):
            continue
        catalyst = catalysts.get(alert.ticker)
        text = format_ticker_alert(alert, catalyst=catalyst)
        if not sender(settings.telegram_bot_token, settings.telegram_breakout_chat_id,
                      text, dry_run=settings.dry_run):
            continue
        store.mark_sent(alert.ticker, "aggregated", "MULTI", date_str)
        alerted.append(alert.ticker)
    return alerted
```

- [ ] **Step 4: Rewire run.py to import from scan_core**

In `run.py`, remove the entire `scan_once` function body (lines defining `def scan_once(...)` through its `return alerted`). Replace the imports block so run.py imports the moved functions. Specifically, delete the `scan_once` def and add, near the other imports at the top of `run.py`:
```python
from news_breakout.signals.scan_core import evaluate_scan, scan_once
```
Remove now-unused imports from `run.py` that were only used by `scan_once` IF they are unused after removal: `resample_ohlcv`, `evaluate_ticker`, `format_ticker_alert`. (Keep `send_message` — `run_scan` uses it as a default; keep `DedupStore`, `Settings`.) `run_scan` still calls `scan_once(...)` — now the imported one. Do not change `run_scan` or `main`.

- [ ] **Step 5: Run to verify pass (new + existing)**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_scan_core.py tests/test_run_smoke.py -q`
Expected: PASS — new scan_core tests pass AND all existing `test_run_smoke.py` tests (which call `run.scan_once` / `run.run_scan`) stay green because `run.scan_once` is the re-exported function with identical behavior at `max_alerts=None`.

- [ ] **Step 6: Full suite + commit**

```bash
PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q
git add news_breakout/signals/scan_core.py run.py tests/test_scan_core.py
git commit -m "refactor(scan): extract evaluate_scan + scan_once max_alerts cap"
```

---

### Task 4: `format_daily_digest`

**Files:**
- Modify: `news_breakout/alerts/formatter.py`
- Test: `tests/test_formatter.py`

**Interfaces:**
- Consumes: `TickerAlert`, `_primary_signal`, `_rupiah` (same module).
- Produces: `format_daily_digest(alerts: list[TickerAlert], *, now) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_formatter.py`:
```python
def test_format_daily_digest_ranks_and_lists(make_alert):
    # make_alert is provided by the existing test module; if absent, build a TickerAlert inline.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from news_breakout.models import TickerAlert, BreakoutSignal
    from news_breakout.alerts.formatter import format_daily_digest
    WIB = ZoneInfo("Asia/Jakarta")
    now = datetime(2026, 7, 20, 16, 30, tzinfo=WIB)

    def alert(tkr, score, price, level):
        sig = BreakoutSignal(ticker=tkr, timeframe="1D", signal_type="resistance_breakout",
                             price=price, level=level, rvol=3.0, pct_change=5.0, timestamp=now)
        a = TickerAlert(ticker=tkr, signals=[sig], priority=3.0, max_rvol=3.0)
        a.quality_score = score
        a.above_sma50 = True
        a.ext_pct = 5.0
        return a

    msg = format_daily_digest([alert("AAA", 9.0, 1000, 950), alert("BBB", 4.0, 500, 490)], now=now)
    assert "Watchlist Pagi" in msg
    assert "1. AAA" in msg and "2. BBB" in msg
    assert "AAA" in msg and "BBB" in msg
    assert "20 Jul 2026" in msg
```
Note: if `tests/test_formatter.py` has no `make_alert` fixture, drop the unused `make_alert` parameter from the signature — the test builds alerts inline.

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_formatter.py::test_format_daily_digest_ranks_and_lists -q`
Expected: FAIL — `format_daily_digest` not defined.

- [ ] **Step 3: Add the formatter**

In `news_breakout/alerts/formatter.py`, append:
```python
def format_daily_digest(alerts: list[TickerAlert], *, now: datetime) -> str:
    lines = [
        f"🗓️ Watchlist Pagi — EOD Breakout ({now:%d %b %Y})",
        "━━━━━━━━━━━━━━━━━━━",
    ]
    for i, a in enumerate(alerts, 1):
        primary = _primary_signal(a.signals)
        trend = "↑" if a.above_sma50 is True else ("↓" if a.above_sma50 is False else "·")
        lines.append(
            f"{i}. {a.ticker} · 🏅{a.quality_score:.1f} {trend} · "
            f"{_rupiah(primary.price)} (level {_rupiah(primary.level)})"
        )
    lines.append("⏱️ ringkasan breakout harian · delay data ~15 mnt")
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_formatter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news_breakout/alerts/formatter.py tests/test_formatter.py
git commit -m "feat(alerts): daily EOD breakout digest formatter"
```

---

### Task 5: `run_daily_scan` orchestration

**Files:**
- Modify: `news_breakout/signals/daily_shift.py`
- Test: `tests/test_daily_shift.py`

**Interfaces:**
- Consumes: `load_daily_universe` (same module), `resolve_scan_tickers` (data.universe), `evaluate_scan`+`scan_once` (signals.scan_core), `format_daily_digest` (alerts.formatter), `recent_by_ticker` (news.booster), `fetch_disclosures` (news.idx_source), `send_message` (alerts.telegram).
- Produces: `run_daily_scan(settings, store, *, now, mode, daily_fetcher, sender=send_message, disclosure_fetcher=fetch_disclosures) -> list[str]` (`mode` ∈ `{"detect","reminder"}`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_daily_shift.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo
from tests.fixtures import make_ohlcv
from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
from news_breakout.signals.daily_shift import run_daily_scan

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 20, 16, 30, tzinfo=WIB)


def _settings(univ_file, **over):
    base = dict(
        watchlist=["ANTM"], donchian_lookback=3, rvol_threshold=2.0, rvol_window=3,
        history_days=120, range_lookback=3, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[], universe_candidates=["BBRI"], min_price=50,
        min_daily_value=1e9, telegram_news_chat_id="-2", curated_keywords=["dividen"],
        disclosure_page_size=50, news_poll_interval_minutes=60, idx_proxy="",
        daily_shift_universe_file=univ_file, daily_shift_min_daily_value=1e9,
        daily_shift_min_price=50, daily_shift_max_alerts=15, daily_shift_history_days=90,
    )
    base.update(over)
    return Settings(**base)


def _breakout_liquid(close):
    # high value (Close*Volume) so it passes the Rp liquidity floor
    return make_ohlcv(highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
                      closes=[100, 100, 100, close],
                      volumes=[10_000_000, 10_000_000, 10_000_000, 30_000_000])


def _no_disc(page_size, *, now, proxy, retries=0):
    return []


def test_run_daily_scan_detect_excludes_intraday_and_alerts(tmp_path):
    f = tmp_path / "idx.txt"
    f.write_text("ANTM\nBBRI\nBMRI\n", encoding="utf-8")  # ANTM=watchlist, BBRI=candidate (both intraday)
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = {"ANTM": _breakout_liquid(121), "BBRI": _breakout_liquid(121), "BMRI": _breakout_liquid(121)}
    out = run_daily_scan(_settings(str(f)), store, now=NOW, mode="detect",
                         daily_fetcher=lambda tickers, days: daily, sender=sender,
                         disclosure_fetcher=_no_disc)
    assert out == ["BMRI"]         # ANTM + BBRI excluded (intraday tier); only BMRI alerts
    assert len(sent) == 1
    store.close()


def test_run_daily_scan_reminder_sends_single_digest_and_dedups(tmp_path):
    f = tmp_path / "idx.txt"
    f.write_text("BMRI\nADRO\n", encoding="utf-8")
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = {"BMRI": _breakout_liquid(121), "ADRO": _breakout_liquid(121)}
    kw = dict(daily_fetcher=lambda tickers, days: daily, sender=sender, disclosure_fetcher=_no_disc)
    first = run_daily_scan(_settings(str(f)), store, now=NOW, mode="reminder", **kw)
    assert len(sent) == 1 and "Watchlist Pagi" in sent[0]   # ONE digest, not 2 individual
    second = run_daily_scan(_settings(str(f)), store, now=NOW, mode="reminder", **kw)
    assert len(sent) == 1                                    # deduped once/day
    store.close()


def test_run_daily_scan_empty_universe_noops(tmp_path):
    store = DedupStore(":memory:")
    sent = []
    out = run_daily_scan(_settings(str(tmp_path / "missing.txt")), store, now=NOW, mode="detect",
                         daily_fetcher=lambda tickers, days: {},
                         sender=lambda *a, **k: sent.append(1) or True, disclosure_fetcher=_no_disc)
    assert out == [] and sent == []
    store.close()
```

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_daily_shift.py -q`
Expected: FAIL — `run_daily_scan` not defined.

- [ ] **Step 3: Implement `run_daily_scan`**

In `news_breakout/signals/daily_shift.py`, add imports at the top and the function:
```python
from news_breakout.data.universe import resolve_scan_tickers
from news_breakout.signals.scan_core import evaluate_scan, scan_once
from news_breakout.alerts.formatter import format_daily_digest
from news_breakout.alerts.telegram import send_message
from news_breakout.news.booster import recent_by_ticker
from news_breakout.news.idx_source import fetch_disclosures


def run_daily_scan(settings, store, *, now, mode, daily_fetcher,
                   sender=send_message, disclosure_fetcher=fetch_disclosures) -> list[str]:
    broad = load_daily_universe(settings.daily_shift_universe_file)
    if not broad:
        return []
    daily = daily_fetcher(broad, settings.daily_shift_history_days)
    intraday_set = set(settings.watchlist) | set(settings.universe_candidates)
    liquid = resolve_scan_tickers([], broad, daily,
                                  settings.daily_shift_min_price, settings.daily_shift_min_daily_value)
    daily_tickers = [t for t in liquid if t not in intraday_set]

    try:
        disc = disclosure_fetcher(settings.disclosure_page_size, now=now,
                                  proxy=settings.idx_proxy, retries=0)
    except Exception:  # noqa: BLE001 — a disclosure fetch failure must not abort the scan
        disc = []
    catalysts = recent_by_ticker(disc, now=now, window_hours=settings.news_booster_window_hours)

    if mode == "detect":
        return scan_once(settings, daily, {}, store, now=now, sender=sender,
                         catalysts=catalysts, tickers=daily_tickers,
                         max_alerts=settings.daily_shift_max_alerts)

    # mode == "reminder": recompute the same shortlist, send ONE digest, dedup per day
    alerts = evaluate_scan(settings, daily, {}, now=now, catalysts=catalysts,
                           tickers=daily_tickers)[: settings.daily_shift_max_alerts]
    if not alerts:
        return []
    key = f"daily-digest-{now:%Y-%m-%d}"
    if store.news_already_sent(key):
        return []
    if sender(settings.telegram_bot_token, settings.telegram_breakout_chat_id,
              format_daily_digest(alerts, now=now), dry_run=settings.dry_run):
        store.news_mark_sent(key)
    return [a.ticker for a in alerts]
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_daily_shift.py -q`
Expected: PASS (5 tests: 2 from Task 2 + 3 here).

- [ ] **Step 5: Full suite + commit**

```bash
PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q
git add news_breakout/signals/daily_shift.py tests/test_daily_shift.py
git commit -m "feat(scan): daily-shift scan (detect alerts + reminder digest)"
```

---

### Task 6: `fetch_to_supabase --mode daily`

**Files:**
- Modify: `scripts/fetch_to_supabase.py`
- Test: `tests/test_fetch_to_supabase.py`

**Interfaces:**
- Produces: `fetch_all(tickers, history_days, intraday_days, downloader, *, mode="intraday")` — `intraday`: plan `[1d, 60m]`; `daily`: plan `[1d]` only. `main()` reads `--mode` (default `intraday`); `daily` mode loads tickers from `daily_shift.universe_file` and uses `daily_shift.history_days`. Downloads are chunked (≤200 tickers/call).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fetch_to_supabase.py`:
```python
def test_fetch_all_daily_mode_is_1d_only():
    from scripts.fetch_to_supabase import fetch_all
    calls = []

    def downloader(jk, **kw):
        calls.append(kw["interval"])
        import pandas as pd
        idx = pd.date_range("2026-07-13", periods=3, freq="D")
        cols = pd.MultiIndex.from_product([[jk[0]], ["Open", "High", "Low", "Close", "Volume"]])
        return pd.DataFrame([[1, 2, 0.5, 1.5, 100]] * 3, index=idx, columns=cols)

    rows = fetch_all(["ANTM"], 90, 60, downloader, mode="daily")
    assert calls == ["1d"]                       # only the daily interval requested
    assert all(r["interval"] == "1d" for r in rows)


def test_fetch_all_intraday_mode_is_1d_and_60m():
    from scripts.fetch_to_supabase import fetch_all
    calls = []

    def downloader(jk, **kw):
        calls.append(kw["interval"])
        import pandas as pd
        idx = pd.date_range("2026-07-13", periods=3, freq="D")
        cols = pd.MultiIndex.from_product([[jk[0]], ["Open", "High", "Low", "Close", "Volume"]])
        return pd.DataFrame([[1, 2, 0.5, 1.5, 100]] * 3, index=idx, columns=cols)

    fetch_all(["ANTM"], 120, 60, downloader)     # default mode
    assert calls == ["1d", "60m"]
```
(If `tests/test_fetch_to_supabase.py` already stubs a downloader differently, mirror that module's existing downloader shape instead of the inline one above — the assertion on `calls`/`interval` is the point.)

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_fetch_to_supabase.py -q`
Expected: FAIL — `fetch_all()` got an unexpected keyword argument `mode`.

- [ ] **Step 3: Add mode + chunking**

In `scripts/fetch_to_supabase.py`:

Change `fetch_all` signature and plan selection:
```python
_FETCH_CHUNK = 200


def fetch_all(watchlist: list, history_days: int, intraday_days: int, downloader,
              *, mode: str = "intraday") -> list:
    if mode == "daily":
        plan = [("1d", f"{history_days}d", "1d")]
    else:
        plan = [("1d", f"{history_days}d", "1d"), ("60m", f"{intraday_days}d", "60m")]
    all_rows: list = []
    for store_iv, period, yf_iv in plan:
        for i in range(0, len(watchlist), _FETCH_CHUNK):
            batch = watchlist[i:i + _FETCH_CHUNK]
            jk = [f"{t}.JK" for t in batch]
            raw = downloader(
                jk, period=period, interval=yf_iv, group_by="ticker",
                auto_adjust=False, progress=False, threads=True,
            )
            for t in batch:
                try:
                    sub = raw[f"{t}.JK"]
                except (KeyError, TypeError):
                    continue
                sub = sub[[c for c in _COLUMNS if c in sub.columns]].dropna(how="all")
                if sub.empty:
                    continue
                sub = sub[~sub.index.duplicated(keep="last")]
                all_rows.extend(to_rows(sub[_COLUMNS], t, store_iv))
    return all_rows
```

Add a daily-universe loader (reuse the same parsing rules as `load_daily_universe` — standalone so GitHub Actions needs no package import):
```python
def load_daily_universe(path: str) -> list:
    import os
    if not os.path.exists(path):
        return []
    out, seen = [], set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip().upper()
            if line and line not in seen:
                seen.add(line)
                out.append(line)
    return out
```

Update `load_config` to also return the daily-shift knobs:
```python
def load_config(path: str = _CONFIG):
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    data = raw.get("data", {})
    universe_candidates = raw.get("universe", {}).get("candidates", [])
    ds = raw.get("daily_shift", {})
    return (raw["watchlist"], data["history_days"], data["intraday_period_days"],
            universe_candidates, ds)
```

Update `main()` to branch on `--mode`:
```python
def main() -> None:
    import argparse
    import yfinance as yf

    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["intraday", "daily"], default="intraday")
    args = ap.parse_args()

    url = _normalize_supabase_url(os.environ["SUPABASE_URL"])
    key = os.environ["SUPABASE_KEY"].strip()
    watchlist, history_days, intraday_days, universe_candidates, ds = load_config()

    if args.mode == "daily":
        tickers = load_daily_universe(ds.get("universe_file", "config/idx_all.txt"))
        hist = ds.get("history_days", 90)
        rows = fetch_all(tickers, hist, intraday_days, yf.download, mode="daily")
    else:
        tickers = list(dict.fromkeys(watchlist + universe_candidates))
        rows = fetch_all(tickers, history_days, intraday_days, yf.download)

    print(f"[{args.mode}] fetched {len(rows)} bars for {len(tickers)} tickers")
    if not rows:
        print("ERROR: 0 bars fetched — aborting upsert (likely a Yahoo outage)", file=sys.stderr)
        sys.exit(1)
    if not upsert(rows, url, key):
        print("ERROR: one or more upsert chunks failed — see warnings above", file=sys.stderr)
        sys.exit(1)
    print("upsert complete")
```

- [ ] **Step 4: Run to verify pass (new + existing)**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_fetch_to_supabase.py -q`
Expected: PASS. Existing `fetch_all` tests still pass (default mode unchanged; chunking is transparent for small inputs). If an existing test calls `load_config` and unpacks 4 values, update it to unpack 5 (`..., ds = load_config()`).

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_to_supabase.py tests/test_fetch_to_supabase.py
git commit -m "feat(fetch): --mode daily (1d-only broad universe) + chunked download"
```

---

### Task 7: Scheduler + serve wiring

**Files:**
- Modify: `news_breakout/scheduling/scheduler.py`
- Modify: `serve.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Produces: `build_scheduler(settings, *, scan_job, weekend_job, news_job, daily_detect_job=None, daily_reminder_job=None, tz="Asia/Jakarta")` — registers `daily_detect` (cron 16:30 Mon–Fri) and `daily_reminder` (cron 08:00 Mon–Fri) only when `settings.daily_shift_enabled` and the respective job is provided.

- [ ] **Step 1: Write/adjust the failing tests**

In `tests/test_scheduler.py`, REPLACE `test_build_scheduler_registers_two_jobs` with:
```python
def test_build_scheduler_core_jobs_without_daily():
    sched = build_scheduler(_settings(daily_shift_enabled=False),
                            scan_job=lambda: None, weekend_job=lambda: None, news_job=lambda: None)
    assert {j.id for j in sched.get_jobs()} == {"scan", "weekend", "news"}


def test_build_scheduler_registers_daily_jobs_when_enabled():
    sched = build_scheduler(_settings(daily_shift_enabled=True),
                            scan_job=lambda: None, weekend_job=lambda: None, news_job=lambda: None,
                            daily_detect_job=lambda: None, daily_reminder_job=lambda: None)
    assert {j.id for j in sched.get_jobs()} == {
        "scan", "weekend", "news", "daily_detect", "daily_reminder"}
```
(The `_settings` helper in this file doesn't set `daily_shift_enabled`; passing it via `**over` works once the Settings field from Task 1 exists.)

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_scheduler.py -q`
Expected: FAIL — `build_scheduler()` got an unexpected keyword argument `daily_detect_job`.

- [ ] **Step 3: Extend build_scheduler**

Replace `build_scheduler` in `news_breakout/scheduling/scheduler.py` with:
```python
def build_scheduler(settings, *, scan_job, weekend_job, news_job,
                    daily_detect_job=None, daily_reminder_job=None,
                    tz: str = "Asia/Jakarta") -> BlockingScheduler:
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(scan_job, "interval", minutes=settings.scan_interval_minutes, id="scan")
    sched.add_job(weekend_job, "cron", day_of_week=settings.weekend_scan_day, hour=8, id="weekend")
    sched.add_job(news_job, "interval", minutes=settings.news_poll_interval_minutes, id="news")
    if settings.daily_shift_enabled and daily_detect_job is not None:
        sched.add_job(daily_detect_job, "cron", day_of_week="mon-fri", hour=16, minute=30,
                      id="daily_detect")
    if settings.daily_shift_enabled and daily_reminder_job is not None:
        sched.add_job(daily_reminder_job, "cron", day_of_week="mon-fri", hour=8, minute=0,
                      id="daily_reminder")
    return sched
```

- [ ] **Step 4: Wire serve.py**

In `serve.py`, inside `main()` (after `news_job` is defined, before `build_scheduler` is called), add:
```python
    def daily_detect_job() -> None:
        from news_breakout.signals.daily_shift import run_daily_scan
        run_daily_scan(settings, store, now=datetime.now(WIB), mode="detect",
                       daily_fetcher=make_daily_fetcher(settings))

    def daily_reminder_job() -> None:
        from news_breakout.signals.daily_shift import run_daily_scan
        run_daily_scan(settings, store, now=datetime.now(WIB), mode="reminder",
                       daily_fetcher=make_daily_fetcher(settings))
```
and change the `build_scheduler(...)` call to pass them:
```python
    sched = build_scheduler(settings, scan_job=scan_job, weekend_job=weekend_job,
                            news_job=news_job, daily_detect_job=daily_detect_job,
                            daily_reminder_job=daily_reminder_job)
```

- [ ] **Step 5: Run to verify pass (new + existing)**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_scheduler.py tests/test_serve_wiring.py -q`
Expected: PASS. `test_serve_wiring` still passes (it only exercises `build_scan_job`).

- [ ] **Step 6: Full suite + commit**

```bash
PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q
git add news_breakout/scheduling/scheduler.py serve.py tests/test_scheduler.py
git commit -m "feat(schedule): daily_detect (16:30) + daily_reminder (08:00) jobs"
```

---

### Task 8: GitHub workflow mode + trigger script (ops)

**Files:**
- Modify: `.github/workflows/price-fetch.yml`
- Modify: `scripts/trigger_fetch.sh`

**Interfaces:** none (CI/ops). No unit test — verified during deploy (Task 10).

- [ ] **Step 1: Add a `mode` input to the workflow**

In `.github/workflows/price-fetch.yml`, change `workflow_dispatch: {}` to accept a mode input, and pass it to the script:
```yaml
  workflow_dispatch:
    inputs:
      mode:
        description: "intraday (1d+60m, watchlist∪candidates) or daily (1d, broad)"
        required: false
        default: intraday
```
And change the run step:
```yaml
      - name: Fetch prices to Supabase
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: python scripts/fetch_to_supabase.py --mode "${{ github.event.inputs.mode || 'intraday' }}"
```
(Scheduled runs have no `inputs.mode`, so the `|| 'intraday'` fallback keeps the cron behavior.)

- [ ] **Step 2: Add a mode arg to the trigger script**

In `scripts/trigger_fetch.sh`, accept an optional first arg (default `intraday`) and include it in the dispatch body. Replace the `curl` payload line's `-d '{"ref":"main"}'` with a mode-aware body:
```bash
MODE="${1:-intraday}"
```
(add near the top, after `set -euo pipefail`), and change the curl data flag to:
```bash
  -d "{\"ref\":\"main\",\"inputs\":{\"mode\":\"${MODE}\"}}")"
```
and update the success log line to `echo "$(date -u +%FT%TZ) dispatched ${WORKFLOW} (mode=${MODE})"`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/price-fetch.yml scripts/trigger_fetch.sh
git commit -m "build(ci): price-fetch mode input + trigger_fetch mode arg"
```

---

### Task 9: Seed `config/idx_all.txt` (data — controller-executed)

**Files:**
- Create: `config/idx_all.txt`

**Note:** Data task, not TDD. The controller (not a code subagent) seeds this by obtaining the current IDX listed-stock list (~950+ codes) from a reliable source (IDX listed-companies data / a verified aggregator), one bare ticker per line, `#` header comment with the source + date. Sanity-check: line count ≥ 900 and includes the existing watchlist. `load_daily_universe` already tolerates comments/blanks/case.

- [ ] **Step 1: Obtain the list + write the file** (controller)
- [ ] **Step 2: Sanity-check**

```bash
grep -vcE '^\s*(#|$)' config/idx_all.txt   # expect >= 900
```

- [ ] **Step 3: Commit**

```bash
git add config/idx_all.txt
git commit -m "data(scan): seed idx_all.txt broad IDX universe"
```

---

### Task 10: Deploy (manual — VPS + GitHub)

**Files:** none. Ops on `hermes-vps` (SHORT, spaced SSH — fail2ban) + GitHub.

- [ ] **Step 1: Merge to main + push** (after all tasks green on the branch)
- [ ] **Step 2: VPS pull**: `cd ~/news-breakout && git pull --ff-only`
- [ ] **Step 3: Add the daily fetch trigger to the VPS crontab** (16:15 WIB = 17:15 CST):
```
15 17 * * 1-5 /home/ubuntu/news-breakout/scripts/trigger_fetch.sh daily >> /home/ubuntu/news-breakout/data_cache/trigger.log 2>&1
```
(keep the existing `*/30 10-17 … intraday` line — note it now needs no arg; default is intraday.)
- [ ] **Step 4: Trigger one daily fetch now** to seed Supabase: `./scripts/trigger_fetch.sh daily` → expect `dispatched price-fetch.yml (mode=daily)`.
- [ ] **Step 5: Restart the service**: `sudo systemctl restart news-breakout && systemctl is-active news-breakout` → `active`; confirm `scheduler started; jobs: [...]` includes `daily_detect` and `daily_reminder`.
- [ ] **Step 6: Watch** the next 16:30 WIB detect + 08:00 WIB digest in the breakout channel; `journalctl -u news-breakout | grep -iE "daily"`.

---

## Self-Review

**Spec coverage:**
- D1 two shifts → Tasks 5,7 (daily scan + scheduler), intraday unchanged.
- D2 static list → Task 2 (loader) + Task 9 (seed).
- D3 explicit intraday, daily auto-filter minus intraday → Task 5 (`daily_tickers` exclusion).
- D4 liquidity floor Rp2B/Rp50 → Task 1 (config) + Task 5 (resolve_scan_tickers).
- D5 detect: top-15 individual, deduped → Task 3 (`max_alerts`) + Task 5 (`detect`).
- D6 reminder digest → Task 4 (formatter) + Task 5 (`reminder`).
- D7 recompute, digest dedup once/day → Task 5 (`daily-digest-{date}`).
- Fetch `--mode daily` + chunking (§4) → Task 6. Workflow/trigger (§4) → Task 8. VPS crontab (§3) → Task 10.
- Error handling matrix (§7) → Task 2 (missing file), Task 5 (empty universe, disclosure try/except), degradation via liquidity filter.
- Testing (§8) → each task's tests; full suite gate in Tasks 3,5,7.

**Placeholder scan:** none — every code/test step has complete code; Task 9 is explicitly a controller data task.

**Type consistency:** `evaluate_scan`/`scan_once` (T3) signatures match their T5 calls; `scan_once(..., max_alerts=…)` matches T3 definition; `load_daily_universe` (T2) used in T5; `resolve_scan_tickers([], broad, daily, min_price, min_daily_value)` matches the existing signature; `format_daily_digest(alerts, *, now)` (T4) matches the T5 call; `run_daily_scan(..., mode, daily_fetcher, sender, disclosure_fetcher)` (T5) matches the serve.py closures (T7); `build_scheduler(..., daily_detect_job, daily_reminder_job)` (T7) matches serve.py; `Settings.daily_shift_*` (T1) match all reads; `fetch_all(..., mode=)` + `load_config` 5-tuple (T6) consistent.
