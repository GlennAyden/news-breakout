from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings, load_settings
from news_breakout.data.yfinance_source import fetch_daily_ohlcv, fetch_intraday_ohlcv
from news_breakout.data.resample import resample_ohlcv
from news_breakout.signals.engine import evaluate_ticker
from news_breakout.alerts.dedup import DedupStore
from news_breakout.alerts.formatter import format_ticker_alert
from news_breakout.alerts.telegram import send_message
from news_breakout.news.idx_source import fetch_disclosures
from news_breakout.news.booster import recent_by_ticker

WIB = ZoneInfo("Asia/Jakarta")
logger = logging.getLogger("news_breakout")


def scan_once(settings: Settings, daily_data, intraday_data, store: DedupStore,
              *, now, sender=send_message, catalysts=None) -> list[str]:
    if catalysts is None:
        catalysts = {}
    alerts = []
    for ticker in settings.watchlist:
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
            rvol_threshold=settings.rvol_threshold, range_lookback=settings.range_lookback,
            range_max_width_pct=settings.range_max_width_pct, now=now,
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
    daily = daily_fetcher(settings.watchlist, settings.history_days)
    intraday = intraday_fetcher(settings.watchlist, settings.intraday_period_days)
    if not daily and not intraday:
        logger.warning(
            "fetch returned 0 tickers for %d watchlist symbols — likely rate-limit or data outage",
            len(settings.watchlist),
        )
    try:
        disc = disclosure_fetcher(settings.disclosure_page_size, now=now,
                                  proxy=settings.idx_proxy, retries=0)
    except Exception:  # noqa: BLE001
        disc = []
    catalysts = recent_by_ticker(disc, now=now, window_hours=settings.news_booster_window_hours)
    return scan_once(settings, daily, intraday, store, now=now, sender=sender, catalysts=catalysts)


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
