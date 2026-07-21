from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.alerts.formatter import format_ticker_alert


def _alert():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sigs = [
        BreakoutSignal("ANTM", "1D", "resistance_breakout", 3070.0, 3.4, 3000.0, 2.7, ts),
    ]
    return TickerAlert("ANTM", sigs, priority=5.0, timestamp=ts)


def test_trade_plan_uses_atr_trailing_when_structure_stop_and_atr_present():
    alert = _alert()
    alert.structure_stop = 2900.0
    alert.atr = 80.0
    msg = format_ticker_alert(alert)
    assert "📍 Rencana" in msg
    assert "Entry ~3.070" in msg
    assert "Stop (EW) <2.900" in msg
    assert "Risk 5.5%" in msg
    assert "Trail 2.5×ATR ~200" in msg
    assert "+1R (~3.240)" in msg
    assert "Target 2R" not in msg
