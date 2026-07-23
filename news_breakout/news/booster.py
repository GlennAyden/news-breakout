from __future__ import annotations

from datetime import timedelta

from news_breakout.news.corp_action import CATEGORY_PRIORITY, classify_corp_action
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


def pick_catalyst(disclosures: list[Disclosure], *, now, window_hours: int) -> dict[str, Disclosure]:
    """Most-material disclosure per ticker within the window (ties/all-routine →
    most recent). Same key set as recent_by_ticker (any ticker with a disclosure
    in the window); only the chosen disclosure differs when a ticker has several."""
    def materiality(d: Disclosure) -> tuple[int, float]:
        cat = classify_corp_action(d.title)
        # lower rank = more material; routine (None) sorts last
        rank = CATEGORY_PRIORITY.index(cat) if cat in CATEGORY_PRIORITY else len(CATEGORY_PRIORITY)
        return (rank, -d.timestamp.timestamp())   # then newest first

    cutoff = now - timedelta(hours=window_hours)
    best: dict[str, Disclosure] = {}
    for d in disclosures:
        if not d.ticker or d.timestamp < cutoff:
            continue
        cur = best.get(d.ticker)
        if cur is None or materiality(d) < materiality(cur):
            best[d.ticker] = d
    return best
