from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings, load_settings
from news_breakout.data.yfinance_source import fetch_daily_ohlcv
from news_breakout.signals.engine import evaluate_daily
from news_breakout.alerts.dedup import DedupStore
from news_breakout.alerts.formatter import format_breakout
from news_breakout.alerts.telegram import send_message

WIB = ZoneInfo("Asia/Jakarta")


def scan_once(settings: Settings, data, store: DedupStore, *, now, sender=send_message) -> list[str]:
    alerted: list[str] = []
    date_str = now.strftime("%Y-%m-%d")
    for ticker, df in data.items():
        sig = evaluate_daily(
            ticker,
            df,
            lookback=settings.donchian_lookback,
            rvol_window=settings.rvol_window,
            rvol_threshold=settings.rvol_threshold,
            now=now,
        )
        if sig is None:
            continue
        if store.already_sent(sig.ticker, sig.signal_type, sig.timeframe, date_str):
            continue
        text = format_breakout(sig)
        sender(
            settings.telegram_bot_token,
            settings.telegram_breakout_chat_id,
            text,
            dry_run=settings.dry_run,
        )
        store.mark_sent(sig.ticker, sig.signal_type, sig.timeframe, date_str)
        alerted.append(sig.ticker)
    return alerted


def main() -> None:
    settings = load_settings()
    data = fetch_daily_ohlcv(settings.watchlist, settings.history_days)
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")
    try:
        now = datetime.now(WIB)
        alerted = scan_once(settings, data, store, now=now)
        print(f"Scan complete. Alerted: {alerted or 'none'}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
