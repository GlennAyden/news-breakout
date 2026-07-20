# Elliott Wave + Fibonacci (EW‑0 + EW‑1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a causal swing/Fibonacci foundation and an impulse Elliott‑Wave labeler that appends an advisory wave/Fib block to each breakout alert — with **zero change** to the production signal, ranking, trade plan, or which alerts are sent.

**Architecture:** New isolated package `news_breakout/signals/elliott/` (models, swings, fibonacci, waves, annotate). The engine computes a `WaveContext` from the 1D frame best‑effort (try/except → `None` on any failure) and attaches it to `TickerAlert`; the formatter renders 0–2 extra lines when a confident, non‑ambiguous context exists, and is byte‑identical to today's output otherwise.

**Tech Stack:** Python 3.12, pandas, numpy, pydantic, pytest. Design spec: `docs/superpowers/specs/2026-07-20-elliott-wave-fibonacci-design.md`.

## Global Constraints

- **Python 3.12** — run tests with the project venv: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest` (default `python` is 3.13). From the worktree, `PYTHONPATH` is handled by `tests/conftest.py`.
- **Causal / no‑repaint:** no function may read beyond the last row of the DataFrame it is given; the most recent swing leg is `provisional=True` and is never used as a confirmed rule boundary.
- **Best‑effort / degradable:** every EW computation the engine calls is wrapped so a failure logs a warning and yields `wave_context=None`; a scan must never fail because of EW.
- **Advisory‑only (this milestone):** no change to signal detection, `quality_score`, trade plan, or send decision. Golden rule: when the EW block is empty, the alert string is identical to the pre‑change output.
- **Daily‑only, impulse‑only, long‑only** for EW‑1 (per spec D2/D3/N4). Corrective / intraday / bearish are deferred.
- **Config style:** `Settings` is a **flat** pydantic model with defaulted fields (follow the existing `portal_*` / `sentiment_*` pattern — NOT a nested sub‑model, despite spec §8 wording).
- **Formatting:** reuse the existing `news_breakout.alerts.formatter._rupiah` for all prices in the EW block.
- **Commit** after every task's tests pass.

---

### Task 1: ATR + causal multi‑scale swing detector

**Files:**
- Create: `news_breakout/signals/elliott/__init__.py` (empty)
- Create: `news_breakout/signals/elliott/models.py` (the `Swing` dataclass)
- Create: `news_breakout/signals/elliott/swings.py`
- Test: `tests/test_elliott_swings.py`

**Interfaces:**
- Produces:
  - `Swing(i: int, date: datetime, price: float, kind: str, provisional: bool)` — `kind` is `'H'` or `'L'`.
  - `atr(df: pd.DataFrame, window: int = 14) -> pd.Series`
  - `detect_swings(df: pd.DataFrame, atr_mult: float, atr_window: int = 14) -> list[Swing]`
  - `multi_scale_swings(df, scales=(2.0, 3.5, 5.0), atr_window=14) -> dict[float, list[Swing]]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_elliott_swings.py
import numpy as np
import pandas as pd
from datetime import datetime

from news_breakout.signals.elliott.swings import atr, detect_swings, multi_scale_swings
from news_breakout.signals.elliott.models import Swing


def _df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    p = np.asarray(prices, dtype=float)
    # simple OHLC around the close path: high/low = close +/- 0.5
    return pd.DataFrame(
        {"Open": p, "High": p + 0.5, "Low": p - 0.5, "Close": p, "Volume": 1000.0},
        index=idx,
    )


def test_atr_is_positive_after_window():
    df = _df(list(range(1, 40)))
    a = atr(df, 14)
    assert a.iloc[-1] > 0
    assert a.iloc[:13].isna().all()  # not enough bars before the window


def test_monotonic_series_yields_single_provisional_swing():
    df = _df([10 + i for i in range(40)])  # strictly rising
    sw = detect_swings(df, atr_mult=2.0, atr_window=14)
    assert len(sw) == 1
    assert sw[0].provisional is True
    assert sw[0].kind == "H"
    assert sw[0].i == len(df) - 1  # the last (highest) bar


def test_zigzag_detects_alternating_pivots():
    # rise to ~40, fall to ~20, rise to ~55  -> expect at least H then L confirmed
    up1 = list(np.linspace(20, 40, 20))
    down = list(np.linspace(40, 20, 20))
    up2 = list(np.linspace(20, 55, 20))
    df = _df(up1 + down + up2)
    sw = detect_swings(df, atr_mult=2.0, atr_window=14)
    kinds = [s.kind for s in sw]
    # alternation holds
    assert all(kinds[i] != kinds[i + 1] for i in range(len(kinds) - 1))
    # a confirmed high near the first peak and a confirmed low near the trough exist
    confirmed = [s for s in sw if not s.provisional]
    assert any(s.kind == "H" and s.price >= 39 for s in confirmed)
    assert any(s.kind == "L" and s.price <= 21 for s in confirmed)
    assert sw[-1].provisional is True  # last leg always provisional


def test_multi_scale_returns_one_list_per_scale():
    df = _df(list(np.linspace(20, 40, 30)) + list(np.linspace(40, 25, 30)))
    out = multi_scale_swings(df, scales=(2.0, 4.0), atr_window=14)
    assert set(out.keys()) == {2.0, 4.0}
    assert all(isinstance(v, list) for v in out.values())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_swings.py -v`
Expected: FAIL — `ModuleNotFoundError: news_breakout.signals.elliott`.

- [ ] **Step 3: Create the package + `Swing` model**

```python
# news_breakout/signals/elliott/__init__.py
```
(empty file)

```python
# news_breakout/signals/elliott/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Swing:
    i: int
    date: datetime
    price: float
    kind: str          # 'H' | 'L'
    provisional: bool  # True = last, unconfirmed leg (no-repaint marker)
```

- [ ] **Step 4: Implement `swings.py`**

```python
# news_breakout/signals/elliott/swings.py
from __future__ import annotations

import pandas as pd

from news_breakout.signals.elliott.models import Swing


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Wilder's ATR."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def detect_swings(df: pd.DataFrame, atr_mult: float, atr_window: int = 14) -> list[Swing]:
    """Causal ATR-ZigZag. A reversal of >= atr_mult*ATR from the running extreme
    confirms that extreme as a pivot and flips direction. The final still-extending
    leg is returned as one provisional=True swing. Uses only bars up to the end."""
    n = len(df)
    if n < atr_window + 2:
        return []
    a = atr(df, atr_window).to_numpy()
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    idx = list(df.index)
    start = atr_window

    swings: list[Swing] = []
    hi_i, hi = start, high[start]
    lo_i, lo = start, low[start]
    trend = 0  # 0 until first confirmed pivot, then +1 (up leg) / -1 (down leg)

    for i in range(start + 1, n):
        thr = atr_mult * a[i]
        if not (thr > 0):
            continue
        if high[i] > hi:
            hi_i, hi = i, high[i]
        if low[i] < lo:
            lo_i, lo = i, low[i]

        if trend >= 0 and (hi - low[i]) >= thr:
            if not swings or swings[-1].kind != "H":
                swings.append(Swing(hi_i, idx[hi_i], float(hi), "H", provisional=False))
            trend = -1
            lo_i, lo = i, low[i]
        elif trend <= 0 and (high[i] - lo) >= thr:
            if not swings or swings[-1].kind != "L":
                swings.append(Swing(lo_i, idx[lo_i], float(lo), "L", provisional=False))
            trend = 1
            hi_i, hi = i, high[i]

    # provisional last leg (always present)
    if trend > 0:
        swings.append(Swing(hi_i, idx[hi_i], float(hi), "H", provisional=True))
    elif trend < 0:
        swings.append(Swing(lo_i, idx[lo_i], float(lo), "L", provisional=True))
    else:
        # never reversed: single provisional pivot at the overall extreme
        if high[n - 1] - low[start] >= low[start] - low[n - 1]:
            swings.append(Swing(hi_i, idx[hi_i], float(hi), "H", provisional=True))
        else:
            swings.append(Swing(lo_i, idx[lo_i], float(lo), "L", provisional=True))
    return swings


def multi_scale_swings(
    df: pd.DataFrame, scales: tuple[float, ...] = (2.0, 3.5, 5.0), atr_window: int = 14
) -> dict[float, list[Swing]]:
    return {s: detect_swings(df, s, atr_window) for s in scales}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_swings.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add news_breakout/signals/elliott/__init__.py news_breakout/signals/elliott/models.py news_breakout/signals/elliott/swings.py tests/test_elliott_swings.py
git commit -m "feat(elliott): causal ATR-zigzag swing detector (EW-0)"
```

---

### Task 2: Fibonacci module

**Files:**
- Create: `news_breakout/signals/elliott/fibonacci.py`
- Test: `tests/test_elliott_fibonacci.py`

**Interfaces:**
- Produces:
  - `RETRACE = (0.382, 0.5, 0.618, 0.786)`, `EXTEND = (1.272, 1.618, 2.0, 2.618)`
  - `retracements(low: float, high: float) -> dict[float, float]` — level = `high - f*(high-low)`
  - `extensions(low: float, high: float) -> dict[float, float]` — level = `low + f*(high-low)`
  - `projection(a: float, b: float, c: float, f: float) -> float` — `c + f*(b-a)`
  - `nearest_ratio(price, low, high, ratios, tol=0.05) -> float | None` — which retrace ratio `price` sits at (within `tol` of the leg)
  - `confluence(level, *, structure=None, sma=None, round_step=None, other_levels=(), tol=0.0) -> tuple[int, list[str]]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_elliott_fibonacci.py
from news_breakout.signals.elliott.fibonacci import (
    retracements, extensions, projection, nearest_ratio, confluence,
)


def test_retracements_math():
    r = retracements(100.0, 200.0)          # leg of 100
    assert r[0.5] == 150.0
    assert abs(r[0.618] - 138.2) < 1e-9
    assert abs(r[0.382] - 161.8) < 1e-9


def test_extensions_math():
    e = extensions(100.0, 200.0)
    assert e[1.618] == 261.8
    assert e[2.0] == 300.0


def test_projection_measured_move():
    # wave A=100->140 (b-a=40), project 1.0 off c=130 -> 170
    assert projection(100.0, 140.0, 130.0, 1.0) == 170.0


def test_nearest_ratio_classifies_a_retrace():
    # price 138 on a 100->200 leg sits at ~0.62 retrace
    assert nearest_ratio(138.0, 100.0, 200.0, (0.5, 0.618, 0.786), tol=0.03) == 0.618
    # price far from any ratio -> None
    assert nearest_ratio(175.0, 100.0, 200.0, (0.5, 0.618), tol=0.02) is None


def test_confluence_counts_weighted_factors():
    score, factors = confluence(
        150.0, structure=150.4, sma=149.6, round_step=50.0,
        other_levels=(150.2,), tol=1.0,
    )
    assert score >= 5           # structure(2)+sma(2)+round(1)+cluster(2) within tol
    assert "structure" in factors and "sma" in factors
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_fibonacci.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `fibonacci.py`**

```python
# news_breakout/signals/elliott/fibonacci.py
from __future__ import annotations

RETRACE = (0.382, 0.5, 0.618, 0.786)
EXTEND = (1.272, 1.618, 2.0, 2.618)


def retracements(low: float, high: float) -> dict[float, float]:
    span = high - low
    return {f: high - f * span for f in RETRACE}


def extensions(low: float, high: float) -> dict[float, float]:
    span = high - low
    return {f: low + f * span for f in EXTEND}


def projection(a: float, b: float, c: float, f: float) -> float:
    return c + f * (b - a)


def nearest_ratio(price, low, high, ratios, tol=0.05):
    """Return the ratio whose retracement level is within tol*(high-low) of price."""
    span = high - low
    if span <= 0:
        return None
    best, best_d = None, None
    for f in ratios:
        level = high - f * span
        d = abs(price - level) / span
        if d <= tol and (best_d is None or d < best_d):
            best, best_d = f, d
    return best


def confluence(level, *, structure=None, sma=None, round_step=None,
               other_levels=(), tol=0.0) -> tuple[int, list[str]]:
    """Weighted confluence score for a candidate price zone + contributing factors."""
    score = 0
    factors: list[str] = []
    if structure is not None and abs(level - structure) <= tol:
        score += 2; factors.append("structure")
    if sma is not None and abs(level - sma) <= tol:
        score += 2; factors.append("sma")
    if round_step:
        nearest_round = round(level / round_step) * round_step
        if abs(level - nearest_round) <= tol:
            score += 1; factors.append("round")
    if any(abs(level - o) <= tol for o in other_levels):
        score += 2; factors.append("cluster")
    return score, factors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_fibonacci.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/signals/elliott/fibonacci.py tests/test_elliott_fibonacci.py
git commit -m "feat(elliott): Fibonacci retracement/extension/confluence module (EW-0)"
```

---

### Task 3: Wave models + hard‑rule impulse validation

**Files:**
- Modify: `news_breakout/signals/elliott/models.py` (add `Wave`, `WaveCount`, `WaveContext`)
- Create: `news_breakout/signals/elliott/waves.py` (rule validation only in this task)
- Test: `tests/test_elliott_rules.py`

**Interfaces:**
- Consumes: `Swing` (Task 1).
- Produces:
  - `Wave(label: str, start: Swing, end: Swing)` with `.length -> float`
  - `WaveCount(waves: list[Wave], scale: float, rules_ok: bool, rule_flags: dict[str,bool], fib_fit: float)`
  - `WaveContext(position: str, confidence: float, primary: WaveCount|None, alternates: list[WaveCount], invalidation: float|None, fib_targets: dict[str,float], note: str)`
  - `validate_impulse(pivots: list[Swing], scale: float, fib_tol: float = 0.06) -> WaveCount` — `pivots` is 6 swings L,H,L,H,L,H (waves 1..5). Returns a `WaveCount` with `rules_ok` + per‑rule flags + `fib_fit`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_elliott_rules.py
from datetime import datetime

from news_breakout.signals.elliott.models import Swing
from news_breakout.signals.elliott.waves import validate_impulse

D = datetime(2024, 1, 1)


def _piv(seq):
    """seq = list of (price, kind) -> Swings with dummy index/date."""
    return [Swing(i, D, p, k, provisional=False) for i, (p, k) in enumerate(seq)]


def _ideal():
    # a textbook up-impulse: 1:100->140, 2:->120, 3:->200, 4:->170, 5:->220
    return _piv([(100, "L"), (140, "H"), (120, "L"), (200, "H"), (170, "L"), (220, "H")])


def test_ideal_impulse_passes_all_rules():
    wc = validate_impulse(_ideal(), scale=2.0)
    assert wc.rules_ok is True
    assert all(wc.rule_flags.values())
    assert [w.label for w in wc.waves] == ["1", "2", "3", "4", "5"]
    assert wc.fib_fit > 0  # some ratio alignment


def test_r1_wave2_retraces_beyond_wave1_start_fails():
    p = _piv([(100, "L"), (140, "H"), (95, "L"), (200, "H"), (170, "L"), (220, "H")])
    wc = validate_impulse(p, scale=2.0)
    assert wc.rule_flags["R1"] is False
    assert wc.rules_ok is False


def test_r2_wave3_shortest_fails():
    # W1 len 40, W5 len 60, W3 len 20 (shortest)
    p = _piv([(100, "L"), (140, "H"), (120, "L"), (140, "H"), (110, "L"), (170, "H")])
    wc = validate_impulse(p, scale=2.0)
    assert wc.rule_flags["R2"] is False
    assert wc.rules_ok is False


def test_r3_wave4_overlaps_wave1_fails():
    # W4 low (135) dips below W1 high (140)? here 135 < 140 -> overlap
    p = _piv([(100, "L"), (140, "H"), (120, "L"), (200, "H"), (135, "L"), (220, "H")])
    wc = validate_impulse(p, scale=2.0)
    assert wc.rule_flags["R3"] is False
    assert wc.rules_ok is False


def test_r4_wrong_alternation_fails():
    # kinds not alternating L,H,L,H,L,H
    p = _piv([(100, "L"), (140, "L"), (120, "L"), (200, "H"), (170, "L"), (220, "H")])
    wc = validate_impulse(p, scale=2.0)
    assert wc.rule_flags["R4"] is False
    assert wc.rules_ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_rules.py -v`
Expected: FAIL — `validate_impulse` undefined.

- [ ] **Step 3: Extend `models.py`**

```python
# append to news_breakout/signals/elliott/models.py

@dataclass
class Wave:
    label: str          # '1'..'5'
    start: Swing
    end: Swing

    @property
    def length(self) -> float:
        return abs(self.end.price - self.start.price)


@dataclass
class WaveCount:
    waves: list[Wave]
    scale: float
    rules_ok: bool
    rule_flags: dict[str, bool]
    fib_fit: float


@dataclass
class WaveContext:
    position: str = "none"
    confidence: float = 0.0
    primary: "WaveCount | None" = None
    alternates: list["WaveCount"] = field(default_factory=list)
    invalidation: float | None = None
    fib_targets: dict[str, float] = field(default_factory=dict)
    note: str = ""
```

- [ ] **Step 4: Implement `validate_impulse` in `waves.py`**

```python
# news_breakout/signals/elliott/waves.py
from __future__ import annotations

from news_breakout.signals.elliott.fibonacci import RETRACE
from news_breakout.signals.elliott.models import Swing, Wave, WaveContext, WaveCount


def _fib_fit(w1, w2, w3, w4, w5, tol: float) -> float:
    """Fraction of EW Fibonacci guidelines the count satisfies (0..1), tolerance-banded."""
    checks: list[bool] = []
    if w1.length > 0:
        r2 = w2.length / w1.length                       # W2 retrace of W1
        checks.append(any(abs(r2 - f) <= tol for f in (0.5, 0.618, 0.786)))
        e3 = w3.length / w1.length                        # W3 extension of W1
        checks.append(any(abs(e3 - f) <= tol * 3 for f in (1.618, 2.618)))
        r5 = w5.length / w1.length                        # W5 vs W1
        checks.append(any(abs(r5 - f) <= tol * 2 for f in (0.618, 1.0, 1.618)))
    if w3.length > 0:
        r4 = w4.length / w3.length                        # W4 retrace of W3
        checks.append(any(abs(r4 - f) <= tol for f in (0.382, 0.5)))
    return sum(checks) / len(checks) if checks else 0.0


def validate_impulse(pivots: list[Swing], scale: float, fib_tol: float = 0.06) -> WaveCount:
    """Validate a 6-pivot (L,H,L,H,L,H) up-impulse against the 4 hard rules + score Fib fit."""
    labels = ["1", "2", "3", "4", "5"]
    waves = [Wave(labels[k], pivots[k], pivots[k + 1]) for k in range(5)]
    w1, w2, w3, w4, w5 = waves

    p0, p1, p2, p3, p4, p5 = (s.price for s in pivots)
    kinds = [s.kind for s in pivots]

    r4 = kinds == ["L", "H", "L", "H", "L", "H"] and p1 > p0 and p3 > p2 and p5 > p4
    r1 = p2 > p0                                   # W2 doesn't retrace >100% of W1
    r3 = p4 > p1                                   # W4 doesn't overlap W1 territory
    len1, len3, len5 = w1.length, w3.length, w5.length
    r2 = not (len3 < len1 and len3 < len5)         # W3 not the shortest

    flags = {"R1": bool(r1), "R2": bool(r2), "R3": bool(r3), "R4": bool(r4)}
    rules_ok = all(flags.values())
    fib_fit = _fib_fit(w1, w2, w3, w4, w5, fib_tol) if rules_ok else 0.0
    return WaveCount(waves=waves, scale=scale, rules_ok=rules_ok,
                     rule_flags=flags, fib_fit=fib_fit)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_rules.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add news_breakout/signals/elliott/models.py news_breakout/signals/elliott/waves.py tests/test_elliott_rules.py
git commit -m "feat(elliott): impulse hard-rule validation + Fib-fit scoring (EW-1)"
```

---

### Task 4: Current‑position inference + `label_current`

**Files:**
- Modify: `news_breakout/signals/elliott/waves.py` (add `interpret`, `label_current`)
- Test: `tests/test_elliott_waves.py`

**Interfaces:**
- Consumes: `detect_swings`/`multi_scale_swings` (Task 1), `extensions`/`projection` (Task 2), `validate_impulse`/`WaveContext` (Task 3).
- Produces:
  - `interpret(swings: list[Swing], scale: float, fib_tol: float = 0.06) -> WaveContext` — infer the position from one scale's swing list (confirmed + trailing provisional).
  - `label_current(df, *, scales=(2.0,3.5,5.0), atr_window=14, max_pivots=9, fib_tol=0.06) -> WaveContext` — combine scales; `position='ambiguous'` when scales disagree.

Position vocabulary: `'wave_3_start' | 'wave_5_possible_exhaustion' | 'wave_2_pullback' | 'wave_4_pullback' | 'impulse_mid' | 'corrective_or_unresolved' | 'ambiguous' | 'none'`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_elliott_waves.py
import numpy as np
import pandas as pd
from datetime import datetime

from news_breakout.signals.elliott.models import Swing
from news_breakout.signals.elliott.waves import interpret, label_current

D = datetime(2024, 1, 1)


def _sw(seq):
    """seq = [(price, kind, provisional?)] -> Swings."""
    out = []
    for i, item in enumerate(seq):
        price, kind = item[0], item[1]
        prov = item[2] if len(item) > 2 else False
        out.append(Swing(i, D, float(price), kind, provisional=prov))
    return out


def test_interpret_wave3_start():
    # 1(100->140) 2(->120)  then provisional up leg breaking above 140 -> Wave-3 start
    sw = _sw([(100, "L"), (140, "H"), (120, "L"), (145, "H", True)])
    ctx = interpret(sw, scale=2.0)
    assert ctx.position == "wave_3_start"
    assert ctx.invalidation == 120.0            # the Wave-2 low
    assert "1.618" in ctx.fib_targets


def test_interpret_wave5_possible_exhaustion():
    # full 1-2-3-4 then a stretched provisional 5th far beyond
    sw = _sw([(100, "L"), (140, "H"), (120, "L"), (200, "H"), (175, "L"), (280, "H", True)])
    ctx = interpret(sw, scale=2.0)
    assert ctx.position == "wave_5_possible_exhaustion"
    assert ctx.invalidation == 175.0            # the Wave-4 low


def test_interpret_down_provisional_is_corrective():
    sw = _sw([(100, "L"), (160, "H"), (140, "L", True)])
    ctx = interpret(sw, scale=2.0)
    assert ctx.position in ("wave_2_pullback", "corrective_or_unresolved")


def test_label_current_smoke_on_synthetic_df():
    prices = list(np.linspace(100, 140, 15)) + list(np.linspace(140, 122, 8)) + \
             list(np.linspace(122, 150, 10))
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    p = np.array(prices)
    df = pd.DataFrame({"Open": p, "High": p + 0.6, "Low": p - 0.6,
                       "Close": p, "Volume": 1000.0}, index=idx)
    ctx = label_current(df, scales=(2.0, 4.0), atr_window=14)
    assert ctx.position in {
        "wave_3_start", "wave_5_possible_exhaustion", "wave_2_pullback",
        "wave_4_pullback", "impulse_mid", "corrective_or_unresolved",
        "ambiguous", "none",
    }
    assert 0.0 <= ctx.confidence <= 1.0


def test_label_current_ambiguous_when_scales_disagree(monkeypatch):
    import news_breakout.signals.elliott.waves as W
    calls = {"n": 0}

    def fake_interpret(swings, scale, fib_tol=0.06):
        calls["n"] += 1
        from news_breakout.signals.elliott.models import WaveContext
        pos = "wave_3_start" if calls["n"] == 1 else "wave_5_possible_exhaustion"
        return WaveContext(position=pos, confidence=0.6)

    monkeypatch.setattr(W, "interpret", fake_interpret)
    df = pd.DataFrame({"Open": [1]*40, "High": [1.5]*40, "Low": [0.5]*40,
                       "Close": [1]*40, "Volume": [1000]*40},
                      index=pd.date_range("2024-01-01", periods=40, freq="D"))
    ctx = W.label_current(df, scales=(2.0, 4.0))
    assert ctx.position == "ambiguous"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_waves.py -v`
Expected: FAIL — `interpret` / `label_current` undefined.

- [ ] **Step 3: Implement `interpret` + `label_current` in `waves.py`**

```python
# append to news_breakout/signals/elliott/waves.py
from collections import Counter

from news_breakout.signals.elliott.swings import multi_scale_swings

_UP_POS = {"wave_3_start", "wave_5_possible_exhaustion", "impulse_mid"}


def interpret(swings: list[Swing], scale: float, fib_tol: float = 0.06) -> WaveContext:
    """Infer the current wave position from one scale's swing list."""
    if len(swings) < 3:
        return WaveContext(position="none")
    cur = swings[-1]
    confirmed = swings[:-1]

    # Down provisional leg after an up move -> a pullback / correction.
    if cur.kind == "L":
        return WaveContext(position="wave_2_pullback" if len(confirmed) <= 2
                           else "corrective_or_unresolved", confidence=0.3)

    # Up provisional leg: try Wave-3 start (need ...L,H,L then breaking the H).
    tail = confirmed[-3:]
    if len(tail) == 3 and [s.kind for s in tail] == ["L", "H", "L"]:
        p0, p1, p2 = (s.price for s in tail)
        if p1 > p0 and p2 > p0 and cur.price > p1:          # valid 1-2 + breakout
            w1 = p1 - p0
            targets = {"1.618": p2 + 1.618 * w1, "2.618": p2 + 2.618 * w1}
            r2 = (p1 - p2) / w1 if w1 else 0.0
            fit = 1.0 if any(abs(r2 - f) <= fib_tol for f in (0.5, 0.618, 0.786)) else 0.4
            return WaveContext(position="wave_3_start", confidence=0.5 + 0.3 * fit,
                               invalidation=p2, fib_targets=targets,
                               note="kemungkinan awal Wave-3")

    # Up provisional leg with a full 1-2-3-4 behind it -> possible 5th (exhaustion?).
    tail5 = confirmed[-5:]
    if len(tail5) == 5 and [s.kind for s in tail5] == ["L", "H", "L", "H", "L"]:
        wc = validate_impulse(tail5 + [cur], scale, fib_tol)
        if wc.rules_ok:
            p0, p1 = tail5[0].price, tail5[1].price
            p4 = tail5[4].price
            w1 = p1 - p0
            stretched = cur.price >= p4 + 1.618 * w1
            pos = "wave_5_possible_exhaustion" if stretched else "impulse_mid"
            targets = {"0.618": p4 + 0.618 * w1, "1.0": p4 + w1}
            note = ("kemungkinan Wave-5 lelah" if stretched else "impuls berjalan")
            return WaveContext(position=pos, confidence=0.4 + 0.4 * wc.fib_fit,
                               primary=wc, invalidation=p4, fib_targets=targets, note=note)

    return WaveContext(position="impulse_mid" if cur.kind == "H" else
                       "corrective_or_unresolved", confidence=0.2)


def label_current(df, *, scales=(2.0, 3.5, 5.0), atr_window=14,
                  max_pivots=9, fib_tol=0.06) -> WaveContext:
    """Label the current wave across scales; disagreement -> 'ambiguous'."""
    scale_swings = multi_scale_swings(df, tuple(scales), atr_window)
    ctxs: list[WaveContext] = []
    for scale, sw in scale_swings.items():
        ctxs.append(interpret(sw[-(max_pivots + 1):], scale, fib_tol))
    ctxs = [c for c in ctxs if c.position != "none"]
    if not ctxs:
        return WaveContext(position="none")

    positions = [c.position for c in ctxs]
    top, count = Counter(positions).most_common(1)[0]

    # Directional disagreement (some up-position, some pullback/corrective) -> ambiguous.
    up = any(p in _UP_POS for p in positions)
    down = any(p in ("wave_2_pullback", "wave_4_pullback", "corrective_or_unresolved")
               for p in positions)
    if up and down:
        return WaveContext(position="ambiguous", confidence=0.0,
                           note="hitungan bertentangan antar skala")

    agree = count / len(ctxs)
    best = max((c for c in ctxs if c.position == top), key=lambda c: c.confidence)
    best.confidence = min(1.0, best.confidence * (0.6 + 0.4 * agree))
    best.alternates = [c.primary for c in ctxs if c is not best and c.primary]
    return best
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_waves.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/signals/elliott/waves.py tests/test_elliott_waves.py
git commit -m "feat(elliott): current-position inference + multi-scale label_current (EW-1)"
```

---

### Task 5: Annotation block

**Files:**
- Create: `news_breakout/signals/elliott/annotate.py`
- Test: `tests/test_elliott_annotate.py`

**Interfaces:**
- Consumes: `WaveContext` (Task 3).
- Produces: `elliott_block(ctx: WaveContext, *, min_conf: float, show_ambiguous: bool, rupiah) -> list[str]` — returns 0–2 strings. `rupiah` is a price‑formatting callable (the formatter passes `_rupiah`) so this module stays dependency‑free.

Rules (from spec §7.2): omit entirely when `position == 'none'`, or `confidence < min_conf`, or (`position == 'ambiguous'` and not `show_ambiguous`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_elliott_annotate.py
from news_breakout.signals.elliott.models import WaveContext
from news_breakout.signals.elliott.annotate import elliott_block


def _r(v):  # stand-in for _rupiah
    return f"{v:,.0f}".replace(",", ".")


def test_wave3_block_has_label_invalidation_and_targets():
    ctx = WaveContext(position="wave_3_start", confidence=0.62, invalidation=2950.0,
                      fib_targets={"1.618": 3480.0, "2.618": 3780.0},
                      note="kemungkinan awal Wave-3")
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False, rupiah=_r)
    text = "\n".join(lines)
    assert "🌊" in text and "Wave-3" in text
    assert "0.62" in text
    assert "2.950" in text            # invalidation, thousands-formatted
    assert "3.480" in text and "3.780" in text


def test_exhaustion_block_warns():
    ctx = WaveContext(position="wave_5_possible_exhaustion", confidence=0.55,
                      invalidation=175.0, note="kemungkinan Wave-5 lelah")
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False, rupiah=_r)
    assert any("⚠️" in ln for ln in lines)


def test_low_confidence_is_omitted():
    ctx = WaveContext(position="wave_3_start", confidence=0.30)
    assert elliott_block(ctx, min_conf=0.45, show_ambiguous=False, rupiah=_r) == []


def test_ambiguous_hidden_by_default_shown_when_enabled():
    ctx = WaveContext(position="ambiguous", confidence=0.0,
                      note="hitungan bertentangan antar skala")
    assert elliott_block(ctx, min_conf=0.45, show_ambiguous=False, rupiah=_r) == []
    shown = elliott_block(ctx, min_conf=0.45, show_ambiguous=True, rupiah=_r)
    assert shown and "ambigu" in shown[0].lower()


def test_none_is_omitted():
    assert elliott_block(WaveContext(position="none"), min_conf=0.0,
                         show_ambiguous=True, rupiah=_r) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_annotate.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `annotate.py`**

```python
# news_breakout/signals/elliott/annotate.py
from __future__ import annotations

from news_breakout.signals.elliott.models import WaveContext

_LABEL = {
    "wave_3_start": "kemungkinan awal Wave-3",
    "wave_5_possible_exhaustion": "⚠️ kemungkinan Wave-5 lelah",
    "wave_2_pullback": "kemungkinan pullback Wave-2",
    "wave_4_pullback": "kemungkinan pullback Wave-4",
    "impulse_mid": "impuls berjalan",
    "corrective_or_unresolved": "struktur korektif / belum jelas",
}


def elliott_block(ctx: WaveContext, *, min_conf: float, show_ambiguous: bool, rupiah) -> list[str]:
    if ctx is None or ctx.position == "none":
        return []
    if ctx.position == "ambiguous":
        if not show_ambiguous:
            return []
        return [f"🌊 Elliott: ambigu ({ctx.note or 'hitungan bertentangan'}) — pakai penilaianmu"]
    if ctx.confidence < min_conf:
        return []

    label = _LABEL.get(ctx.position, ctx.position)
    head = f"🌊 Elliott: {label} (conf {ctx.confidence:.2f})"
    if ctx.invalidation is not None:
        head += f" · invalidasi <{rupiah(ctx.invalidation)}"
    lines = [head]
    if ctx.fib_targets:
        parts = " · ".join(f"{k}×→{rupiah(v)}" for k, v in ctx.fib_targets.items())
        lines.append(f"📐 Fib: target {parts}")
    return lines
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_elliott_annotate.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/signals/elliott/annotate.py tests/test_elliott_annotate.py
git commit -m "feat(elliott): advisory alert annotation block (EW-1)"
```

---

### Task 6: Config — `elliott_*` settings

**Files:**
- Modify: `news_breakout/config.py` (add flat fields + load from `elliott:` section)
- Modify: `config/config.example.yaml` (add `elliott:` block)
- Test: `tests/test_config_elliott.py`

**Interfaces:**
- Produces on `Settings`: `elliott_enabled: bool=True`, `elliott_atr_scales: list[float]=[2.0,3.5,5.0]`, `elliott_atr_window: int=14`, `elliott_max_pivots: int=9`, `elliott_fib_tolerance: float=0.06`, `elliott_min_confidence: float=0.45`, `elliott_show_ambiguous: bool=False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_elliott.py
import os
from news_breakout.config import load_settings


def _write(tmp_path):
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
        "elliott: {enabled: true, atr_scales: [2.0, 4.0], min_confidence: 0.5}\n",
        encoding="utf-8",
    )
    return cfg


def test_elliott_settings_load_with_overrides_and_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "x")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "x")
    s = load_settings(config_path=str(_write(tmp_path)), env_path=str(tmp_path / ".env"))
    assert s.elliott_enabled is True
    assert s.elliott_atr_scales == [2.0, 4.0]        # overridden
    assert s.elliott_min_confidence == 0.5           # overridden
    assert s.elliott_atr_window == 14                # default
    assert s.elliott_show_ambiguous is False         # default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_config_elliott.py -v`
Expected: FAIL — `Settings` has no `elliott_*` fields.

- [ ] **Step 3: Add fields to `Settings` (after the `sentiment_*` fields, ~line 47)**

```python
    elliott_enabled: bool = True
    elliott_atr_scales: list[float] = [2.0, 3.5, 5.0]
    elliott_atr_window: int = 14
    elliott_max_pivots: int = 9
    elliott_fib_tolerance: float = 0.06
    elliott_min_confidence: float = 0.45
    elliott_show_ambiguous: bool = False
```

- [ ] **Step 4: Load the `elliott:` section in `load_settings`**

After `sentiment = raw.get("sentiment", {})` add:
```python
    elliott = raw.get("elliott", {})
```
And add these keyword args to the `Settings(...)` construction (e.g. after the `sentiment_*` args):
```python
        elliott_enabled=elliott.get("enabled", True),
        elliott_atr_scales=elliott.get("atr_scales", [2.0, 3.5, 5.0]),
        elliott_atr_window=elliott.get("atr_window", 14),
        elliott_max_pivots=elliott.get("max_pivots", 9),
        elliott_fib_tolerance=elliott.get("fib_tolerance", 0.06),
        elliott_min_confidence=elliott.get("min_confidence", 0.45),
        elliott_show_ambiguous=elliott.get("show_ambiguous", False),
```

- [ ] **Step 5: Add the `elliott:` block to `config/config.example.yaml`** (after the `sentiment:` block)

```yaml
elliott:
  enabled: true
  atr_scales: [2.0, 3.5, 5.0]   # ZigZag sensitivities; cross-scale disagreement -> ambiguous
  atr_window: 14
  max_pivots: 9                 # confirmed swings fed to the labeler
  fib_tolerance: 0.06           # ± band for ratio-fit scoring
  min_confidence: 0.45          # below this, show nothing (or only 'ambiguous' if show_ambiguous)
  show_ambiguous: false         # if true, print the 'ambigu' line instead of omitting
```

- [ ] **Step 6: Run test to verify it passes**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_config_elliott.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add news_breakout/config.py config/config.example.yaml tests/test_config_elliott.py
git commit -m "feat(elliott): config section (enabled, scales, thresholds) (EW-1)"
```

---

### Task 7: `TickerAlert.wave_context` + formatter hook (golden test)

**Files:**
- Modify: `news_breakout/models.py` (add `wave_context` field)
- Modify: `news_breakout/alerts/formatter.py` (render the block after the score line)
- Test: `tests/test_formatter_elliott.py`

**Interfaces:**
- Consumes: `WaveContext` (Task 3), `elliott_block` (Task 5).
- Produces: `TickerAlert.wave_context: WaveContext | None = None`. Formatter renders `elliott_block(...)` between the `🏅 Skor` line and the catalyst/timestamp; thresholds passed by the caller (default to spec values so existing callers are unaffected).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_formatter_elliott.py
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.signals.elliott.models import WaveContext
from news_breakout.alerts.formatter import format_ticker_alert

TS = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))


def _alert(wave_context=None):
    sigs = [BreakoutSignal("ANTM", "1D", "resistance_breakout", 3070.0, 2.3, 3000.0, 3.1, TS)]
    a = TickerAlert("ANTM", sigs, priority=3.0, timestamp=TS)
    a.wave_context = wave_context
    return a


def test_no_context_is_byte_identical_to_before():
    # golden: an alert with wave_context=None must not contain the EW block
    msg = format_ticker_alert(_alert(None))
    assert "🌊" not in msg
    assert "📐" not in msg


def test_confident_wave3_context_renders_block():
    ctx = WaveContext(position="wave_3_start", confidence=0.62, invalidation=2950.0,
                      fib_targets={"1.618": 3480.0}, note="kemungkinan awal Wave-3")
    msg = format_ticker_alert(_alert(ctx))
    assert "🌊 Elliott" in msg and "Wave-3" in msg
    assert "2.950" in msg and "3.480" in msg


def test_low_confidence_context_hidden():
    ctx = WaveContext(position="wave_3_start", confidence=0.20, invalidation=2950.0)
    msg = format_ticker_alert(_alert(ctx))
    assert "🌊" not in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_formatter_elliott.py -v`
Expected: FAIL — `TickerAlert` has no `wave_context` attribute.

- [ ] **Step 3: Add the field to `TickerAlert` (`news_breakout/models.py`)**

Add an import guard at the top (avoid a runtime circular import; annotation is a string thanks to `from __future__ import annotations`):
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from news_breakout.signals.elliott.models import WaveContext
```
Add the field to `TickerAlert` (after `above_sma50`):
```python
    wave_context: "WaveContext | None" = None
```

- [ ] **Step 4: Render the block in `formatter.py`**

Add the import at the top of `news_breakout/alerts/formatter.py`:
```python
from news_breakout.signals.elliott.annotate import elliott_block
```
In `format_ticker_alert`, replace the tail (from the `_score_line` append onward) so the EW block sits after the score and before the catalyst:
```python
    lines.append(_score_line(alert))
    for ln in elliott_block(
        getattr(alert, "wave_context", None),
        min_conf=0.45, show_ambiguous=False, rupiah=_rupiah,
    ):
        lines.append(ln)
    if catalyst is not None:
        lines.append(
            f"📰 Katalis: {catalyst.title} ({_time_ago(catalyst.timestamp, alert.timestamp)})"
        )
    lines.append(f"⏱️ {alert.timestamp:%H:%M} WIB · delay data ~15 mnt")
    return "\n".join(lines)
```

- [ ] **Step 5: Run the new tests AND the existing formatter tests (regression / golden)**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_formatter_elliott.py tests/test_formatter.py -v`
Expected: PASS — all new tests pass AND every existing `test_formatter.py` test still passes (proves no behavior change when `wave_context` is None).

- [ ] **Step 6: Commit**

```bash
git add news_breakout/models.py news_breakout/alerts/formatter.py tests/test_formatter_elliott.py
git commit -m "feat(elliott): render advisory block on alerts; identical when absent (EW-1)"
```

---

### Task 8: Engine integration (best‑effort, degradable)

**Files:**
- Modify: `news_breakout/signals/engine.py` (compute `wave_context` in `evaluate_ticker`)
- Test: `tests/test_engine_elliott.py`

**Interfaces:**
- Consumes: `label_current` (Task 4), `TickerAlert.wave_context` (Task 7).
- Behavior: after the alert is built and scored, compute `label_current(daily_1D)` wrapped in try/except; on any exception log a warning and leave `wave_context=None`. Controlled by an `elliott_enabled` flag defaulting to True so existing calls are unchanged.

Note: `evaluate_ticker` currently has no `logger`; add a module logger. Keep the new labeling **opt-outable** via a keyword arg (`elliott_enabled: bool = True`) plus the config values, so `run.py`/`serve.py` can pass them through later without changing this milestone's default behavior.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engine_elliott.py
import numpy as np
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.signals import engine as E
from news_breakout.signals.engine import evaluate_ticker

NOW = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))


def _breakout_daily(n=80):
    # a clean uptrend that ends on a new-high breakout bar with a volume spike
    base = np.linspace(100, 150, n)
    p = base.copy()
    df = pd.DataFrame(
        {"Open": p, "High": p + 0.5, "Low": p - 0.5, "Close": p,
         "Volume": [1000.0] * (n - 1) + [5000.0]},
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )
    df.iloc[-1, df.columns.get_loc("High")] = df["High"].iloc[-2] + 5
    df.iloc[-1, df.columns.get_loc("Close")] = df["High"].iloc[-2] + 4
    return df


def test_evaluate_ticker_attaches_wave_context():
    df = _breakout_daily()
    alert = evaluate_ticker(
        "ANTM", {"1D": df}, donchian_lookback=20, rvol_window=20,
        rvol_threshold=2.5, now=NOW,
    )
    assert alert is not None                      # a breakout fired
    assert hasattr(alert, "wave_context")         # context attached (may be a 'none' ctx)


def test_labeling_failure_is_swallowed(monkeypatch):
    df = _breakout_daily()

    def boom(*a, **k):
        raise ValueError("boom")

    monkeypatch.setattr(E, "label_current", boom)
    alert = evaluate_ticker(
        "ANTM", {"1D": df}, donchian_lookback=20, rvol_window=20,
        rvol_threshold=2.5, now=NOW,
    )
    assert alert is not None                      # scan still succeeds
    assert alert.wave_context is None             # failure degraded to None


def test_elliott_disabled_leaves_context_none():
    df = _breakout_daily()
    alert = evaluate_ticker(
        "ANTM", {"1D": df}, donchian_lookback=20, rvol_window=20,
        rvol_threshold=2.5, now=NOW, elliott_enabled=False,
    )
    assert alert is not None
    assert alert.wave_context is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_engine_elliott.py -v`
Expected: FAIL — `evaluate_ticker` has no `elliott_enabled` kwarg / does not attach context.

- [ ] **Step 3: Wire labeling into `evaluate_ticker`**

At the top of `news_breakout/signals/engine.py` add:
```python
import logging

from news_breakout.signals.elliott.waves import label_current

logger = logging.getLogger(__name__)
```
Change the `evaluate_ticker` signature to accept the new flag/params (defaults preserve current behavior):
```python
def evaluate_ticker(
    ticker: str, frames: dict[str, pd.DataFrame], *,
    donchian_lookback: int, rvol_window: int, rvol_threshold: float,
    now: datetime, elliott_enabled: bool = True,
    elliott_scales: tuple[float, ...] = (2.0, 3.5, 5.0),
    elliott_atr_window: int = 14, elliott_max_pivots: int = 9,
    elliott_fib_tolerance: float = 0.06,
) -> TickerAlert | None:
```
After the block that sets `alert.above_sma50 = components.above_sma50`, and before `return alert`, insert:
```python
    if elliott_enabled and (daily := frames.get("1D")) is not None:
        try:
            alert.wave_context = label_current(
                daily, scales=elliott_scales, atr_window=elliott_atr_window,
                max_pivots=elliott_max_pivots, fib_tol=elliott_fib_tolerance,
            )
        except Exception:
            logger.warning("elliott labeling failed for %s", ticker, exc_info=True)
            alert.wave_context = None
    return alert
```

- [ ] **Step 4: Run the new tests AND the existing engine tests (regression)**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest tests/test_engine_elliott.py tests/test_engine.py -v`
Expected: PASS — new tests pass AND existing `test_engine.py` unaffected.

- [ ] **Step 5: Full suite (confirm nothing else regressed)**

Run: `C:\Data\Tools\news-breakout\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS — all prior tests plus the new EW tests green.

- [ ] **Step 6: Commit**

```bash
git add news_breakout/signals/engine.py tests/test_engine_elliott.py
git commit -m "feat(elliott): attach wave context in engine, best-effort/degradable (EW-1)"
```

---

## Self-Review

**1. Spec coverage:**
- Spec §4 architecture (package `signals/elliott/` with models/swings/fibonacci/waves/annotate) → Tasks 1–5. ✓
- §5 data models (Swing/Wave/WaveCount/WaveContext) → Tasks 1 & 3. ✓
- §6.1 swings (atr, detect_swings, multi_scale_swings) → Task 1. ✓
- §6.2 fibonacci (retracements/extensions/projection/nearest_ratio/confluence) → Task 2. ✓
- §7.1 hard rules R1–R4 + fib_fit → Task 3; enumeration/position/ambiguity/label_current → Task 4. ✓
- §7.2 annotate + formatter hook, empty-block rule → Tasks 5 & 7. ✓
- §7.3 engine integration + `TickerAlert.wave_context` → Tasks 7 & 8. ✓
- §8 config (flat `elliott_*` fields — deviation from spec's "sub-model" wording, noted in Global Constraints) → Task 6. ✓
- §9 no-repaint (provisional last leg; no reads past end) → enforced in Task 1 impl + relied on throughout. ✓
- §10 tests incl. golden "empty ⇒ identical" (Task 7) + failure-swallow (Task 8) + ambiguity (Task 4). ✓
- §2 non-goals (no corrective/intraday/bearish; no ranking/trade-plan/send change) → nothing in the tasks touches scoring/trade-plan/send. ✓

**2. Placeholder scan:** No TBD/TODO; every code step contains complete code; every test step has real assertions. ✓

**3. Type consistency:** `Swing(i,date,price,kind,provisional)` used identically in Tasks 1/3/4/5. `WaveContext(position,confidence,primary,alternates,invalidation,fib_targets,note)` consistent across Tasks 3/4/5/7. `elliott_block(ctx,*,min_conf,show_ambiguous,rupiah)` defined in Task 5, called with the same kwargs in Task 7. `label_current(df,*,scales,atr_window,max_pivots,fib_tol)` defined in Task 4, called with those kwargs in Task 8. ✓

**Deviations from spec (intentional):** config uses flat `elliott_*` fields (matches the codebase's `Settings` convention) rather than a nested sub-model; `elliott_block`/`label_current` take a `rupiah`/scales injection to keep modules dependency-light. Both noted above.
