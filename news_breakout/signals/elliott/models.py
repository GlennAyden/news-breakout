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
