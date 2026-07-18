from __future__ import annotations

from news_breakout.models import TickerAlert
from news_breakout.data.yfinance_source import fetch_daily_ohlcv
from news_breakout.data.universe import filter_liquid_universe
from news_breakout.signals.engine import evaluate_ticker
from news_breakout.alerts.telegram import send_message


def build_weekend_summary(alerts: list[TickerAlert], top_n: int = 10) -> str:
    if not alerts:
        return "📊 WEEKEND DEEP-SCAN (1D)\nTidak ada setup breakout terdeteksi."
    ranked = sorted(alerts, key=lambda a: (a.priority, a.max_rvol), reverse=True)[:top_n]
    lines = ["📊 WEEKEND DEEP-SCAN (1D)", "━━━━━━━━━━━━━━━━━━━"]
    for a in ranked:
        tfs = "+".join(sorted({s.timeframe for s in a.signals}))
        lines.append(f"⭐{a.priority:.0f}  {a.ticker}  [{tfs}]  RVOL {a.max_rvol:.1f}×")
    return "\n".join(lines)


def run_weekend_scan(settings, store, *, now, sender=send_message, daily_fetcher=fetch_daily_ohlcv) -> str:
    liquid = filter_liquid_universe(
        settings.universe_candidates, daily_fetcher(settings.universe_candidates, settings.history_days),
        settings.min_price, settings.min_daily_value,
    ) if settings.universe_candidates else []
    tickers = list(dict.fromkeys(settings.watchlist + liquid))
    daily = daily_fetcher(tickers, settings.history_days)
    alerts = []
    for t in tickers:
        if t not in daily:
            continue
        a = evaluate_ticker(
            t, {"1D": daily[t]},
            donchian_lookback=settings.donchian_lookback, rvol_window=settings.rvol_window,
            rvol_threshold=settings.rvol_threshold, range_lookback=settings.range_lookback,
            range_max_width_pct=settings.range_max_width_pct, now=now,
        )
        if a is not None:
            alerts.append(a)
    summary = build_weekend_summary(alerts)
    sender(settings.telegram_bot_token, settings.telegram_breakout_chat_id, summary, dry_run=settings.dry_run)
    return summary
