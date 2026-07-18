# Milestone 3 — Always-On Scheduler + Market Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the manual one-shot scanner into an always-on service: an APScheduler-driven process that runs the multi-timeframe scan every 30 minutes during IDX trading hours (Mon–Fri, minus configured holidays), runs a weekend deep-scan, logs cleanly, and pushes results to Telegram.

**Architecture:** Builds on M1+M2. Adds (1) a pure market-calendar module (trading-day / market-open checks), (2) a liquid-universe filter (mechanism ready; candidate list empty by default), (3) a weekend-summary builder, (4) config additions + logging setup that silences yfinance's noisy warnings, (5) scheduler gating + a `build_scheduler`, and (6) a `serve.py` entrypoint that wires it together and reuses M1/M2's `scan_once`/`evaluate_ticker`/Telegram sender. The 30-minute scan covers the watchlist; the weekend deep-scan covers watchlist + filtered liquid universe on the 1D timeframe.

**Tech Stack:** Python 3.12 · `APScheduler` · `yfinance` · `pandas` · `pydantic` · `PyYAML` · `httpx` · `pytest`.

## Global Constraints

- Python **3.12**. All timestamps timezone **Asia/Jakarta (WIB)**, tz-aware. `run.py`/`serve.py` force UTF-8 stdout.
- **No API keys** (yfinance free, `.JK`). Anti-spam: one aggregated alert per (ticker, trading-date) — unchanged from M2.
- Secrets only in `.env` (git-ignored); non-secret config in `config.yaml`.
- **Scheduler timezone is Asia/Jakarta.** 30-min scan runs only when the market is open (trading day AND within session window). Holidays come from config (list of `YYYY-MM-DD`); do NOT hardcode specific IDX holiday dates.
- Default schedule/universe params (tunable via config): `market_open` **"09:00"**, `market_close` **"16:00"**, `scan_interval_minutes` **30**, `weekend_scan_day` **"sat"**, `min_price` **50**, `min_daily_value` **1000000000** (Rp 1 B), `universe_candidates` **[]** (empty).

---

## File Structure

```
news_breakout/
  scheduling/
    __init__.py        # CREATE (empty)
    market_calendar.py # CREATE: parse_holidays, is_trading_day, is_market_open
    weekend.py         # CREATE: build_weekend_summary (pure) + run_weekend_scan (integration)
    scheduler.py       # CREATE: should_scan_now, build_scheduler
  data/
    universe.py        # CREATE: filter_liquid_universe
  logging_setup.py     # CREATE: setup_logging (+ silence yfinance warnings)
  config.py            # MODIFY: add schedule/universe fields
config/config.example.yaml  # MODIFY: add schedule + universe sections
run.py                 # MODIFY: extract run_scan(settings, store, *, now, sender)
serve.py               # CREATE: long-running scheduler entrypoint
requirements.txt       # MODIFY: add APScheduler
tests/                 # CREATE test_market_calendar.py, test_universe.py, test_weekend.py, test_scheduler.py; MODIFY test_config.py
```

---

### Task 1: Market calendar

**Files:**
- Create: `news_breakout/scheduling/__init__.py` (empty)
- Create: `news_breakout/scheduling/market_calendar.py`
- Test: `tests/test_market_calendar.py`

**Interfaces:**
- Produces:
  - `parse_holidays(items: list[str]) -> set[datetime.date]` — parse `YYYY-MM-DD` strings.
  - `is_trading_day(d: date, holidays: set[date]) -> bool` — Mon–Fri and not a holiday.
  - `is_market_open(dt: datetime, holidays: set[date], open_str: str, close_str: str) -> bool` —
    trading day AND `open_str <= dt.time() <= close_str`.

- [ ] **Step 1: Write the failing test**

`tests/test_market_calendar.py`:
```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

from news_breakout.scheduling.market_calendar import (
    parse_holidays, is_trading_day, is_market_open,
)

WIB = ZoneInfo("Asia/Jakarta")


def test_parse_holidays():
    hs = parse_holidays(["2026-01-01", "2026-03-31"])
    assert date(2026, 1, 1) in hs and date(2026, 3, 31) in hs


def test_trading_day_weekday_vs_weekend_vs_holiday():
    hs = parse_holidays(["2026-07-17"])  # a Friday, marked holiday
    assert is_trading_day(date(2026, 7, 16), hs) is True   # Thursday
    assert is_trading_day(date(2026, 7, 18), hs) is False  # Saturday
    assert is_trading_day(date(2026, 7, 17), hs) is False  # holiday Friday


def test_market_open_within_and_outside_hours():
    hs = set()
    # 2026-07-16 is a Thursday
    assert is_market_open(datetime(2026, 7, 16, 10, 0, tzinfo=WIB), hs, "09:00", "16:00") is True
    assert is_market_open(datetime(2026, 7, 16, 8, 0, tzinfo=WIB), hs, "09:00", "16:00") is False
    assert is_market_open(datetime(2026, 7, 16, 16, 30, tzinfo=WIB), hs, "09:00", "16:00") is False
    # Saturday -> closed regardless of time
    assert is_market_open(datetime(2026, 7, 18, 10, 0, tzinfo=WIB), hs, "09:00", "16:00") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_market_calendar.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.scheduling.market_calendar'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/scheduling/__init__.py`:
```python
```
(empty file)

`news_breakout/scheduling/market_calendar.py`:
```python
from __future__ import annotations

from datetime import date, datetime, time


def parse_holidays(items: list[str]) -> set[date]:
    return {date.fromisoformat(x) for x in items}


def is_trading_day(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def is_market_open(
    dt: datetime, holidays: set[date], open_str: str, close_str: str
) -> bool:
    if not is_trading_day(dt.date(), holidays):
        return False
    return time.fromisoformat(open_str) <= dt.time() <= time.fromisoformat(close_str)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_market_calendar.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/scheduling/__init__.py news_breakout/scheduling/market_calendar.py tests/test_market_calendar.py
git commit -m "feat: add IDX market calendar (trading day / market open)"
```

---

### Task 2: Liquid universe filter

**Files:**
- Create: `news_breakout/data/universe.py`
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `filter_liquid_universe(candidates: list[str], daily_data: dict[str, DataFrame], min_price: float, min_daily_value: float, value_window: int = 20) -> list[str]`.
  Keeps a candidate when it has daily data, its last Close >= `min_price`, and the mean of
  `Close * Volume` over the last `value_window` bars >= `min_daily_value`. Order preserved.

- [ ] **Step 1: Write the failing test**

`tests/test_universe.py`:
```python
from tests.fixtures import make_ohlcv
from news_breakout.data.universe import filter_liquid_universe


def test_filters_by_price_and_value():
    data = {
        "LIQD": make_ohlcv(  # price 1000, value 1000*2000 = 2M/bar
            highs=[1000] * 5, lows=[1000] * 5, closes=[1000] * 5, volumes=[2000] * 5),
        "CHEAP": make_ohlcv(  # price 40 < 50 -> excluded
            highs=[40] * 5, lows=[40] * 5, closes=[40] * 5, volumes=[100000] * 5),
        "ILLQ": make_ohlcv(  # price 1000 but value 1000*10 = 10k < 1M -> excluded
            highs=[1000] * 5, lows=[1000] * 5, closes=[1000] * 5, volumes=[10] * 5),
    }
    out = filter_liquid_universe(
        ["LIQD", "CHEAP", "ILLQ", "NODATA"], data,
        min_price=50, min_daily_value=1_000_000, value_window=5,
    )
    assert out == ["LIQD"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_universe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.data.universe'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/data/universe.py`:
```python
from __future__ import annotations

import pandas as pd


def filter_liquid_universe(
    candidates: list[str],
    daily_data: dict[str, pd.DataFrame],
    min_price: float,
    min_daily_value: float,
    value_window: int = 20,
) -> list[str]:
    out: list[str] = []
    for t in candidates:
        df = daily_data.get(t)
        if df is None or df.empty:
            continue
        if float(df["Close"].iloc[-1]) < min_price:
            continue
        recent = df.iloc[-value_window:]
        avg_value = float((recent["Close"] * recent["Volume"]).mean())
        if avg_value < min_daily_value:
            continue
        out.append(t)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_universe.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news_breakout/data/universe.py tests/test_universe.py
git commit -m "feat: add liquid universe filter"
```

---

### Task 3: Weekend summary builder

**Files:**
- Create: `news_breakout/scheduling/weekend.py` (this task adds ONLY the pure `build_weekend_summary`; `run_weekend_scan` is added in Task 6)
- Test: `tests/test_weekend.py`

**Interfaces:**
- Produces: `build_weekend_summary(alerts: list[TickerAlert], top_n: int = 10) -> str`.
  Returns a Telegram summary: a header, then one line per alert (sorted by
  `(priority, max_rvol)` desc, capped at `top_n`) showing `⭐priority`, ticker, the
  fired timeframes, and max RVOL. A friendly message when `alerts` is empty.

- [ ] **Step 1: Write the failing test**

`tests/test_weekend.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.scheduling.weekend import build_weekend_summary

TS = datetime(2026, 7, 18, 8, 0, tzinfo=ZoneInfo("Asia/Jakarta"))


def _alert(ticker, priority, rvol):
    sig = BreakoutSignal(ticker, "1D", "resistance_breakout", 100.0, 1.0, 95.0, rvol, TS)
    return TickerAlert(ticker, [sig], priority, TS)


def test_summary_empty():
    msg = build_weekend_summary([])
    assert "tidak ada" in msg.lower() or "no " in msg.lower()


def test_summary_sorted_and_capped():
    alerts = [_alert("AAA", 3.0, 2.0), _alert("BBB", 6.0, 4.0), _alert("CCC", 3.0, 5.0)]
    msg = build_weekend_summary(alerts, top_n=2)
    lines = [ln for ln in msg.splitlines() if "⭐" in ln]
    assert len(lines) == 2                 # capped
    assert "BBB" in lines[0]               # highest priority first
    assert "CCC" in lines[1]               # tie broken by rvol (5.0 > 2.0)
    assert "AAA" not in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weekend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.scheduling.weekend'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/scheduling/weekend.py`:
```python
from __future__ import annotations

from news_breakout.models import TickerAlert


def build_weekend_summary(alerts: list[TickerAlert], top_n: int = 10) -> str:
    if not alerts:
        return "📊 WEEKEND DEEP-SCAN (1D)\nTidak ada setup breakout terdeteksi."
    ranked = sorted(alerts, key=lambda a: (a.priority, a.max_rvol), reverse=True)[:top_n]
    lines = ["📊 WEEKEND DEEP-SCAN (1D)", "━━━━━━━━━━━━━━━━━━━"]
    for a in ranked:
        tfs = "+".join(sorted({s.timeframe for s in a.signals}))
        lines.append(f"⭐{a.priority:.0f}  {a.ticker}  [{tfs}]  RVOL {a.max_rvol:.1f}×")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weekend.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news_breakout/scheduling/weekend.py tests/test_weekend.py
git commit -m "feat: add weekend deep-scan summary builder"
```

---

### Task 4: Config additions + logging setup

**Files:**
- Modify: `news_breakout/config.py`, `config/config.example.yaml`, `tests/test_config.py`
- Create: `news_breakout/logging_setup.py`
- Modify: `requirements.txt`

**Interfaces:**
- `Settings` gains: `market_open: str`, `market_close: str`, `scan_interval_minutes: int`,
  `weekend_scan_day: str`, `holidays: list[str]`, `universe_candidates: list[str]`,
  `min_price: float`, `min_daily_value: float`.
- `news_breakout.logging_setup.setup_logging(logfile: str = "logs/news_breakout.log") -> logging.Logger`.
  Configures root logging to stdout + a file, forces UTF-8 stdout, and silences yfinance
  `DeprecationWarning`s. Returns the app logger.

- [ ] **Step 1: Add the dependency**

Append to `requirements.txt`:
```text
APScheduler==3.10.4
```
Run: `.venv/Scripts/python.exe -m pip install -r requirements.txt`
Expected: APScheduler installs cleanly.

- [ ] **Step 2: Write the failing test (update `tests/test_config.py`)**

Extend the YAML fixture in the existing config test with a `schedule` and `universe`
section and assert the new fields. Add to the written YAML:
```yaml
schedule: {market_open: "09:00", market_close: "16:00", scan_interval_minutes: 30, weekend_scan_day: "sat", holidays: ["2026-01-01"]}
universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}
```
and add assertions:
```python
    assert s.market_open == "09:00"
    assert s.scan_interval_minutes == 30
    assert s.weekend_scan_day == "sat"
    assert s.holidays == ["2026-01-01"]
    assert s.universe_candidates == []
    assert s.min_price == 50
    assert s.min_daily_value == 1000000000
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL (`Settings` has no `market_open`, or validation error).

- [ ] **Step 4: Write minimal implementation**

Add fields to `Settings` in `news_breakout/config.py`:
```python
    market_open: str
    market_close: str
    scan_interval_minutes: int
    weekend_scan_day: str
    holidays: list[str]
    universe_candidates: list[str]
    min_price: float
    min_daily_value: float
```
In `load_settings`, read a `schedule` and `universe` section and pass them:
```python
    schedule = raw.get("schedule", {})
    universe = raw.get("universe", {})
    # ... inside Settings(...):
        market_open=schedule["market_open"],
        market_close=schedule["market_close"],
        scan_interval_minutes=schedule["scan_interval_minutes"],
        weekend_scan_day=schedule["weekend_scan_day"],
        holidays=schedule["holidays"],
        universe_candidates=universe["candidates"],
        min_price=universe["min_price"],
        min_daily_value=universe["min_daily_value"],
```
Add to `config/config.example.yaml`:
```yaml
schedule:
  market_open: "09:00"
  market_close: "16:00"
  scan_interval_minutes: 30
  weekend_scan_day: "sat"
  holidays: []   # IDX holiday dates as "YYYY-MM-DD"; fill these in yearly

universe:
  candidates: []            # tickers to consider beyond the watchlist (populated later)
  min_price: 50
  min_daily_value: 1000000000   # Rp 1 billion avg daily transaction value
```

`news_breakout/logging_setup.py`:
```python
from __future__ import annotations

import logging
import os
import sys
import warnings


def setup_logging(logfile: str = "logs/news_breakout.log") -> logging.Logger:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="yfinance")
    os.makedirs(os.path.dirname(logfile) or ".", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(logfile, encoding="utf-8")],
    )
    return logging.getLogger("news_breakout")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: PASS. Also `cp config/config.example.yaml config/config.yaml` to refresh the local
config with the new sections (git-ignored; verify not staged).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt news_breakout/config.py news_breakout/logging_setup.py config/config.example.yaml tests/test_config.py
git commit -m "feat: add schedule/universe config and logging setup"
```

---

### Task 5: Scheduler gating + builder

**Files:**
- Create: `news_breakout/scheduling/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Produces:
  - `should_scan_now(now: datetime, settings) -> bool` — True when the market is open per the
    settings' calendar (parses `settings.holidays` internally).
  - `build_scheduler(settings, *, scan_job, weekend_job, tz: str = "Asia/Jakarta") -> BlockingScheduler`.
    Registers an interval job (`scan_job`, every `settings.scan_interval_minutes`, id `"scan"`)
    and a cron job (`weekend_job`, `day_of_week=settings.weekend_scan_day`, hour 8, id `"weekend"`).
    Returns the (not-yet-started) scheduler.

- [ ] **Step 1: Write the failing test**

`tests/test_scheduler.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings
from news_breakout.scheduling.scheduler import should_scan_now, build_scheduler

WIB = ZoneInfo("Asia/Jakarta")


def _settings(**over):
    base = dict(
        watchlist=["ANTM"], donchian_lookback=20, rvol_threshold=2.0, rvol_window=20,
        history_days=120, range_lookback=30, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=["2026-07-17"],
        universe_candidates=[], min_price=50, min_daily_value=1_000_000_000,
    )
    base.update(over)
    return Settings(**base)


def test_should_scan_now_true_during_session():
    now = datetime(2026, 7, 16, 10, 30, tzinfo=WIB)  # Thursday 10:30
    assert should_scan_now(now, _settings()) is True


def test_should_scan_now_false_on_holiday_and_offhours():
    assert should_scan_now(datetime(2026, 7, 17, 10, 0, tzinfo=WIB), _settings()) is False  # holiday
    assert should_scan_now(datetime(2026, 7, 16, 7, 0, tzinfo=WIB), _settings()) is False   # pre-open


def test_build_scheduler_registers_two_jobs():
    sched = build_scheduler(_settings(), scan_job=lambda: None, weekend_job=lambda: None)
    ids = {j.id for j in sched.get_jobs()}
    assert ids == {"scan", "weekend"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.scheduling.scheduler'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/scheduling/scheduler.py`:
```python
from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from news_breakout.scheduling.market_calendar import is_market_open, parse_holidays


def should_scan_now(now: datetime, settings) -> bool:
    return is_market_open(
        now, parse_holidays(settings.holidays), settings.market_open, settings.market_close
    )


def build_scheduler(settings, *, scan_job, weekend_job, tz: str = "Asia/Jakarta") -> BlockingScheduler:
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(scan_job, "interval", minutes=settings.scan_interval_minutes, id="scan")
    sched.add_job(weekend_job, "cron", day_of_week=settings.weekend_scan_day, hour=8, id="weekend")
    return sched
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scheduler.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/scheduling/scheduler.py tests/test_scheduler.py
git commit -m "feat: add scheduler gating and job builder"
```

---

### Task 6: Service wiring (`run_scan`, `run_weekend_scan`, `serve.py`)

**Files:**
- Modify: `run.py` (extract `run_scan`)
- Modify: `news_breakout/scheduling/weekend.py` (add `run_weekend_scan`)
- Create: `serve.py`
- Test: `tests/test_run_smoke.py` (add a `run_scan` test with injected fetchers)

**Interfaces:**
- `run.run_scan(settings, store, *, now, sender=send_message, daily_fetcher=fetch_daily_ohlcv, intraday_fetcher=fetch_intraday_ohlcv) -> list[str]`.
  Fetches daily + intraday for `settings.watchlist`, then delegates to `scan_once`. Fetchers
  are injectable for testing.
- `news_breakout.scheduling.weekend.run_weekend_scan(settings, store, *, now, sender=send_message, daily_fetcher=fetch_daily_ohlcv) -> str`.
  Builds the effective universe (`watchlist + filter_liquid_universe(candidates, ...)`), fetches
  daily, evaluates 1D-only per ticker via `evaluate_ticker`, sends `build_weekend_summary(...)`
  to Telegram, and returns the summary text.
- `serve.py`: `main()` — `setup_logging`, open the SQLite store, define `scan_job` (guarded by
  `should_scan_now`) and `weekend_job`, `build_scheduler(...)`, and `sched.start()`.

- [ ] **Step 1: Write the failing test (append to `tests/test_run_smoke.py`)**

```python
def test_run_scan_uses_injected_fetchers():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = _breakout_daily()
    result = run.run_scan(
        _settings(), store, now=NOW, sender=sender,
        daily_fetcher=lambda tickers, days: daily,
        intraday_fetcher=lambda tickers, days: {},
    )
    assert result == ["ANTM"]
    assert len(sent) == 1
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run_smoke.py -v`
Expected: FAIL (`AttributeError: module 'run' has no attribute 'run_scan'`).

- [ ] **Step 3: Write minimal implementation**

In `run.py`, add `run_scan` and simplify `main` to use it (keep `scan_once` and the UTF-8 reconfigure):
```python
def run_scan(
    settings: Settings, store: DedupStore, *, now, sender=send_message,
    daily_fetcher=fetch_daily_ohlcv, intraday_fetcher=fetch_intraday_ohlcv,
) -> list[str]:
    daily = daily_fetcher(settings.watchlist, settings.history_days)
    intraday = intraday_fetcher(settings.watchlist, settings.intraday_period_days)
    return scan_once(settings, daily, intraday, store, now=now, sender=sender)
```
and in `main`, replace the inline fetch+scan with:
```python
        now = datetime.now(WIB)
        alerted = run_scan(settings, store, now=now)
        print(f"Scan complete. Alerted: {alerted or 'none'}")
```

Append `run_weekend_scan` to `news_breakout/scheduling/weekend.py`:
```python
from news_breakout.data.yfinance_source import fetch_daily_ohlcv
from news_breakout.data.universe import filter_liquid_universe
from news_breakout.signals.engine import evaluate_ticker
from news_breakout.alerts.telegram import send_message


def run_weekend_scan(settings, store, *, now, sender=send_message, daily_fetcher=fetch_daily_ohlcv) -> str:
    liquid = filter_liquid_universe(
        settings.universe_candidates, daily_fetcher(settings.universe_candidates, settings.history_days),
        settings.min_price, settings.min_daily_value,
    ) if settings.universe_candidates else []
    tickers = list(dict.fromkeys(settings.watchlist + liquid))
    daily = daily_fetcher(tickers, settings.history_days)
    alerts = []
    for t in tickers:
        if t not in daily:
            continue
        a = evaluate_ticker(
            t, {"1D": daily[t]},
            donchian_lookback=settings.donchian_lookback, rvol_window=settings.rvol_window,
            rvol_threshold=settings.rvol_threshold, range_lookback=settings.range_lookback,
            range_max_width_pct=settings.range_max_width_pct, now=now,
        )
        if a is not None:
            alerts.append(a)
    summary = build_weekend_summary(alerts)
    sender(settings.telegram_bot_token, settings.telegram_breakout_chat_id, summary, dry_run=settings.dry_run)
    return summary
```

`serve.py`:
```python
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import load_settings
from news_breakout.logging_setup import setup_logging
from news_breakout.alerts.dedup import DedupStore
from news_breakout.scheduling.scheduler import should_scan_now, build_scheduler
from news_breakout.scheduling.weekend import run_weekend_scan
import run

WIB = ZoneInfo("Asia/Jakarta")


def main() -> None:
    log = setup_logging()
    settings = load_settings()
    import os
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")

    def scan_job() -> None:
        now = datetime.now(WIB)
        if not should_scan_now(now, settings):
            return
        alerted = run.run_scan(settings, store, now=now)
        log.info("scan complete; alerted: %s", alerted or "none")

    def weekend_job() -> None:
        now = datetime.now(WIB)
        log.info("weekend deep-scan starting")
        run_weekend_scan(settings, store, now=now)

    sched = build_scheduler(settings, scan_job=scan_job, weekend_job=weekend_job)
    log.info("scheduler started; jobs: %s", [j.id for j in sched.get_jobs()])
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        store.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all tests PASS (M1 + M2 + M3).

- [ ] **Step 5: Live smoke of the service**

Start the service in the background, let it initialize, then stop it:
```bash
PYTHONPATH=. .venv/Scripts/python.exe serve.py &
SERVE_PID=$!
sleep 5
kill $SERVE_PID 2>/dev/null
grep -E "scheduler started|jobs" logs/news_breakout.log | tail -3
```
Expected: the log shows `scheduler started; jobs: ['scan', 'weekend']` and no traceback.
(The 30-min scan won't fire in 5s — this only verifies the service boots and registers jobs.)

- [ ] **Step 6: Commit**

```bash
git add run.py news_breakout/scheduling/weekend.py serve.py tests/test_run_smoke.py
git commit -m "feat: add serve.py scheduler entrypoint wiring run_scan and weekend scan"
```

---

## Self-Review

**Spec coverage (M3 slice):**
- APScheduler service, 30-min scans → Task 5 (`build_scheduler`), Task 6 (`serve.py`, `scan_job`) ✔
- Runs only during IDX trading hours (Mon–Fri, holidays, session window) → Task 1, Task 5 (`should_scan_now`) ✔
- Weekend deep-scan → Task 3 (`build_weekend_summary`), Task 6 (`run_weekend_scan`, cron job) ✔
- Liquid universe auto-filter (mechanism; candidates empty by default) → Task 2, Task 6 ✔
- Clean logging + silence yfinance warnings → Task 4 (`setup_logging`) ✔
- Timezone Asia/Jakarta, tz-aware → Tasks 1, 5, 6 ✔
- *Deferred (out of M3 scope):* populating the universe candidate list from an authoritative IDX ticker source (arrives with M4's IDX integration); news engine (M4); systemd deploy (M5); intraday coverage of the universe (weekend scan is 1D-only by design).

**Placeholder scan:** none — every code step has complete code; every run step has an exact command and expected output.

**Type consistency:** `Settings` new fields (Task 4) are consumed by `should_scan_now`/`build_scheduler` (Task 5) and `run_weekend_scan` (Task 6). `filter_liquid_universe` (Task 2) is called in `run_weekend_scan` (Task 6). `build_weekend_summary` (Task 3) consumes `TickerAlert` and is called by `run_weekend_scan`. `run_scan` (Task 6) reuses `scan_once` (M2) and `fetch_*` (M1/M2). `should_scan_now`/`build_scheduler` signatures match their `serve.py` call sites.

---

## After M3

Once M3 is green and `serve.py` boots cleanly, we write M4 (news engine): IDX Keterbukaan Informasi
poller with curated price-sensitive filtering, a standalone news Telegram feed, and the breakout
booster — which also yields the authoritative IDX ticker list to finally populate the universe.
