from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.models import Disclosure
from news_breakout.news.curated import is_price_sensitive, keyword_match

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


def test_keyword_match_word_boundary_rejects_prefix_extension():
    assert keyword_match("Proyek kontraktor tambang", ["kontrak"]) is False


def test_keyword_match_accepts_exact_and_nya_enclitic():
    assert keyword_match("Pembagian dividen final", ["dividen"]) is True
    assert keyword_match("Besaran dividennya naik", ["dividen"]) is True


def test_keyword_match_multiword_and_case_insensitive():
    assert keyword_match("Jadwal RIGHTS ISSUE emiten", ["rights issue"]) is True
    assert keyword_match("Right issue saja", ["rights issue"]) is False


def test_keyword_match_regex_metachars_are_literal():
    assert keyword_match("laba (unaudited) naik", ["(unaudited)"]) is True
