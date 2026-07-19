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


@dataclass
class TickerAlert:
    ticker: str
    signals: list["BreakoutSignal"]
    priority: float
    timestamp: datetime
    quality_score: float = 0.0
    ext_pct: float = 0.0
    above_sma50: bool | None = None

    @property
    def max_rvol(self) -> float:
        return max(s.rvol for s in self.signals)
