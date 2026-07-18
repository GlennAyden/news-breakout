from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.news.models import Disclosure
from news_breakout.alerts.formatter import format_breakout, format_ticker_alert


def test_format_contains_key_fields():
    sig = BreakoutSignal(
        ticker="ANTM",
        timeframe="1D",
        signal_type="resistance_breakout",
        price=1500.0,
        pct_change=3.4,
        level=1480.0,
        rvol=2.7,
        timestamp=datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta")),
    )
    msg = format_breakout(sig)
    assert "ANTM" in msg
    assert "1D" in msg
    assert "1.480" in msg          # level, thousands-formatted
    assert "1.500" in msg          # price
    assert "3.4%" in msg
    assert "2.7" in msg            # rvol
    assert "15:30" in msg          # WIB time


def test_format_ticker_alert_lists_each_timeframe():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sigs = [
        BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1480.0, 2.7, ts),
        BreakoutSignal("ANTM", "4H", "wyckoff_range_breakout", 1500.0, 3.4, 1450.0, 2.1, ts),
    ]
    alert = TickerAlert("ANTM", sigs, priority=5.0, timestamp=ts)
    msg = format_ticker_alert(alert)
    assert "ANTM" in msg
    assert "1D" in msg and "4H" in msg
    assert "1.480" in msg and "1.450" in msg
    assert "2.7" in msg and "2.1" in msg
    assert "15:30" in msg
    assert "🚨" in msg
    assert "🔥" not in msg


def test_format_ticker_alert_with_catalyst_shows_fire_and_katalis():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sigs = [
        BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1480.0, 2.7, ts),
    ]
    alert = TickerAlert("ANTM", sigs, priority=5.0, timestamp=ts)
    catalyst = Disclosure(
        ticker="ANTM",
        title="Right Issue Announcement",
        timestamp=ts - timedelta(hours=2),
        disclosure_id="123",
        url="https://example.com",
    )
    msg = format_ticker_alert(alert, catalyst=catalyst)
    assert "🔥" in msg
    assert "Katalis" in msg
    assert "Right Issue Announcement" in msg
    assert "jam lalu" in msg
