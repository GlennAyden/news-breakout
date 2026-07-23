from __future__ import annotations

import logging
import time
from datetime import timedelta

from news_breakout.alerts.telegram import send_message
from news_breakout.orderbook.formatter import format_orderbook_alert
from news_breakout.orderbook.phase import PhaseConfig, classify_phase
from news_breakout.orderbook.stockbit_source import fetch_orderbook, is_market_open
from news_breakout.orderbook.volume_filter import VolumeConfig, passes_early_volume

logger = logging.getLogger("news_breakout")

_SIGNAL_TYPE = "ready_markup"
_TIMEFRAME = "ORDERBOOK"


def run_orderbook_scan(
    settings, daily_data, store, phase_store, *, now, auth,
    sender=send_message, fetcher=fetch_orderbook, is_open=None, sleeper=time.sleep,
) -> list[str]:
    """Ready-Markup orderbook scan. Returns tickers alerted this cycle.

    Population = tickers in ``daily_data`` passing the rule-2 early-volume
    filter (cheap, no API). Only those get a Stockbit orderbook call.
    """
    if not settings.orderbook_enabled:
        return []

    chat_id = settings.telegram_orderbook_chat_id or settings.telegram_breakout_chat_id
    if not chat_id:
        logger.warning("orderbook scan: no chat id configured; skipping")
        return []

    if is_open is None:
        def is_open():
            return is_market_open(auth)
    if not is_open():
        logger.info("orderbook scan: market closed; skipping")
        return []

    # Rule-2 timing gate: too early into the session to judge today's pace, and
    # never after the close (defends even if is_open fails open).
    oh, om = (int(x) for x in settings.market_open.split(":"))
    session_open = now.replace(hour=oh, minute=om, second=0, microsecond=0)
    minutes_after_open = int((now - session_open).total_seconds() // 60)
    if now - session_open < timedelta(minutes=settings.orderbook_window_after_open_minutes):
        return []
    ch, cm = (int(x) for x in settings.market_close.split(":"))
    if now > now.replace(hour=ch, minute=cm, second=0, microsecond=0):
        return []

    vcfg = VolumeConfig(min_ratio_prev_day=settings.orderbook_early_volume_min_ratio)
    pcfg = PhaseConfig(rm_balance_min_ratio=settings.orderbook_phase_rm_balance_min_ratio)

    candidates = []
    for ticker, df in daily_data.items():
        vr = passes_early_volume(df, now, vcfg)
        if vr.passed:
            candidates.append((ticker, vr))
    candidates.sort(key=lambda cv: cv[1].ratio, reverse=True)

    cap = settings.orderbook_max_symbols_per_scan
    if len(candidates) > cap:
        logger.info("orderbook scan: %d passed volume filter, capping to %d",
                    len(candidates), cap)
        candidates = candidates[:cap]

    date_str = now.strftime("%Y-%m-%d")
    alerted: list[str] = []
    for ticker, vr in candidates:
        snap = fetcher(ticker, auth, now=now)
        sleeper(settings.orderbook_request_delay_seconds)  # throttle every API call
        if snap is None:
            continue
        result = classify_phase(snap, pcfg)
        prev = phase_store.get_last_phase(ticker, date_str)
        phase_store.set_phase(ticker, date_str, result.phase.value)
        if not result.is_ready_markup:
            continue
        if store.already_sent(ticker, _SIGNAL_TYPE, _TIMEFRAME, date_str):
            continue
        text = format_orderbook_alert(
            snap, result, prev, vr, now=now, minutes_after_open=minutes_after_open
        )
        if sender(settings.telegram_bot_token, chat_id, text, dry_run=settings.dry_run):
            store.mark_sent(ticker, _SIGNAL_TYPE, _TIMEFRAME, date_str)
            alerted.append(ticker)
    return alerted
