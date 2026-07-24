from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import load_settings
from news_breakout.logging_setup import setup_logging
from news_breakout.confluence.engine import run_confluence_cycle
from news_breakout.confluence.store import ConfluenceStore
from news_breakout.confluence.trigger import positive_news_triggers
from news_breakout.data.supabase_source import make_daily_fetcher, make_intraday_fetcher
from news_breakout.news.idx_source import fetch_disclosures
from news_breakout.news.portal import fetch_portal_news
from news_breakout.news.sentiment import classify
from news_breakout.orderbook.auth import StockbitAuth
from news_breakout.scheduling.market_calendar import parse_holidays

WIB = ZoneInfo("Asia/Jakarta")


def _collect_portal_items(settings, *, now):
    """Fetch portal news for the universe and tag positive/negative sentiment on
    titles (no article extraction — the trigger only needs the sentiment sign)."""
    if not settings.portal_enabled:
        return []
    tickers = list(dict.fromkeys(settings.watchlist + settings.universe_candidates))
    items = fetch_portal_news(settings.portal_sources, tickers, settings.portal_name_map,
                              now=now, corp_keywords=settings.curated_keywords,
                              global_proxy=settings.portal_proxy)
    if settings.sentiment_enabled and items:
        labels = classify([it.title for it in items],
                          min_confidence=settings.sentiment_min_confidence)
        if isinstance(labels, list) and len(labels) == len(items):
            for it, lab in zip(items, labels):
                it.sentiment = lab
    return items


def run_once(settings, *, now, store, auth=None) -> list[tuple[str, str]]:
    try:
        disclosures = fetch_disclosures(settings.disclosure_page_size, now=now,
                                        proxy=settings.idx_proxy, retries=0)
    except Exception:  # noqa: BLE001 — a feed hiccup must not abort the cycle
        disclosures = []
    portal_items = _collect_portal_items(settings, now=now)

    trig = positive_news_triggers(portal_items, disclosures, settings.curated_keywords)
    watch_tickers = [w.ticker for w in store.active_watches()]
    symbols = list(dict.fromkeys([t.ticker for t in trig] + watch_tickers))
    daily = make_daily_fetcher(settings)(symbols, settings.history_days) if symbols else {}
    intraday = (make_intraday_fetcher(settings)(symbols, settings.intraday_period_days)
                if symbols else {})

    if auth is None and settings.confluence_require_orderbook and (
            settings.stockbit_refresh_token or settings.stockbit_access_token):
        auth = StockbitAuth(settings.stockbit_refresh_token,
                            access_token=settings.stockbit_access_token)

    return run_confluence_cycle(
        settings, store, now=now, holidays=parse_holidays(settings.holidays),
        portal_items=portal_items, disclosures=disclosures,
        daily_data=daily, intraday_data=intraday, auth=auth)


def main() -> None:
    setup_logging()
    settings = load_settings()
    if not settings.confluence_enabled:
        print("confluence disabled (set confluence.enabled: true)")
        return
    os.makedirs("data_cache", exist_ok=True)
    store = ConfluenceStore("data_cache/confluence.sqlite")
    try:
        sent = run_once(settings, now=datetime.now(WIB), store=store)
        print(f"confluence cycle complete. sent: {sent or 'none'}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
