from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from news_breakout.orderbook.models import OrderbookSnapshot


class Phase(str, Enum):
    """Orderbook phase from the user's Wyckoff-style playbook."""

    ACCUMULATION = "A"      # offer-dominant — supply overhead, not ready
    READY_MARKUP = "RM"     # bid ~= offer — entry trigger
    BEFORE_MARKDOWN = "BM"  # bid-dominant — trap, can revert to A
    UNKNOWN = "?"           # not enough data to classify


@dataclass
class PhaseConfig:
    # RM when min(bid,offer)/max(bid,offer) >= this. Below it, the dominant
    # side decides A (offer>bid) vs BM (bid>offer).
    rm_balance_min_ratio: float = 0.85


@dataclass
class PhaseResult:
    phase: Phase
    bid_lot: int
    offer_lot: int
    ratio: float  # min(bid,offer)/max(bid,offer), 0..1; balance measure

    @property
    def is_ready_markup(self) -> bool:
        return self.phase is Phase.READY_MARKUP


def classify_phase(snapshot: OrderbookSnapshot, cfg: PhaseConfig) -> PhaseResult:
    """Classify A / RM / BM from total bid vs offer lot.

    Balance ``ratio = min/max`` is symmetric (1.0 = perfectly balanced). When
    ``ratio >= rm_balance_min_ratio`` the book is balanced enough for Ready
    Markup; otherwise the larger side names the phase.
    """
    bid, offer = snapshot.total_bid_lot, snapshot.total_offer_lot
    if bid <= 0 or offer <= 0:
        return PhaseResult(Phase.UNKNOWN, bid, offer, 0.0)
    ratio = min(bid, offer) / max(bid, offer)
    if ratio >= cfg.rm_balance_min_ratio:
        phase = Phase.READY_MARKUP
    elif offer > bid:
        phase = Phase.ACCUMULATION
    else:
        phase = Phase.BEFORE_MARKDOWN
    return PhaseResult(phase, bid, offer, ratio)
