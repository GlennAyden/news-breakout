from __future__ import annotations

import sqlite3


class PhaseStore:
    """Remembers each ticker's last-seen orderbook phase for the trading day so
    the alert can distinguish a genuine A→RM entry from a BM→RM bounce (trap).
    """

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orderbook_phase (
                ticker TEXT NOT NULL,
                date_str TEXT NOT NULL,
                phase TEXT NOT NULL,
                PRIMARY KEY (ticker, date_str)
            )
            """
        )
        self._conn.commit()

    def get_last_phase(self, ticker: str, date_str: str) -> str | None:
        cur = self._conn.execute(
            "SELECT phase FROM orderbook_phase WHERE ticker=? AND date_str=?",
            (ticker, date_str),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def set_phase(self, ticker: str, date_str: str, phase: str) -> None:
        self._conn.execute(
            "INSERT INTO orderbook_phase (ticker, date_str, phase) VALUES (?, ?, ?) "
            "ON CONFLICT(ticker, date_str) DO UPDATE SET phase=excluded.phase",
            (ticker, date_str, phase),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
