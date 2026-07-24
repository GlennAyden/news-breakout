from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from news_breakout.alerts.telegram import send_message
from news_breakout.confluence.calendar import add_trading_days
from news_breakout.confluence.formatter import format_confluence_alert
from news_breakout.confluence.trigger import positive_news_triggers
from news_breakout.models import TF_WEIGHT, TickerAlert
from news_breakout.orderbook.phase import PhaseConfig, classify_phase
from news_breakout.orderbook.stockbit_source import fetch_orderbook, is_market_open
from news_breakout.signals.scan_core import evaluate_scan

logger = logging.getLogger("news_breakout")


def _breakout_payload(alert: TickerAlert) -> dict:
    """Serializable summary of the winning breakout signal (highest TF weight)."""
    sig = max(alert.signals, key=lambda s: TF_WEIGHT.get(s.timeframe, 0.0))
    return {"tf": sig.timeframe, "price": sig.price, "pct_change": sig.pct_change,
            "level": sig.level, "rvol": sig.rvol, "quality": alert.quality_score}


def _orderbook_window_open(settings, now: datetime, is_open) -> bool:
    """Same gate as the standalone orderbook scan: session open, at least
    ``window_after_open_minutes`` into it, and not past the close."""
    if not is_open():
        return False
    oh, om = (int(x) for x in settings.market_open.split(":"))
    session_open = now.replace(hour=oh, minute=om, second=0, microsecond=0)
    if (now - session_open) < timedelta(minutes=settings.orderbook_window_after_open_minutes):
        return False
    ch, cm = (int(x) for x in settings.market_close.split(":"))
    if now > now.replace(hour=ch, minute=cm, second=0, microsecond=0):
        return False
    return True


def _send(settings, chat_id, text, sender) -> bool:
    return bool(chat_id) and sender(
        settings.telegram_bot_token, chat_id, text,
        dry_run=settings.dry_run, parse_mode="HTML", disable_preview=True)


def run_confluence_cycle(
    settings, store, *, now, holidays, portal_items, disclosures,
    daily_data, intraday_data, auth=None, sender=send_message,
    evaluator=evaluate_scan, orderbook_fetcher=fetch_orderbook, is_open=None,
) -> list[tuple[str, str]]:
    """One confluence cycle: ingest triggers → prune → breakout(2/3) → orderbook(3/3).

    Pure orchestration over injected data/deps (no fetching here). Returns the
    ``(ticker, stage)`` pairs alerted this cycle.
    """
    sent: list[tuple[str, str]] = []
    chat_id = settings.telegram_confluence_chat_id
    if not chat_id:
        logger.warning("confluence: TELEGRAM_CONFLUENCE_CHAT_ID unset; not sending")

    # 1. Ingest positive-news triggers → upsert onto the watchlist.
    triggers = positive_news_triggers(portal_items, disclosures, settings.curated_keywords)
    expires_at = add_trading_days(now, settings.confluence_ttl_trading_days, holidays).isoformat()
    for t in triggers:
        store.upsert_watch(t.ticker, news_ts=t.ts.isoformat(), catalyst_text=t.headline,
                           source=t.source, expires_at=expires_at)

    # 2. Drop expired watches (silent).
    store.prune_expired(now_iso=now.isoformat())

    # 3. Breakout pass (any hour) for watches still at stage 'none'.
    for w in store.active_watches(stage="none"):
        try:
            alerts = evaluator(settings, daily_data, intraday_data, now=now,
                               catalysts={w.ticker: True}, tickers=[w.ticker])
            alert = alerts[0] if alerts else None
            if alert is None:
                continue
            if settings.min_quality_score is not None and alert.quality_score < settings.min_quality_score:
                continue
            payload = _breakout_payload(alert)
            store.mark_breakout(w.ticker, at=now.isoformat(), payload=payload)
            text = format_confluence_alert(
                ticker=w.ticker, stage="2of3", catalyst_text=w.catalyst_text,
                catalyst_source=w.source, catalyst_ts=datetime.fromisoformat(w.news_ts),
                breakout=payload, orderbook=None, now=now)
            if _send(settings, chat_id, text, sender):
                store.mark_stage_alerted(w.ticker, "2of3")
                sent.append((w.ticker, "2of3"))
                if not settings.confluence_require_orderbook:
                    store.mark_stage_alerted(w.ticker, "3of3")   # 2/3 is terminal
        except Exception:  # noqa: BLE001 — one bad symbol never aborts the cycle
            logger.warning("confluence breakout pass failed: %s", w.ticker, exc_info=True)
            continue

    # 4. Orderbook pass (market hours only) for watches at stage '2of3'.
    if settings.confluence_require_orderbook:
        watches = store.active_watches(stage="2of3")
        if watches and auth is not None:
            if is_open is None:
                def is_open():
                    return is_market_open(auth)
            if _orderbook_window_open(settings, now, is_open):
                pcfg = PhaseConfig(rm_balance_min_ratio=settings.orderbook_phase_rm_balance_min_ratio)
                for w in watches:
                    try:
                        snap = orderbook_fetcher(w.ticker, auth, now=now)
                        if snap is None:
                            continue
                        result = classify_phase(snap, pcfg)
                        if not result.is_ready_markup:
                            continue
                        ob = {"bid_lot": result.bid_lot, "offer_lot": result.offer_lot,
                              "ratio": result.ratio}
                        payload = json.loads(w.breakout_payload) if w.breakout_payload else {}
                        text = format_confluence_alert(
                            ticker=w.ticker, stage="3of3", catalyst_text=w.catalyst_text,
                            catalyst_source=w.source,
                            catalyst_ts=datetime.fromisoformat(w.news_ts),
                            breakout=payload, orderbook=ob, now=now)
                        if _send(settings, chat_id, text, sender):
                            store.mark_orderbook(w.ticker, at=now.isoformat())
                            store.mark_stage_alerted(w.ticker, "3of3")
                            sent.append((w.ticker, "3of3"))
                    except Exception:  # noqa: BLE001 — one bad symbol never aborts the cycle
                        logger.warning("confluence orderbook pass failed: %s", w.ticker,
                                       exc_info=True)
                        continue
    return sent
