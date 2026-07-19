from __future__ import annotations

import logging

from news_breakout.news.idx_source import fetch_disclosures
from news_breakout.news.curated import is_price_sensitive
from news_breakout.news.formatter import format_disclosure, format_portal
from news_breakout.news.portal import fetch_portal_news
from news_breakout.alerts.telegram import send_message

logger = logging.getLogger("news_breakout")


def run_news_feed(settings, store, *, now, sender=send_message, fetcher=fetch_disclosures) -> list[str]:
    disclosures = fetcher(settings.disclosure_page_size, now=now, proxy=settings.idx_proxy)
    curated = [d for d in disclosures if is_price_sensitive(d, settings.curated_keywords)]
    curated.sort(key=lambda d: d.timestamp)  # oldest first
    sent_ids: list[str] = []
    for d in curated:
        if store.news_already_sent(d.disclosure_id):
            continue
        if not sender(settings.telegram_bot_token, settings.telegram_news_chat_id,
                      format_disclosure(d), dry_run=settings.dry_run):
            continue
        store.news_mark_sent(d.disclosure_id)
        sent_ids.append(d.disclosure_id)
    logger.info("news feed: %d curated, %d newly sent", len(curated), len(sent_ids))
    return sent_ids


def run_portal_feed(settings, store, *, now, sender=send_message, fetcher=fetch_portal_news) -> list[str]:
    if not settings.portal_enabled:
        return []
    # match against the full universe (watchlist + candidates), not just the watchlist,
    # so market news about any scanned liquid stock gets surfaced too
    tickers = list(dict.fromkeys(settings.watchlist + settings.universe_candidates))
    items = fetcher(settings.portal_sources, tickers, settings.portal_name_map, now=now)
    items.sort(key=lambda i: i.timestamp)
    sent = []
    for it in items:
        if store.news_already_sent(it.url):
            continue
        if not sender(settings.telegram_bot_token, settings.telegram_news_chat_id,
                      format_portal(it), dry_run=settings.dry_run):
            continue
        store.news_mark_sent(it.url)
        sent.append(it.url)
    logger.info("portal feed: %d matched, %d newly sent", len(items), len(sent))
    return sent
