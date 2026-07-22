from __future__ import annotations

import re

from news_breakout.news.models import Disclosure


def keyword_match(text: str, keywords: list[str]) -> bool:
    """Word-boundary keyword match, tolerating the Indonesian ``-nya`` enclitic.

    ``kontrak`` must NOT hit ``kontraktor``, but ``dividen`` must still hit
    ``dividennya``. Uses lookarounds instead of ``\\b`` because ``\\b`` never
    matches between two non-word chars — a keyword like ``(unaudited)`` would
    silently stop matching with plain word boundaries.
    """
    low = (text or "").lower()
    for kw in keywords:
        kw = kw.strip().lower()
        if kw and re.search(rf"(?<!\w){re.escape(kw)}(?:nya)?(?!\w)", low):
            return True
    return False


def is_price_sensitive(disclosure: Disclosure, keywords: list[str]) -> bool:
    return keyword_match(disclosure.title, keywords)
