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
    from_abc: bool = False
