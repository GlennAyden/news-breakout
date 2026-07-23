from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
from news_breakout.news.portal import PortalNews
from news_breakout.news.feed import run_portal_feed

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=WIB)


def _settings():
    return Settings(
        watchlist=["ANTM"], donchian_lookback=20, rvol_threshold=2.0, rvol_window=20,
        history_days=120, range_lookback=30, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[], universe_candidates=[], min_price=50,
        min_daily_value=1e9, telegram_news_chat_id="-200",
        curated_keywords=["dividen", "akuisisi"], disclosure_page_size=50,
        news_poll_interval_minutes=60, idx_proxy="",
    )


def test_news_dedup_roundtrip():
    store = DedupStore(":memory:")
    assert store.news_already_sent("d1") is False
    store.news_mark_sent("d1")
    assert store.news_already_sent("d1") is True
    store.news_mark_sent("d1")  # idempotent
    assert store.news_already_sent("d2") is False
    store.close()


def _item(url, title, ticker="ANTM"):
    return PortalNews(ticker, title, NOW, url, "src", summary="s")


def test_cross_portal_near_dup_suppressed_same_ticker_only():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot, chat, text, *, dry_run, client=None, parse_mode=None, disable_preview=False):
        sent.append(text)
        return True

    items = [
        _item("u1", "ANTM bagikan dividen Rp 500 miliar tahun ini"),
        _item("u2", "Dividen ANTM Rp 500 miliar dibagikan"),           # near-dup of u1
        _item("u3", "Laba TINS naik 500 miliar dibagikan", ticker="TINS"),  # other ticker: kept
    ]
    s = _settings().model_copy(update={"portal_enabled": True, "sentiment_enabled": False, "portal_dup_title_threshold": 0.55})
    urls = run_portal_feed(s, store, now=NOW, sender=sender,
                           fetcher=lambda *a, **k: items,
                           extractor=lambda url: "", classifier=None)
    assert "u1" in urls and "u3" in urls
    assert "u2" not in urls
    assert store.news_already_sent("u2")     # suppressed, never resurfaces
    assert len(sent) == 2
    store.close()


def test_near_dup_suppressed_across_runs_same_day():
    store = DedupStore(":memory:")
    s = _settings().model_copy(update={"portal_enabled": True, "sentiment_enabled": False, "portal_dup_title_threshold": 0.55})
    kw = dict(sender=lambda *a, **k: True, extractor=lambda url: "", classifier=None)
    run_portal_feed(s, store, now=NOW,
                    fetcher=lambda *a, **k: [_item("u1", "ANTM bagikan dividen Rp 500 miliar tahun ini")], **kw)
    urls = run_portal_feed(s, store, now=NOW,
                           fetcher=lambda *a, **k: [_item("u9", "Dividen ANTM Rp 500 miliar dibagikan")], **kw)
    assert urls == []
    store.close()
