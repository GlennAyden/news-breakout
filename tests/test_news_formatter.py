from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.models import Disclosure
from news_breakout.news.formatter import format_disclosure


def test_format_contains_ticker_title_time():
    d = Disclosure("BBRI", "Pembagian Dividen Tunai",
                   datetime(2026, 7, 17, 15, 0, tzinfo=ZoneInfo("Asia/Jakarta")),
                   "id1", "https://www.idx.co.id/en/listed-companies/disclosure/")
    msg = format_disclosure(d)
    assert "BBRI" in msg
    assert "Pembagian Dividen Tunai" in msg
    assert "15:00" in msg
    assert "IDX" in msg


def test_format_blank_ticker_falls_back():
    d = Disclosure("", "Fakta Material",
                   datetime(2026, 7, 17, 15, 0, tzinfo=ZoneInfo("Asia/Jakarta")), "id2", "url")
    assert "IDX" in format_disclosure(d)
