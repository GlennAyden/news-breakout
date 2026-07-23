from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.news.models import Disclosure
from news_breakout.news.booster import recent_by_ticker, pick_catalyst

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 18, 16, 0, tzinfo=WIB)


def _disc(ticker, hours_ago, disclosure_id="1", title="Some disclosure"):
    return Disclosure(
        ticker=ticker,
        title=title,
        timestamp=NOW - timedelta(hours=hours_ago),
        disclosure_id=disclosure_id,
        url="https://example.com",
    )


def test_within_window_kept():
    discs = [_disc("ANTM", 1)]
    result = recent_by_ticker(discs, now=NOW, window_hours=48)
    assert "ANTM" in result
    assert result["ANTM"].disclosure_id == "1"


def test_out_of_window_dropped():
    discs = [_disc("ANTM", 49)]
    result = recent_by_ticker(discs, now=NOW, window_hours=48)
    assert "ANTM" not in result


def test_empty_ticker_dropped():
    discs = [_disc("", 1)]
    result = recent_by_ticker(discs, now=NOW, window_hours=48)
    assert result == {}


def test_keeps_most_recent_when_ticker_has_two():
    older = _disc("ANTM", 10, disclosure_id="old", title="Older")
    newer = _disc("ANTM", 2, disclosure_id="new", title="Newer")
    result = recent_by_ticker([older, newer], now=NOW, window_hours=48)
    assert result["ANTM"].disclosure_id == "new"

    result2 = recent_by_ticker([newer, older], now=NOW, window_hours=48)
    assert result2["ANTM"].disclosure_id == "new"


def test_pick_catalyst_prefers_material_over_more_recent_routine():
    routine = _disc("ANTM", 1, disclosure_id="routine",
                    title="Laporan Bulanan Registrasi Pemegang Efek")   # newer
    material = _disc("ANTM", 5, disclosure_id="rights",
                     title="Jadwal rights issue ANTM")                  # older but material
    result = pick_catalyst([routine, material], now=NOW, window_hours=48)
    assert result["ANTM"].disclosure_id == "rights"


def test_pick_catalyst_falls_back_to_most_recent_when_all_routine():
    older = _disc("ANTM", 10, disclosure_id="old", title="Penyampaian Bukti Iklan")
    newer = _disc("ANTM", 2, disclosure_id="new", title="Laporan Bulanan Registrasi")
    result = pick_catalyst([older, newer], now=NOW, window_hours=48)
    assert result["ANTM"].disclosure_id == "new"


def test_pick_catalyst_same_keyset_as_recent_by_ticker():
    discs = [_disc("ANTM", 1, title="Rights issue"),
             _disc("BBRI", 2, title="Laporan Bulanan"),
             _disc("TINS", 60, title="Dividen")]   # out of window
    assert set(pick_catalyst(discs, now=NOW, window_hours=48)) == \
           set(recent_by_ticker(discs, now=NOW, window_hours=48))
