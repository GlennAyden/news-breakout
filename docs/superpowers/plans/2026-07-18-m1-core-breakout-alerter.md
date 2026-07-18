# Milestone 1 — Core Breakout Alerter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable tool that scans the IDX watchlist on the daily (1D) timeframe, detects volume-confirmed new-high (Donchian) breakouts, de-duplicates them, and pushes formatted alerts to Telegram (with a dry-run mode).

**Architecture:** A single-pass pipeline (`run.py`) wires five focused modules — config loader, yfinance data source, signal engine (Donchian breakout + RVOL), SQLite dedup store, and Telegram dispatcher. No scheduler yet: one invocation = one scan. Later milestones add multi-timeframe/Wyckoff, scheduling, universe auto-filter, news, and deployment.

**Tech Stack:** Python 3.12 · `yfinance` · `pandas` · `pydantic` v2 + `pydantic-settings` · `PyYAML` · `httpx` · `pytest`

## Global Constraints

- Python **3.12** (matches VPS `hermes-vps`).
- All timestamps in timezone **Asia/Jakarta (WIB)**, explicit — never naive local time.
- **No API keys / no paid data.** Price data via `yfinance` (free, ticker suffix `.JK`, ~15-min delay).
- Keep memory small: fetch only the history window needed (≤ ~120 bars/ticker), process per-ticker. Target < 300 MB RAM.
- **Anti-spam:** a given (ticker, signal_type, timeframe) fires at most once per trading date.
- Secrets live only in `.env` (git-ignored). Never commit tokens. `config.yaml` holds non-secret config.
- Default signal params (tunable via config): Donchian lookback **20**, RVOL threshold **2.0×**, RVOL window **20**.

---

## File Structure

```
news-breakout/
  news_breakout/
    __init__.py
    config.py            # load .env + config.yaml into typed Settings
    models.py            # BreakoutSignal dataclass
    data/
      __init__.py
      yfinance_source.py # fetch daily OHLCV, data-availability check
    signals/
      __init__.py
      volume.py          # compute_rvol
      breakout.py        # detect_donchian_breakout
      engine.py          # evaluate_daily -> Optional[BreakoutSignal]
    alerts/
      __init__.py
      dedup.py           # SQLite sent-alerts store
      formatter.py       # BreakoutSignal -> Telegram text
      telegram.py        # send_message (httpx, dry-run aware)
  config/
    config.example.yaml
  .env.example
  run.py                 # single-pass entrypoint
  requirements.txt
  tests/
    conftest.py
    fixtures.py          # synthetic OHLCV builders
    test_config.py
    test_yfinance_source.py
    test_volume.py
    test_breakout.py
    test_engine.py
    test_dedup.py
    test_formatter.py
    test_telegram.py
    test_run_smoke.py
```

Each module has one responsibility. Signal math (`volume.py`, `breakout.py`) is pure and network-free so it is trivially testable; all network access is isolated in `data/yfinance_source.py` and `alerts/telegram.py`.

---

### Task 1: Project scaffolding, dependencies, and typed config loader

**Files:**
- Create: `requirements.txt`
- Create: `news_breakout/__init__.py` (empty)
- Create: `news_breakout/config.py`
- Create: `config/config.example.yaml`
- Create: `.env.example`
- Create: `tests/conftest.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `news_breakout.config.Settings` (pydantic model) with fields:
    `watchlist: list[str]`, `donchian_lookback: int`, `rvol_threshold: float`,
    `rvol_window: int`, `history_days: int`, `telegram_bot_token: str`,
    `telegram_breakout_chat_id: str`, `dry_run: bool`.
  - `news_breakout.config.load_settings(config_path: str = "config/config.yaml", env_path: str = ".env") -> Settings`.

- [ ] **Step 1: Create `requirements.txt`**

```text
yfinance==0.2.66
pandas==2.2.3
pydantic==2.9.2
pydantic-settings==2.5.2
PyYAML==6.0.2
httpx==0.27.2
pytest==8.3.3
```

- [ ] **Step 2: Create a virtualenv and install deps**

Run (Windows PowerShell):
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```
Expected: all packages install without error. `python --version` prints 3.12.x.

- [ ] **Step 3: Create the example config files**

`config/config.example.yaml`:
```yaml
# Non-secret configuration. Copy to config/config.yaml and edit.
watchlist:
  - ANTM
  - ARCI
  - BREN
  - BRMS
  - BRPT
  - BUMI
  - BUVA
  - CUAN
  - DEWA
  - DSSA
  - ENRG
  - HRUM
  - IMPC
  - MEDC
  - MINA
  - PANI
  - PTRO
  - RATU
  - RAJA
  - TINS
  - TOBA
  - TPIA
  - VKTR
  - WIFI

signals:
  donchian_lookback: 20
  rvol_threshold: 2.0
  rvol_window: 20

data:
  history_days: 120

runtime:
  dry_run: true   # true = log alerts instead of sending to Telegram
```

`.env.example`:
```text
# Secrets — copy to .env and fill in. .env is git-ignored.
TELEGRAM_BOT_TOKEN=123456:REPLACE_ME
TELEGRAM_BREAKOUT_CHAT_ID=-1000000000000
```

- [ ] **Step 4: Write the failing test**

`tests/conftest.py`:
```python
import sys
from pathlib import Path

# Make the project root importable when running pytest from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

`tests/test_config.py`:
```python
from news_breakout.config import load_settings


def test_load_settings_merges_yaml_and_env(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM, BBRI]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20}\n"
        "data: {history_days: 120}\n"
        "runtime: {dry_run: true}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=abc:123\nTELEGRAM_BREAKOUT_CHAT_ID=-100999\n",
        encoding="utf-8",
    )

    s = load_settings(str(cfg), str(env))

    assert s.watchlist == ["ANTM", "BBRI"]
    assert s.donchian_lookback == 20
    assert s.rvol_threshold == 2.0
    assert s.rvol_window == 20
    assert s.history_days == 120
    assert s.dry_run is True
    assert s.telegram_bot_token == "abc:123"
    assert s.telegram_breakout_chat_id == "-100999"
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.config'`.

- [ ] **Step 6: Write minimal implementation**

`news_breakout/__init__.py`:
```python
```
(empty file)

`news_breakout/config.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class Settings(BaseModel):
    watchlist: list[str]
    donchian_lookback: int
    rvol_threshold: float
    rvol_window: int
    history_days: int
    telegram_bot_token: str
    telegram_breakout_chat_id: str
    dry_run: bool


def _load_env_file(env_path: str) -> None:
    """Minimal .env loader: KEY=VALUE lines into os.environ (no override)."""
    p = Path(env_path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_settings(
    config_path: str = "config/config.yaml", env_path: str = ".env"
) -> Settings:
    _load_env_file(env_path)
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    signals = raw.get("signals", {})
    data = raw.get("data", {})
    runtime = raw.get("runtime", {})
    return Settings(
        watchlist=raw["watchlist"],
        donchian_lookback=signals["donchian_lookback"],
        rvol_threshold=signals["rvol_threshold"],
        rvol_window=signals["rvol_window"],
        history_days=data["history_days"],
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_breakout_chat_id=os.environ["TELEGRAM_BREAKOUT_CHAT_ID"],
        dry_run=runtime["dry_run"],
    )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt news_breakout/ config/ .env.example tests/conftest.py tests/test_config.py
git commit -m "feat: project scaffolding and typed config loader"
```

---

### Task 2: Data models

**Files:**
- Create: `news_breakout/models.py`
- Test: `tests/test_config.py` already covers config; models get exercised in later tasks, but define & smoke-test the dataclass here.
- Test: add `tests/test_models.py`

**Interfaces:**
- Produces: `news_breakout.models.BreakoutSignal` dataclass with fields
  `ticker: str`, `timeframe: str`, `signal_type: str`, `price: float`,
  `pct_change: float`, `level: float`, `rvol: float`, `timestamp: datetime`.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal


def test_breakout_signal_holds_fields():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sig = BreakoutSignal(
        ticker="ANTM",
        timeframe="1D",
        signal_type="resistance_breakout",
        price=1500.0,
        pct_change=3.4,
        level=1480.0,
        rvol=2.7,
        timestamp=ts,
    )
    assert sig.ticker == "ANTM"
    assert sig.timeframe == "1D"
    assert sig.rvol == 2.7
    assert sig.timestamp.tzinfo is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.models'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class BreakoutSignal:
    ticker: str
    timeframe: str
    signal_type: str
    price: float
    pct_change: float
    level: float
    rvol: float
    timestamp: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news_breakout/models.py tests/test_models.py
git commit -m "feat: add BreakoutSignal model"
```

---

### Task 3: Volume — RVOL computation

**Files:**
- Create: `news_breakout/signals/__init__.py` (empty)
- Create: `news_breakout/signals/volume.py`
- Create: `tests/fixtures.py`
- Test: `tests/test_volume.py`

**Interfaces:**
- Consumes: a `pandas.DataFrame` with a `Volume` column (chronological, oldest first).
- Produces: `news_breakout.signals.volume.compute_rvol(df, window: int) -> float`.
  Returns `last_volume / mean(previous `window` volumes)`. Returns `0.0` if the
  average is zero or there are fewer than `window + 1` rows.

- [ ] **Step 1: Write the shared fixture helper**

`tests/fixtures.py`:
```python
from __future__ import annotations

import pandas as pd


def make_ohlcv(highs, lows, closes, volumes, opens=None):
    """Build a chronological OHLCV DataFrame (oldest row first)."""
    n = len(closes)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": opens if opens is not None else closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        },
        index=idx,
    )
```

- [ ] **Step 2: Write the failing test**

`tests/test_volume.py`:
```python
from tests.fixtures import make_ohlcv
from news_breakout.signals.volume import compute_rvol


def test_rvol_is_last_over_average_of_previous_window():
    # previous 4 volumes average = 100; last = 300 -> rvol 3.0
    df = make_ohlcv(
        highs=[1, 1, 1, 1, 1],
        lows=[1, 1, 1, 1, 1],
        closes=[1, 1, 1, 1, 1],
        volumes=[100, 100, 100, 100, 300],
    )
    assert compute_rvol(df, window=4) == 3.0


def test_rvol_zero_when_not_enough_rows():
    df = make_ohlcv(highs=[1, 1], lows=[1, 1], closes=[1, 1], volumes=[100, 200])
    assert compute_rvol(df, window=20) == 0.0


def test_rvol_zero_when_average_is_zero():
    df = make_ohlcv(
        highs=[1, 1, 1], lows=[1, 1, 1], closes=[1, 1, 1], volumes=[0, 0, 500]
    )
    assert compute_rvol(df, window=2) == 0.0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_volume.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.signals.volume'`.

- [ ] **Step 4: Write minimal implementation**

`news_breakout/signals/__init__.py`:
```python
```
(empty file)

`news_breakout/signals/volume.py`:
```python
from __future__ import annotations

import pandas as pd


def compute_rvol(df: pd.DataFrame, window: int) -> float:
    """Relative volume: last bar's volume / mean of the previous `window` bars."""
    if len(df) < window + 1:
        return 0.0
    prev = df["Volume"].iloc[-(window + 1):-1]
    avg = float(prev.mean())
    if avg <= 0:
        return 0.0
    return float(df["Volume"].iloc[-1]) / avg
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_volume.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add news_breakout/signals/__init__.py news_breakout/signals/volume.py tests/fixtures.py tests/test_volume.py
git commit -m "feat: add RVOL computation"
```

---

### Task 4: Breakout — Donchian new-high detection

**Files:**
- Create: `news_breakout/signals/breakout.py`
- Test: `tests/test_breakout.py`

**Interfaces:**
- Consumes: OHLCV `DataFrame` (chronological), `lookback: int`.
- Produces: `news_breakout.signals.breakout.detect_donchian_breakout(df, lookback: int) -> tuple[bool, float]`.
  Returns `(is_breakout, level)` where `level` is the highest High of the previous
  `lookback` bars (the resistance broken). `is_breakout` is True when the last
  Close is strictly greater than that level. Returns `(False, 0.0)` if fewer than
  `lookback + 1` rows.

- [ ] **Step 1: Write the failing test**

`tests/test_breakout.py`:
```python
from tests.fixtures import make_ohlcv
from news_breakout.signals.breakout import detect_donchian_breakout


def test_breakout_true_when_close_exceeds_prior_high():
    # prior 3 highs max = 110; last close = 115 -> breakout, level 110
    df = make_ohlcv(
        highs=[100, 105, 110, 116],
        lows=[90, 95, 100, 108],
        closes=[95, 100, 105, 115],
        volumes=[1, 1, 1, 1],
    )
    is_bo, level = detect_donchian_breakout(df, lookback=3)
    assert is_bo is True
    assert level == 110


def test_no_breakout_when_close_below_prior_high():
    df = make_ohlcv(
        highs=[100, 105, 110, 111],
        lows=[90, 95, 100, 101],
        closes=[95, 100, 105, 108],  # 108 < 110
        volumes=[1, 1, 1, 1],
    )
    is_bo, level = detect_donchian_breakout(df, lookback=3)
    assert is_bo is False
    assert level == 110


def test_no_breakout_when_not_enough_rows():
    df = make_ohlcv(highs=[100, 105], lows=[90, 95], closes=[95, 100], volumes=[1, 1])
    is_bo, level = detect_donchian_breakout(df, lookback=20)
    assert is_bo is False
    assert level == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_breakout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.signals.breakout'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/signals/breakout.py`:
```python
from __future__ import annotations

import pandas as pd


def detect_donchian_breakout(df: pd.DataFrame, lookback: int) -> tuple[bool, float]:
    """Detect a new-high breakout: last Close above the max High of the prior `lookback` bars."""
    if len(df) < lookback + 1:
        return (False, 0.0)
    prior_high = float(df["High"].iloc[-(lookback + 1):-1].max())
    last_close = float(df["Close"].iloc[-1])
    return (last_close > prior_high, prior_high)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_breakout.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/signals/breakout.py tests/test_breakout.py
git commit -m "feat: add Donchian new-high breakout detection"
```

---

### Task 5: Signal engine — combine breakout + volume into a BreakoutSignal

**Files:**
- Create: `news_breakout/signals/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `detect_donchian_breakout`, `compute_rvol`, `BreakoutSignal`.
- Produces: `news_breakout.signals.engine.evaluate_daily(ticker: str, df, *, lookback: int, rvol_window: int, rvol_threshold: float, now) -> BreakoutSignal | None`.
  Returns a `BreakoutSignal` only when there is a breakout AND `rvol >= rvol_threshold`;
  otherwise `None`. `pct_change` = percent change of last Close vs previous Close.
  `timestamp` = the passed-in `now` (tz-aware).

- [ ] **Step 1: Write the failing test**

`tests/test_engine.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.fixtures import make_ohlcv
from news_breakout.signals.engine import evaluate_daily

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)


def _breakout_df(last_volume):
    # prior 3 highs max = 110; last close 115 breaks out. prior vols avg 100.
    return make_ohlcv(
        highs=[100, 105, 110, 116],
        lows=[90, 95, 100, 108],
        closes=[100, 100, 100, 115],
        volumes=[100, 100, 100, last_volume],
    )


def test_signal_when_breakout_and_volume_confirmed():
    df = _breakout_df(last_volume=300)  # rvol 3.0 >= 2.0
    sig = evaluate_daily(
        "ANTM", df, lookback=3, rvol_window=3, rvol_threshold=2.0, now=NOW
    )
    assert sig is not None
    assert sig.ticker == "ANTM"
    assert sig.timeframe == "1D"
    assert sig.signal_type == "resistance_breakout"
    assert sig.price == 115
    assert sig.level == 110
    assert sig.rvol == 3.0
    assert round(sig.pct_change, 1) == 15.0  # 100 -> 115
    assert sig.timestamp == NOW


def test_no_signal_when_volume_too_low():
    df = _breakout_df(last_volume=120)  # rvol 1.2 < 2.0
    sig = evaluate_daily(
        "ANTM", df, lookback=3, rvol_window=3, rvol_threshold=2.0, now=NOW
    )
    assert sig is None


def test_no_signal_when_no_breakout():
    df = make_ohlcv(
        highs=[100, 105, 110, 111],
        lows=[90, 95, 100, 101],
        closes=[100, 100, 100, 108],  # no breakout
        volumes=[100, 100, 100, 500],
    )
    sig = evaluate_daily(
        "ANTM", df, lookback=3, rvol_window=3, rvol_threshold=2.0, now=NOW
    )
    assert sig is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.signals.engine'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/signals/engine.py`:
```python
from __future__ import annotations

from datetime import datetime

import pandas as pd

from news_breakout.models import BreakoutSignal
from news_breakout.signals.breakout import detect_donchian_breakout
from news_breakout.signals.volume import compute_rvol


def evaluate_daily(
    ticker: str,
    df: pd.DataFrame,
    *,
    lookback: int,
    rvol_window: int,
    rvol_threshold: float,
    now: datetime,
) -> BreakoutSignal | None:
    if len(df) < 2:
        return None
    is_bo, level = detect_donchian_breakout(df, lookback)
    if not is_bo:
        return None
    rvol = compute_rvol(df, rvol_window)
    if rvol < rvol_threshold:
        return None

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    pct_change = ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0

    return BreakoutSignal(
        ticker=ticker,
        timeframe="1D",
        signal_type="resistance_breakout",
        price=last_close,
        pct_change=pct_change,
        level=level,
        rvol=rvol,
        timestamp=now,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_engine.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/signals/engine.py tests/test_engine.py
git commit -m "feat: add daily signal engine combining breakout and volume"
```

---

### Task 6: Dedup store (SQLite)

**Files:**
- Create: `news_breakout/alerts/__init__.py` (empty)
- Create: `news_breakout/alerts/dedup.py`
- Test: `tests/test_dedup.py`

**Interfaces:**
- Produces: `news_breakout.alerts.dedup.DedupStore(db_path: str)` with methods:
  - `already_sent(ticker: str, signal_type: str, timeframe: str, date_str: str) -> bool`
  - `mark_sent(ticker: str, signal_type: str, timeframe: str, date_str: str) -> None`
  - `close() -> None`
  `date_str` is the trading date `YYYY-MM-DD` (WIB). Uses `":memory:"` for tests.

- [ ] **Step 1: Write the failing test**

`tests/test_dedup.py`:
```python
from news_breakout.alerts.dedup import DedupStore


def test_mark_then_already_sent():
    store = DedupStore(":memory:")
    args = ("ANTM", "resistance_breakout", "1D", "2026-07-17")
    assert store.already_sent(*args) is False
    store.mark_sent(*args)
    assert store.already_sent(*args) is True
    store.close()


def test_different_date_is_not_deduped():
    store = DedupStore(":memory:")
    store.mark_sent("ANTM", "resistance_breakout", "1D", "2026-07-17")
    assert store.already_sent("ANTM", "resistance_breakout", "1D", "2026-07-18") is False
    store.close()


def test_mark_sent_is_idempotent():
    store = DedupStore(":memory:")
    args = ("BREN", "resistance_breakout", "1D", "2026-07-17")
    store.mark_sent(*args)
    store.mark_sent(*args)  # must not raise
    assert store.already_sent(*args) is True
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dedup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.alerts.dedup'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/alerts/__init__.py`:
```python
```
(empty file)

`news_breakout/alerts/dedup.py`:
```python
from __future__ import annotations

import sqlite3


class DedupStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_alerts (
                ticker TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                date_str TEXT NOT NULL,
                PRIMARY KEY (ticker, signal_type, timeframe, date_str)
            )
            """
        )
        self._conn.commit()

    def already_sent(
        self, ticker: str, signal_type: str, timeframe: str, date_str: str
    ) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM sent_alerts WHERE ticker=? AND signal_type=? "
            "AND timeframe=? AND date_str=?",
            (ticker, signal_type, timeframe, date_str),
        )
        return cur.fetchone() is not None

    def mark_sent(
        self, ticker: str, signal_type: str, timeframe: str, date_str: str
    ) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO sent_alerts VALUES (?, ?, ?, ?)",
            (ticker, signal_type, timeframe, date_str),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dedup.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/alerts/__init__.py news_breakout/alerts/dedup.py tests/test_dedup.py
git commit -m "feat: add SQLite dedup store"
```

---

### Task 7: Alert formatter

**Files:**
- Create: `news_breakout/alerts/formatter.py`
- Test: `tests/test_formatter.py`

**Interfaces:**
- Consumes: `BreakoutSignal`.
- Produces: `news_breakout.alerts.formatter.format_breakout(sig: BreakoutSignal) -> str`.
  Returns a Telegram-ready message string containing ticker, signal label,
  price, pct change, broken level, RVOL, and the WIB timestamp.

- [ ] **Step 1: Write the failing test**

`tests/test_formatter.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal
from news_breakout.alerts.formatter import format_breakout


def test_format_contains_key_fields():
    sig = BreakoutSignal(
        ticker="ANTM",
        timeframe="1D",
        signal_type="resistance_breakout",
        price=1500.0,
        pct_change=3.4,
        level=1480.0,
        rvol=2.7,
        timestamp=datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta")),
    )
    msg = format_breakout(sig)
    assert "ANTM" in msg
    assert "1D" in msg
    assert "1.480" in msg          # level, thousands-formatted
    assert "1.500" in msg          # price
    assert "3.4%" in msg
    assert "2.7" in msg            # rvol
    assert "15:30" in msg          # WIB time
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_formatter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.alerts.formatter'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/alerts/formatter.py`:
```python
from __future__ import annotations

from news_breakout.models import BreakoutSignal


def _rupiah(value: float) -> str:
    """Format a number with '.' as thousands separator (Indonesian style)."""
    return f"{value:,.0f}".replace(",", ".")


def format_breakout(sig: BreakoutSignal) -> str:
    arrow = "🟢" if sig.rvol >= 2.0 else "🟡"
    return (
        f"🚨 BREAKOUT — {sig.ticker}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Sinyal : Resistance breakout (new high) · TF {sig.timeframe}\n"
        f"Harga  : {_rupiah(sig.price)} ({sig.pct_change:+.1f}%)\n"
        f"Level  : tembus resistance {_rupiah(sig.level)}\n"
        f"Volume : RVOL {sig.rvol:.1f}× {arrow}\n"
        f"⏱️ {sig.timestamp:%H:%M} WIB · delay data ~15 mnt"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_formatter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news_breakout/alerts/formatter.py tests/test_formatter.py
git commit -m "feat: add Telegram alert formatter"
```

---

### Task 8: Telegram sender (httpx, dry-run aware)

**Files:**
- Create: `news_breakout/alerts/telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Produces: `news_breakout.alerts.telegram.send_message(bot_token: str, chat_id: str, text: str, *, dry_run: bool, client=None) -> bool`.
  When `dry_run` is True: print the message, do no network I/O, return True.
  Otherwise POST to the Telegram Bot API `sendMessage` using `httpx` and return
  True on HTTP 200. `client` is an injectable httpx-like client for testing.

- [ ] **Step 1: Write the failing test**

`tests/test_telegram.py`:
```python
from news_breakout.alerts.telegram import send_message


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json})
        return FakeResponse(200)


def test_dry_run_does_not_call_network(capsys):
    fake = FakeClient()
    ok = send_message("tok", "-100", "hello", dry_run=True, client=fake)
    assert ok is True
    assert fake.calls == []  # no network in dry-run
    assert "hello" in capsys.readouterr().out


def test_real_send_posts_to_telegram():
    fake = FakeClient()
    ok = send_message("tok", "-100", "hello", dry_run=False, client=fake)
    assert ok is True
    assert len(fake.calls) == 1
    assert fake.calls[0]["url"].endswith("/bottok/sendMessage")
    assert fake.calls[0]["json"]["chat_id"] == "-100"
    assert fake.calls[0]["json"]["text"] == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.alerts.telegram'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/alerts/telegram.py`:
```python
from __future__ import annotations

import httpx


def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    dry_run: bool,
    client=None,
) -> bool:
    if dry_run:
        print(f"[DRY-RUN] -> {chat_id}\n{text}\n")
        return True

    close_after = client is None
    if client is None:
        client = httpx.Client()
    try:
        resp = client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        return resp.status_code == 200
    finally:
        if close_after:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_telegram.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/alerts/telegram.py tests/test_telegram.py
git commit -m "feat: add dry-run-aware Telegram sender"
```

---

### Task 9: yfinance data source + availability check

**Files:**
- Create: `news_breakout/data/__init__.py` (empty)
- Create: `news_breakout/data/yfinance_source.py`
- Test: `tests/test_yfinance_source.py`

**Interfaces:**
- Produces:
  - `news_breakout.data.yfinance_source.fetch_daily_ohlcv(tickers: list[str], history_days: int, downloader=None) -> dict[str, pandas.DataFrame]`.
    Appends `.JK`, calls the downloader once, and returns a mapping of the ORIGINAL
    ticker (no suffix) to a chronological OHLCV DataFrame. Tickers with no data are
    omitted. `downloader` is an injectable callable matching `yfinance.download`'s
    signature for testing.
  - `news_breakout.data.yfinance_source.report_availability(data: dict, tickers: list[str], min_bars: int) -> dict[str, str]`.
    Classifies each requested ticker as `"ok"`, `"thin"` (fewer than `min_bars`
    rows), or `"missing"` (no data).

- [ ] **Step 1: Write the failing test**

`tests/test_yfinance_source.py`:
```python
import pandas as pd

from news_breakout.data.yfinance_source import fetch_daily_ohlcv, report_availability


def _multiindex_frame(per_ticker):
    """Build a yfinance-style multiindex-column frame: columns = (Field, Ticker)."""
    frames = {}
    for jk_ticker, df in per_ticker.items():
        frames[jk_ticker] = df
    return pd.concat(frames, axis=1).swaplevel(axis=1)


def _one(n, close):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close, "Volume": 100},
        index=idx,
    )


def test_fetch_maps_original_ticker_and_drops_empty():
    combined = _multiindex_frame({"ANTM.JK": _one(3, 100), "BREN.JK": _one(0, 100)})

    def fake_downloader(tickers, period, interval, group_by, auto_adjust, progress, threads):
        return combined

    out = fetch_daily_ohlcv(["ANTM", "BREN"], history_days=10, downloader=fake_downloader)
    assert "ANTM" in out
    assert "BREN" not in out          # empty dropped
    assert list(out["ANTM"].columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out["ANTM"]) == 3


def test_report_availability_classifies():
    data = {"ANTM": _one(30, 100), "BREN": _one(5, 100)}
    report = report_availability(data, ["ANTM", "BREN", "RATU"], min_bars=21)
    assert report["ANTM"] == "ok"
    assert report["BREN"] == "thin"
    assert report["RATU"] == "missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_yfinance_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'news_breakout.data.yfinance_source'`.

- [ ] **Step 3: Write minimal implementation**

`news_breakout/data/__init__.py`:
```python
```
(empty file)

`news_breakout/data/yfinance_source.py`:
```python
from __future__ import annotations

import pandas as pd

_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def fetch_daily_ohlcv(
    tickers: list[str], history_days: int, downloader=None
) -> dict[str, pd.DataFrame]:
    """Download daily OHLCV for `.JK` tickers; return {original_ticker: DataFrame}."""
    if downloader is None:
        import yfinance as yf

        downloader = yf.download

    jk = [f"{t}.JK" for t in tickers]
    raw = downloader(
        jk,
        period=f"{history_days}d",
        interval="1d",
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


def report_availability(
    data: dict[str, pd.DataFrame], tickers: list[str], min_bars: int
) -> dict[str, str]:
    report: dict[str, str] = {}
    for t in tickers:
        if t not in data:
            report[t] = "missing"
        elif len(data[t]) < min_bars:
            report[t] = "thin"
        else:
            report[t] = "ok"
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_yfinance_source.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Real-data verification (the yfinance coverage spike we promised)**

Create `scripts/check_data.py`:
```python
from news_breakout.config import load_settings
from news_breakout.data.yfinance_source import fetch_daily_ohlcv, report_availability

s = load_settings()
data = fetch_daily_ohlcv(s.watchlist, s.history_days)
report = report_availability(data, s.watchlist, min_bars=s.donchian_lookback + 1)
for ticker, status in sorted(report.items()):
    print(f"{ticker:6} {status}")
```

Run: `python scripts/check_data.py`
Expected: a real network call to Yahoo Finance printing `ok` / `thin` / `missing`
for each of the 24 watchlist tickers. **Record any `thin`/`missing` tickers** —
these get special handling (skip or 1D-only) in later milestones. This confirms
free data coverage before we build further.

- [ ] **Step 6: Commit**

```bash
git add news_breakout/data/ tests/test_yfinance_source.py scripts/check_data.py
git commit -m "feat: add yfinance daily data source and availability report"
```

---

### Task 10: Wire-up — single-pass `run.py` and smoke test

**Files:**
- Create: `run.py`
- Test: `tests/test_run_smoke.py`

**Interfaces:**
- Consumes: `load_settings`, `fetch_daily_ohlcv`, `evaluate_daily`, `DedupStore`,
  `format_breakout`, `send_message`.
- Produces: `run.scan_once(settings, data, store, *, now, sender=send_message) -> list[str]`.
  Runs the engine over `data`, skips already-sent signals, sends the rest (respecting
  `settings.dry_run`), marks them sent, and returns the list of tickers alerted.
  `run.main()` loads settings, fetches live data, opens the SQLite store at
  `data_cache/dedup.sqlite`, and calls `scan_once` with the current WIB time.

- [ ] **Step 1: Write the failing test**

`tests/test_run_smoke.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.fixtures import make_ohlcv
from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
import run

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)


def _settings():
    return Settings(
        watchlist=["ANTM"],
        donchian_lookback=3,
        rvol_threshold=2.0,
        rvol_window=3,
        history_days=120,
        telegram_bot_token="tok",
        telegram_breakout_chat_id="-100",
        dry_run=True,
    )


def _breakout_data():
    return {
        "ANTM": make_ohlcv(
            highs=[100, 105, 110, 116],
            lows=[90, 95, 100, 108],
            closes=[100, 100, 100, 115],
            volumes=[100, 100, 100, 300],
        )
    }


def test_scan_once_alerts_then_dedups():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append((chat_id, text))
        return True

    first = run.scan_once(_settings(), _breakout_data(), store, now=NOW, sender=sender)
    assert first == ["ANTM"]
    assert len(sent) == 1
    assert "ANTM" in sent[0][1]

    # second pass same day -> deduped, no new send
    second = run.scan_once(_settings(), _breakout_data(), store, now=NOW, sender=sender)
    assert second == []
    assert len(sent) == 1
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run'` or `AttributeError: scan_once`.

- [ ] **Step 3: Write minimal implementation**

`run.py`:
```python
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings, load_settings
from news_breakout.data.yfinance_source import fetch_daily_ohlcv
from news_breakout.signals.engine import evaluate_daily
from news_breakout.alerts.dedup import DedupStore
from news_breakout.alerts.formatter import format_breakout
from news_breakout.alerts.telegram import send_message

WIB = ZoneInfo("Asia/Jakarta")


def scan_once(settings: Settings, data, store: DedupStore, *, now, sender=send_message) -> list[str]:
    alerted: list[str] = []
    date_str = now.strftime("%Y-%m-%d")
    for ticker, df in data.items():
        sig = evaluate_daily(
            ticker,
            df,
            lookback=settings.donchian_lookback,
            rvol_window=settings.rvol_window,
            rvol_threshold=settings.rvol_threshold,
            now=now,
        )
        if sig is None:
            continue
        if store.already_sent(sig.ticker, sig.signal_type, sig.timeframe, date_str):
            continue
        text = format_breakout(sig)
        sender(
            settings.telegram_bot_token,
            settings.telegram_breakout_chat_id,
            text,
            dry_run=settings.dry_run,
        )
        store.mark_sent(sig.ticker, sig.signal_type, sig.timeframe, date_str)
        alerted.append(sig.ticker)
    return alerted


def main() -> None:
    settings = load_settings()
    data = fetch_daily_ohlcv(settings.watchlist, settings.history_days)
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")
    try:
        now = datetime.now(WIB)
        alerted = scan_once(settings, data, store, now=now)
        print(f"Scan complete. Alerted: {alerted or 'none'}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_run_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: End-to-end dry-run against live data**

Prerequisites: `cp config/config.example.yaml config/config.yaml` and
`cp .env.example .env`, fill `.env` with the real bot token and breakout chat ID
(you do this — the assistant never touches the raw token). Keep `dry_run: true`.

Run: `python run.py`
Expected: fetches live daily data for the 24 tickers and prints any breakout
alerts as `[DRY-RUN]` blocks (or "Alerted: none" if nothing broke out today). No
message is sent to Telegram while `dry_run` is true.

- [ ] **Step 7: Commit**

```bash
git add run.py tests/test_run_smoke.py
git commit -m "feat: wire single-pass scan in run.py with dedup"
```

---

## Self-Review

**Spec coverage (M1 slice):**
- Data via yfinance `.JK`, no API key → Task 9 ✔
- Data-availability verification for 24 tickers → Task 9 Step 5 ✔
- Resistance/new-high (Donchian) breakout on 1D → Tasks 4, 5 ✔
- RVOL volume confirmation (default 2.0×) → Tasks 3, 5 ✔
- Anti-spam dedup (1×/ticker/type/tf/day) → Tasks 6, 10 ✔
- Telegram push, dry-run mode → Tasks 7, 8, 10 ✔
- Config in YAML + secrets in `.env` → Task 1 ✔
- WIB timestamps → Tasks 2, 5, 10 ✔
- Watchlist (24 tickers) → Task 1 config ✔
- *Deferred to later milestones (correctly out of M1 scope):* 4H/1H timeframes & Wyckoff range (M2), scheduler + market hours + universe auto-filter + weekend scan (M3), news engine (M4), systemd deploy (M5).

**Placeholder scan:** No TBD/TODO; every code step contains complete code; every run step lists an exact command and expected output. ✔

**Type consistency:** `BreakoutSignal` fields defined in Task 2 are used consistently in Tasks 5, 7, 10. `detect_donchian_breakout -> (bool, float)` (Task 4) matches its use in Task 5. `compute_rvol -> float` (Task 3) matches Task 5. `DedupStore` method signatures (Task 6) match calls in Task 10. `send_message(..., dry_run, client)` (Task 8) matches the `sender` used in Tasks 10. `fetch_daily_ohlcv` return type (Task 9) matches `scan_once` iteration (Task 10). ✔

---

## After M1

Once M1 is green and you have run the dry-run end-to-end (and recorded any `thin`/`missing`
tickers from the data check), we write the M2 plan: 1H/4H resampling, Wyckoff accumulation-range
breakout, and multi-timeframe priority ranking.
