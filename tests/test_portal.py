from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
from news_breakout.news.portal import PortalNews, parse_rss, match_ticker, fetch_portal_news
from news_breakout.news.formatter import format_portal
from news_breakout.news.feed import run_portal_feed

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=WIB)

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Kontan</title>
<item>
<title>Barito Pacific catat kinerja positif</title>
<link>https://www.kontan.co.id/news/barito-pacific-1</link>
<pubDate>Fri, 17 Jul 2026 15:00:00 +0700</pubDate>
</item>
<item>
<title>ANTM naik signifikan hari ini</title>
<link>https://www.kontan.co.id/news/antm-naik</link>
<pubDate>Fri, 17 Jul 2026 16:00:00 +0700</pubDate>
</item>
<item>
<title>Berita tidak relevan tentang cuaca</title>
<link>https://www.kontan.co.id/news/cuaca</link>
<pubDate>Fri, 17 Jul 2026 17:00:00 +0700</pubDate>
</item>
</channel>
</rss>
"""


def _settings(**overrides):
    base = dict(
        watchlist=["ANTM", "BRPT"], donchian_lookback=20, rvol_threshold=2.0, rvol_window=20,
        history_days=120, range_lookback=30, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[], universe_candidates=[], min_price=50,
        min_daily_value=1e9, telegram_news_chat_id="-200",
        curated_keywords=["dividen", "akuisisi"], disclosure_page_size=50,
        news_poll_interval_minutes=60, idx_proxy="",
        portal_enabled=False, portal_sources=[], portal_name_map={},
    )
    base.update(overrides)
    return Settings(**base)


# ---- parse_rss -------------------------------------------------------------

def test_parse_rss_yields_title_link_timestamp():
    items = parse_rss(RSS_XML, "kontan.co.id", now=NOW)
    assert len(items) == 3
    first = items[0]
    assert isinstance(first, PortalNews)
    assert first.title == "Barito Pacific catat kinerja positif"
    assert first.url == "https://www.kontan.co.id/news/barito-pacific-1"
    assert first.source == "kontan.co.id"
    assert first.timestamp.hour == 15


def test_parse_rss_malformed_xml_returns_empty():
    assert parse_rss("<not-valid-xml", "kontan.co.id", now=NOW) == []


RSS_DESC = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
<title>Kabar emiten energi sore ini</title>
<link>https://x.example/news/1</link>
<description>PT Barito Pacific Tbk mengumumkan ekspansi &lt;b&gt;besar&lt;/b&gt;.</description>
<pubDate>Fri, 17 Jul 2026 15:00:00 +0700</pubDate>
</item>
</channel></rss>
"""


# ---- A: title + description matching ---------------------------------------

def test_parse_rss_captures_stripped_description():
    items = parse_rss(RSS_DESC, "x.example", now=NOW)
    assert len(items) == 1
    assert "Barito Pacific" in items[0].summary
    assert "<b>" not in items[0].summary and "besar" in items[0].summary


def test_fetch_matches_company_in_description_not_title():
    # title alone has no watchlist mention; the company name is only in the body
    def http_get(url):
        return RSS_DESC

    out = fetch_portal_news(["https://x.example/rss"], ["BRPT"], {"barito pacific": "BRPT"},
                            now=NOW, http_get=http_get)
    assert len(out) == 1 and out[0].ticker == "BRPT"


# ---- B: universe tickers included in matching ------------------------------

def test_run_portal_feed_passes_watchlist_plus_universe_to_fetcher():
    store = DedupStore(":memory:")
    captured = {}

    def fetcher(sources, tickers, name_map, *, now, http_get=None):
        captured["tickers"] = list(tickers)
        return []

    settings = _settings(portal_enabled=True, portal_sources=["x"],
                          watchlist=["ANTM"], universe_candidates=["TLKM", "BBCA"])
    run_portal_feed(settings, store, now=NOW, sender=lambda *a, **k: True, fetcher=fetcher)
    assert captured["tickers"] == ["ANTM", "TLKM", "BBCA"]
    store.close()


# ---- match_ticker -----------------------------------------------------------

def test_match_ticker_by_company_name():
    tk = match_ticker("Barito Pacific catat kinerja positif", ["BRPT", "ANTM"],
                       {"barito pacific": "BRPT"})
    assert tk == "BRPT"


def test_match_ticker_by_whole_word_code():
    tk = match_ticker("ANTM naik signifikan hari ini", ["ANTM", "BRPT"], {})
    assert tk == "ANTM"


def test_match_ticker_no_match_returns_empty():
    tk = match_ticker("Berita tidak relevan tentang cuaca", ["ANTM", "BRPT"], {})
    assert tk == ""


# ---- fetch_portal_news -------------------------------------------------------

def test_fetch_portal_news_keeps_only_ticker_matches_and_skips_failing_source():
    def http_get(url):
        if url == "https://bad.example/rss":
            raise RuntimeError("boom")
        return RSS_XML

    out = fetch_portal_news(
        ["https://bad.example/rss", "https://www.kontan.co.id/rss"],
        ["ANTM", "BRPT"], {"barito pacific": "BRPT"},
        now=NOW, http_get=http_get,
    )
    assert {i.url for i in out} == {
        "https://www.kontan.co.id/news/barito-pacific-1",
        "https://www.kontan.co.id/news/antm-naik",
    }
    tickers = {i.ticker for i in out}
    assert tickers == {"BRPT", "ANTM"}


def test_fetch_portal_news_dict_source_defaults_to_rss_parser():
    def http_get(url):
        return RSS_XML

    out = fetch_portal_news(
        [{"url": "https://www.kontan.co.id/rss"}],
        ["ANTM", "BRPT"], {"barito pacific": "BRPT"},
        now=NOW, http_get=http_get,
    )
    assert {i.url for i in out} == {
        "https://www.kontan.co.id/news/barito-pacific-1",
        "https://www.kontan.co.id/news/antm-naik",
    }


def test_fetch_portal_news_dict_source_dispatches_to_named_parser():
    emiten_html = """
    <a href="https://emitennews.com/news/barito-pacific-catat-kinerja" class="news-card-2 search-result-item">
        <div class="news-card-2-content title-category">
            <p class="fs-16">Barito Pacific catat kinerja positif</p>
            <div class="label"><span class="small">2 jam yang lalu</span></div>
        </div>
    </a>
    """

    def http_get(url):
        assert url == "https://emitennews.com/category/emiten"
        return emiten_html

    out = fetch_portal_news(
        [{"url": "https://emitennews.com/category/emiten", "parser": "emitennews"}],
        ["BRPT"], {"barito pacific": "BRPT"},
        now=NOW, http_get=http_get,
    )
    assert len(out) == 1
    assert out[0].ticker == "BRPT"
    assert out[0].url == "https://emitennews.com/news/barito-pacific-catat-kinerja"
    assert out[0].source == "emitennews.com"


def test_fetch_portal_news_skips_malformed_dict_source_without_url():
    def http_get(url):
        return RSS_XML

    out = fetch_portal_news(
        [{"parser": "rss"}, "https://www.kontan.co.id/rss"],
        ["ANTM", "BRPT"], {"barito pacific": "BRPT"},
        now=NOW, http_get=http_get,
    )
    assert {i.url for i in out} == {
        "https://www.kontan.co.id/news/barito-pacific-1",
        "https://www.kontan.co.id/news/antm-naik",
    }


def test_fetch_portal_news_mixed_string_and_dict_sources():
    def http_get(url):
        return RSS_XML

    out = fetch_portal_news(
        ["https://www.kontan.co.id/rss", {"url": "https://www.kontan.co.id/rss", "parser": "rss"}],
        ["ANTM", "BRPT"], {"barito pacific": "BRPT"},
        now=NOW, http_get=http_get,
    )
    # both sources parsed the same RSS_XML -> 2 matches each = 4 total
    assert len(out) == 4


# ---- format_portal ------------------------------------------------------------

def test_format_portal_contains_key_fields():
    item = PortalNews("BRPT", "Barito Pacific catat kinerja positif",
                       datetime(2026, 7, 17, 15, 0, tzinfo=WIB),
                       "https://www.kontan.co.id/news/barito-pacific-1", "kontan.co.id")
    msg = format_portal(item)
    assert "BRPT" in msg
    assert "kontan.co.id" in msg
    assert "Barito Pacific catat kinerja positif" in msg
    assert "https://www.kontan.co.id/news/barito-pacific-1" in msg
    assert "15:00" in msg


# ---- run_portal_feed ----------------------------------------------------------

def test_run_portal_feed_disabled_returns_empty_and_sends_nothing():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append((chat_id, text))
        return True

    def fetcher(sources, watchlist, name_map, *, now, http_get=None):
        raise AssertionError("fetcher should not be called when portal disabled")

    result = run_portal_feed(_settings(portal_enabled=False), store, now=NOW,
                              sender=sender, fetcher=fetcher)
    assert result == []
    assert sent == []
    store.close()


def test_run_portal_feed_enabled_sends_and_dedups_on_second_run():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append((chat_id, text))
        return True

    def fetcher(sources, watchlist, name_map, *, now, http_get=None):
        return [
            PortalNews("BRPT", "Barito Pacific catat kinerja positif", NOW,
                       "https://www.kontan.co.id/news/barito-pacific-1", "kontan.co.id"),
            PortalNews("ANTM", "ANTM naik signifikan hari ini", NOW,
                       "https://www.kontan.co.id/news/antm-naik", "kontan.co.id"),
        ]

    settings = _settings(portal_enabled=True, portal_sources=["https://www.kontan.co.id/rss"],
                          portal_name_map={"barito pacific": "BRPT"})

    first = run_portal_feed(settings, store, now=NOW, sender=sender, fetcher=fetcher)
    assert len(first) == 2
    assert len(sent) == 2
    assert all(chat_id == "-200" for chat_id, _ in sent)

    second = run_portal_feed(settings, store, now=NOW, sender=sender, fetcher=fetcher)
    assert second == []
    assert len(sent) == 2   # no new sends
    store.close()
