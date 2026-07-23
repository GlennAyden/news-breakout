from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.config import Settings, load_settings
from news_breakout.data.yfinance_source import fetch_daily_ohlcv, fetch_intraday_ohlcv
from news_breakout.data.universe import resolve_scan_tickers
from news_breakout.alerts.staleness import check_price_staleness
from news_breakout.alerts.dedup import DedupStore
from news_breakout.alerts.telegram import send_message
from news_breakout.news.idx_source import fetch_disclosures
from news_breakout.news.booster import pick_catalyst
from news_breakout.signals.scan_core import evaluate_scan, scan_once
from news_breakout.orderbook.auth import StockbitAuth
from news_breakout.orderbook.state import PhaseStore
from news_breakout.orderbook.scan import run_orderbook_scan

WIB = ZoneInfo("Asia/Jakarta")
logger = logging.getLogger("news_breakout")


def _maybe_run_orderbook(settings: Settings, daily, store, *, now, sender) -> None:
    """Ready-Markup orderbook pass — a standalone side alert. Gated by config and
    fully isolated: any failure here must never abort the main breakout scan."""
    if not settings.orderbook_enabled:
        return
    phase_store = None
    try:
        auth = StockbitAuth(settings.stockbit_refresh_token,
                            access_token=settings.stockbit_access_token)
        phase_store = PhaseStore("data_cache/orderbook.sqlite")
        alerted = run_orderbook_scan(settings, daily, store, phase_store,
                                     now=now, auth=auth, sender=sender)
        if alerted:
            logger.info("orderbook Ready-Markup alerts: %s", alerted)
    except Exception:  # noqa: BLE001 — the orderbook side alert must never break the scan
        logger.warning("orderbook scan failed", exc_info=True)
    finally:
        if phase_store is not None:
            phase_store.close()


def run_scan(
    settings: Settings, store: DedupStore, *, now, sender=send_message,
    daily_fetcher=fetch_daily_ohlcv, intraday_fetcher=fetch_intraday_ohlcv,
    disclosure_fetcher=fetch_disclosures,
) -> list[str]:
    scan_symbols = list(dict.fromkeys(settings.watchlist + settings.universe_candidates))
    daily = daily_fetcher(scan_symbols, settings.history_days)
    intraday = intraday_fetcher(scan_symbols, settings.intraday_period_days)
    # Staleness heads-up — but only once the session has had time to produce a
    # fresh bar. Before market_open + threshold, the freshest 60m bar is still
    # yesterday's close (a working fetcher hasn't made today's bar yet), so
    # checking then would false-alarm every morning; the threshold (>lunch gap)
    # also tolerates the IDX 12:00–13:30 break.
    _oh, _om = (int(x) for x in settings.market_open.split(":"))
    session_open = now.replace(hour=_oh, minute=_om, second=0, microsecond=0)
    if now - session_open >= timedelta(minutes=settings.price_staleness_max_minutes):
        try:
            warning = check_price_staleness(
                daily, intraday, now,
                max_intraday_age_minutes=settings.price_staleness_max_minutes,
                session_active=True,  # gated above to >=threshold into the session
            )
        except Exception:  # noqa: BLE001 — a staleness check must never abort the scan
            warning = None
        if warning:
            logger.warning("price staleness: %s", warning)  # visible in the journal
            key = f"stale-{now.strftime('%Y-%m-%d')}"
            if not store.news_already_sent(key) and sender(
                settings.telegram_bot_token, settings.telegram_breakout_chat_id,
                warning, dry_run=settings.dry_run,
            ):
                store.news_mark_sent(key)  # one staleness heads-up per trading day
    if not daily and not intraday:
        logger.warning(
            "fetch returned 0 tickers for %d scan symbols — likely rate-limit or data outage",
            len(scan_symbols),
        )
    try:
        disc = disclosure_fetcher(settings.disclosure_page_size, now=now,
                                  proxy=settings.idx_proxy, retries=0)
    except Exception:  # noqa: BLE001
        disc = []
    catalysts = pick_catalyst(disc, now=now, window_hours=settings.news_booster_window_hours)
    scan_tickers = resolve_scan_tickers(
        settings.watchlist, settings.universe_candidates, daily,
        settings.min_price, settings.min_daily_value,
    )
    breakout_alerted = scan_once(settings, daily, intraday, store, now=now, sender=sender,
                                 catalysts=catalysts, tickers=scan_tickers)
    _maybe_run_orderbook(settings, daily, store, now=now, sender=sender)
    return breakout_alerted


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    settings = load_settings()
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")
    try:
        now = datetime.now(WIB)
        alerted = run_scan(settings, store, now=now)
        print(f"Scan complete. Alerted: {alerted or 'none'}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
