from __future__ import annotations

from datetime import timedelta

from news_breakout.news.models import Disclosure


def recent_by_ticker(disclosures: list[Disclosure], *, now, window_hours: int) -> dict[str, Disclosure]:
    """Most-recent disclosure per ticker within the last window_hours (empty-ticker skipped)."""
    cutoff = now - timedelta(hours=window_hours)
    best: dict[str, Disclosure] = {}
    for d in disclosures:
        if not d.ticker or d.timestamp < cutoff:
            continue
        cur = best.get(d.ticker)
        if cur is None or d.timestamp > cur.timestamp:
            best[d.ticker] = d
    return best
