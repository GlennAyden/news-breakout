import sqlite3
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.alerts.dedup import DedupStore

NOW = datetime(2026, 7, 22, tzinfo=ZoneInfo("Asia/Jakarta"))


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


def test_dedup_store_usable_across_threads(tmp_path):
    # Reproduces the serve.py pattern: store created in the main thread,
    # used from an APScheduler worker thread. Must not raise.
    db = str(tmp_path / "dedup.sqlite")
    store = DedupStore(db)
    args = ("ANTM", "aggregated", "MULTI", "2026-07-18")
    errors = []

    def worker():
        try:
            assert store.already_sent(*args) is False
            store.mark_sent(*args)
            assert store.already_sent(*args) is True
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert errors == []
    store.close()


def test_sent_at_migration_on_legacy_db(tmp_path):
    db = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sent_news (disclosure_id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO sent_news VALUES ('old')")
    conn.commit()
    conn.close()
    store = DedupStore(str(db))                    # must not raise
    assert store.news_already_sent("old")
    store.news_mark_sent("new", sent_at="2026-07-22")
    store.prune_news(90, now=NOW)
    assert store.news_already_sent("old")          # NULL sent_at is never pruned
    store.close()


def test_prune_news_drops_old_rows_and_titles():
    store = DedupStore(":memory:")
    store.news_mark_sent("old", sent_at="2026-01-01")
    store.news_mark_sent("fresh", sent_at="2026-07-20")
    store.add_title("2026-01-01", "ANTM", "tua")
    store.add_title("2026-07-20", "ANTM", "baru")
    store.prune_news(90, now=NOW)
    assert store.news_already_sent("old") is False
    assert store.news_already_sent("fresh") is True
    assert store.titles_for_day("2026-01-01", "ANTM") == []
    assert store.titles_for_day("2026-07-20", "ANTM") == ["baru"]
    store.close()
