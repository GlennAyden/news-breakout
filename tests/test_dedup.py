from news_breakout.alerts.dedup import DedupStore


def test_mark_then_already_sent():
    store = DedupStore(":memory:")
    args = ("ANTM", "resistance_breakout", "1D", "2026-07-17")
    assert store.already_sent(*args) is False
    store.mark_sent(*args)
    assert store.already_sent(*args) is True
    store.close()


def test_different_date_is_not_deduped():
    store = DedupStore(":memory:")
    store.mark_sent("ANTM", "resistance_breakout", "1D", "2026-07-17")
    assert store.already_sent("ANTM", "resistance_breakout", "1D", "2026-07-18") is False
    store.close()


def test_mark_sent_is_idempotent():
    store = DedupStore(":memory:")
    args = ("BREN", "resistance_breakout", "1D", "2026-07-17")
    store.mark_sent(*args)
    store.mark_sent(*args)  # must not raise
    assert store.already_sent(*args) is True
    store.close()
