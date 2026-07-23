from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from news_breakout.signals.elliott.models import WaveContext

# Canonical timeframe confluence weights — the single source of truth shared by
# the ranking (engine/scoring) and the display (formatter) so they never desync.
TF_WEIGHT: dict[str, float] = {"1D": 3.0, "4H": 2.0, "1H": 1.0}


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


@dataclass
class TickerAlert:
    ticker: str
    signals: list["BreakoutSignal"]
    priority: float
    timestamp: datetime
    quality_score: float = 0.0
    ext_pct: float = 0.0
    above_sma50: bool | None = None
    long_channel: bool | None = None
    wave_context: "WaveContext | None" = None
    structure_stop: float | None = None
    atr: float | None = None

    @property
    def max_rvol(self) -> float:
        return max(s.rvol for s in self.signals)
