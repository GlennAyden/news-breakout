from news_breakout.alerts.dedup import DedupStore


def test_news_dedup_roundtrip():
    store = DedupStore(":memory:")
    assert store.news_already_sent("d1") is False
    store.news_mark_sent("d1")
    assert store.news_already_sent("d1") is True
    store.news_mark_sent("d1")  # idempotent
    assert store.news_already_sent("d2") is False
    store.close()
