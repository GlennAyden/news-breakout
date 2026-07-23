from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OrderbookLevel:
    """One price level on one side of the book."""

    price: float
    lot: int
    freq: int


@dataclass
class OrderbookSnapshot:
    """A single-symbol orderbook depth snapshot.

    ``total_*`` are the aggregate figures the playbook works on (the bottom
    total row in Stockbit's orderbook). They are provided explicitly by the
    parser; :meth:`from_levels` derives them by summing when a caller builds a
    snapshot from levels alone (tests, fixtures).
    """

    symbol: str
    ts: datetime
    bids: list[OrderbookLevel] = field(default_factory=list)
    offers: list[OrderbookLevel] = field(default_factory=list)
    total_bid_lot: int = 0
    total_offer_lot: int = 0
    total_bid_freq: int = 0
    total_offer_freq: int = 0
    last_price: float | None = None

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_offer(self) -> float | None:
        return self.offers[0].price if self.offers else None

    @classmethod
    def from_levels(
        cls,
        symbol: str,
        ts: datetime,
        bids: list[OrderbookLevel],
        offers: list[OrderbookLevel],
        *,
        last_price: float | None = None,
    ) -> "OrderbookSnapshot":
        return cls(
            symbol=symbol,
            ts=ts,
            bids=bids,
            offers=offers,
            total_bid_lot=sum(l.lot for l in bids),
            total_offer_lot=sum(l.lot for l in offers),
            total_bid_freq=sum(l.freq for l in bids),
            total_offer_freq=sum(l.freq for l in offers),
            last_price=last_price,
        )
