# Milestone 2 — Multi-Timeframe + Wyckoff Range Breakout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the scanner to evaluate each ticker on 1H, 4H, and 1D timeframes, detect both resistance (Donchian) breakouts and Wyckoff accumulation-range breakouts (RVOL-confirmed), aggregate all fired signals per ticker into one priority-ranked Telegram alert, and send them highest-priority first.

**Architecture:** Builds on M1. Adds (1) a Wyckoff range-breakout detector, (2) a generic per-timeframe evaluator that reuses M1's Donchian + RVOL helpers, (3) an intraday data source with 1H→4H resampling, (4) a per-ticker aggregation + priority-ranking step producing a new `TickerAlert`, (5) a multi-timeframe formatter, and (6) rewired `run.py`. M1's `evaluate_daily`, `BreakoutSignal`, dedup, and Telegram sender are reused.

**Tech Stack:** Python 3.12 · `yfinance` · `pandas` · `pydantic` · `PyYAML` · `httpx` · `pytest` (unchanged from M1).

## Global Constraints

- Python **3.12**. All timestamps timezone **Asia/Jakarta (WIB)**, tz-aware.
- **No API keys** (yfinance free, ticker `.JK`). Keep memory small: fetch bounded history windows, process per-ticker.
- **Anti-spam:** one aggregated alert per (ticker, trading-date).
- Secrets only in `.env` (git-ignored). Windows console prints emoji — `run.py` already forces UTF-8 stdout; keep that.
- Timeframe priority weights: **1D = 3, 4H = 2, 1H = 1** (an aggregated alert's priority is the sum over every fired signal's timeframe weight).
- Default signal params, tunable via config: Donchian lookback **20**, RVOL threshold **2.0**, RVOL window **20**, Wyckoff range lookback **30**, range max width **0.15** (15%).
- 4H bars are **resampled from 1H** (yfinance has no native 4H); resampling is an approximation of trading sessions — acceptable for breakout detection.

---

## File Structure

```
news_breakout/
  models.py            # MODIFY: add TickerAlert
  signals/
    wyckoff.py         # CREATE: detect_range_breakout
    engine.py          # MODIFY: add evaluate_timeframe, evaluate_ticker, TF_WEIGHT; keep evaluate_daily
  data/
    yfinance_source.py # MODIFY: add fetch_intraday_ohlcv
    resample.py        # CREATE: resample_ohlcv
  alerts/
    formatter.py       # MODIFY: add format_ticker_alert (keep format_breakout)
  config.py            # MODIFY: add range_lookback, range_max_width_pct, intraday_period_days
config/config.example.yaml  # MODIFY: add new signal/data keys
run.py                 # MODIFY: multi-timeframe scan
tests/                 # CREATE test_wyckoff.py, test_resample.py, test_ranking.py, test_intraday_source.py; MODIFY others
scripts/check_data.py  # MODIFY: also report 1H availability
```

---

### Task 1: Wyckoff range-breakout detector

**Files:**
- Create: `news_breakout/signals/wyckoff.py`
- Test: `tests/test_wyckoff.py`

**Interfaces:**
- Consumes: OHLCV `DataFrame` (chronological), `range_lookback: int`, `max_width_pct: float`.
- Produces: `news_breakout.signals.wyckoff.detect_range_breakout(df, range_lookback, max_width_pct) -> tuple[bool, float, float]`.
  Returns `(is_breakout, range_low, range_high)` where the range is computed over the
  `range_lookback` bars **before** the current bar. `is_breakout` is True when the
  prior range is tight (`(range_high - range_low) / range_low <= max_width_pct`) AND
  the last Close is strictly above `range_high`. Returns `(False, 0.0, 0.0)` if fewer
  than `range_lookback + 1` rows.

- [ ] **Step 1: Write the failing test**

`tests/test_wyckoff.py`:
```python
from tests.fixtures import make_ohlcv
from news_breakout.signals.wyckoff import detect_range_breakout


def test_breakout_when_tight_range_then_close_above():
    # prior 4 bars range 100..110 (width 10%), last close 112 breaks above 110
    df = make_ohlcv(
        highs=[110, 108, 109, 110, 112],
        lows=[100, 101, 100, 102, 108],
        closes=[105, 104, 106, 107, 112],
        volumes=[1, 1, 1, 1, 1],
    )
    is_bo, low, high = detect_range_breakout(df, range_lookback=4, max_width_pct=0.15)
    assert is_bo is True
    assert low == 100
    assert high == 110


def test_no_breakout_when_range_too_wide():
    # prior range 100..140 = 40% width, exceeds 15% even though close breaks above
    df = make_ohlcv(
        highs=[140, 120, 130, 140, 145],
        lows=[100, 101, 100, 102, 141],
        closes=[110, 104, 106, 107, 144],
        volumes=[1, 1, 1, 1, 1],
    )
    is_bo, low, high = detect_range_breakout(df, range_lookback=4, max_width_pct=0.15)
    assert is_bo is False


def test_no_breakout_when_close_inside_range():
    df = make_ohlcv(
        highs=[110, 108, 109, 110, 109],
        lows=[100, 101, 100, 102, 103],
        closes=[105, 104, 106, 107, 108],  # 108 < range_high 110
        volumes=[1, 1, 1, 1, 1],
    )
    is_bo, low, high = detect_range_breakout(df, range_lookback=4, max_width_pct=0.15)
    assert is_bo is False


def test_no_breakout_when_not_enough_rows():
    df = make_ohlcv(highs=[110, 108], lows=[100, 101], closes=[105, 104], volumes=[1, 1])
    assert detect_range_breakout(df, range_lookback=30, max_width_pct=0.15) == (False, 0.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_wyckoff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.signals.wyckoff'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/signals/wyckoff.py`:
```python
from __future__ import annotations

import pandas as pd


def detect_range_breakout(
    df: pd.DataFrame, range_lookback: int, max_width_pct: float
) -> tuple[bool, float, float]:
    """Wyckoff-style breakout: a tight prior consolidation range, then a close above it."""
    if len(df) < range_lookback + 1:
        return (False, 0.0, 0.0)
    window = df.iloc[-(range_lookback + 1):-1]
    range_high = float(window["High"].max())
    range_low = float(window["Low"].min())
    if range_low <= 0:
        return (False, range_low, range_high)
    width = (range_high - range_low) / range_low
    is_tight = width <= max_width_pct
    breaks_out = float(df["Close"].iloc[-1]) > range_high
    return (is_tight and breaks_out, range_low, range_high)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_wyckoff.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/signals/wyckoff.py tests/test_wyckoff.py
git commit -m "feat: add Wyckoff range-breakout detector"
```

---

### Task 2: Generic per-timeframe evaluator

**Files:**
- Modify: `news_breakout/signals/engine.py`
- Test: `tests/test_engine.py` (add cases; keep existing `evaluate_daily` tests untouched)

**Interfaces:**
- Consumes: `detect_donchian_breakout`, `compute_rvol`, `detect_range_breakout`, `BreakoutSignal`.
- Produces: `news_breakout.signals.engine.evaluate_timeframe(ticker, df, timeframe, *, donchian_lookback, rvol_window, rvol_threshold, range_lookback, range_max_width_pct, now) -> list[BreakoutSignal]`.
  Runs BOTH detectors on `df`; each detected pattern that also passes RVOL
  confirmation (`rvol >= rvol_threshold`) yields one `BreakoutSignal` with the given
  `timeframe`. `signal_type` is `"resistance_breakout"` or `"wyckoff_range_breakout"`.
  Returns `[]` when nothing fires. Existing `evaluate_daily` keeps its behavior and
  signature (delegates to the shared resistance helper).

- [ ] **Step 1: Write the failing test (append to `tests/test_engine.py`)**

```python
from news_breakout.signals.engine import evaluate_timeframe


def _tight_range_breakout_df(last_volume):
    # prior 4 bars tight 100..110, last close 112 breaks both the 4-bar high AND the range
    return make_ohlcv(
        highs=[110, 108, 109, 110, 112],
        lows=[100, 101, 100, 102, 108],
        closes=[105, 104, 106, 107, 112],
        volumes=[100, 100, 100, 100, last_volume],
    )


def test_evaluate_timeframe_returns_both_signal_types():
    df = _tight_range_breakout_df(last_volume=300)  # rvol 3.0
    sigs = evaluate_timeframe(
        "ANTM", df, "4H",
        donchian_lookback=4, rvol_window=4, rvol_threshold=2.0,
        range_lookback=4, range_max_width_pct=0.15, now=NOW,
    )
    types = {s.signal_type for s in sigs}
    assert types == {"resistance_breakout", "wyckoff_range_breakout"}
    assert all(s.timeframe == "4H" for s in sigs)
    assert all(s.rvol == 3.0 for s in sigs)


def test_evaluate_timeframe_empty_when_volume_low():
    df = _tight_range_breakout_df(last_volume=110)  # rvol 1.1 < 2.0
    sigs = evaluate_timeframe(
        "ANTM", df, "1H",
        donchian_lookback=4, rvol_window=4, rvol_threshold=2.0,
        range_lookback=4, range_max_width_pct=0.15, now=NOW,
    )
    assert sigs == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_engine.py -v`
Expected: FAIL with `ImportError: cannot import name 'evaluate_timeframe'`.

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `news_breakout/signals/engine.py` with:
```python
from __future__ import annotations

from datetime import datetime

import pandas as pd

from news_breakout.models import BreakoutSignal
from news_breakout.signals.breakout import detect_donchian_breakout
from news_breakout.signals.volume import compute_rvol
from news_breakout.signals.wyckoff import detect_range_breakout


def _pct_change(df: pd.DataFrame) -> float:
    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    return ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0


def _resistance_signal(
    ticker: str, df: pd.DataFrame, timeframe: str, *,
    donchian_lookback: int, rvol: float, now: datetime,
) -> BreakoutSignal | None:
    is_bo, level = detect_donchian_breakout(df, donchian_lookback)
    if not is_bo:
        return None
    return BreakoutSignal(
        ticker=ticker, timeframe=timeframe, signal_type="resistance_breakout",
        price=float(df["Close"].iloc[-1]), pct_change=_pct_change(df),
        level=level, rvol=rvol, timestamp=now,
    )


def _wyckoff_signal(
    ticker: str, df: pd.DataFrame, timeframe: str, *,
    range_lookback: int, range_max_width_pct: float, rvol: float, now: datetime,
) -> BreakoutSignal | None:
    is_bo, _low, high = detect_range_breakout(df, range_lookback, range_max_width_pct)
    if not is_bo:
        return None
    return BreakoutSignal(
        ticker=ticker, timeframe=timeframe, signal_type="wyckoff_range_breakout",
        price=float(df["Close"].iloc[-1]), pct_change=_pct_change(df),
        level=high, rvol=rvol, timestamp=now,
    )


def evaluate_timeframe(
    ticker: str, df: pd.DataFrame, timeframe: str, *,
    donchian_lookback: int, rvol_window: int, rvol_threshold: float,
    range_lookback: int, range_max_width_pct: float, now: datetime,
) -> list[BreakoutSignal]:
    if len(df) < 2:
        return []
    rvol = compute_rvol(df, rvol_window)
    if rvol < rvol_threshold:
        return []
    signals: list[BreakoutSignal] = []
    res = _resistance_signal(
        ticker, df, timeframe, donchian_lookback=donchian_lookback, rvol=rvol, now=now
    )
    if res is not None:
        signals.append(res)
    wyk = _wyckoff_signal(
        ticker, df, timeframe,
        range_lookback=range_lookback, range_max_width_pct=range_max_width_pct,
        rvol=rvol, now=now,
    )
    if wyk is not None:
        signals.append(wyk)
    return signals


def evaluate_daily(
    ticker: str, df: pd.DataFrame, *,
    lookback: int, rvol_window: int, rvol_threshold: float, now: datetime,
) -> BreakoutSignal | None:
    if len(df) < 2:
        return None
    rvol = compute_rvol(df, rvol_window)
    if rvol < rvol_threshold:
        return None
    return _resistance_signal(
        ticker, df, "1D", donchian_lookback=lookback, rvol=rvol, now=now
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_engine.py -v`
Expected: PASS (all prior `evaluate_daily` tests + 2 new `evaluate_timeframe` tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/signals/engine.py tests/test_engine.py
git commit -m "feat: add generic per-timeframe evaluator (resistance + wyckoff)"
```

---

### Task 3: TickerAlert model + per-ticker aggregation and priority

**Files:**
- Modify: `news_breakout/models.py`
- Modify: `news_breakout/signals/engine.py` (add `TF_WEIGHT`, `evaluate_ticker`)
- Test: `tests/test_ranking.py`

**Interfaces:**
- Produces:
  - `news_breakout.models.TickerAlert` dataclass: `ticker: str`, `signals: list[BreakoutSignal]`,
    `priority: float`, `timestamp: datetime`, plus a `max_rvol` property returning the
    highest `rvol` among its signals.
  - `news_breakout.signals.engine.TF_WEIGHT` = `{"1D": 3.0, "4H": 2.0, "1H": 1.0}`.
  - `news_breakout.signals.engine.evaluate_ticker(ticker, frames, *, donchian_lookback, rvol_window, rvol_threshold, range_lookback, range_max_width_pct, now) -> TickerAlert | None`.
    `frames` is `{timeframe: DataFrame}`. Evaluates each present timeframe (order 1D, 4H,
    1H), collects all signals, and returns a `TickerAlert` with
    `priority = sum(TF_WEIGHT[s.timeframe] for s in signals)`. Returns `None` if no signal fires.

- [ ] **Step 1: Write the failing test**

`tests/test_ranking.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.fixtures import make_ohlcv
from news_breakout.signals.engine import evaluate_ticker

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)

PARAMS = dict(
    donchian_lookback=3, rvol_window=3, rvol_threshold=2.0,
    range_lookback=3, range_max_width_pct=0.15,
)


def _breakout_df():
    return make_ohlcv(
        highs=[110, 108, 110, 116],
        lows=[100, 101, 102, 108],
        closes=[105, 104, 107, 115],
        volumes=[100, 100, 100, 300],  # rvol 3.0
    )


def _flat_df():
    return make_ohlcv(
        highs=[110, 110, 110, 110],
        lows=[100, 100, 100, 100],
        closes=[105, 105, 105, 105],
        volumes=[100, 100, 100, 100],  # rvol 1.0, no breakout
    )


def test_evaluate_ticker_aggregates_and_scores():
    frames = {"1D": _breakout_df(), "1H": _breakout_df()}
    alert = evaluate_ticker("ANTM", frames, now=NOW, **PARAMS)
    assert alert is not None
    assert alert.ticker == "ANTM"
    fired_tfs = {s.timeframe for s in alert.signals}
    assert fired_tfs == {"1D", "1H"}
    # 1D weight 3 + 1H weight 1, counted once per fired signal on each TF
    assert alert.priority >= 4.0
    assert alert.max_rvol == 3.0


def test_evaluate_ticker_none_when_nothing_fires():
    frames = {"1D": _flat_df(), "1H": _flat_df()}
    assert evaluate_ticker("ANTM", frames, now=NOW, **PARAMS) is None


def test_priority_higher_tf_outranks_lower():
    a = evaluate_ticker("A", {"1D": _breakout_df()}, now=NOW, **PARAMS)
    b = evaluate_ticker("B", {"1H": _breakout_df()}, now=NOW, **PARAMS)
    assert a.priority > b.priority
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ranking.py -v`
Expected: FAIL with `ImportError: cannot import name 'evaluate_ticker'`.

- [ ] **Step 3: Write minimal implementation**

Append to `news_breakout/models.py`:
```python
@dataclass
class TickerAlert:
    ticker: str
    signals: list["BreakoutSignal"]
    priority: float
    timestamp: datetime

    @property
    def max_rvol(self) -> float:
        return max(s.rvol for s in self.signals)
```

Append to `news_breakout/signals/engine.py`:
```python
from news_breakout.models import TickerAlert

TF_WEIGHT = {"1D": 3.0, "4H": 2.0, "1H": 1.0}
_TF_ORDER = ["1D", "4H", "1H"]


def evaluate_ticker(
    ticker: str, frames: dict[str, pd.DataFrame], *,
    donchian_lookback: int, rvol_window: int, rvol_threshold: float,
    range_lookback: int, range_max_width_pct: float, now: datetime,
) -> TickerAlert | None:
    signals: list[BreakoutSignal] = []
    for tf in _TF_ORDER:
        df = frames.get(tf)
        if df is None:
            continue
        signals.extend(evaluate_timeframe(
            ticker, df, tf,
            donchian_lookback=donchian_lookback, rvol_window=rvol_window,
            rvol_threshold=rvol_threshold, range_lookback=range_lookback,
            range_max_width_pct=range_max_width_pct, now=now,
        ))
    if not signals:
        return None
    priority = sum(TF_WEIGHT[s.timeframe] for s in signals)
    return TickerAlert(ticker=ticker, signals=signals, priority=priority, timestamp=now)
```

Note: `from news_breakout.models import BreakoutSignal` already exists at the top of
`engine.py`; extend that import to `from news_breakout.models import BreakoutSignal, TickerAlert`
rather than adding a duplicate import line.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ranking.py tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news_breakout/models.py news_breakout/signals/engine.py tests/test_ranking.py
git commit -m "feat: add TickerAlert aggregation with timeframe priority"
```

---

### Task 4: Intraday data source + 4H resample

**Files:**
- Create: `news_breakout/data/resample.py`
- Modify: `news_breakout/data/yfinance_source.py`
- Test: `tests/test_resample.py`, `tests/test_intraday_source.py`

**Interfaces:**
- Produces:
  - `news_breakout.data.resample.resample_ohlcv(df, rule) -> pandas.DataFrame`. Resamples a
    chronological OHLCV frame (DatetimeIndex) with aggregation
    Open=first, High=max, Low=min, Close=last, Volume=sum, dropping empty buckets.
  - `news_breakout.data.yfinance_source.fetch_intraday_ohlcv(tickers, period_days, interval="1h", downloader=None) -> dict[str, pandas.DataFrame]`.
    Same shape/contract as `fetch_daily_ohlcv` but for intraday bars; period is `f"{period_days}d"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_resample.py`:
```python
import pandas as pd

from news_breakout.data.resample import resample_ohlcv


def test_resample_1h_to_4h_aggregates_correctly():
    idx = pd.date_range("2026-01-01 08:00", periods=8, freq="1h")
    df = pd.DataFrame(
        {
            "Open": [10, 11, 12, 13, 20, 21, 22, 23],
            "High": [15, 16, 17, 18, 25, 26, 27, 28],
            "Low": [5, 6, 7, 8, 15, 16, 17, 18],
            "Close": [11, 12, 13, 14, 21, 22, 23, 24],
            "Volume": [1, 2, 3, 4, 5, 6, 7, 8],
        },
        index=idx,
    )
    out = resample_ohlcv(df, "4h")
    assert len(out) == 2
    first = out.iloc[0]
    assert first["Open"] == 10 and first["High"] == 18
    assert first["Low"] == 5 and first["Close"] == 14 and first["Volume"] == 10
    second = out.iloc[1]
    assert second["Open"] == 20 and second["High"] == 28
    assert second["Low"] == 15 and second["Close"] == 24 and second["Volume"] == 26


def test_resample_drops_empty_buckets():
    idx = pd.DatetimeIndex(["2026-01-01 08:00", "2026-01-01 20:00"])
    df = pd.DataFrame(
        {"Open": [10, 20], "High": [15, 25], "Low": [5, 15], "Close": [11, 21], "Volume": [1, 2]},
        index=idx,
    )
    out = resample_ohlcv(df, "4h")
    assert len(out) == 2  # the empty 4h buckets between are dropped
```

`tests/test_intraday_source.py`:
```python
import pandas as pd

from news_breakout.data.yfinance_source import fetch_intraday_ohlcv


def _one(n):
    idx = pd.date_range("2026-01-01 09:00", periods=n, freq="1h")
    return pd.DataFrame(
        {"Open": 100, "High": 100, "Low": 100, "Close": 100, "Volume": 100}, index=idx
    )


def test_fetch_intraday_maps_ticker_and_drops_empty():
    combined = pd.concat({"ANTM.JK": _one(4), "BREN.JK": _one(0)}, axis=1)

    def fake_downloader(tickers, period, interval, group_by, auto_adjust, progress, threads):
        assert period == "60d" and interval == "1h"
        return combined

    out = fetch_intraday_ohlcv(["ANTM", "BREN"], period_days=60, downloader=fake_downloader)
    assert "ANTM" in out and "BREN" not in out
    assert list(out["ANTM"].columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out["ANTM"]) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_resample.py tests/test_intraday_source.py -v`
Expected: FAIL with `ModuleNotFoundError` for `news_breakout.data.resample` / missing `fetch_intraday_ohlcv`.

- [ ] **Step 3: Write minimal implementations**

`news_breakout/data/resample.py`:
```python
from __future__ import annotations

import pandas as pd

_AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample a chronological OHLCV frame to a coarser bar `rule` (e.g. '4h')."""
    out = df.resample(rule).agg(_AGG)
    return out.dropna(how="all")[["Open", "High", "Low", "Close", "Volume"]]
```

Add to `news_breakout/data/yfinance_source.py` (reuse the existing `_COLUMNS` and the
same per-ticker extraction pattern as `fetch_daily_ohlcv`):
```python
def fetch_intraday_ohlcv(
    tickers: list[str], period_days: int, interval: str = "1h", downloader=None
) -> dict[str, pd.DataFrame]:
    """Download intraday OHLCV for `.JK` tickers; return {original_ticker: DataFrame}."""
    if downloader is None:
        import yfinance as yf

        downloader = yf.download

    jk = [f"{t}.JK" for t in tickers]
    raw = downloader(
        jk,
        period=f"{period_days}d",
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        jk_t = f"{t}.JK"
        try:
            sub = raw[jk_t]
        except (KeyError, TypeError):
            continue
        sub = sub[[c for c in _COLUMNS if c in sub.columns]].dropna(how="all")
        if sub.empty:
            continue
        out[t] = sub[_COLUMNS]
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_resample.py tests/test_intraday_source.py -v`
Expected: PASS.

- [ ] **Step 5: Real 1H data-availability spike**

Modify `scripts/check_data.py` to also fetch 1H and report coverage:
```python
from news_breakout.config import load_settings
from news_breakout.data.yfinance_source import (
    fetch_daily_ohlcv, fetch_intraday_ohlcv, report_availability,
)

s = load_settings()
daily = fetch_daily_ohlcv(s.watchlist, s.history_days)
intra = fetch_intraday_ohlcv(s.watchlist, s.intraday_period_days)
d_report = report_availability(daily, s.watchlist, min_bars=s.donchian_lookback + 1)
i_report = report_availability(intra, s.watchlist, min_bars=s.donchian_lookback + 1)
print(f"{'ticker':7} {'1D':8} {'1H':8}")
for t in sorted(s.watchlist):
    print(f"{t:7} {d_report[t]:8} {i_report.get(t, 'missing'):8}")
```

Run: `PYTHONPATH=. .venv/Scripts/python.exe scripts/check_data.py`
Expected: a real network call printing 1D and 1H coverage for all 24 tickers. **Record any
ticker whose 1H is `thin`/`missing`** — those tickers will simply produce fewer timeframes
in the scan (the scan already handles absent frames gracefully). This confirms intraday
coverage before wiring it in.

- [ ] **Step 6: Commit**

```bash
git add news_breakout/data/resample.py news_breakout/data/yfinance_source.py scripts/check_data.py tests/test_resample.py tests/test_intraday_source.py
git commit -m "feat: add intraday data source and 1H->4H resampling"
```

---

### Task 5: Multi-timeframe alert formatter

**Files:**
- Modify: `news_breakout/alerts/formatter.py`
- Test: `tests/test_formatter.py` (add cases; keep `format_breakout` tests untouched)

**Interfaces:**
- Consumes: `TickerAlert`, `BreakoutSignal`.
- Produces: `news_breakout.alerts.formatter.format_ticker_alert(alert: TickerAlert) -> str`.
  A Telegram-ready message with the ticker, a priority indicator, the latest price, and
  one line per fired signal (timeframe, signal-type label, broken level, RVOL), plus the
  WIB timestamp. Reuses the existing `_rupiah` helper.

- [ ] **Step 1: Write the failing test (append to `tests/test_formatter.py`)**

```python
from news_breakout.models import TickerAlert
from news_breakout.alerts.formatter import format_ticker_alert


def test_format_ticker_alert_lists_each_timeframe():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sigs = [
        BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1480.0, 2.7, ts),
        BreakoutSignal("ANTM", "4H", "wyckoff_range_breakout", 1500.0, 3.4, 1450.0, 2.1, ts),
    ]
    alert = TickerAlert("ANTM", sigs, priority=5.0, timestamp=ts)
    msg = format_ticker_alert(alert)
    assert "ANTM" in msg
    assert "1D" in msg and "4H" in msg
    assert "1.480" in msg and "1.450" in msg
    assert "2.7" in msg and "2.1" in msg
    assert "15:30" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_formatter.py -v`
Expected: FAIL with `ImportError: cannot import name 'format_ticker_alert'`.

- [ ] **Step 3: Write minimal implementation (append to `news_breakout/alerts/formatter.py`)**

```python
from news_breakout.models import TickerAlert

_SIGNAL_LABEL = {
    "resistance_breakout": "Resistance breakout (new high)",
    "wyckoff_range_breakout": "Wyckoff range breakout",
}


def format_ticker_alert(alert: TickerAlert) -> str:
    price = alert.signals[0].price
    lines = [
        f"🚨 BREAKOUT — {alert.ticker}  ⭐{alert.priority:.0f}",
        "━━━━━━━━━━━━━━━━━━━",
        f"Harga : {_rupiah(price)}",
    ]
    for s in alert.signals:
        arrow = "🟢" if s.rvol >= 2.0 else "🟡"
        label = _SIGNAL_LABEL.get(s.signal_type, s.signal_type)
        lines.append(
            f"• TF {s.timeframe}: {label} · level {_rupiah(s.level)} · RVOL {s.rvol:.1f}× {arrow}"
        )
    lines.append(f"⏱️ {alert.timestamp:%H:%M} WIB · delay data ~15 mnt")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_formatter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news_breakout/alerts/formatter.py tests/test_formatter.py
git commit -m "feat: add multi-timeframe ticker alert formatter"
```

---

### Task 6: Config additions + multi-timeframe `run.py` wiring

**Files:**
- Modify: `news_breakout/config.py`, `config/config.example.yaml`, `tests/test_config.py`
- Modify: `run.py`, `tests/test_run_smoke.py`

**Interfaces:**
- `Settings` gains `range_lookback: int`, `range_max_width_pct: float`, `intraday_period_days: int`.
- `run.scan_once(settings, daily_data, intraday_data, store, *, now, sender=send_message) -> list[str]`
  builds `frames` per ticker (1D from daily; 1H from intraday; 4H via `resample_ohlcv(intraday, "4h")`),
  calls `evaluate_ticker`, ranks alerts by `(priority, max_rvol)` descending, dedups per
  `(ticker, "aggregated", "MULTI", date_str)`, sends `format_ticker_alert`, and returns
  alerted tickers in send order. `date_str` = the latest 1D bar date if present, else `now`.

- [ ] **Step 1: Write the failing test (update `tests/test_run_smoke.py`)**

Replace the smoke test's settings/data helpers and add a multi-timeframe test:
```python
def _settings():
    return Settings(
        watchlist=["ANTM"], donchian_lookback=3, rvol_threshold=2.0, rvol_window=3,
        history_days=120, range_lookback=3, range_max_width_pct=0.15,
        intraday_period_days=60,
        telegram_bot_token="tok", telegram_breakout_chat_id="-100", dry_run=True,
    )


def _breakout_daily():
    return {"ANTM": make_ohlcv(
        highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
        closes=[100, 100, 100, 115], volumes=[100, 100, 100, 300])}


def test_scan_once_multitf_alerts_then_dedups():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    first = run.scan_once(_settings(), _breakout_daily(), {}, store, now=NOW, sender=sender)
    assert first == ["ANTM"]
    assert len(sent) == 1 and "ANTM" in sent[0]
    second = run.scan_once(_settings(), _breakout_daily(), {}, store, now=NOW, sender=sender)
    assert second == []
    assert len(sent) == 1
    store.close()
```
(Delete the old M1 `_settings`/`_breakout_data`/`test_scan_once_alerts_then_dedups`/
`test_failed_send_is_not_marked_and_retries` bodies that referenced the two-arg
`scan_once`, or update them to the new three-data-arg signature — the failed-send test
should pass `{}` as `intraday_data` and assert retry behavior as before.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run_smoke.py -v`
Expected: FAIL (signature mismatch / `TypeError`).

- [ ] **Step 3: Write minimal implementation**

Add the three fields to `Settings` in `news_breakout/config.py` and read them in
`load_settings` (from the `signals` and `data` sections):
```python
# in Settings:
    range_lookback: int
    range_max_width_pct: float
    intraday_period_days: int
# in load_settings return Settings(...):
        range_lookback=signals["range_lookback"],
        range_max_width_pct=signals["range_max_width_pct"],
        intraday_period_days=data["intraday_period_days"],
```

Add to `config/config.example.yaml` under the existing sections:
```yaml
signals:
  donchian_lookback: 20
  rvol_threshold: 2.0
  rvol_window: 20
  range_lookback: 30
  range_max_width_pct: 0.15

data:
  history_days: 120
  intraday_period_days: 60
```

Update `tests/test_config.py`'s YAML fixture to include the new keys and assert them
(add `range_lookback: 30`, `range_max_width_pct: 0.15` to `signals`; `intraday_period_days: 60`
to `data`; assert `s.range_lookback == 30`, `s.range_max_width_pct == 0.15`,
`s.intraday_period_days == 60`).

Rewrite `run.py`'s `scan_once` and `main`:
```python
from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings, load_settings
from news_breakout.data.yfinance_source import fetch_daily_ohlcv, fetch_intraday_ohlcv
from news_breakout.data.resample import resample_ohlcv
from news_breakout.signals.engine import evaluate_ticker
from news_breakout.alerts.dedup import DedupStore
from news_breakout.alerts.formatter import format_ticker_alert
from news_breakout.alerts.telegram import send_message

WIB = ZoneInfo("Asia/Jakarta")


def scan_once(settings: Settings, daily_data, intraday_data, store: DedupStore,
              *, now, sender=send_message) -> list[str]:
    alerts = []
    for ticker in settings.watchlist:
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
            rvol_threshold=settings.rvol_threshold, range_lookback=settings.range_lookback,
            range_max_width_pct=settings.range_max_width_pct, now=now,
        )
        if alert is not None:
            alerts.append(alert)

    alerts.sort(key=lambda a: (a.priority, a.max_rvol), reverse=True)

    alerted: list[str] = []
    for alert in alerts:
        if "1D" in {s.timeframe for s in alert.signals}:
            date_str = daily_data[alert.ticker].index[-1].strftime("%Y-%m-%d")
        else:
            date_str = now.strftime("%Y-%m-%d")
        if store.already_sent(alert.ticker, "aggregated", "MULTI", date_str):
            continue
        text = format_ticker_alert(alert)
        if not sender(settings.telegram_bot_token, settings.telegram_breakout_chat_id,
                      text, dry_run=settings.dry_run):
            continue
        store.mark_sent(alert.ticker, "aggregated", "MULTI", date_str)
        alerted.append(alert.ticker)
    return alerted


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    settings = load_settings()
    daily = fetch_daily_ohlcv(settings.watchlist, settings.history_days)
    intraday = fetch_intraday_ohlcv(settings.watchlist, settings.intraday_period_days)
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")
    try:
        now = datetime.now(WIB)
        alerted = scan_once(settings, daily, intraday, store, now=now)
        print(f"Scan complete. Alerted: {alerted or 'none'}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all tests PASS (M1 tests still green, new M2 tests green).

- [ ] **Step 5: End-to-end dry-run against live data**

Run: `PYTHONPATH=. .venv/Scripts/python.exe run.py`
Expected: fetches live 1D + 1H data for the 24 tickers, evaluates multi-timeframe, prints
`[DRY-RUN]` aggregated alert blocks (with per-TF lines and ⭐priority) or `Alerted: none`.
No Telegram send while `dry_run: true`. If 1H is unavailable for some tickers, they simply
scan on 1D only — no crash.

- [ ] **Step 6: Commit**

```bash
git add news_breakout/config.py config/config.example.yaml tests/test_config.py run.py tests/test_run_smoke.py
git commit -m "feat: wire multi-timeframe scan with ranked aggregated alerts"
```

---

## Self-Review

**Spec coverage (M2 slice):**
- 1H timeframe → Task 4 (`fetch_intraday_ohlcv`), Task 6 (wiring) ✔
- 4H resampled from 1H → Task 4 (`resample_ohlcv`), Task 6 ✔
- Wyckoff accumulation-range breakout → Task 1, Task 2 ✔
- RVOL confirmation on every TF → Task 2 ✔
- Multi-timeframe priority ranking → Task 3 (`TF_WEIGHT`, `evaluate_ticker`), Task 6 (sort) ✔
- One aggregated alert per ticker → Task 3, Task 5, Task 6 ✔
- Anti-spam dedup per (ticker, date) → Task 6 ✔
- 1H data-availability verification → Task 4 Step 5 ✔
- *Deferred (out of M2 scope):* scheduler/market-hours/universe/weekend (M3), news (M4), deploy (M5), ATR-based contraction refinement of Wyckoff.

**Placeholder scan:** none — every code step has complete code; every run step has an exact command and expected output.

**Type consistency:** `BreakoutSignal` (M1) reused unchanged; `evaluate_timeframe -> list[BreakoutSignal]` (Task 2) feeds `evaluate_ticker -> TickerAlert | None` (Task 3); `TickerAlert.signals`/`.priority`/`.max_rvol` used by `format_ticker_alert` (Task 5) and `scan_once` sort (Task 6). `evaluate_ticker` param names match across Tasks 3 and 6. `fetch_intraday_ohlcv` return type matches `scan_once` iteration. `resample_ohlcv(df, "4h")` signature matches Task 6 usage. `evaluate_daily` kept intact so M1 engine tests stay green.

---

## After M2

Once M2 is green and the live dry-run shows aggregated multi-TF alerts, we write M3: APScheduler,
IDX market-hours + holiday calendar, liquid universe auto-filter, and the weekend deep-scan.
