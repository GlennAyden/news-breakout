from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
from news_breakout.news.models import Disclosure
from news_breakout.news.feed import run_news_feed

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


def _disc(i, title):
    return Disclosure("BBRI", title, NOW, i, "url")


def test_news_feed_sends_curated_and_dedups():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append((chat_id, text))
        return True

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return [_disc("a", "Pembagian Dividen"), _disc("b", "Public Expose"),
                _disc("c", "Akuisisi Anak Usaha")]

    first = run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher)
    assert set(first) == {"a", "c"}                 # only curated
    assert len(sent) == 2
    assert all(chat_id == "-200" for chat_id, _ in sent)   # news channel
    second = run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher)
    assert second == []                             # deduped
    assert len(sent) == 2
    store.close()


def test_news_feed_failed_send_not_marked():
    store = DedupStore(":memory:")

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        return False

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return [_disc("a", "Pembagian Dividen")]

    first = run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher)
    assert first == []
    assert store.news_already_sent("a") is False   # failed send -> not marked, retries next poll
    store.close()
