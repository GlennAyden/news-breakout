from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.orderbook.formatter import format_orderbook_alert
from news_breakout.orderbook.models import OrderbookSnapshot
from news_breakout.orderbook.phase import Phase, PhaseResult
from news_breakout.orderbook.volume_filter import VolumeResult

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 20, 10, 0, tzinfo=WIB)


def _snap():
    return OrderbookSnapshot(
        symbol="ANTM", ts=NOW, total_bid_lot=300_000, total_offer_lot=300_000,
        last_price=1500,
    )


def _rm():
    return PhaseResult(Phase.READY_MARKUP, 300_000, 300_000, 1.0)


def _vol():
    return VolumeResult(True, 800.0, 1000.0, 0.8)


def test_alert_has_symbol_phase_and_ratio():
    text = format_orderbook_alert(_snap(), _rm(), None, _vol(), now=NOW, minutes_after_open=45)
    assert "ANTM" in text
    assert "<b>READY MARKUP</b>" in text
    assert "balance 100%" in text
    assert "300,000" in text
    assert "WIB" in text
    # ticker is a tappable Stockbit link
    assert 'href="https://stockbit.com/symbol/ANTM"' in text
    assert "Buka orderbook" in text


def test_prior_accumulation_note():
    text = format_orderbook_alert(_snap(), _rm(), "A", _vol(), now=NOW)
    assert "AKUMULASI" in text


def test_prior_before_markdown_warns_trap():
    text = format_orderbook_alert(_snap(), _rm(), "BM", _vol(), now=NOW)
    assert "tipuan" in text.lower()


def test_volume_line_included_with_minutes():
    text = format_orderbook_alert(_snap(), _rm(), None, _vol(), now=NOW, minutes_after_open=30)
    assert "0.80× kemarin" in text
    assert "30 mnt" in text
