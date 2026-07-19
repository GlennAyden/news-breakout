from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.config import Settings, load_settings
from news_breakout.data.yfinance_source import fetch_daily_ohlcv, fetch_intraday_ohlcv
from news_breakout.data.resample import resample_ohlcv
from news_breakout.data.universe import resolve_scan_tickers
from news_breakout.alerts.staleness import check_price_staleness
from news_breakout.signals.engine import evaluate_ticker
from news_breakout.alerts.dedup import DedupStore
from news_breakout.alerts.formatter import format_ticker_alert
from news_breakout.alerts.telegram import send_message
from news_breakout.news.idx_source import fetch_disclosures
from news_breakout.news.booster import recent_by_ticker

WIB = ZoneInfo("Asia/Jakarta")
logger = logging.getLogger("news_breakout")


def scan_once(settings: Settings, daily_data, intraday_data, store: DedupStore,
              *, now, sender=send_message, catalysts=None, tickers=None) -> list[str]:
    if catalysts is None:
        catalysts = {}
    scan_list = settings.watchlist if tickers is None else tickers
    alerts = []
    for ticker in scan_list:
        frames = {}
        if ticker in daily_data:
            frames["1D"] = daily_data[ticker]
        if ticker in intraday_data:
            frames["1H"] = intraday_data[ticker]
            frames["4H"] = resample_ohlcv(intraday_data[ticker], "4h")
        if not frames:
            continue
        alert = evaluate_ticker(
            ticker, frames,
            donchian_lookback=settings.donchian_lookback, rvol_window=settings.rvol_window,
            rvol_threshold=settings.rvol_threshold, now=now,
        )
        if alert is not None:
            if alert.ticker in catalysts:
                alert.priority += settings.news_priority_boost
            alerts.append(alert)

    alerts.sort(key=lambda a: (a.priority, a.max_rvol), reverse=True)

    alerted: list[str] = []
    for alert in alerts:
        if "1D" in {s.timeframe for s in alert.signals}:
            date_str = daily_data[alert.ticker].index[-1].strftime("%Y-%m-%d")
        else:
            date_str = now.strftime("%Y-%m-%d")
        if store.already_sent(alert.ticker, "aggregated", "MULTI", date_str):
            continue
        catalyst = catalysts.get(alert.ticker)
        text = format_ticker_alert(alert, catalyst=catalyst)
        if not sender(settings.telegram_bot_token, settings.telegram_breakout_chat_id,
                      text, dry_run=settings.dry_run):
            continue
        store.mark_sent(alert.ticker, "aggregated", "MULTI", date_str)
        alerted.append(alert.ticker)
    return alerted


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
            )
        except Exception:  # noqa: BLE001 — a staleness check must never abort the scan
            warning = None
        if warning:
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
    catalysts = recent_by_ticker(disc, now=now, window_hours=settings.news_booster_window_hours)
    scan_tickers = resolve_scan_tickers(
        settings.watchlist, settings.universe_candidates, daily,
        settings.min_price, settings.min_daily_value,
    )
    return scan_once(settings, daily, intraday, store, now=now, sender=sender,
                     catalysts=catalysts, tickers=scan_tickers)


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
