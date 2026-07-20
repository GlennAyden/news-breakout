from datetime import datetime
from zoneinfo import ZoneInfo

from tests.fixtures import make_ohlcv
from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
from news_breakout.signals.scan_core import evaluate_scan, scan_once

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)


def _settings(**over):
    base = dict(
        watchlist=["ANTM"], donchian_lookback=3, rvol_threshold=2.0, rvol_window=3,
        history_days=120, range_lookback=3, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[], universe_candidates=[], min_price=50,
        min_daily_value=1e9, telegram_news_chat_id="-2", curated_keywords=["dividen"],
        disclosure_page_size=50, news_poll_interval_minutes=60, idx_proxy="",
    )
    base.update(over)
    return Settings(**base)


def _breakout(close):
    return make_ohlcv(highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
                      closes=[100, 100, 100, close], volumes=[100, 100, 100, 300])


def test_evaluate_scan_returns_sorted_alerts_without_sending():
    daily = {"HIGHX": _breakout(121), "LOWX": _breakout(111)}
    alerts = evaluate_scan(_settings(), daily, {}, now=NOW, catalysts={},
                           tickers=["LOWX", "HIGHX"])
    assert [a.ticker for a in alerts] == ["HIGHX", "LOWX"]  # higher extension ranks first


def test_scan_once_max_alerts_caps_sends():
    daily = {"A": _breakout(121), "B": _breakout(120), "C": _breakout(119)}
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    out = scan_once(_settings(), daily, {}, store, now=NOW, sender=sender,
                    tickers=["A", "B", "C"], max_alerts=2)
    assert len(out) == 2 and len(sent) == 2
    store.close()
