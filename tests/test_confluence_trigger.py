from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.models import Disclosure
from news_breakout.news.portal import PortalNews
from news_breakout.confluence.trigger import positive_news_triggers

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 24, 10, 0, tzinfo=WIB)
KW = ["kontrak", "buyback", "ekspansi"]


def _portal(ticker, sentiment):
    return PortalNews(ticker=ticker, title=f"{ticker} berita", timestamp=NOW,
                      url="u", source="s", sentiment=sentiment)


def _disc(ticker, title):
    return Disclosure(ticker=ticker, title=title, timestamp=NOW,
                      disclosure_id=f"{ticker}-1", url="u")


def test_positive_portal_triggers_negative_and_neutral_do_not():
    items = [_portal("AAAA", "positif"), _portal("BBBB", "negatif"),
             _portal("CCCC", "netral"), _portal("DDDD", "")]
    trig = {t.ticker for t in positive_news_triggers(items, [], KW)}
    assert trig == {"AAAA"}


def test_price_sensitive_non_caution_disclosure_triggers():
    trig = positive_news_triggers([], [_disc("EEEE", "Kontrak baru senilai Rp2T")], KW)
    assert [t.ticker for t in trig] == ["EEEE"]
    assert trig[0].source == "disclosure"


def test_buyback_disclosure_triggers_but_rights_issue_does_not():
    discs = [_disc("FFFF", "Rencana buyback saham"),        # non-caution corp action
             _disc("GGGG", "Pelaksanaan Rights Issue / HMETD")]  # caution → excluded
    trig = {t.ticker for t in positive_news_triggers([], discs, KW)}
    assert trig == {"FFFF"}


def test_non_price_sensitive_disclosure_does_not_trigger():
    trig = positive_news_triggers([], [_disc("HHHH", "Laporan bulanan rutin")], KW)
    assert trig == []


def test_dedup_prefers_portal_source():
    items = [_portal("IIII", "positif")]
    discs = [_disc("IIII", "Kontrak baru")]
    trig = positive_news_triggers(items, discs, KW)
    assert len(trig) == 1 and trig[0].source == "portal"


def test_empty_ticker_skipped():
    assert positive_news_triggers([_portal("", "positif")],
                                  [_disc("", "Kontrak baru")], KW) == []
