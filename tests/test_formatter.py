from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal
from news_breakout.alerts.formatter import format_breakout


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
