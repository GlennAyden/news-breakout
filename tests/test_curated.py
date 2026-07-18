from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.models import Disclosure
from news_breakout.news.curated import is_price_sensitive

TS = datetime(2026, 7, 18, 9, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
KW = ["dividen", "buyback", "akuisisi", "fakta material"]


def _d(title):
    return Disclosure("BBRI", title, TS, "id1", "url")


def test_matches_curated_keyword_case_insensitive():
    assert is_price_sensitive(_d("Pembagian DIVIDEN Tunai"), KW) is True
    assert is_price_sensitive(_d("Laporan Fakta Material Akuisisi"), KW) is True


def test_rejects_non_curated():
    assert is_price_sensitive(_d("Perubahan Jadwal Public Expose"), KW) is False
    assert is_price_sensitive(_d(""), KW) is False
