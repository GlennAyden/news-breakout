from __future__ import annotations

import sqlite3


class DedupStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_alerts (
                ticker TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                date_str TEXT NOT NULL,
                PRIMARY KEY (ticker, signal_type, timeframe, date_str)
            )
            """
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sent_news (disclosure_id TEXT PRIMARY KEY)"
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_news_titles (
                date_str TEXT NOT NULL,
                ticker TEXT NOT NULL,
                title_norm TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        # Additive migration for pre-existing VPS databases
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(sent_news)")]
        if "sent_at" not in cols:
            self._conn.execute("ALTER TABLE sent_news ADD COLUMN sent_at TEXT")

    def already_sent(
        self, ticker: str, signal_type: str, timeframe: str, date_str: str
    ) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM sent_alerts WHERE ticker=? AND signal_type=? "
            "AND timeframe=? AND date_str=?",
            (ticker, signal_type, timeframe, date_str),
        )
        return cur.fetchone() is not None

    def mark_sent(
        self, ticker: str, signal_type: str, timeframe: str, date_str: str
    ) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO sent_alerts VALUES (?, ?, ?, ?)",
            (ticker, signal_type, timeframe, date_str),
        )
        self._conn.commit()

    def news_already_sent(self, disclosure_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM sent_news WHERE disclosure_id=?", (disclosure_id,)
        )
        return cur.fetchone() is not None

    def news_mark_sent(self, disclosure_id: str, *, sent_at: str | None = None) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO sent_news (disclosure_id, sent_at) VALUES (?, ?)",
            (disclosure_id, sent_at),
        )
        self._conn.commit()

    def add_title(self, date_str: str, ticker: str, title_norm: str) -> None:
        self._conn.execute(
            "INSERT INTO sent_news_titles VALUES (?, ?, ?)", (date_str, ticker, title_norm)
        )
        self._conn.commit()

    def titles_for_day(self, date_str: str, ticker: str) -> list[str]:
        cur = self._conn.execute(
            "SELECT title_norm FROM sent_news_titles WHERE date_str=? AND ticker=?",
            (date_str, ticker),
        )
        return [r[0] for r in cur.fetchall()]

    def prune_news(self, older_than_days: int, *, now) -> None:
        from datetime import timedelta

        cutoff = (now - timedelta(days=older_than_days)).strftime("%Y-%m-%d")
        self._conn.execute(
            "DELETE FROM sent_news WHERE sent_at IS NOT NULL AND sent_at < ?", (cutoff,)
        )
        self._conn.execute("DELETE FROM sent_news_titles WHERE date_str < ?", (cutoff,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
