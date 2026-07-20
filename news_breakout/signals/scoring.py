from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from news_breakout.models import TF_WEIGHT, TickerAlert

# --- Tunable weights (backtest-derived; see .superpowers/sdd/r3-ranking-report.md) ---
# Extension above the broken level is the strongest predictor (monotonic in backtest):
# reward it, capped so an outlier thrust can't dominate the score.
W_EXT = 0.3
EXT_PCT_CAP = 10.0

# Daily close vs SMA50 trend filter: below-SMA50 breakouts are net-negative in backtest,
# so the penalty outweighs the bonus.
W_TREND_UP = 1.5
W_TREND_DOWN = 3.0
SMA_WINDOW = 50

# RVOL is inverted-U (moderate-high best, extreme = exhaustion) — deliberately NOT part
# of the score. It remains a tiebreaker only (see run.py::scan_once / TickerAlert.max_rvol).

# EW-2 wave-position adjustment (gate-derived directions; magnitudes are a first
# cut, tuned by the confirming ranking backtest). wave_3_start reward scales with
# confidence (gate: high-conf outperformed low-conf).
W_WAVE3_START = 2.0        # "start of Wave-3" breakouts outperformed (+4pp/10d)
W_IMPULSE_MID = 1.5        # already-extended mid-impulse breakouts underperformed (-4pp/10d)
W_WAVE5_EXHAUSTION = 1.0   # possible exhausted 5th — advisory penalty (gate n small)


@dataclass
class ScoreComponents:
    ext_pct: float
    above_sma50: bool | None
    score: float
    wave_adjust: float = 0.0


def _top_signal(alert: TickerAlert):
    """The highest-timeframe fired signal (1D > 4H > 1H); ties broken by highest level."""
    return max(alert.signals, key=lambda s: (TF_WEIGHT.get(s.timeframe, 0.0), s.level))


def _extension_pct(price: float, level: float) -> float:
    if level <= 0:
        return 0.0
    raw = (price - level) / level * 100
    return max(0.0, min(raw, EXT_PCT_CAP))


def _trend_state(daily_df: pd.DataFrame | None) -> bool | None:
    """True if daily close is at/above SMA50, False if below, None when it can't be computed.

    An exact tie counts as 'above' (no penalty) — a breakout AT the mean is not the
    counter-trend case the penalty targets.
    """
    if daily_df is None or len(daily_df) < SMA_WINDOW:
        return None
    closes = daily_df["Close"]
    sma50 = float(closes.iloc[-SMA_WINDOW:].mean())
    last_close = float(closes.iloc[-1])
    return last_close >= sma50


def _wave_adjust(wave_context) -> float:
    """Score nudge from the (advisory) Elliott wave position. 0 when unavailable/neutral."""
    if wave_context is None:
        return 0.0
    pos = getattr(wave_context, "position", "none")
    conf = getattr(wave_context, "confidence", 0.0)
    if pos == "wave_3_start":
        return W_WAVE3_START * conf
    if pos == "impulse_mid":
        return -W_IMPULSE_MID
    if pos == "wave_5_possible_exhaustion":
        return -W_WAVE5_EXHAUSTION
    return 0.0


def compute_score_components(
    alert: TickerAlert, daily_df: pd.DataFrame | None = None, wave_context=None
) -> ScoreComponents:
    """Pure ranking score: TF-confluence base + extension reward +/- trend filter +/- wave position.

    RVOL is intentionally excluded (inverted-U in backtest) — callers should use
    alert.max_rvol as a secondary tiebreaker instead.
    """
    top = _top_signal(alert)
    ext_pct = _extension_pct(top.price, top.level)
    above_sma50 = _trend_state(daily_df)

    score = alert.priority + W_EXT * ext_pct
    if above_sma50 is True:
        score += W_TREND_UP
    elif above_sma50 is False:
        score -= W_TREND_DOWN

    wave_adj = _wave_adjust(wave_context)
    score += wave_adj

    return ScoreComponents(
        ext_pct=ext_pct, above_sma50=above_sma50, score=score, wave_adjust=wave_adj
    )


def compute_quality_score(
    alert: TickerAlert, daily_df: pd.DataFrame | None = None, wave_context=None
) -> float:
    return compute_score_components(alert, daily_df, wave_context=wave_context).score
