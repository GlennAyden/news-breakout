from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Disclosure:
    ticker: str
    title: str
    timestamp: datetime
    disclosure_id: str
    url: str
