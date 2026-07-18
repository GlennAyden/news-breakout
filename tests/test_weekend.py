from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.scheduling.weekend import build_weekend_summary

TS = datetime(2026, 7, 18, 8, 0, tzinfo=ZoneInfo("Asia/Jakarta"))


def _alert(ticker, priority, rvol):
    sig = BreakoutSignal(ticker, "1D", "resistance_breakout", 100.0, 1.0, 95.0, rvol, TS)
    return TickerAlert(ticker, [sig], priority, TS)


def test_summary_empty():
    msg = build_weekend_summary([])
    assert "tidak ada" in msg.lower() or "no " in msg.lower()


def test_summary_sorted_and_capped():
    alerts = [_alert("AAA", 3.0, 2.0), _alert("BBB", 6.0, 4.0), _alert("CCC", 3.0, 5.0)]
    msg = build_weekend_summary(alerts, top_n=2)
    lines = [ln for ln in msg.splitlines() if "⭐" in ln]
    assert len(lines) == 2                 # capped
    assert "BBB" in lines[0]               # highest priority first
    assert "CCC" in lines[1]               # tie broken by rvol (5.0 > 2.0)
    assert "AAA" not in msg
