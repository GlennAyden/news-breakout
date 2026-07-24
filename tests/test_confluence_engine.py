import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from news_breakout.models import BreakoutSignal, TickerAlert
from news_breakout.orderbook.models import OrderbookSnapshot
from news_breakout.confluence.store import ConfluenceStore
from news_breakout.confluence.engine import run_confluence_cycle
from news_breakout.news.portal import PortalNews

WIB = ZoneInfo("Asia/Jakarta")


def _settings(**over):
    base = dict(
        curated_keywords=["kontrak"], confluence_ttl_trading_days=5,
        telegram_confluence_chat_id="-100", telegram_bot_token="tok", dry_run=True,
        min_quality_score=None, confluence_require_orderbook=True,
        orderbook_phase_rm_balance_min_ratio=0.85, market_open="09:00",
        market_close="16:00", orderbook_window_after_open_minutes=30,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _alert(ticker, now):
    sig = BreakoutSignal(ticker=ticker, timeframe="1D", signal_type="resistance_breakout",
                         price=4850, pct_change=3.2, level=4800, rvol=3.2, timestamp=now)
    return TickerAlert(ticker=ticker, signals=[sig], priority=5.0, timestamp=now,
                       quality_score=7.0)


def _sender_recorder():
    sent = []
    def sender(token, chat_id, text, **kw):
        sent.append((chat_id, text))
        return True
    return sent, sender


def test_news_plus_breakout_sends_2of3_offhours():
    now = datetime(2026, 7, 25, 20, 0, tzinfo=WIB)   # Saturday evening — market closed
    store = ConfluenceStore(":memory:")
    items = [PortalNews(ticker="BBRI", title="BBRI kontrak", timestamp=now, url="u",
                        source="s", sentiment="positif")]
    sent, sender = _sender_recorder()
    out = run_confluence_cycle(
        _settings(), store, now=now, holidays=set(), portal_items=items, disclosures=[],
        daily_data={"BBRI": object()}, intraday_data={},
        sender=sender, evaluator=lambda *a, **k: [_alert("BBRI", now)],
        is_open=lambda: False)
    assert out == [("BBRI", "2of3")]
    assert store.get("BBRI").stage_alerted == "2of3"
    assert "CONFLUENCE 2/3" in sent[0][1]


def test_2of3_not_resent_next_cycle():
    now = datetime(2026, 7, 25, 20, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")
    items = [PortalNews(ticker="BBRI", title="t", timestamp=now, url="u",
                        source="s", sentiment="positif")]
    s = _settings()
    ev = lambda *a, **k: [_alert("BBRI", now)]
    run_confluence_cycle(s, store, now=now, holidays=set(), portal_items=items,
                         disclosures=[], daily_data={"BBRI": object()}, intraday_data={},
                         sender=_sender_recorder()[1], evaluator=ev, is_open=lambda: False)
    sent2, sender2 = _sender_recorder()
    out = run_confluence_cycle(s, store, now=now, holidays=set(), portal_items=items,
                               disclosures=[], daily_data={"BBRI": object()},
                               intraday_data={}, sender=sender2, evaluator=ev,
                               is_open=lambda: False)
    assert out == []            # already at 2of3, breakout pass skips it
    assert sent2 == []


def test_orderbook_ready_markup_upgrades_to_3of3_in_hours():
    now = datetime(2026, 7, 24, 10, 0, tzinfo=WIB)   # Friday 10:00, >30m after open
    store = ConfluenceStore(":memory:")
    store.upsert_watch("BBRI", news_ts=now.isoformat(), catalyst_text="c",
                       source="portal", expires_at="2026-08-01T00:00:00+07:00")
    store.mark_breakout("BBRI", at=now.isoformat(),
                        payload={"tf": "1D", "price": 4850, "pct_change": 3.2,
                                 "level": 4800, "rvol": 3.2, "quality": 7.0})
    store.mark_stage_alerted("BBRI", "2of3")
    snap = OrderbookSnapshot(symbol="BBRI", ts=now, total_bid_lot=300000,
                             total_offer_lot=295000, last_price=4850)
    sent, sender = _sender_recorder()
    out = run_confluence_cycle(
        _settings(), store, now=now, holidays=set(), portal_items=[], disclosures=[],
        daily_data={}, intraday_data={}, auth=object(), sender=sender,
        evaluator=lambda *a, **k: [], orderbook_fetcher=lambda *a, **k: snap,
        is_open=lambda: True)
    assert out == [("BBRI", "3of3")]
    assert store.get("BBRI").stage_alerted == "3of3"
    assert "CONFLUENCE 3/3" in sent[0][1]


def test_orderbook_skipped_when_market_closed():
    now = datetime(2026, 7, 24, 10, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")
    store.upsert_watch("BBRI", news_ts=now.isoformat(), catalyst_text="c",
                       source="portal", expires_at="2026-08-01T00:00:00+07:00")
    store.mark_stage_alerted("BBRI", "2of3")
    called = {"n": 0}
    def ob(*a, **k):
        called["n"] += 1
        return None
    out = run_confluence_cycle(
        _settings(), store, now=now, holidays=set(), portal_items=[], disclosures=[],
        daily_data={}, intraday_data={}, auth=object(), sender=_sender_recorder()[1],
        evaluator=lambda *a, **k: [], orderbook_fetcher=ob, is_open=lambda: False)
    assert out == [] and called["n"] == 0


def test_require_orderbook_false_makes_2of3_terminal():
    now = datetime(2026, 7, 25, 20, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")
    items = [PortalNews(ticker="BBRI", title="t", timestamp=now, url="u",
                        source="s", sentiment="positif")]
    out = run_confluence_cycle(
        _settings(confluence_require_orderbook=False), store, now=now, holidays=set(),
        portal_items=items, disclosures=[], daily_data={"BBRI": object()},
        intraday_data={}, sender=_sender_recorder()[1],
        evaluator=lambda *a, **k: [_alert("BBRI", now)], is_open=lambda: False)
    assert out == [("BBRI", "2of3")]
    assert store.get("BBRI").stage_alerted == "3of3"     # marked terminal


def test_expired_watch_is_pruned_silently():
    now = datetime(2026, 7, 24, 10, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")
    store.upsert_watch("OLD", news_ts="t", catalyst_text="c", source="portal",
                       expires_at="2026-07-01T00:00:00+07:00")
    out = run_confluence_cycle(
        _settings(), store, now=now, holidays=set(), portal_items=[], disclosures=[],
        daily_data={}, intraday_data={}, sender=_sender_recorder()[1],
        evaluator=lambda *a, **k: [], is_open=lambda: True)
    assert out == []
    assert store.get("OLD") is None
