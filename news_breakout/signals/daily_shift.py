from __future__ import annotations

import logging
from pathlib import Path

from news_breakout.data.universe import resolve_scan_tickers
from news_breakout.signals.scan_core import evaluate_scan, scan_once
from news_breakout.alerts.formatter import format_daily_digest
from news_breakout.alerts.telegram import send_message
from news_breakout.news.booster import recent_by_ticker
from news_breakout.news.idx_source import fetch_disclosures

logger = logging.getLogger("news_breakout")


def load_daily_universe(path: str) -> list[str]:
    """Read the broad daily-shift ticker list (one code per line; '#' comments
    and blanks ignored). Uppercased, de-duped, order-preserving. Missing file -> []."""
    p = Path(path)
    if not p.exists():
        logger.warning("daily shift: universe file not found: %s", path)
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().upper()
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def run_daily_scan(settings, store, *, now, mode, daily_fetcher,
                   sender=send_message, disclosure_fetcher=fetch_disclosures) -> list[str]:
    broad = load_daily_universe(settings.daily_shift_universe_file)
    if not broad:
        return []
    daily = daily_fetcher(broad, settings.daily_shift_history_days)
    intraday_set = set(settings.watchlist) | set(settings.universe_candidates)
    liquid = resolve_scan_tickers([], broad, daily,
                                  settings.daily_shift_min_price, settings.daily_shift_min_daily_value)
    daily_tickers = [t for t in liquid if t not in intraday_set]

    try:
        disc = disclosure_fetcher(settings.disclosure_page_size, now=now,
                                  proxy=settings.idx_proxy, retries=0)
    except Exception:  # noqa: BLE001 — a disclosure fetch failure must not abort the scan
        disc = []
    catalysts = recent_by_ticker(disc, now=now, window_hours=settings.news_booster_window_hours)

    if mode == "detect":
        return scan_once(settings, daily, {}, store, now=now, sender=sender,
                         catalysts=catalysts, tickers=daily_tickers,
                         max_alerts=settings.daily_shift_max_alerts)

    # mode == "reminder": recompute the same shortlist, send ONE digest, dedup per day
    alerts = evaluate_scan(settings, daily, {}, now=now, catalysts=catalysts,
                           tickers=daily_tickers)[: settings.daily_shift_max_alerts]
    if not alerts:
        return []
    key = f"daily-digest-{now:%Y-%m-%d}"
    if store.news_already_sent(key):
        return []
    sent = sender(settings.telegram_bot_token, settings.telegram_breakout_chat_id,
                  format_daily_digest(alerts, now=now), dry_run=settings.dry_run)
    if not sent:
        return []                      # not delivered -> report nothing (key stays unmarked -> retry next run)
    store.news_mark_sent(key)
    return [a.ticker for a in alerts]
