# tests/test_formatter_elliott.py
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.signals.elliott.models import WaveContext
from news_breakout.alerts.formatter import format_ticker_alert

TS = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))


def _alert(wave_context=None):
    sigs = [BreakoutSignal("ANTM", "1D", "resistance_breakout", 3070.0, 2.3, 3000.0, 3.1, TS)]
    a = TickerAlert("ANTM", sigs, priority=3.0, timestamp=TS)
    a.wave_context = wave_context
    return a


def test_no_context_is_byte_identical_to_before():
    # golden: an alert with wave_context=None must not contain the EW block
    msg = format_ticker_alert(_alert(None))
    assert "🌊" not in msg
    assert "📐" not in msg


def test_confident_wave3_context_renders_block():
    ctx = WaveContext(position="wave_3_start", confidence=0.62, invalidation=2950.0,
                      fib_targets={"1.618": 3480.0}, note="kemungkinan awal Wave-3")
    msg = format_ticker_alert(_alert(ctx))
    assert "🌊 Elliott" in msg and "Wave-3" in msg and "0.62" in msg
    # invalidation lives in the Stop line; fib targets dropped (no backtest edge)
    assert "2.950" not in msg and "3.480" not in msg and "📐" not in msg


def test_low_confidence_context_hidden():
    ctx = WaveContext(position="wave_3_start", confidence=0.20, invalidation=2950.0)
    msg = format_ticker_alert(_alert(ctx))
    assert "🌊" not in msg


def test_show_ambiguous_param_renders_ambiguous_line():
    ctx = WaveContext(position="ambiguous", confidence=0.0, note="konflik")
    default_msg = format_ticker_alert(_alert(ctx))
    assert "🌊" not in default_msg
    shown_msg = format_ticker_alert(_alert(ctx), show_ambiguous=True)
    assert "ambigu" in shown_msg


def test_min_conf_param_gates_block():
    ctx = WaveContext(position="wave_3_start", confidence=0.50, invalidation=2950.0)
    strict_msg = format_ticker_alert(_alert(ctx), min_conf=0.60)
    assert "🌊" not in strict_msg
    lenient_msg = format_ticker_alert(_alert(ctx), min_conf=0.40)
    assert "🌊" in lenient_msg
