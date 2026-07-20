# Elliott Wave + Fibonacci — Design Spec (EW‑0 + EW‑1)

- **Date:** 2026-07-20
- **Status:** Approved (design) — pending spec review
- **Owner:** news-breakout
- **Scope of THIS spec:** Milestone **EW‑0** (foundation: causal swings + Fibonacci) and **EW‑1** (impulse wave labeling + alert annotation). EW‑2/3/4 are described in the roadmap only and get their own spec + backtest each.
- **Relation to existing code:** purely additive. No change to the production signal, ranking, trade plan, or which alerts are sent. A new `signals/elliott/` package is computed best‑effort and only *appends* an advisory block to the alert.

---

## 1. Motivation & Backtest Findings

The tool already emits a mechanical trade plan (`alerts/formatter.py::_trade_plan_line`): Entry = breakout close, Invalidation = the broken Donchian level, Target = fixed 2R. The user asked to (a) backtest that plan and (b) add Elliott Wave + Fibonacci support.

A trade‑plan backtest was run (5y daily, 24‑name watchlist, reusing the **exact** production signal `detect_donchian_breakout` + `compute_rvol` at `rvol_threshold=2.5`; entry at breakout close; monitor from the next bar; conservative same‑bar SL‑first; max hold 40 bars; metrics in **% of entry** because "risk = entry − level" can approach zero and makes raw R‑multiples explode). Results (Appendix A) established:

- **F1 — The signal has a real edge.** Every "buy‑strength" plan is net positive (profit factor ≈ 2.0–2.5).
- **F2 — The current plan works but is not optimal.** +2.93%/trade, win 44%, PF 2.01 — but the *median trade is a −1% stop‑out*; profit comes from a minority of large winners.
- **F3 — The biggest lever is STOP WIDTH, not the target.** Moving the stop from the exact broken level to a structure‑based level (below the 0.618 retrace, or below the anchoring swing low) lifts win rate to ~50–52% and 2.5–3× the per‑trade %‑expectancy. Mechanism: breakouts almost always retest; a stop at the exact level is tagged on the normal pullback. **This is where a swing/Fibonacci layer adds measured value — stop placement.**
- **F4 — Wider stops are not free edge.** Risk‑normalized, all buy‑strength variants converge to ≈ +0.43–0.56R/trade; wider stops mainly reshape P&L (higher win rate, fewer/larger trades, more timeouts) — better for a time‑poor trader, similar total edge.
- **F5 — Fibonacci TARGETS add ≈ nothing.** A 1.618‑extension target ≈ the fixed‑2R baseline ≈ a random‑target control. Consistent with the academic literature (no standalone Fib edge).
- **F6 — Fibonacci/pullback ENTRIES actively hurt here.** Waiting for a 0.5 pullback → 41% participation, 14% win, PF ≈ 1. These momentum names reward buying strength.
- **F7 — Fixed targets leave runners on the table.** Median breakout MFE +7.1%; 40% run ≥10%, 20% run ≥20% → argues for partial‑profit + trailing, not a smarter fixed target.

**Design consequence:** Elliott Wave naturally supplies the structure‑based invalidation that F3 rewards (a Wave‑3 long is invalid below the Wave‑2 low = a swing low). Fibonacci **retracements** are valuable for **stop placement**; Fibonacci **extensions** are kept as *informational* projections (F5), not mechanical targets. Fibonacci **entries** are excluded (F6). These consequences land in EW‑3, not EW‑1; EW‑1 is annotation‑only.

## 2. Goals & Non‑Goals (EW‑0 + EW‑1)

**Goals**
- G1: A causal, no‑repaint swing detector (multi‑scale) and a Fibonacci module, unit‑tested, usable by all later milestones.
- G2: An impulse (5‑wave) labeler that validates the machine‑checkable rules, scores counts by Fibonacci fit, infers the *current wave position*, and honestly reports **ambiguity** and **confidence**.
- G3: An advisory Elliott/Fibonacci block appended to the breakout alert; degrades silently to nothing when ambiguous/unavailable.
- G4: Zero change to production behavior (signal, ranking, trade plan, send decision).

**Non‑Goals (deferred)**
- N1: Automatic detection of **corrective** patterns (ABC/flat/triangle) → labeled `ambiguous/unresolved` for now (research: this is the fragile part).
- N2: **Intraday** (4H/1H) wave counting → later milestone. EW‑1 computes on **1D only**.
- N3: Any use of EW to change ranking, stop/target, or which alert is sent (EW‑2/3/4).
- N4: **Bearish/short** structures — the tool is long‑only; down‑legs are used only as context (e.g., is the breakout emerging from a completed correction vs. an exhausted 5th).

## 3. Key Decisions (from brainstorming)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Phased build** EW‑0→EW‑4; each behavior‑changing milestone (EW‑2/3/4) has a **mandatory backtest gate**. | Matches the project's milestone rhythm; the crude Wyckoff signal was net‑negative when shipped un‑backtested. |
| D2 | **Daily‑first.** Wave counting on 1D only for now. | Cleanest data; strongest signal edge; easiest to validate. |
| D3 | **Impulse‑only.** Corrective patterns flagged `ambiguous`. | Auto‑detecting corrections is the least reliable part of auto‑EW. |
| D4 | **Advisory‑only in EW‑1.** EW appends text; never blocks or reorders alerts. | Zero‑risk first milestone; lets the expert user calibrate trust before EW influences decisions. |
| D5 | **Causal / no‑repaint.** Only bars ≤ current used; the last leg is explicitly *provisional*. | Prevents look‑ahead; required for the later backtests to be honest. |
| D6 | **Multi‑scale swings (2–3 ATR scales); cross‑scale disagreement ⇒ lower confidence / `ambiguous`.** | There is no threshold‑free pivot detector; the count is a function of the threshold. Disagreement is the honest ambiguity signal. |
| D7 | **Encode only the 4 machine‑checkable impulse rules as hard filters; Fibonacci ratios only *score* valid counts (tolerance bands), never force a label.** | The hard rules are the only objective content of EW; the Fib layer has weak/negative predictive evidence and must not be a gate. |
| D8 | **Fibonacci extensions are informational; retracements feed later stop placement.** | F5/F3 from the backtest. |
| D9 | **Best‑effort, fully degradable.** All EW computation wrapped so a failure logs and yields "no context", never aborts a scan. | Same resilience contract as the news subsystem. |

## 4. Architecture

New package, isolated from the engine, mirroring the project's package style:

```
news_breakout/signals/elliott/
  __init__.py
  models.py      # Swing, Wave, WaveCount, WaveContext
  swings.py      # causal multi-scale ZigZag/ATR pivot detector
  fibonacci.py   # retracement / extension / projection / confluence
  waves.py       # impulse enumeration + hard-rule validation + scoring + position inference
  annotate.py    # render the advisory Elliott/Fibonacci block
```

**Integration seam (one call, best‑effort):** `signals/engine.py::evaluate_ticker` computes a `WaveContext` from the 1D frame after building the `TickerAlert`, wrapped in try/except, and attaches it to a new optional field `TickerAlert.wave_context`. `alerts/formatter.py::format_ticker_alert` renders the block when present. Config gains an `elliott:` section. `serve.py`/`run.py` unchanged (defaults on).

## 5. Data Models (`models.py`)

```python
@dataclass
class Swing:
    i: int            # bar index
    date: datetime
    price: float
    kind: str         # 'H' | 'L'
    provisional: bool # True = last, unconfirmed leg (no-repaint marker)

@dataclass
class Wave:
    label: str        # '1'..'5'
    start: Swing
    end: Swing
    @property
    def length(self) -> float: ...   # abs(end.price - start.price)

@dataclass
class WaveCount:
    waves: list[Wave]         # the 5 impulse legs (or partial, up to current)
    scale: float              # ATR multiple that produced the underlying swings
    rules_ok: bool            # all 4 hard rules pass
    rule_flags: dict[str,bool]
    fib_fit: float            # 0..1 how well internal ratios match EW guidelines

@dataclass
class WaveContext:
    position: str             # 'wave_3_start' | 'wave_5_possible_exhaustion' |
                              # 'wave_2_pullback' | 'wave_4_pullback' | 'impulse_mid' |
                              # 'corrective_or_unresolved' | 'ambiguous' | 'none'
    confidence: float         # 0..1
    primary: WaveCount | None
    alternates: list[WaveCount]
    invalidation: float | None   # price that negates the primary count (e.g. Wave-2 low)
    fib_targets: dict[str,float] # informational, e.g. {'1.618': .., '2.618': ..}
    note: str                    # short human string for the alert
```

## 6. EW‑0 — Foundation

### 6.1 `swings.py` — causal multi‑scale pivots
```python
def atr(df, window=14) -> pd.Series: ...          # Wilder ATR

def detect_swings(df, atr_mult, atr_window=14) -> list[Swing]:
    """Causal ZigZag: a reversal of >= atr_mult*ATR from the running extreme
    confirms the prior extreme as a pivot. The final, still-extending leg is
    returned as a single provisional=True swing. Uses only bars up to len(df)-1."""

def multi_scale_swings(df, scales=(2.0, 3.5, 5.0)) -> dict[float, list[Swing]]: ...
```
- Alternation is enforced (H,L,H,L…). Confirmation latency is inherent (a pivot is known only once price reverses by the threshold) — this is the anti‑repaint guarantee, not a bug.

### 6.2 `fibonacci.py`
```python
RETRACE = (0.382, 0.5, 0.618, 0.786)
EXTEND  = (1.272, 1.618, 2.0, 2.618)

def retracements(low, high) -> dict[float,float]:   # high - f*(high-low)
def extensions(low, high) -> dict[float,float]:     # low + f*(high-low)
def projection(a, b, c, f) -> float:                # 3-point measured move: c + f*(b-a)
def nearest_ratio(price, low, high, ratios, tol=0.05) -> float | None:  # which ratio price sits at

def confluence(level, *, structure=None, sma=None, round_step=None,
               other_scale_levels=()) -> tuple[int, list[str]]:
    """Weighted confluence score + contributing factors for a candidate price zone.
    structure/SMA/round-number/cross-scale-Fib-cluster within a ±tol*ATR band."""
```

## 7. EW‑1 — Impulse labeling + annotation

### 7.1 `waves.py` — algorithm (causal, impulse‑first)
1. For each scale, take the last **K** confirmed swings (K small, e.g. 9) plus the provisional leg.
2. Enumerate candidate up‑impulse segmentations: 5 consecutive legs with correct alternation ending at/near the current bar (bounded combinatorics on K).
3. **Hard‑rule filter** (a candidate is discarded unless *all* pass):
   - **R1** Wave 2 does not retrace > 100% of Wave 1 (W2 low > W1 start).
   - **R2** Wave 3 is not the shortest of {1,3,5} by price length.
   - **R3** Wave 4 does not enter Wave 1 price territory (W4 low > W1 high).
   - **R4** Directional alternation correct (1,3,5 up; 2,4 down).
4. **Score** each surviving count: `fib_fit` from how close W2 retrace is to 0.5/0.618, W3 to 1.618×W1, W4 to 0.382×W3, W5 to 0.618×W1 / equality — each as a tolerance band (±~6%). Add a bonus when ≥2 scales yield a compatible count.
5. **Rank** → `primary` + `alternates`. **Confidence** = f(rule pass margin, `fib_fit`, cross‑scale agreement, uniqueness). If no valid impulse, or top counts imply contradictory positions across scales → `position='ambiguous'` (or `corrective_or_unresolved` when the recent structure is a clean 3‑swing counter‑move).
6. **Current‑position inference** from where the provisional leg sits in the primary count:
   - just resolved a valid Wave‑2 and breaking above Wave‑1 high → `wave_3_start` (the highest‑odds, confirming case);
   - price ≥ 1.618×W1 beyond Wave‑4 with the count near a 5th → `wave_5_possible_exhaustion` (the caution/veto case);
   - inside a 2nd/4th counter‑move → `wave_2_pullback` / `wave_4_pullback`; otherwise `impulse_mid`.
7. `invalidation` = the primary count's negating price (typically the Wave‑2 low for a Wave‑3 thesis). `fib_targets` = W3/W5 extension projections (informational).

```python
def label_current(df, *, scales=(2.0,3.5,5.0), max_pivots=9,
                  fib_tol=0.06, min_conf=0.0) -> WaveContext: ...
```

### 7.2 `annotate.py` + formatter hook
```python
def elliott_block(ctx: WaveContext, *, min_conf: float, show_ambiguous: bool) -> list[str]:
    """Return 0–2 lines. Omitted entirely when ctx.position == 'none', OR when
    ctx.confidence < min_conf, OR when ctx.position == 'ambiguous' and
    show_ambiguous is False. All dynamic prices formatted via existing _rupiah()."""
```
Rendered lines (examples):
- `🌊 Elliott: kemungkinan awal Wave-3 (conf 0.62) · invalidasi W2 <2.950`
- `📐 Fib: target W3 1.618×→3.480 · 2.618×→3.780`
- `🌊 Elliott: ⚠️ kemungkinan Wave-5 lelah (conf 0.55) — hati-hati kejar breakout`
- `🌊 Elliott: ambigu (hitungan bertentangan antar skala) — pakai penilaianmu`  *(only if `show_ambiguous: true`; else omitted)*

Hook: in `format_ticker_alert`, insert `elliott_block(alert.wave_context, ...)` after the `🏅 Skor` line, before the catalyst/timestamp. When the block is empty, the alert is byte‑identical to today's.

### 7.3 Engine integration
```python
# engine.py::evaluate_ticker, after alert is built:
if elliott_enabled and (daily := frames.get("1D")) is not None:
    try:
        alert.wave_context = label_current(daily, **elliott_cfg)
    except Exception:
        logger.warning("elliott labeling failed for %s", ticker, exc_info=True)
        alert.wave_context = None
```
`TickerAlert` gains `wave_context: WaveContext | None = None` (default None keeps every existing construction/test valid).

## 8. Config (`config.example.yaml`, new section — all defaulted)
```yaml
elliott:
  enabled: true
  atr_scales: [2.0, 3.5, 5.0]
  atr_window: 14
  max_pivots: 9          # confirmed swings fed to the labeler
  fib_tolerance: 0.06    # ± band for ratio-fit scoring
  min_confidence: 0.45   # below this, show nothing (or only 'ambiguous' if show_ambiguous)
  show_ambiguous: false  # if true, print the 'ambigu' line instead of omitting
```
`config.py::Settings` gains an `ElliottSettings` sub‑model with these defaults so existing construction is unaffected.

## 9. Causality / No‑Repaint Discipline

- `detect_swings` consumes only `df` as given; the caller passes bars up to "now". The most recent leg is a single `provisional=True` swing and is **never** treated as a confirmed pivot for rule R1–R4 boundaries (only for the "where is price now" inference).
- No function peeks beyond the last row. This makes the EW‑2/3/4 backtests (which recompute `label_current` bar‑by‑bar over history) honest by construction.

## 10. Testing Strategy

Unit tests (`tests/test_elliott_*.py`), each unit isolated:
- **swings:** a known zig‑zag series → expected pivots; a monotonic series → single provisional swing; ATR scaling changes pivot count as expected.
- **fibonacci:** exact retracement/extension/projection math; `nearest_ratio` classification; `confluence` scoring on crafted inputs.
- **waves — hard rules:** an ideal 5‑wave impulse array → `rules_ok=True`, correct labels, `position` inference; individually violate R1/R2/R3/R4 → that count rejected.
- **waves — ambiguity:** a fixture where two scales imply contradictory counts → `position='ambiguous'`; a clean 3‑swing counter‑move → `corrective_or_unresolved`.
- **waves — position:** post‑Wave‑2 breakout fixture → `wave_3_start` with invalidation = W2 low; extended‑5th fixture → `wave_5_possible_exhaustion`.
- **annotate/formatter:** block renders & html‑safe; **empty block ⇒ alert identical to current** (golden test); confidence below `min_confidence` ⇒ omitted.
- **engine:** labeling failure is swallowed (monkeypatch `label_current` to raise) → scan still returns the alert with `wave_context=None`.
- **real fixture (sanity):** 1–2 cached watchlist daily series → `label_current` runs without error and returns a plausible context (no assertion on the exact count — guards against crashes/look‑ahead, not correctness of the count).

## 11. Roadmap (later milestones — separate spec + backtest each)

- **EW‑2 Filter & Ranking** — feed `position`/confidence into `scoring.compute_score_components` (boost `wave_3_start`, penalize `wave_5_possible_exhaustion`). **Backtest gate:** does EW‑aware ranking beat the current top‑quartile edge?
- **EW‑3 Trade‑plan** — stop below Wave‑2/4 low (= backtest variant V4), Fib‑extension **informational** targets + partial‑profit/trailing management. **Backtest gate:** beat the fixed‑2R baseline on expectancy + MAE/MFE + R‑distribution, net of IDX costs.
- **EW‑4 Standalone EW signals** — end‑of‑Wave‑2/4 entries. **Separate backtest;** highest risk (pullback entries tested weakly in Appendix A).

## 12. Risks & Open Questions

- **R‑a (fragility):** even validated auto‑EW is ambiguous; confidence + ambiguity gating are the mitigations. Mitigate further by surfacing to the human, not deciding for them (EW‑1 is advisory).
- **R‑b (overfit in EW‑2/3):** the mandatory backtests use walk‑forward, causal labeling, and a random‑level/label control; ship only if the edge survives.
- **R‑c (cost realism):** EW‑3 backtest must include IDX round‑trip costs (~0.3–0.5%) and slippage; EW‑1 has no such exposure.
- **OQ‑1:** confidence formula weights (`min_confidence` default 0.45) are a first guess — expect to tune once real alerts are observed.
- **OQ‑2:** whether to add minimal ABC‑zigzag corrective detection in EW‑1 or keep it fully deferred (current spec: deferred, D3).

---

## Appendix A — Trade‑plan backtest results

5y daily, 24‑name watchlist, signal = production Donchian‑20 new‑high + RVOL≥2.5, entry at breakout close, monitor from next bar, max hold 40 bars, same‑bar SL‑first. Metrics in **% of entry**.

| Plan | n | Mean/trade | Median | Win% | PF | Exit mix | Risk‑norm (clipped R) |
|---|---|---|---|---|---|---|---|
| Baseline (stop@level, 2R) | 433 | +2.93% | −1.00% | 44.1% | 2.01 | 55% SL / 43% TP | +0.46R |
| V1 Fib‑ext 1.618 target | 419 | +3.61% | −1.49% | 36.5% | 2.20 | 63% SL | +0.56R |
| V3 stop<0.618 retrace, 2R | 355 | +7.22% | −0.79% | 49.3% | 2.36 | 46% SL / 11% TO | +0.43R |
| V4 stop<swing low, 2R | 312 | +10.09% | +1.86% | 51.9% | 2.50 | 28% SL / 38% TO | +0.43R |
| Control random‑R target | 436 | +2.90% | −0.72% | 46.8% | 2.09 | — | +0.43R |
| V2 pullback‑to‑0.5 entry | 145 | +0.24% | −2.38% | 13.8% | 1.08 | 86% SL | +0.04R |

Baseline MFE distribution (max favorable %‑move before reversing): p50 +7.1%, p75 +16.9%, p90 +28.2%; reached ≥10%: 40.4%, ≥20%: 19.6%.

**Caveats:** excludes fees/slippage/tax (~0.3–0.5% round trip in IDX); daily timeframe only; 24 volatile commodity/energy names (may not generalize to the 141‑ticker universe); idealized entry at the breakout close. Backtest harness: `scratchpad/bt_common.py` + `bt_run.py` (reuses production `detect_donchian_breakout` / `compute_rvol`).
