from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.confluence.formatter import format_confluence_alert

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 24, 10, 32, tzinfo=WIB)
BREAKOUT = {"tf": "1D", "price": 4850, "pct_change": 3.2, "level": 4800,
            "rvol": 3.2, "quality": 7.0}
CATALYST_TS = datetime(2026, 7, 24, 8, 12, tzinfo=WIB)


def test_two_of_three_has_pending_orderbook_and_no_orderbook_line():
    text = format_confluence_alert(
        ticker="BBRI", stage="2of3", catalyst_text="Kontrak baru Rp2,1T",
        catalyst_source="disclosure", catalyst_ts=CATALYST_TS,
        breakout=BREAKOUT, orderbook=None, now=NOW)
    assert "CONFLUENCE 2/3 — BBRI" in text
    assert "ORDERBOOK ⏳" in text
    assert "RVOL 3.2×" in text
    assert "READY MARKUP" not in text
    assert "4.850" in text          # Indonesian thousands separator


def test_three_of_three_has_ready_markup_and_orderbook_line():
    text = format_confluence_alert(
        ticker="BBRI", stage="3of3", catalyst_text="Kontrak baru Rp2,1T",
        catalyst_source="disclosure", catalyst_ts=CATALYST_TS,
        breakout=BREAKOUT, orderbook={"bid_lot": 300000, "offer_lot": 295000, "ratio": 0.98},
        now=NOW)
    assert "CONFLUENCE 3/3 — BBRI" in text
    assert "ORDERBOOK ✅ READY MARKUP" in text
    assert "300.000/295.000" in text
    assert "0.98" in text


def test_html_special_chars_in_catalyst_are_escaped():
    text = format_confluence_alert(
        ticker="BBRI", stage="2of3", catalyst_text="Laba naik & ekspansi <baru>",
        catalyst_source="disclosure", catalyst_ts=CATALYST_TS, breakout=BREAKOUT,
        orderbook=None, now=NOW)
    assert "&amp;" in text and "&lt;baru&gt;" in text
    assert "& ekspansi <baru>" not in text   # raw unescaped must not survive
