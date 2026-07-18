from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal


def test_breakout_signal_holds_fields():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sig = BreakoutSignal(
        ticker="ANTM",
        timeframe="1D",
        signal_type="resistance_breakout",
        price=1500.0,
        pct_change=3.4,
        level=1480.0,
        rvol=2.7,
        timestamp=ts,
    )
    assert sig.ticker == "ANTM"
    assert sig.timeframe == "1D"
    assert sig.rvol == 2.7
    assert sig.timestamp.tzinfo is not None
