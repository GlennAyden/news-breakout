from news_breakout.alerts.dedup import DedupStore
from news_breakout.news.portal_dedup import is_duplicate, jaccard, normalize_title


def test_normalize_drops_stopwords_short_tokens_and_punct():
    toks = normalize_title("Laba ANTM naik 20% di kuartal II, ini kata analis")
    assert "yang" not in toks and "di" not in toks and "ini" not in toks
    assert {"laba", "antm", "naik", "kuartal", "analis"} <= toks


def test_jaccard_and_duplicate_threshold():
    a = normalize_title("ANTM bagikan dividen Rp 500 miliar tahun ini")
    b = normalize_title("Dividen ANTM Rp 500 miliar dibagikan")
    assert jaccard(a, b) >= 0.55
    assert is_duplicate(b, [a], 0.55) is True
    c = normalize_title("ANTM ekspansi pabrik feronikel Halmahera")
    assert is_duplicate(c, [a], 0.55) is False


def test_is_duplicate_threshold_zero_disables():
    a = normalize_title("judul sama persis")
    assert is_duplicate(a, [a], 0) is False


def test_store_titles_round_trip_scoped_by_ticker_and_day():
    store = DedupStore(":memory:")
    store.add_title("2026-07-22", "ANTM", "antm dividen miliar")
    store.add_title("2026-07-22", "TINS", "tins laba naik")
    store.add_title("2026-07-21", "ANTM", "antm lama")
    assert store.titles_for_day("2026-07-22", "ANTM") == ["antm dividen miliar"]
    assert store.titles_for_day("2026-07-22", "") == []
    store.close()
