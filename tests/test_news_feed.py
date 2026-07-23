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


def test_watchlist_disclosure_bypasses_keyword_gate():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return [Disclosure("ANTM", "Public Expose", NOW, "w1", "url"),   # watchlist, no keyword
                Disclosure("BBRI", "Public Expose", NOW, "n1", "url")]   # neither

    ids = run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher)
    assert ids == ["w1"]
    store.close()


def test_watchlist_passthrough_disabled_keeps_keyword_gate():
    store = DedupStore(":memory:")
    s = _settings().model_copy(update={"news_watchlist_passthrough": False})

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return [Disclosure("ANTM", "Public Expose", NOW, "w1", "url")]

    ids = run_news_feed(s, store, now=NOW,
                        sender=lambda *a, **k: True, fetcher=fetcher)
    assert ids == []
    store.close()


def test_outage_warning_sent_once_per_day_at_threshold():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return []

    for _ in range(2):
        run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher,
                      failure_streak=4)
    warnings = [t for t in sent if "gagal 4 kali" in t]
    assert len(warnings) == 1                      # once/day dedup
    assert store.news_already_sent("news-outage-2026-07-18")
    store.close()


def test_outage_warning_below_threshold_and_callable_streak():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return []

    run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher,
                  failure_streak=3)
    assert sent == []                              # below default threshold 4
    run_news_feed(_settings(), store, now=NOW, sender=sender, fetcher=fetcher,
                  failure_streak=lambda: 5)        # callable form
    assert any("gagal 5 kali" in t for t in sent)
    store.close()


from news_breakout.news.feed import _extract_leads


class _Item:
    def __init__(self, url):
        self.url = url


def test_extract_leads_preserves_order_and_degrades():
    items = [_Item("a"), _Item("boom"), _Item("c")]

    def extractor(url):
        if url == "boom":
            raise RuntimeError("net down")
        return f"body-{url}"

    for workers in (1, 4):
        assert _extract_leads(items, extractor, workers) == ["body-a", "", "body-c"]


def test_sends_are_spaced_but_not_before_first():
    store = DedupStore(":memory:")
    sleeps = []

    def fetcher(page_size, *, now, proxy="", retries=3, http_get=None, sleeper=None):
        return [_disc("a", "Pembagian Dividen"), _disc("b", "Rencana Akuisisi"),
                _disc("c", "Dividen Interim")]

    run_news_feed(_settings(), store, now=NOW, sender=lambda *a, **k: True,
                  fetcher=fetcher, sleeper=sleeps.append)
    assert sleeps == [1.05, 1.05]   # 3 sends -> 2 gaps
    store.close()
