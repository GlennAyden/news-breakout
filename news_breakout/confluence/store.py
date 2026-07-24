from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass
class Watch:
    ticker: str
    news_ts: str
    catalyst_text: str
    source: str
    stage_alerted: str          # "none" | "2of3" | "3of3"
    expires_at: str
    breakout_at: str | None = None
    breakout_payload: str | None = None   # JSON string
    orderbook_at: str | None = None


class ConfluenceStore:
    """One active watch row per ticker; ``stage_alerted`` is the staged-alert
    dedup, ``expires_at`` (ISO) bounds table growth via ``prune_expired``."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS confluence_watch (
                ticker TEXT PRIMARY KEY,
                news_ts TEXT NOT NULL,
                catalyst_text TEXT NOT NULL,
                source TEXT NOT NULL,
                breakout_at TEXT,
                breakout_payload TEXT,
                orderbook_at TEXT,
                stage_alerted TEXT NOT NULL DEFAULT 'none',
                expires_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def upsert_watch(self, ticker: str, *, news_ts: str, catalyst_text: str,
                     source: str, expires_at: str) -> None:
        """Insert a new watch, or refresh catalyst/expiry of an existing one
        WITHOUT resetting its stage (a re-triggered symbol keeps its progress)."""
        self._conn.execute(
            """
            INSERT INTO confluence_watch (ticker, news_ts, catalyst_text, source, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                news_ts=excluded.news_ts,
                catalyst_text=excluded.catalyst_text,
                source=excluded.source,
                expires_at=excluded.expires_at
            """,
            (ticker, news_ts, catalyst_text, source, expires_at),
        )
        self._conn.commit()

    def active_watches(self, *, stage: str | None = None) -> list[Watch]:
        if stage is None:
            cur = self._conn.execute("SELECT * FROM confluence_watch")
        else:
            cur = self._conn.execute(
                "SELECT * FROM confluence_watch WHERE stage_alerted=?", (stage,))
        return [self._row(r) for r in cur.fetchall()]

    def get(self, ticker: str) -> Watch | None:
        cur = self._conn.execute(
            "SELECT * FROM confluence_watch WHERE ticker=?", (ticker,))
        r = cur.fetchone()
        return self._row(r) if r else None

    def mark_breakout(self, ticker: str, *, at: str, payload: dict) -> None:
        self._conn.execute(
            "UPDATE confluence_watch SET breakout_at=?, breakout_payload=? WHERE ticker=?",
            (at, json.dumps(payload), ticker),
        )
        self._conn.commit()

    def mark_orderbook(self, ticker: str, *, at: str) -> None:
        self._conn.execute(
            "UPDATE confluence_watch SET orderbook_at=? WHERE ticker=?", (at, ticker))
        self._conn.commit()

    def mark_stage_alerted(self, ticker: str, stage: str) -> None:
        self._conn.execute(
            "UPDATE confluence_watch SET stage_alerted=? WHERE ticker=?", (stage, ticker))
        self._conn.commit()

    def prune_expired(self, *, now_iso: str) -> list[str]:
        cur = self._conn.execute(
            "SELECT ticker FROM confluence_watch WHERE expires_at <= ?", (now_iso,))
        expired = [r[0] for r in cur.fetchall()]
        if expired:
            self._conn.execute(
                "DELETE FROM confluence_watch WHERE expires_at <= ?", (now_iso,))
            self._conn.commit()
        return expired

    @staticmethod
    def _row(r: sqlite3.Row) -> Watch:
        return Watch(
            ticker=r["ticker"], news_ts=r["news_ts"], catalyst_text=r["catalyst_text"],
            source=r["source"], stage_alerted=r["stage_alerted"], expires_at=r["expires_at"],
            breakout_at=r["breakout_at"], breakout_payload=r["breakout_payload"],
            orderbook_at=r["orderbook_at"],
        )

    def close(self) -> None:
        self._conn.close()
