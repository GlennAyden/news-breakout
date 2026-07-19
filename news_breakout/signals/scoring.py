from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from news_breakout.models import TickerAlert

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

_TF_WEIGHT = {"1D": 3.0, "4H": 2.0, "1H": 1.0}


@dataclass
class ScoreComponents:
    ext_pct: float
    above_sma50: bool | None
    score: float


def _top_signal(alert: TickerAlert):
    """The highest-timeframe fired signal (1D > 4H > 1H); ties broken by highest level."""
    return max(alert.signals, key=lambda s: (_TF_WEIGHT.get(s.timeframe, 0.0), s.level))


def _extension_pct(price: float, level: float) -> float:
    if level <= 0:
        return 0.0
    raw = (price - level) / level * 100
    return max(0.0, min(raw, EXT_PCT_CAP))


def _trend_state(daily_df: pd.DataFrame | None) -> bool | None:
    """True if daily close is above SMA50, False if at/below, None when it can't be computed."""
    if daily_df is None or len(daily_df) < SMA_WINDOW:
        return None
    closes = daily_df["Close"]
    sma50 = float(closes.iloc[-SMA_WINDOW:].mean())
    last_close = float(closes.iloc[-1])
    return last_close > sma50


def compute_score_components(
    alert: TickerAlert, daily_df: pd.DataFrame | None = None
) -> ScoreComponents:
    """Pure ranking score: TF-confluence base + extension reward +/- trend filter.

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

    return ScoreComponents(ext_pct=ext_pct, above_sma50=above_sma50, score=score)


def compute_quality_score(alert: TickerAlert, daily_df: pd.DataFrame | None = None) -> float:
    return compute_score_components(alert, daily_df).score
