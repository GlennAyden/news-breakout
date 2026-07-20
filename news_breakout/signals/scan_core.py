from __future__ import annotations

from news_breakout.config import Settings
from news_breakout.data.resample import resample_ohlcv
from news_breakout.signals.engine import evaluate_ticker
from news_breakout.alerts.dedup import DedupStore
from news_breakout.alerts.formatter import format_ticker_alert
from news_breakout.alerts.telegram import send_message


def evaluate_scan(settings: Settings, daily_data, intraday_data, *, now, catalysts, tickers):
    """Evaluate `tickers` over available frames; return alerts sorted by
    (quality_score, max_rvol) desc. No sending, no dedup."""
    alerts = []
    for ticker in tickers:
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
                alert.quality_score += settings.news_priority_boost
            alerts.append(alert)
    alerts.sort(key=lambda a: (a.quality_score, a.max_rvol), reverse=True)
    return alerts


def scan_once(settings: Settings, daily_data, intraday_data, store: DedupStore,
              *, now, sender=send_message, catalysts=None, tickers=None,
              max_alerts=None) -> list[str]:
    if catalysts is None:
        catalysts = {}
    scan_list = settings.watchlist if tickers is None else tickers
    alerts = evaluate_scan(settings, daily_data, intraday_data, now=now,
                           catalysts=catalysts, tickers=scan_list)
    if max_alerts is not None:
        alerts = alerts[:max_alerts]

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
