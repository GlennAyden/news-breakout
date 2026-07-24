# Three-Layer Confluence Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a news-triggered staged confluence engine that promotes a symbol
through News → Breakout → Orderbook and sends staged (2/3 → 3/3) alerts to a new
dedicated Telegram channel, reusing existing signal code with zero behavior
change to the three existing layers.

**Architecture:** A new isolated `news_breakout/confluence/` package plus two root
entry points (`run_confluence.py` = one cycle; `serve_confluence.py` = own
scheduler process). It *consumes* existing pure functions (`evaluate_scan`,
`fetch_orderbook`, `classify_phase`, `positive-sentiment classify`,
`classify_corp_action`) and persists per-symbol watch state in a new sqlite file.

**Tech Stack:** Python 3.11+, pydantic `Settings`, `sqlite3`, `httpx` (via existing
sources), `apscheduler` (BlockingScheduler), pytest with dependency injection.

## Global Constraints

- **Zero edits** to `run.py`, `run_news.py`, `serve.py`, `scheduling/scheduler.py`, the three existing Telegram channels, and every module under `signals/`, `news/`, `orderbook/`. New surface only: the `confluence/` package, `run_confluence.py`, `serve_confluence.py`, **additive** new fields in `config.py`, one `.env.example` line, and a `config.yaml` `confluence:` block. (This is a refinement of the spec's "additive serve.py job": a separate process gives stronger isolation and keeps `serve.py`/`scheduler.py` untouched.)
- All timestamps are **WIB (`Asia/Jakarta`)**, persisted as **ISO 8601 strings** (lexicographic order == chronological, same offset everywhere).
- **TTL default = 5 trading days.** Staged alerts: `news+breakout` → **2/3** (any hour); `+ orderbook Ready-Markup` → **3/3** (market hours only).
- **Trigger (long-bias):** portal item `sentiment == "positif"` **OR** a disclosure that `is_price_sensitive(...)` **and** whose `classify_corp_action(title)` is **not** in the caution set `{rights_issue, private_placement, akuisisi, dividen}` (so buyback and non-corp-action price-sensitive news pass; dilutive/fade catalysts do not).
- **No network in tests** — inject evaluator / orderbook fetcher / sender / auth.
- Follow the repo's degrade pattern: per-symbol failures log and continue (`# noqa: BLE001`), never abort the cycle. Start every module with `from __future__ import annotations`.
- **YAGNI deviation from spec:** the confluence orderbook stage does **not** re-apply the rule-2 early-volume filter (the symbol already earned its place via news+breakout). The `orderbook_require_volume` config key from the spec is therefore dropped.

## File Structure

**Create:**
- `news_breakout/confluence/__init__.py` — empty package marker.
- `news_breakout/confluence/calendar.py` — `add_trading_days(start, n, holidays)`.
- `news_breakout/confluence/trigger.py` — `Trigger` dataclass + `positive_news_triggers(...)`.
- `news_breakout/confluence/store.py` — `Watch` dataclass + `ConfluenceStore` (sqlite).
- `news_breakout/confluence/formatter.py` — `format_confluence_alert(...)`.
- `news_breakout/confluence/engine.py` — `run_confluence_cycle(...)` + private helpers.
- `run_confluence.py` — one-cycle entry (`run_once()` + `main()`).
- `serve_confluence.py` — own `BlockingScheduler` calling `run_confluence.run_once`.
- Tests: `tests/test_confluence_calendar.py`, `tests/test_confluence_trigger.py`, `tests/test_confluence_store.py`, `tests/test_confluence_formatter.py`, `tests/test_confluence_engine.py`, `tests/test_confluence_config.py`, `tests/test_confluence_entry.py`.

**Modify (additive only):**
- `news_breakout/config.py` — 4 new `Settings` fields + their loading.
- `.env.example` — add `TELEGRAM_CONFLUENCE_CHAT_ID=`.

---

### Task 1: Package skeleton + trading-day helper

**Files:**
- Create: `news_breakout/confluence/__init__.py`
- Create: `news_breakout/confluence/calendar.py`
- Test: `tests/test_confluence_calendar.py`

**Interfaces:**
- Produces: `add_trading_days(start: datetime, n: int, holidays: set[date]) -> datetime` — advances `start` by `n` trading days (weekends + holidays skipped), preserving time-of-day; `n <= 0` returns `start` unchanged.

- [ ] **Step 1: Create the empty package marker**

Create `news_breakout/confluence/__init__.py` with a single line:

```python
"""Three-layer confluence engine (news → breakout → orderbook)."""
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_confluence_calendar.py`:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

from news_breakout.confluence.calendar import add_trading_days

WIB = ZoneInfo("Asia/Jakarta")


def test_one_trading_day_skips_the_weekend():
    start = datetime(2026, 7, 24, 9, 30, tzinfo=WIB)  # a Friday
    assert start.weekday() == 4                       # guard: fixture really is Friday
    out = add_trading_days(start, 1, set())
    assert out.date() == date(2026, 7, 27)            # Monday
    assert (out.hour, out.minute) == (9, 30)          # time-of-day preserved


def test_five_trading_days_from_friday_is_next_friday():
    start = datetime(2026, 7, 24, 12, 0, tzinfo=WIB)  # Friday
    out = add_trading_days(start, 5, set())
    assert out.date() == date(2026, 7, 31)            # Mon..Fri = 5 trading days


def test_holiday_is_skipped():
    start = datetime(2026, 7, 24, 12, 0, tzinfo=WIB)  # Friday
    out = add_trading_days(start, 1, {date(2026, 7, 27)})  # Monday is a holiday
    assert out.date() == date(2026, 7, 28)            # Tuesday


def test_non_positive_n_returns_start():
    start = datetime(2026, 7, 24, 12, 0, tzinfo=WIB)
    assert add_trading_days(start, 0, set()) == start
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_confluence_calendar.py -q`
Expected: FAIL — `ModuleNotFoundError: news_breakout.confluence.calendar`.

- [ ] **Step 4: Write minimal implementation**

Create `news_breakout/confluence/calendar.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timedelta

from news_breakout.scheduling.market_calendar import is_trading_day


def add_trading_days(start: datetime, n: int, holidays: set[date]) -> datetime:
    """Advance ``start`` by ``n`` trading days (weekends + holidays skipped).

    Time-of-day is preserved. ``n <= 0`` returns ``start`` unchanged.
    """
    if n <= 0:
        return start
    d = start
    remaining = n
    while remaining > 0:
        d = d + timedelta(days=1)
        if is_trading_day(d.date(), holidays):
            remaining -= 1
    return d
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_confluence_calendar.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add news_breakout/confluence/__init__.py news_breakout/confluence/calendar.py tests/test_confluence_calendar.py
git commit -m "feat(confluence): trading-day TTL helper + package skeleton"
```

---

### Task 2: Long-bias news trigger

**Files:**
- Create: `news_breakout/confluence/trigger.py`
- Test: `tests/test_confluence_trigger.py`

**Interfaces:**
- Consumes: `PortalNews` (`news/portal.py`: fields `ticker, title, timestamp, sentiment`), `Disclosure` (`news/models.py`: `ticker, title, timestamp`), `is_price_sensitive` (`news/curated.py`), `classify_corp_action` + `CAUTION_LINES` (`news/corp_action.py`).
- Produces: `Trigger(ticker: str, source: str, headline: str, ts: datetime)` and `positive_news_triggers(portal_items, disclosures, curated_keywords) -> list[Trigger]` (de-duplicated per ticker, portal precedence).

- [ ] **Step 1: Write the failing test**

Create `tests/test_confluence_trigger.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.models import Disclosure
from news_breakout.news.portal import PortalNews
from news_breakout.confluence.trigger import positive_news_triggers

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 24, 10, 0, tzinfo=WIB)
KW = ["kontrak", "buyback", "ekspansi"]


def _portal(ticker, sentiment):
    return PortalNews(ticker=ticker, title=f"{ticker} berita", timestamp=NOW,
                      url="u", source="s", sentiment=sentiment)


def _disc(ticker, title):
    return Disclosure(ticker=ticker, title=title, timestamp=NOW,
                      disclosure_id=f"{ticker}-1", url="u")


def test_positive_portal_triggers_negative_and_neutral_do_not():
    items = [_portal("AAAA", "positif"), _portal("BBBB", "negatif"),
             _portal("CCCC", "netral"), _portal("DDDD", "")]
    trig = {t.ticker for t in positive_news_triggers(items, [], KW)}
    assert trig == {"AAAA"}


def test_price_sensitive_non_caution_disclosure_triggers():
    trig = positive_news_triggers([], [_disc("EEEE", "Kontrak baru senilai Rp2T")], KW)
    assert [t.ticker for t in trig] == ["EEEE"]
    assert trig[0].source == "disclosure"


def test_buyback_disclosure_triggers_but_rights_issue_does_not():
    discs = [_disc("FFFF", "Rencana buyback saham"),        # non-caution corp action
             _disc("GGGG", "Pelaksanaan Rights Issue / HMETD")]  # caution → excluded
    trig = {t.ticker for t in positive_news_triggers([], discs, KW)}
    assert trig == {"FFFF"}


def test_non_price_sensitive_disclosure_does_not_trigger():
    trig = positive_news_triggers([], [_disc("HHHH", "Laporan bulanan rutin")], KW)
    assert trig == []


def test_dedup_prefers_portal_source():
    items = [_portal("IIII", "positif")]
    discs = [_disc("IIII", "Kontrak baru")]
    trig = positive_news_triggers(items, discs, KW)
    assert len(trig) == 1 and trig[0].source == "portal"


def test_empty_ticker_skipped():
    assert positive_news_triggers([_portal("", "positif")],
                                  [_disc("", "Kontrak baru")], KW) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_confluence_trigger.py -q`
Expected: FAIL — `ModuleNotFoundError: news_breakout.confluence.trigger`.

- [ ] **Step 3: Write minimal implementation**

Create `news_breakout/confluence/trigger.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from news_breakout.news.corp_action import CAUTION_LINES, classify_corp_action
from news_breakout.news.curated import is_price_sensitive
from news_breakout.news.models import Disclosure
from news_breakout.news.portal import PortalNews

# Corp-action categories the project treats as fade/dilution risk (they carry an
# advisory caution line). A disclosure classified into any of these must NOT
# start a long watch. Buyback and non-corp-action price-sensitive news pass.
CAUTION_CATEGORIES = frozenset(CAUTION_LINES)  # rights_issue, private_placement, akuisisi, dividen


@dataclass
class Trigger:
    ticker: str
    source: str      # "portal" | "disclosure"
    headline: str
    ts: datetime


def positive_news_triggers(
    portal_items: list[PortalNews],
    disclosures: list[Disclosure],
    curated_keywords: list[str],
) -> list[Trigger]:
    """Long-bias trigger set, de-duplicated per ticker (portal precedence)."""
    out: dict[str, Trigger] = {}
    for it in portal_items:
        if it.ticker and it.sentiment == "positif" and it.ticker not in out:
            out[it.ticker] = Trigger(it.ticker, "portal", it.title, it.timestamp)
    for d in disclosures:
        if not d.ticker or d.ticker in out:
            continue
        if not is_price_sensitive(d, curated_keywords):
            continue
        if classify_corp_action(d.title) in CAUTION_CATEGORIES:
            continue
        out[d.ticker] = Trigger(d.ticker, "disclosure", d.title, d.timestamp)
    return list(out.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_confluence_trigger.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/confluence/trigger.py tests/test_confluence_trigger.py
git commit -m "feat(confluence): long-bias news trigger (positive sentiment / non-caution disclosure)"
```

---

### Task 3: Watchlist state store

**Files:**
- Create: `news_breakout/confluence/store.py`
- Test: `tests/test_confluence_store.py`

**Interfaces:**
- Produces:
  - `Watch(ticker, news_ts, catalyst_text, source, stage_alerted, expires_at, breakout_at=None, breakout_payload=None, orderbook_at=None)`.
  - `ConfluenceStore(db_path)` with: `upsert_watch(ticker, *, news_ts, catalyst_text, source, expires_at)`, `active_watches(*, stage=None) -> list[Watch]`, `get(ticker) -> Watch | None`, `mark_breakout(ticker, *, at, payload: dict)`, `mark_orderbook(ticker, *, at)`, `mark_stage_alerted(ticker, stage)`, `prune_expired(*, now_iso) -> list[str]`, `close()`.
  - Stage values are the strings `"none"`, `"2of3"`, `"3of3"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_confluence_store.py`:

```python
from news_breakout.confluence.store import ConfluenceStore


def _store():
    return ConfluenceStore(":memory:")


def test_upsert_and_get_defaults_to_stage_none():
    s = _store()
    s.upsert_watch("BBRI", news_ts="2026-07-24T08:00:00+07:00",
                   catalyst_text="Kontrak baru", source="disclosure",
                   expires_at="2026-07-31T08:00:00+07:00")
    w = s.get("BBRI")
    assert w.ticker == "BBRI" and w.stage_alerted == "none"
    assert w.breakout_at is None and w.orderbook_at is None


def test_reupsert_refreshes_catalyst_without_resetting_stage():
    s = _store()
    s.upsert_watch("BBRI", news_ts="t1", catalyst_text="old", source="portal",
                   expires_at="e1")
    s.mark_stage_alerted("BBRI", "2of3")
    s.upsert_watch("BBRI", news_ts="t2", catalyst_text="new", source="portal",
                   expires_at="e2")
    w = s.get("BBRI")
    assert w.catalyst_text == "new" and w.expires_at == "e2"
    assert w.stage_alerted == "2of3"          # stage preserved


def test_mark_breakout_stores_payload_json():
    s = _store()
    s.upsert_watch("BBRI", news_ts="t", catalyst_text="c", source="portal", expires_at="e")
    s.mark_breakout("BBRI", at="2026-07-24T10:30:00+07:00", payload={"tf": "1D", "rvol": 3.2})
    w = s.get("BBRI")
    assert w.breakout_at.endswith("10:30:00+07:00")
    assert '"tf": "1D"' in w.breakout_payload


def test_active_watches_filters_by_stage():
    s = _store()
    s.upsert_watch("AAAA", news_ts="t", catalyst_text="c", source="portal", expires_at="e")
    s.upsert_watch("BBBB", news_ts="t", catalyst_text="c", source="portal", expires_at="e")
    s.mark_stage_alerted("BBBB", "2of3")
    assert {w.ticker for w in s.active_watches(stage="none")} == {"AAAA"}
    assert {w.ticker for w in s.active_watches(stage="2of3")} == {"BBBB"}
    assert {w.ticker for w in s.active_watches()} == {"AAAA", "BBBB"}


def test_prune_expired_removes_past_keeps_future():
    s = _store()
    s.upsert_watch("OLD", news_ts="t", catalyst_text="c", source="portal",
                   expires_at="2026-07-24T00:00:00+07:00")
    s.upsert_watch("NEW", news_ts="t", catalyst_text="c", source="portal",
                   expires_at="2026-08-01T00:00:00+07:00")
    removed = s.prune_expired(now_iso="2026-07-25T00:00:00+07:00")
    assert removed == ["OLD"]
    assert {w.ticker for w in s.active_watches()} == {"NEW"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_confluence_store.py -q`
Expected: FAIL — `ModuleNotFoundError: news_breakout.confluence.store`.

- [ ] **Step 3: Write minimal implementation**

Create `news_breakout/confluence/store.py`:

```python
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass
class Watch:
    ticker: str
    news_ts: str
    catalyst_text: str
    source: str
    stage_alerted: str          # "none" | "2of3" | "3of3"
    expires_at: str
    breakout_at: str | None = None
    breakout_payload: str | None = None   # JSON string
    orderbook_at: str | None = None


class ConfluenceStore:
    """One active watch row per ticker; ``stage_alerted`` is the staged-alert
    dedup, ``expires_at`` (ISO) bounds table growth via ``prune_expired``."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS confluence_watch (
                ticker TEXT PRIMARY KEY,
                news_ts TEXT NOT NULL,
                catalyst_text TEXT NOT NULL,
                source TEXT NOT NULL,
                breakout_at TEXT,
                breakout_payload TEXT,
                orderbook_at TEXT,
                stage_alerted TEXT NOT NULL DEFAULT 'none',
                expires_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def upsert_watch(self, ticker: str, *, news_ts: str, catalyst_text: str,
                     source: str, expires_at: str) -> None:
        """Insert a new watch, or refresh catalyst/expiry of an existing one
        WITHOUT resetting its stage (a re-triggered symbol keeps its progress)."""
        self._conn.execute(
            """
            INSERT INTO confluence_watch (ticker, news_ts, catalyst_text, source, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                news_ts=excluded.news_ts,
                catalyst_text=excluded.catalyst_text,
                source=excluded.source,
                expires_at=excluded.expires_at
            """,
            (ticker, news_ts, catalyst_text, source, expires_at),
        )
        self._conn.commit()

    def active_watches(self, *, stage: str | None = None) -> list[Watch]:
        if stage is None:
            cur = self._conn.execute("SELECT * FROM confluence_watch")
        else:
            cur = self._conn.execute(
                "SELECT * FROM confluence_watch WHERE stage_alerted=?", (stage,))
        return [self._row(r) for r in cur.fetchall()]

    def get(self, ticker: str) -> Watch | None:
        cur = self._conn.execute(
            "SELECT * FROM confluence_watch WHERE ticker=?", (ticker,))
        r = cur.fetchone()
        return self._row(r) if r else None

    def mark_breakout(self, ticker: str, *, at: str, payload: dict) -> None:
        self._conn.execute(
            "UPDATE confluence_watch SET breakout_at=?, breakout_payload=? WHERE ticker=?",
            (at, json.dumps(payload), ticker),
        )
        self._conn.commit()

    def mark_orderbook(self, ticker: str, *, at: str) -> None:
        self._conn.execute(
            "UPDATE confluence_watch SET orderbook_at=? WHERE ticker=?", (at, ticker))
        self._conn.commit()

    def mark_stage_alerted(self, ticker: str, stage: str) -> None:
        self._conn.execute(
            "UPDATE confluence_watch SET stage_alerted=? WHERE ticker=?", (stage, ticker))
        self._conn.commit()

    def prune_expired(self, *, now_iso: str) -> list[str]:
        cur = self._conn.execute(
            "SELECT ticker FROM confluence_watch WHERE expires_at <= ?", (now_iso,))
        expired = [r[0] for r in cur.fetchall()]
        if expired:
            self._conn.execute(
                "DELETE FROM confluence_watch WHERE expires_at <= ?", (now_iso,))
            self._conn.commit()
        return expired

    @staticmethod
    def _row(r: sqlite3.Row) -> Watch:
        return Watch(
            ticker=r["ticker"], news_ts=r["news_ts"], catalyst_text=r["catalyst_text"],
            source=r["source"], stage_alerted=r["stage_alerted"], expires_at=r["expires_at"],
            breakout_at=r["breakout_at"], breakout_payload=r["breakout_payload"],
            orderbook_at=r["orderbook_at"],
        )

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_confluence_store.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/confluence/store.py tests/test_confluence_store.py
git commit -m "feat(confluence): ConfluenceStore watchlist state (stages + TTL prune)"
```

---

### Task 4: Alert formatter (2/3 and 3/3)

**Files:**
- Create: `news_breakout/confluence/formatter.py`
- Test: `tests/test_confluence_formatter.py`

**Interfaces:**
- Produces: `format_confluence_alert(*, ticker, stage, catalyst_text, catalyst_source, catalyst_ts, breakout: dict, orderbook: dict | None, now) -> str`.
  - `breakout` dict keys: `tf, price, pct_change, level, rvol, quality`.
  - `orderbook` dict keys (only for 3/3): `bid_lot, offer_lot, ratio`.
  - `stage` is `"2of3"` or `"3of3"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_confluence_formatter.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.confluence.formatter import format_confluence_alert

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 24, 10, 32, tzinfo=WIB)
BREAKOUT = {"tf": "1D", "price": 4850, "pct_change": 3.2, "level": 4800,
            "rvol": 3.2, "quality": 7.0}
CATALYST_TS = datetime(2026, 7, 24, 8, 12, tzinfo=WIB)


def test_two_of_three_has_pending_orderbook_and_no_orderbook_line():
    text = format_confluence_alert(
        ticker="BBRI", stage="2of3", catalyst_text="Kontrak baru Rp2,1T",
        catalyst_source="disclosure", catalyst_ts=CATALYST_TS,
        breakout=BREAKOUT, orderbook=None, now=NOW)
    assert "CONFLUENCE 2/3 — BBRI" in text
    assert "ORDERBOOK ⏳" in text
    assert "RVOL 3.2×" in text
    assert "READY MARKUP" not in text
    assert "4.850" in text          # Indonesian thousands separator


def test_three_of_three_has_ready_markup_and_orderbook_line():
    text = format_confluence_alert(
        ticker="BBRI", stage="3of3", catalyst_text="Kontrak baru Rp2,1T",
        catalyst_source="disclosure", catalyst_ts=CATALYST_TS,
        breakout=BREAKOUT, orderbook={"bid_lot": 300000, "offer_lot": 295000, "ratio": 0.98},
        now=NOW)
    assert "CONFLUENCE 3/3 — BBRI" in text
    assert "ORDERBOOK ✅ READY MARKUP" in text
    assert "300.000/295.000" in text
    assert "0.98" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_confluence_formatter.py -q`
Expected: FAIL — `ModuleNotFoundError: news_breakout.confluence.formatter`.

- [ ] **Step 3: Write minimal implementation**

Create `news_breakout/confluence/formatter.py`:

```python
from __future__ import annotations

from datetime import datetime


def _rupiah(value: float) -> str:
    """Indonesian thousands separator: 4850 -> '4.850'."""
    return f"{value:,.0f}".replace(",", ".")


def format_confluence_alert(
    *, ticker: str, stage: str, catalyst_text: str, catalyst_source: str,
    catalyst_ts: datetime, breakout: dict, orderbook: dict | None, now: datetime,
) -> str:
    """HTML Telegram body for a staged confluence alert (2/3 or 3/3)."""
    is_final = stage == "3of3"
    head = "⭐ CONFLUENCE 3/3" if is_final else "🔸 CONFLUENCE 2/3"
    ob_mark = "✅ READY MARKUP" if is_final else "⏳ (menunggu jam bursa / ready markup)"
    lines = [
        f"<b>{head} — {ticker}</b>",
        f"📰 NEWS ✅ · 📈 BREAKOUT ✅ · 📊 ORDERBOOK {ob_mark}",
        "",
        f"📰 {catalyst_ts:%H:%M} {catalyst_text}  ({catalyst_source})",
        (f"📈 TF {breakout['tf']} · harga {_rupiah(breakout['price'])} "
         f"({breakout['pct_change']:+.1f}%) · tembus {_rupiah(breakout['level'])} · "
         f"RVOL {breakout['rvol']:.1f}× · Q{breakout['quality']:.0f}"),
    ]
    if is_final and orderbook:
        lines.append(
            f"📊 bid/offer {_rupiah(orderbook['bid_lot'])}/{_rupiah(orderbook['offer_lot'])} "
            f"({orderbook['ratio']:.2f})"
        )
    lines.append(f"🔗 https://stockbit.com/symbol/{ticker}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_confluence_formatter.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/confluence/formatter.py tests/test_confluence_formatter.py
git commit -m "feat(confluence): staged 2/3 and 3/3 alert formatter"
```

---

### Task 5: Config fields

**Files:**
- Modify: `news_breakout/config.py` (add 4 fields to `Settings`; add loading in `load_settings`)
- Test: `tests/test_confluence_config.py`

**Interfaces:**
- Produces new `Settings` fields: `confluence_enabled: bool = False`, `confluence_ttl_trading_days: int = 5`, `confluence_require_orderbook: bool = True`, `telegram_confluence_chat_id: str = ""`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_confluence_config.py`:

```python
from news_breakout.config import load_settings


def _write(tmp_path, confluence_block: str) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.5, rvol_window: 20,"
        " range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: '09:00', market_close: '16:00',"
        " scan_interval_minutes: 30, weekend_scan_day: sat, holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [], disclosure_page_size: 50, news_poll_interval_minutes: 60}\n"
        + confluence_block,
        encoding="utf-8",
    )
    return str(cfg)


def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "x")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "x")


def test_confluence_defaults_when_block_absent(tmp_path, monkeypatch):
    _env(monkeypatch)
    s = load_settings(config_path=_write(tmp_path, ""), env_path=str(tmp_path / ".env"))
    assert s.confluence_enabled is False
    assert s.confluence_ttl_trading_days == 5
    assert s.confluence_require_orderbook is True
    assert s.telegram_confluence_chat_id == ""


def test_confluence_overrides_and_env_chat_id(tmp_path, monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_CONFLUENCE_CHAT_ID", "-100999")
    block = "confluence: {enabled: true, ttl_trading_days: 3, require_orderbook: false}\n"
    s = load_settings(config_path=_write(tmp_path, block), env_path=str(tmp_path / ".env"))
    assert s.confluence_enabled is True
    assert s.confluence_ttl_trading_days == 3
    assert s.confluence_require_orderbook is False
    assert s.telegram_confluence_chat_id == "-100999"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_confluence_config.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'confluence_enabled'`.

- [ ] **Step 3: Add the fields to the `Settings` model**

In `news_breakout/config.py`, add these four lines immediately after
`telegram_orderbook_chat_id: str = ""` (currently the last field, line 83):

```python
    confluence_enabled: bool = False
    confluence_ttl_trading_days: int = 5
    confluence_require_orderbook: bool = True
    telegram_confluence_chat_id: str = ""
```

- [ ] **Step 4: Load the block in `load_settings`**

In `news_breakout/config.py`, after the line `orderbook = raw.get("orderbook", {})`
(line 145), add:

```python
    confluence = raw.get("confluence", {})
```

Then, inside the `return Settings(...)` call, after the
`telegram_orderbook_chat_id=...` argument (line 222), add:

```python
        confluence_enabled=confluence.get("enabled", False),
        confluence_ttl_trading_days=confluence.get("ttl_trading_days", 5),
        confluence_require_orderbook=confluence.get("require_orderbook", True),
        telegram_confluence_chat_id=os.environ.get("TELEGRAM_CONFLUENCE_CHAT_ID", "").strip(),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_confluence_config.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full config suite (no regression)**

Run: `python -m pytest tests/test_config_elliott.py tests/test_config_supabase.py tests/test_confluence_config.py -q`
Expected: PASS (all green).

- [ ] **Step 7: Commit**

```bash
git add news_breakout/config.py tests/test_confluence_config.py
git commit -m "feat(confluence): config fields (enabled, ttl, require_orderbook, chat id)"
```

---

### Task 6: Confluence engine (state machine)

**Files:**
- Create: `news_breakout/confluence/engine.py`
- Test: `tests/test_confluence_engine.py`

**Interfaces:**
- Consumes: `positive_news_triggers` (Task 2), `add_trading_days` (Task 1), `ConfluenceStore` (Task 3), `format_confluence_alert` (Task 4), `evaluate_scan` (`signals/scan_core.py`), `classify_phase`/`PhaseConfig` (`orderbook/phase.py`), `fetch_orderbook`/`is_market_open` (`orderbook/stockbit_source.py`), `send_message` (`alerts/telegram.py`), `TickerAlert`/`TF_WEIGHT` (`models.py`).
- Produces:
  ```python
  run_confluence_cycle(
      settings, store, *, now, holidays, portal_items, disclosures,
      daily_data, intraday_data, auth=None, sender=send_message,
      evaluator=evaluate_scan, orderbook_fetcher=fetch_orderbook, is_open=None,
  ) -> list[tuple[str, str]]   # e.g. [("BBRI", "2of3")]
  ```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_confluence_engine.py`:

```python
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.orderbook.models import OrderbookSnapshot
from news_breakout.confluence.store import ConfluenceStore
from news_breakout.confluence.engine import run_confluence_cycle
from news_breakout.news.portal import PortalNews

WIB = ZoneInfo("Asia/Jakarta")


def _settings(**over):
    base = dict(
        curated_keywords=["kontrak"], confluence_ttl_trading_days=5,
        telegram_confluence_chat_id="-100", telegram_bot_token="tok", dry_run=True,
        min_quality_score=None, confluence_require_orderbook=True,
        orderbook_phase_rm_balance_min_ratio=0.85, market_open="09:00",
        market_close="16:00", orderbook_window_after_open_minutes=30,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _alert(ticker, now):
    sig = BreakoutSignal(ticker=ticker, timeframe="1D", signal_type="resistance_breakout",
                         price=4850, pct_change=3.2, level=4800, rvol=3.2, timestamp=now)
    return TickerAlert(ticker=ticker, signals=[sig], priority=5.0, timestamp=now,
                       quality_score=7.0)


def _sender_recorder():
    sent = []
    def sender(token, chat_id, text, **kw):
        sent.append((chat_id, text))
        return True
    return sent, sender


def test_news_plus_breakout_sends_2of3_offhours():
    now = datetime(2026, 7, 25, 20, 0, tzinfo=WIB)   # Saturday evening — market closed
    store = ConfluenceStore(":memory:")
    items = [PortalNews(ticker="BBRI", title="BBRI kontrak", timestamp=now, url="u",
                        source="s", sentiment="positif")]
    sent, sender = _sender_recorder()
    out = run_confluence_cycle(
        _settings(), store, now=now, holidays=set(), portal_items=items, disclosures=[],
        daily_data={"BBRI": object()}, intraday_data={},
        sender=sender, evaluator=lambda *a, **k: [_alert("BBRI", now)],
        is_open=lambda: False)
    assert out == [("BBRI", "2of3")]
    assert store.get("BBRI").stage_alerted == "2of3"
    assert "CONFLUENCE 2/3" in sent[0][1]


def test_2of3_not_resent_next_cycle():
    now = datetime(2026, 7, 25, 20, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")
    items = [PortalNews(ticker="BBRI", title="t", timestamp=now, url="u",
                        source="s", sentiment="positif")]
    s = _settings()
    ev = lambda *a, **k: [_alert("BBRI", now)]
    run_confluence_cycle(s, store, now=now, holidays=set(), portal_items=items,
                         disclosures=[], daily_data={"BBRI": object()}, intraday_data={},
                         sender=_sender_recorder()[1], evaluator=ev, is_open=lambda: False)
    sent2, sender2 = _sender_recorder()
    out = run_confluence_cycle(s, store, now=now, holidays=set(), portal_items=items,
                               disclosures=[], daily_data={"BBRI": object()},
                               intraday_data={}, sender=sender2, evaluator=ev,
                               is_open=lambda: False)
    assert out == []            # already at 2of3, breakout pass skips it
    assert sent2 == []


def test_orderbook_ready_markup_upgrades_to_3of3_in_hours():
    now = datetime(2026, 7, 24, 10, 0, tzinfo=WIB)   # Friday 10:00, >30m after open
    store = ConfluenceStore(":memory:")
    store.upsert_watch("BBRI", news_ts=now.isoformat(), catalyst_text="c",
                       source="portal", expires_at="2026-08-01T00:00:00+07:00")
    store.mark_breakout("BBRI", at=now.isoformat(),
                        payload={"tf": "1D", "price": 4850, "pct_change": 3.2,
                                 "level": 4800, "rvol": 3.2, "quality": 7.0})
    store.mark_stage_alerted("BBRI", "2of3")
    snap = OrderbookSnapshot(symbol="BBRI", ts=now, total_bid_lot=300000,
                             total_offer_lot=295000, last_price=4850)
    sent, sender = _sender_recorder()
    out = run_confluence_cycle(
        _settings(), store, now=now, holidays=set(), portal_items=[], disclosures=[],
        daily_data={}, intraday_data={}, auth=object(), sender=sender,
        evaluator=lambda *a, **k: [], orderbook_fetcher=lambda *a, **k: snap,
        is_open=lambda: True)
    assert out == [("BBRI", "3of3")]
    assert store.get("BBRI").stage_alerted == "3of3"
    assert "CONFLUENCE 3/3" in sent[0][1]


def test_orderbook_skipped_when_market_closed():
    now = datetime(2026, 7, 24, 10, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")
    store.upsert_watch("BBRI", news_ts=now.isoformat(), catalyst_text="c",
                       source="portal", expires_at="2026-08-01T00:00:00+07:00")
    store.mark_stage_alerted("BBRI", "2of3")
    called = {"n": 0}
    def ob(*a, **k):
        called["n"] += 1
        return None
    out = run_confluence_cycle(
        _settings(), store, now=now, holidays=set(), portal_items=[], disclosures=[],
        daily_data={}, intraday_data={}, auth=object(), sender=_sender_recorder()[1],
        evaluator=lambda *a, **k: [], orderbook_fetcher=ob, is_open=lambda: False)
    assert out == [] and called["n"] == 0


def test_require_orderbook_false_makes_2of3_terminal():
    now = datetime(2026, 7, 25, 20, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")
    items = [PortalNews(ticker="BBRI", title="t", timestamp=now, url="u",
                        source="s", sentiment="positif")]
    out = run_confluence_cycle(
        _settings(confluence_require_orderbook=False), store, now=now, holidays=set(),
        portal_items=items, disclosures=[], daily_data={"BBRI": object()},
        intraday_data={}, sender=_sender_recorder()[1],
        evaluator=lambda *a, **k: [_alert("BBRI", now)], is_open=lambda: False)
    assert out == [("BBRI", "2of3")]
    assert store.get("BBRI").stage_alerted == "3of3"     # marked terminal


def test_expired_watch_is_pruned_silently():
    now = datetime(2026, 7, 24, 10, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")
    store.upsert_watch("OLD", news_ts="t", catalyst_text="c", source="portal",
                       expires_at="2026-07-01T00:00:00+07:00")
    out = run_confluence_cycle(
        _settings(), store, now=now, holidays=set(), portal_items=[], disclosures=[],
        daily_data={}, intraday_data={}, sender=_sender_recorder()[1],
        evaluator=lambda *a, **k: [], is_open=lambda: True)
    assert out == []
    assert store.get("OLD") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_confluence_engine.py -q`
Expected: FAIL — `ModuleNotFoundError: news_breakout.confluence.engine`.

- [ ] **Step 3: Write the implementation**

Create `news_breakout/confluence/engine.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from news_breakout.alerts.telegram import send_message
from news_breakout.confluence.calendar import add_trading_days
from news_breakout.confluence.formatter import format_confluence_alert
from news_breakout.confluence.trigger import positive_news_triggers
from news_breakout.models import TF_WEIGHT, TickerAlert
from news_breakout.orderbook.phase import PhaseConfig, classify_phase
from news_breakout.orderbook.stockbit_source import fetch_orderbook, is_market_open
from news_breakout.signals.scan_core import evaluate_scan

logger = logging.getLogger("news_breakout")


def _breakout_payload(alert: TickerAlert) -> dict:
    """Serializable summary of the winning breakout signal (highest TF weight)."""
    sig = max(alert.signals, key=lambda s: TF_WEIGHT.get(s.timeframe, 0.0))
    return {"tf": sig.timeframe, "price": sig.price, "pct_change": sig.pct_change,
            "level": sig.level, "rvol": sig.rvol, "quality": alert.quality_score}


def _orderbook_window_open(settings, now: datetime, is_open) -> bool:
    """Same gate as the standalone orderbook scan: session open, at least
    ``window_after_open_minutes`` into it, and not past the close."""
    if not is_open():
        return False
    oh, om = (int(x) for x in settings.market_open.split(":"))
    session_open = now.replace(hour=oh, minute=om, second=0, microsecond=0)
    if (now - session_open) < timedelta(minutes=settings.orderbook_window_after_open_minutes):
        return False
    ch, cm = (int(x) for x in settings.market_close.split(":"))
    if now > now.replace(hour=ch, minute=cm, second=0, microsecond=0):
        return False
    return True


def _send(settings, chat_id, text, sender) -> bool:
    return bool(chat_id) and sender(
        settings.telegram_bot_token, chat_id, text,
        dry_run=settings.dry_run, parse_mode="HTML", disable_preview=True)


def run_confluence_cycle(
    settings, store, *, now, holidays, portal_items, disclosures,
    daily_data, intraday_data, auth=None, sender=send_message,
    evaluator=evaluate_scan, orderbook_fetcher=fetch_orderbook, is_open=None,
) -> list[tuple[str, str]]:
    """One confluence cycle: ingest triggers → prune → breakout(2/3) → orderbook(3/3).

    Pure orchestration over injected data/deps (no fetching here). Returns the
    ``(ticker, stage)`` pairs alerted this cycle.
    """
    sent: list[tuple[str, str]] = []
    chat_id = settings.telegram_confluence_chat_id
    if not chat_id:
        logger.warning("confluence: TELEGRAM_CONFLUENCE_CHAT_ID unset; not sending")

    # 1. Ingest positive-news triggers → upsert onto the watchlist.
    triggers = positive_news_triggers(portal_items, disclosures, settings.curated_keywords)
    expires_at = add_trading_days(now, settings.confluence_ttl_trading_days, holidays).isoformat()
    for t in triggers:
        store.upsert_watch(t.ticker, news_ts=t.ts.isoformat(), catalyst_text=t.headline,
                           source=t.source, expires_at=expires_at)

    # 2. Drop expired watches (silent).
    store.prune_expired(now_iso=now.isoformat())

    # 3. Breakout pass (any hour) for watches still at stage 'none'.
    for w in store.active_watches(stage="none"):
        try:
            alerts = evaluator(settings, daily_data, intraday_data, now=now,
                               catalysts={w.ticker: True}, tickers=[w.ticker])
        except Exception:  # noqa: BLE001 — one bad symbol never aborts the cycle
            logger.warning("confluence breakout eval failed: %s", w.ticker, exc_info=True)
            continue
        alert = alerts[0] if alerts else None
        if alert is None:
            continue
        if settings.min_quality_score is not None and alert.quality_score < settings.min_quality_score:
            continue
        payload = _breakout_payload(alert)
        store.mark_breakout(w.ticker, at=now.isoformat(), payload=payload)
        text = format_confluence_alert(
            ticker=w.ticker, stage="2of3", catalyst_text=w.catalyst_text,
            catalyst_source=w.source, catalyst_ts=datetime.fromisoformat(w.news_ts),
            breakout=payload, orderbook=None, now=now)
        if _send(settings, chat_id, text, sender):
            store.mark_stage_alerted(w.ticker, "2of3")
            sent.append((w.ticker, "2of3"))
            if not settings.confluence_require_orderbook:
                store.mark_stage_alerted(w.ticker, "3of3")   # 2/3 is terminal

    # 4. Orderbook pass (market hours only) for watches at stage '2of3'.
    if settings.confluence_require_orderbook:
        watches = store.active_watches(stage="2of3")
        if watches and auth is not None:
            if is_open is None:
                def is_open():
                    return is_market_open(auth)
            if _orderbook_window_open(settings, now, is_open):
                pcfg = PhaseConfig(rm_balance_min_ratio=settings.orderbook_phase_rm_balance_min_ratio)
                for w in watches:
                    try:
                        snap = orderbook_fetcher(w.ticker, auth, now=now)
                    except Exception:  # noqa: BLE001
                        logger.warning("confluence orderbook fetch failed: %s", w.ticker,
                                       exc_info=True)
                        continue
                    if snap is None:
                        continue
                    result = classify_phase(snap, pcfg)
                    if not result.is_ready_markup:
                        continue
                    ob = {"bid_lot": result.bid_lot, "offer_lot": result.offer_lot,
                          "ratio": result.ratio}
                    payload = json.loads(w.breakout_payload) if w.breakout_payload else {}
                    text = format_confluence_alert(
                        ticker=w.ticker, stage="3of3", catalyst_text=w.catalyst_text,
                        catalyst_source=w.source,
                        catalyst_ts=datetime.fromisoformat(w.news_ts),
                        breakout=payload, orderbook=ob, now=now)
                    if _send(settings, chat_id, text, sender):
                        store.mark_orderbook(w.ticker, at=now.isoformat())
                        store.mark_stage_alerted(w.ticker, "3of3")
                        sent.append((w.ticker, "3of3"))
    return sent
```

- [ ] **Step 4: Add the missing `json` import**

The orderbook branch uses `json.loads`. Add `import json` at the top of
`news_breakout/confluence/engine.py` (after `from __future__ import annotations`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_confluence_engine.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add news_breakout/confluence/engine.py tests/test_confluence_engine.py
git commit -m "feat(confluence): staged engine (news->2/3->orderbook 3/3) with TTL + dedup"
```

---

### Task 7: One-cycle entry point

**Files:**
- Create: `run_confluence.py`
- Test: `tests/test_confluence_entry.py`

**Interfaces:**
- Produces: `run_once(settings, *, now, store, auth=None) -> list[tuple[str, str]]` (fetches its own data, then calls `run_confluence_cycle`), and `main()` (wires real settings/store/auth). Also `_collect_portal_items(settings, *, now)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_confluence_entry.py`:

```python
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import run_confluence
from news_breakout.confluence.store import ConfluenceStore

WIB = ZoneInfo("Asia/Jakarta")


def _settings():
    return SimpleNamespace(
        confluence_enabled=True, confluence_require_orderbook=False,
        confluence_ttl_trading_days=5, watchlist=["BBRI"], universe_candidates=[],
        history_days=120, intraday_period_days=60, disclosure_page_size=50,
        idx_proxy="", portal_enabled=False, sentiment_enabled=False,
        curated_keywords=["kontrak"], holidays=[], stockbit_refresh_token="",
        stockbit_access_token="", telegram_confluence_chat_id="-1",
        telegram_bot_token="t", dry_run=True, min_quality_score=None,
        market_open="09:00", market_close="16:00",
        orderbook_window_after_open_minutes=30,
        orderbook_phase_rm_balance_min_ratio=0.85,
        portal_sources=[], portal_name_map={}, portal_proxy="",
        sentiment_min_confidence=0.6,
    )


def test_run_once_fetches_and_delegates_to_engine(monkeypatch):
    now = datetime(2026, 7, 25, 20, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")

    # stub the network-bound collaborators
    monkeypatch.setattr(run_confluence, "fetch_disclosures", lambda *a, **k: [])
    monkeypatch.setattr(run_confluence, "_collect_portal_items", lambda s, *, now: [])
    monkeypatch.setattr(run_confluence, "make_daily_fetcher",
                        lambda s: (lambda syms, days: {}))
    monkeypatch.setattr(run_confluence, "make_intraday_fetcher",
                        lambda s: (lambda syms, days: {}))
    captured = {}
    def fake_cycle(settings, st, **kw):
        captured.update(kw)
        return [("BBRI", "2of3")]
    monkeypatch.setattr(run_confluence, "run_confluence_cycle", fake_cycle)

    out = run_confluence.run_once(_settings(), now=now, store=store)

    assert out == [("BBRI", "2of3")]
    assert "portal_items" in captured and "disclosures" in captured
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_confluence_entry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_confluence'`.

- [ ] **Step 3: Write the implementation**

Create `run_confluence.py` (project root):

```python
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import load_settings
from news_breakout.logging_setup import setup_logging
from news_breakout.confluence.engine import run_confluence_cycle
from news_breakout.confluence.store import ConfluenceStore
from news_breakout.confluence.trigger import positive_news_triggers
from news_breakout.data.supabase_source import make_daily_fetcher, make_intraday_fetcher
from news_breakout.news.idx_source import fetch_disclosures
from news_breakout.news.portal import fetch_portal_news
from news_breakout.news.sentiment import classify
from news_breakout.orderbook.auth import StockbitAuth
from news_breakout.scheduling.market_calendar import parse_holidays

WIB = ZoneInfo("Asia/Jakarta")


def _collect_portal_items(settings, *, now):
    """Fetch portal news for the universe and tag positive/negative sentiment on
    titles (no article extraction — the trigger only needs the sentiment sign)."""
    if not settings.portal_enabled:
        return []
    tickers = list(dict.fromkeys(settings.watchlist + settings.universe_candidates))
    items = fetch_portal_news(settings.portal_sources, tickers, settings.portal_name_map,
                              now=now, corp_keywords=settings.curated_keywords,
                              global_proxy=settings.portal_proxy)
    if settings.sentiment_enabled and items:
        labels = classify([it.title for it in items],
                          min_confidence=settings.sentiment_min_confidence)
        if isinstance(labels, list) and len(labels) == len(items):
            for it, lab in zip(items, labels):
                it.sentiment = lab
    return items


def run_once(settings, *, now, store, auth=None) -> list[tuple[str, str]]:
    try:
        disclosures = fetch_disclosures(settings.disclosure_page_size, now=now,
                                        proxy=settings.idx_proxy, retries=0)
    except Exception:  # noqa: BLE001 — a feed hiccup must not abort the cycle
        disclosures = []
    portal_items = _collect_portal_items(settings, now=now)

    trig = positive_news_triggers(portal_items, disclosures, settings.curated_keywords)
    watch_tickers = [w.ticker for w in store.active_watches()]
    symbols = list(dict.fromkeys([t.ticker for t in trig] + watch_tickers))
    daily = make_daily_fetcher(settings)(symbols, settings.history_days) if symbols else {}
    intraday = (make_intraday_fetcher(settings)(symbols, settings.intraday_period_days)
                if symbols else {})

    if auth is None and settings.confluence_require_orderbook and (
            settings.stockbit_refresh_token or settings.stockbit_access_token):
        auth = StockbitAuth(settings.stockbit_refresh_token,
                            access_token=settings.stockbit_access_token)

    return run_confluence_cycle(
        settings, store, now=now, holidays=parse_holidays(settings.holidays),
        portal_items=portal_items, disclosures=disclosures,
        daily_data=daily, intraday_data=intraday, auth=auth)


def main() -> None:
    setup_logging()
    settings = load_settings()
    if not settings.confluence_enabled:
        print("confluence disabled (set confluence.enabled: true)")
        return
    os.makedirs("data_cache", exist_ok=True)
    store = ConfluenceStore("data_cache/confluence.sqlite")
    try:
        sent = run_once(settings, now=datetime.now(WIB), store=store)
        print(f"confluence cycle complete. sent: {sent or 'none'}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_confluence_entry.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add run_confluence.py tests/test_confluence_entry.py
git commit -m "feat(confluence): run_confluence.py one-cycle entry (fetch + delegate)"
```

---

### Task 8: Scheduler process, config block, docs

**Files:**
- Create: `serve_confluence.py`
- Modify: `.env.example` (add `TELEGRAM_CONFLUENCE_CHAT_ID=`)
- Docs: append deploy runbook to the spec; document the `config.yaml` block below.

**Interfaces:**
- Consumes: `run_confluence.run_once`, `load_settings`, `BlockingScheduler`.
- Produces: `build_confluence_scheduler(settings, *, job) -> BlockingScheduler` (testable) + `main()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_confluence_serve.py`:

```python
from types import SimpleNamespace

import serve_confluence


def test_scheduler_registers_a_single_interval_job():
    settings = SimpleNamespace(scan_interval_minutes=30)
    sched = serve_confluence.build_confluence_scheduler(settings, job=lambda: None)
    ids = [j.id for j in sched.get_jobs()]
    assert ids == ["confluence"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_confluence_serve.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'serve_confluence'`.

- [ ] **Step 3: Write the implementation**

Create `serve_confluence.py` (project root):

```python
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

import run_confluence
from news_breakout.config import load_settings
from news_breakout.confluence.store import ConfluenceStore
from news_breakout.logging_setup import setup_logging

WIB = ZoneInfo("Asia/Jakarta")


def build_confluence_scheduler(settings, *, job, tz: str = "Asia/Jakarta") -> BlockingScheduler:
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(job, "interval", minutes=settings.scan_interval_minutes, id="confluence")
    return sched


def main() -> None:
    log = setup_logging()
    settings = load_settings()
    if not settings.confluence_enabled:
        log.info("confluence disabled; serve_confluence exiting")
        return
    os.makedirs("data_cache", exist_ok=True)
    store = ConfluenceStore("data_cache/confluence.sqlite")

    def job() -> None:
        sent = run_confluence.run_once(settings, now=datetime.now(WIB), store=store)
        log.info("confluence cycle complete; sent: %s", sent or "none")

    sched = build_confluence_scheduler(settings, job=job)
    log.info("confluence scheduler started; interval=%dm", settings.scan_interval_minutes)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        store.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_confluence_serve.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Add the env example line**

Append to `.env.example`:

```
# Confluence engine — dedicated channel for staged news→breakout→orderbook alerts
TELEGRAM_CONFLUENCE_CHAT_ID=
```

- [ ] **Step 6: Full-suite regression + commit**

Run: `python -m pytest -q`
Expected: PASS (all existing tests + the new confluence tests green).

```bash
git add serve_confluence.py tests/test_confluence_serve.py .env.example
git commit -m "feat(confluence): serve_confluence scheduler process + env example"
```

---

## `config.yaml` block (operator reference — added on the VPS, not in git)

```yaml
confluence:
  enabled: false            # true to activate the engine
  ttl_trading_days: 5       # how long a news catalyst stays on the watchlist
  require_orderbook: true   # true → 3/3 target; false → 2/3 is terminal
```

## Deploy to VPS (runbook)

Standard project flow (VPS runs `main`; `config/config.yaml` is the git-ignored
live copy — never re-`cp` from example or `dry_run` resets to true):

1. Push branch → merge to `main`. **Fetch + check first** (concurrent sessions edit this repo/VPS).
2. On VPS (short, spaced SSH — fail2ban): `cd ~/news-breakout && git fetch && git merge --ff-only origin/main`.
3. Append the `confluence:` block with `enabled: true` to the VPS `config/config.yaml`.
4. **User** creates the new Telegram channel, adds the bot, gets the chat id, adds `TELEGRAM_CONFLUENCE_CHAT_ID=...` to the VPS `.env` (assistant never writes VPS secrets). Reuses the existing `STOCKBIT_*` token for the orderbook stage.
5. Smoke test one cycle: `PYTHONPATH=. .venv/bin/python run_confluence.py` → prints a clean cycle summary.
6. Install a second systemd service `news-breakout-confluence.service` running `serve_confluence.py` (mirror the existing unit; same venv/workdir/env), then `sudo -n systemctl daemon-reload && sudo -n systemctl enable --now news-breakout-confluence.service`.
7. Verify: `journalctl -u news-breakout-confluence --since "-2min"` shows "confluence scheduler started".

## Self-Review

**Spec coverage:**
- New dedicated channel → `telegram_confluence_chat_id`, Task 5 + `_send`. ✅
- Active news-triggered pipeline → `run_confluence_cycle` steps 1–4 + `run_once`. ✅
- 2/3 (any hour) → step 3, tested off-hours (Saturday). ✅
- 3/3 (market hours) → step 4 gated by `_orderbook_window_open`, tested open + closed. ✅
- Long-bias trigger (positive OR non-caution material) → Task 2. ✅
- TTL 5 trading days → Task 1 + `prune_expired`, tested. ✅
- Standalone runtime → Tasks 7–8 (own process; `serve.py`/`scheduler.py` untouched). ✅
- Zero edits to existing signal/news/orderbook/run modules → only `config.py` (additive) + `.env.example` touched. ✅
- Staged dedup → `stage_alerted`, tested (`test_2of3_not_resent_next_cycle`). ✅

**Deviations from spec (intentional):** (a) separate process instead of a `serve.py` job — stronger isolation, more faithful to "zero edits"; (b) `orderbook_require_volume` config dropped (YAGNI — news+breakout already qualify the symbol). Both noted in Global Constraints.

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:** `Trigger(ticker, source, headline, ts)`, `Watch(...)`, stage strings `"none"/"2of3"/"3of3"`, and the breakout payload keys (`tf, price, pct_change, level, rvol, quality`) are used identically across store, engine, and formatter. `run_once(settings, *, now, store, auth=None)` matches its test call.
