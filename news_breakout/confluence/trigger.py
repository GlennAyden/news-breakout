from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from news_breakout.news.corp_action import CAUTION_LINES, classify_corp_action
from news_breakout.news.curated import is_price_sensitive
from news_breakout.news.models import Disclosure
from news_breakout.news.portal import PortalNews

# Corp-action categories the project treats as fade/dilution risk (they carry an
# advisory caution line). A disclosure classified into any of these must NOT
# start a long watch. Buyback and non-corp-action price-sensitive news pass.
CAUTION_CATEGORIES = frozenset(CAUTION_LINES)  # rights_issue, private_placement, akuisisi, dividen


@dataclass
class Trigger:
    ticker: str
    source: str      # "portal" | "disclosure"
    headline: str
    ts: datetime


def positive_news_triggers(
    portal_items: list[PortalNews],
    disclosures: list[Disclosure],
    curated_keywords: list[str],
) -> list[Trigger]:
    """Long-bias trigger set, de-duplicated per ticker (portal precedence)."""
    out: dict[str, Trigger] = {}
    for it in portal_items:
        if it.ticker and it.sentiment == "positif" and it.ticker not in out:
            out[it.ticker] = Trigger(it.ticker, "portal", it.title, it.timestamp)
    for d in disclosures:
        if not d.ticker or d.ticker in out:
            continue
        if not is_price_sensitive(d, curated_keywords):
            continue
        if classify_corp_action(d.title) in CAUTION_CATEGORIES:
            continue
        out[d.ticker] = Trigger(d.ticker, "disclosure", d.title, d.timestamp)
    return list(out.values())
