import json
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.idx_source import fetch_disclosures

NOW = datetime(2026, 7, 18, 9, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
GOOD = json.dumps({"Replies": [{"pengumuman": {
    "Id2": "x1", "KodeEmiten": "BBRI", "TglPengumuman": "2026-07-17T15:00:00",
    "JudulPengumuman": "Dividen"}}]})
CF_HTML = "<!DOCTYPE html><title>Attention Required! | Cloudflare</title>"


def test_fetch_retries_past_cloudflare_then_parses():
    calls = []

    def http_get(url, proxy):
        calls.append(1)
        return CF_HTML if len(calls) == 1 else GOOD

    out = fetch_disclosures(now=NOW, http_get=http_get, sleeper=lambda s: None)
    assert len(calls) == 2
    assert len(out) == 1 and out[0].ticker == "BBRI"


def test_fetch_gives_up_returns_empty():
    def http_get(url, proxy):
        return CF_HTML

    out = fetch_disclosures(now=NOW, retries=2, http_get=http_get, sleeper=lambda s: None)
    assert out == []


def test_fetch_does_not_crash_on_null_pengumuman():
    out = fetch_disclosures(now=NOW, http_get=lambda u, p: '{"Replies":[{"pengumuman": null}]}',
                            sleeper=lambda s: None)
    assert out == []
