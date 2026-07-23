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


def test_trade_plan_uses_structure_stop_when_present():
    alert = _alert()
    alert.structure_stop = 2900.0
    msg = format_ticker_alert(alert)
    assert "💰 Beli  : ~3.070" in msg
    assert "🛑 Stop  : 2.900 (EW, risiko 5.5%)" in msg
    assert "🎯 Target: 2R ~3.410" in msg


def test_trade_plan_falls_back_to_level_when_no_structure_stop():
    alert = _alert()
    alert.structure_stop = None
    msg = format_ticker_alert(alert)
    assert "💰 Beli  : ~3.070" in msg
    assert "🛑 Stop  : <3.000 (risiko 2.3%)" in msg
    assert "(EW" not in msg
    assert "🎯 Target: 2R ~3.210" in msg
