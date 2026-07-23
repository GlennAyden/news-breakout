from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.orderbook.models import OrderbookSnapshot
from news_breakout.orderbook.phase import Phase, PhaseConfig, classify_phase

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 20, 10, 0, tzinfo=WIB)
CFG = PhaseConfig(rm_balance_min_ratio=0.85)


def _snap(bid, offer):
    return OrderbookSnapshot(symbol="X", ts=NOW, total_bid_lot=bid, total_offer_lot=offer)


def test_accumulation_offer_dominant():
    # playbook example: 300k bid / 700k offer
    r = classify_phase(_snap(300_000, 700_000), CFG)
    assert r.phase is Phase.ACCUMULATION
    assert not r.is_ready_markup


def test_ready_markup_balanced():
    # playbook example: 300k / 300k
    r = classify_phase(_snap(300_000, 300_000), CFG)
    assert r.phase is Phase.READY_MARKUP
    assert r.is_ready_markup
    assert r.ratio == 1.0


def test_before_markdown_bid_dominant():
    # playbook example: 500k bid / 300k offer
    r = classify_phase(_snap(500_000, 300_000), CFG)
    assert r.phase is Phase.BEFORE_MARKDOWN


def test_boundary_at_min_ratio():
    assert classify_phase(_snap(85, 100), CFG).phase is Phase.READY_MARKUP   # 0.85
    assert classify_phase(_snap(84, 100), CFG).phase is Phase.ACCUMULATION   # 0.84


def test_unknown_when_side_empty():
    assert classify_phase(_snap(0, 500), CFG).phase is Phase.UNKNOWN
    assert classify_phase(_snap(500, 0), CFG).phase is Phase.UNKNOWN
