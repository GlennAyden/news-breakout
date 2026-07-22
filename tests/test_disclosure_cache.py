from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.news.disclosure_cache import DisclosureCache
from news_breakout.news.models import Disclosure

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 22, 9, 0, tzinfo=WIB)


def _disc(i):
    return Disclosure("ANTM", f"t{i}", NOW, str(i), "url")


def test_fetch_uses_canonical_page_size_and_caches_within_ttl():
    calls = []

    def fetcher(page_size, *, now, proxy="", retries=3, **_):
        calls.append((page_size, retries))
        return [_disc(1)], True

    cache = DisclosureCache(200, 10, fetcher=fetcher)
    a = cache.fetch(50, now=NOW, proxy="p")            # caller size ignored
    b = cache.fetch(50, now=NOW + timedelta(minutes=9))  # within TTL -> no refetch
    assert a == b == [_disc(1)]
    assert calls == [(200, 3)]                          # one fetch, canonical size


def test_ttl_expiry_refetches_and_retries_forwarded():
    calls = []

    def fetcher(page_size, *, now, proxy="", retries=3, **_):
        calls.append(retries)
        return [_disc(len(calls))], True

    cache = DisclosureCache(200, 10, fetcher=fetcher)
    cache.fetch(50, now=NOW)
    cache.fetch(50, now=NOW + timedelta(minutes=11), retries=0)
    assert calls == [3, 0]   # default forwarded as fetcher default, explicit 0 forwarded


def test_stale_while_error_and_failure_counter():
    state = {"ok": True}

    def fetcher(page_size, *, now, proxy="", retries=3, **_):
        return ([_disc(1)], True) if state["ok"] else ([], False)

    cache = DisclosureCache(200, 10, fetcher=fetcher)
    good = cache.fetch(50, now=NOW)
    state["ok"] = False
    stale = cache.fetch(50, now=NOW + timedelta(minutes=20))
    assert stale == good                       # last good result served
    assert cache.consecutive_failures == 1
    cache.fetch(50, now=NOW + timedelta(minutes=40))
    assert cache.consecutive_failures == 2
    state["ok"] = True
    fresh = cache.fetch(50, now=NOW + timedelta(minutes=60))
    assert fresh == good
    assert cache.consecutive_failures == 0     # success resets the streak


def test_failed_fetch_does_not_extend_ttl():
    calls = []

    def fetcher(page_size, *, now, proxy="", retries=3, **_):
        calls.append(now)
        return [], False

    cache = DisclosureCache(200, 10, fetcher=fetcher)
    cache.fetch(50, now=NOW)
    cache.fetch(50, now=NOW + timedelta(minutes=1))   # still retries: no good cache yet
    assert len(calls) == 2
