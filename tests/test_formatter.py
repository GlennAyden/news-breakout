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


def test_format_ticker_alert_compresses_timeframes_into_header():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sigs = [
        BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1480.0, 2.7, ts),
        BreakoutSignal("ANTM", "4H", "wyckoff_range_breakout", 1500.0, 3.4, 1450.0, 2.1, ts),
    ]
    alert = TickerAlert("ANTM", sigs, priority=5.0, timestamp=ts)
    alert.quality_score = 6.5
    msg = format_ticker_alert(alert)
    assert "ANTM" in msg
    assert "1D+4H" in msg                  # confluence compressed into the header
    assert "• TF" not in msg               # no per-TF bullet lines anymore
    assert "1.480" in msg and "2.7" in msg  # primary (1D) level + rvol still shown
    assert "1.450" not in msg and "2.1" not in msg  # secondary TF details dropped
    assert "skor 6.5" in msg
    assert "15:30" in msg
    assert "🚨" in msg
    assert "🔥" not in msg


def test_format_ticker_alert_strength_stars_scale_with_score():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    def alert(score):
        sigs = [BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1480.0, 2.7, ts)]
        a = TickerAlert("ANTM", sigs, priority=3.0, timestamp=ts)
        a.quality_score = score
        return a
    assert "⭐⭐⭐" in format_ticker_alert(alert(9.5))
    two = format_ticker_alert(alert(7.5))
    assert "⭐⭐" in two and "⭐⭐⭐" not in two
    one = format_ticker_alert(alert(6.0))
    assert "⭐" in one and "⭐⭐" not in one


def test_format_ticker_alert_trend_line_with_long_channel_tag():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sigs = [BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1480.0, 2.7, ts)]
    alert = TickerAlert("ANTM", sigs, priority=3.0, timestamp=ts)
    alert.above_sma50 = True
    alert.long_channel = True
    msg = format_ticker_alert(alert)
    assert "Tren" in msg and "SMA50" in msg and "🏔️" in msg
    # neither trend nor long-channel info -> the whole line is omitted
    bare = TickerAlert("ANTM", sigs, priority=3.0, timestamp=ts)
    assert "Tren" not in format_ticker_alert(bare)


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


def test_format_ticker_alert_trade_plan_normal_breakout():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sigs = [
        BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1480.0, 2.7, ts),
        BreakoutSignal("ANTM", "4H", "wyckoff_range_breakout", 1500.0, 3.4, 1450.0, 2.1, ts),
    ]
    alert = TickerAlert("ANTM", sigs, priority=5.0, timestamp=ts)
    msg = format_ticker_alert(alert)
    # primary = 1D signal (highest timeframe weight): entry=1500, level=1480
    # risk = (1500-1480)/1500*100 = 1.3%; target = 1500 + 2*20 = 1540
    assert "💰 Beli  : ~1.500" in msg
    assert "🛑 Stop  : <1.480 (risiko 1.3%)" in msg
    assert "🎯 Target: 2R ~1.540" in msg


def test_format_ticker_alert_trade_plan_degenerate_level_does_not_crash():
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sigs = [
        BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1550.0, 2.7, ts),
    ]
    alert = TickerAlert("ANTM", sigs, priority=5.0, timestamp=ts)
    msg = format_ticker_alert(alert)
    assert "💰 Beli  : ~1.500" in msg
    assert "🛑" not in msg
    assert "🎯" not in msg


def test_format_daily_digest_ranks_and_lists():
    from news_breakout.alerts.formatter import format_daily_digest
    WIB = ZoneInfo("Asia/Jakarta")
    now = datetime(2026, 7, 20, 16, 30, tzinfo=WIB)

    def alert(tkr, score, price, level):
        sig = BreakoutSignal(ticker=tkr, timeframe="1D", signal_type="resistance_breakout",
                             price=price, pct_change=5.0, level=level, rvol=3.0, timestamp=now)
        a = TickerAlert(ticker=tkr, signals=[sig], priority=3.0, timestamp=now)
        a.quality_score = score
        a.above_sma50 = True
        a.ext_pct = 5.0
        return a

    msg = format_daily_digest([alert("AAA", 9.0, 1000, 950), alert("BBB", 4.0, 500, 490)], now=now)
    assert "Watchlist Pagi" in msg
    assert "1. AAA" in msg and "2. BBB" in msg
    assert "AAA" in msg and "BBB" in msg
    assert "20 Jul 2026" in msg
