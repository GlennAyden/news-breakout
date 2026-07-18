from __future__ import annotations

from news_breakout.news.models import Disclosure


def is_price_sensitive(disclosure: Disclosure, keywords: list[str]) -> bool:
    title = disclosure.title.lower()
    return any(kw.lower() in title for kw in keywords)
