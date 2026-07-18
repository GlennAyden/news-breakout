from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.scheduling.weekend import build_weekend_summary, run_weekend_scan
from news_breakout.config import Settings
from tests.fixtures import make_ohlcv

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


def _weekend_settings():
    return Settings(
        watchlist=["ANTM"], donchian_lookback=3, rvol_threshold=2.0, rvol_window=3,
        history_days=120, range_lookback=3, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[], universe_candidates=[],
        min_price=50, min_daily_value=1_000_000_000,
        telegram_news_chat_id="-200", curated_keywords=["dividen"],
        disclosure_page_size=50, news_poll_interval_minutes=60, idx_proxy="",
    )


def test_run_weekend_scan_scans_watchlist_and_sends():
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = {"ANTM": make_ohlcv(
        highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
        closes=[100, 100, 100, 115], volumes=[100, 100, 100, 300])}
    summary = run_weekend_scan(_weekend_settings(), now=TS, sender=sender,
                               daily_fetcher=lambda tickers, days: daily)
    assert len(sent) == 1
    assert "ANTM" in summary
