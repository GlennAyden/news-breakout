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
        self._conn.commit()

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

    def close(self) -> None:
        self._conn.close()
