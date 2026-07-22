from __future__ import annotations

import logging

from news_breakout.news.idx_source import fetch_disclosures
from news_breakout.news.curated import is_price_sensitive
from news_breakout.news.formatter import format_disclosure, format_portal
from news_breakout.news.portal import fetch_portal_news
from news_breakout.news.portal_dedup import is_duplicate, normalize_title
from news_breakout.alerts.telegram import send_message

logger = logging.getLogger("news_breakout")


def run_news_feed(settings, store, *, now, sender=send_message, fetcher=fetch_disclosures,
                  failure_streak=0) -> list[str]:
    disclosures = fetcher(settings.disclosure_page_size, now=now, proxy=settings.idx_proxy)
    streak = failure_streak() if callable(failure_streak) else failure_streak
    if streak >= settings.news_outage_max_failures:
        key = f"news-outage-{now:%Y-%m-%d}"
        if not store.news_already_sent(key):
            warn = (f"⚠️ Feed keterbukaan IDX gagal {streak} kali beruntun — "
                    "Cloudflare/proxy bermasalah?")
            if sender(settings.telegram_bot_token, settings.telegram_news_chat_id,
                      warn, dry_run=settings.dry_run):
                store.news_mark_sent(key)   # one outage heads-up per day
    watchset = set(settings.watchlist) if settings.news_watchlist_passthrough else set()
    curated = [d for d in disclosures
               if is_price_sensitive(d, settings.curated_keywords) or d.ticker in watchset]
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


def run_portal_feed(settings, store, *, now, sender=send_message, fetcher=fetch_portal_news,
                    extractor=None, classifier=None) -> list[str]:
    if not settings.portal_enabled:
        return []
    from news_breakout.news.extract import fetch_article_text, lead_summary, strip_leading_title
    from news_breakout.news.portal import _default_http_get
    from news_breakout.news.sentiment import classify as _classify

    if extractor is None:
        def extractor(url):
            return fetch_article_text(url, http_get=_default_http_get)
    if classifier is None:
        classifier = _classify

    # match against the full universe (watchlist + candidates), not just the watchlist,
    # so market news about any scanned liquid stock gets surfaced too
    tickers = list(dict.fromkeys(settings.watchlist + settings.universe_candidates))
    items = fetcher(settings.portal_sources, tickers, settings.portal_name_map, now=now,
                    corp_keywords=settings.curated_keywords)

    # drop already-sent items before the expensive per-item fetch/classify stages below
    items = [it for it in items if not store.news_already_sent(it.url)]

    # extractive summary from the full article body (fall back to the RSS description)
    for it in items:
        try:
            body = extractor(it.url)
        except Exception:  # noqa: BLE001 — a fetch failure must not drop the item
            body = ""
        body = strip_leading_title(body, it.title)  # avoid echoing the hyperlinked headline
        it.lead = lead_summary(body or it.summary, settings.portal_summary_sentences)

    # optional sentiment tag; any failure degrades to no tag, news still flows
    if settings.sentiment_enabled and items:
        try:
            labels = classifier([it.lead or it.title for it in items],
                                min_confidence=settings.sentiment_min_confidence)
            if not isinstance(labels, list) or len(labels) != len(items):
                labels = [""] * len(items)
        except Exception:  # noqa: BLE001
            labels = [""] * len(items)
        for it, lab in zip(items, labels):
            it.sentiment = lab

    # corporate actions first, then strong sentiment, then oldest -> newest
    strong = {"positif": 0, "negatif": 0}
    items.sort(key=lambda i: (not i.corp_action, strong.get(i.sentiment, 1), i.timestamp))

    day = f"{now:%Y-%m-%d}"
    threshold = settings.portal_dup_title_threshold
    seen_by_ticker: dict[str, list[set[str]]] = {}

    def _seen(ticker: str) -> list[set[str]]:
        if ticker not in seen_by_ticker:
            seen_by_ticker[ticker] = [set(t.split())
                                      for t in store.titles_for_day(day, ticker)]
        return seen_by_ticker[ticker]

    sent = []
    for it in items:
        if len(sent) >= settings.portal_max_per_run:
            break
        if store.news_already_sent(it.url):
            continue
        tokens = normalize_title(it.title)
        if is_duplicate(tokens, _seen(it.ticker), threshold):
            store.news_mark_sent(it.url)   # suppressed near-dup must not resurface
            logger.info("portal near-dup suppressed: %s", it.title)
            continue
        if not sender(settings.telegram_bot_token, settings.telegram_news_chat_id,
                      format_portal(it), dry_run=settings.dry_run,
                      parse_mode="HTML", disable_preview=True):
            continue
        store.news_mark_sent(it.url)
        store.add_title(day, it.ticker, " ".join(sorted(tokens)))
        _seen(it.ticker).append(tokens)
        sent.append(it.url)
    logger.info("portal feed: %d matched, %d newly sent", len(items), len(sent))
    return sent
