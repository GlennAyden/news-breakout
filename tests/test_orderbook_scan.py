from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from news_breakout.alerts.dedup import DedupStore
from news_breakout.config import Settings
from news_breakout.orderbook.models import OrderbookSnapshot
from news_breakout.orderbook.scan import run_orderbook_scan
from news_breakout.orderbook.state import PhaseStore

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 20, 10, 0, tzinfo=WIB)   # 60 min after 09:00 open


def _settings(**over):
    base = dict(
        watchlist=["ANTM"], donchian_lookback=3, rvol_threshold=2.0, rvol_window=3,
        history_days=120, range_lookback=3, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[], universe_candidates=["BBRI"], min_price=50,
        min_daily_value=1e9, telegram_news_chat_id="-2", curated_keywords=["dividen"],
        disclosure_page_size=50, news_poll_interval_minutes=60, idx_proxy="",
        orderbook_enabled=True, orderbook_max_symbols_per_scan=15,
        orderbook_request_delay_seconds=0.0, orderbook_window_after_open_minutes=30,
        orderbook_early_volume_min_ratio=0.5, orderbook_phase_rm_balance_min_ratio=0.85,
    )
    base.update(over)
    return Settings(**base)


def _daily(today_vol, prev_vol=1000):
    idx = pd.to_datetime(["2026-07-17", "2026-07-20"])
    return pd.DataFrame({"Close": [100, 100], "Volume": [prev_vol, today_vol]}, index=idx)


def _snap(sym, bid, offer):
    return OrderbookSnapshot(symbol=sym, ts=NOW, total_bid_lot=bid, total_offer_lot=offer,
                             last_price=100)


def _run(settings, daily, *, fetch_map, sent, calls=None, phase_store=None, store=None,
         is_open=lambda: True):
    store = store or DedupStore(":memory:")
    phase_store = phase_store or PhaseStore(":memory:")

    def fetcher(symbol, auth, *, now=None):
        if calls is not None:
            calls.append(symbol)
        return fetch_map.get(symbol)

    def sender(bot_token, chat_id, text, *, dry_run, client=None, **_):
        sent.append((chat_id, text))
        return True

    return run_orderbook_scan(settings, daily, store, phase_store, now=NOW, auth=None,
                              sender=sender, fetcher=fetcher, is_open=is_open,
                              sleeper=lambda *_: None), store, phase_store


def test_disabled_returns_empty():
    sent = []
    res, *_ = _run(_settings(orderbook_enabled=False), {"ANTM": _daily(800)},
                   fetch_map={"ANTM": _snap("ANTM", 300, 300)}, sent=sent)
    assert res == []
    assert sent == []


def test_market_closed_skips():
    sent = []
    res, *_ = _run(_settings(), {"ANTM": _daily(800)},
                   fetch_map={"ANTM": _snap("ANTM", 300, 300)}, sent=sent,
                   is_open=lambda: False)
    assert res == []
    assert sent == []


def test_too_early_in_session_skips():
    sent = []
    early = datetime(2026, 7, 20, 9, 15, tzinfo=WIB)  # 15 min < 30 window
    store = DedupStore(":memory:")
    phase_store = PhaseStore(":memory:")

    def fetcher(symbol, auth, *, now=None):
        return _snap(symbol, 300, 300)

    def sender(bot_token, chat_id, text, *, dry_run, client=None, **_):
        sent.append(text)
        return True

    res = run_orderbook_scan(_settings(), {"ANTM": _daily(800)}, store, phase_store,
                             now=early, auth=None, sender=sender, fetcher=fetcher,
                             is_open=lambda: True, sleeper=lambda *_: None)
    assert res == []
    assert sent == []


def test_volume_filter_excludes_low_volume():
    sent, calls = [], []
    res, *_ = _run(_settings(), {"ANTM": _daily(100)},   # ratio 0.1 < 0.5
                   fetch_map={"ANTM": _snap("ANTM", 300, 300)}, sent=sent, calls=calls)
    assert res == []
    assert calls == []          # never even fetched the orderbook


def test_ready_markup_alerts_then_dedupes():
    sent = []
    store = DedupStore(":memory:")
    phase_store = PhaseStore(":memory:")
    res, *_ = _run(_settings(), {"ANTM": _daily(800)},
                   fetch_map={"ANTM": _snap("ANTM", 300, 300)}, sent=sent,
                   store=store, phase_store=phase_store)
    assert res == ["ANTM"]
    assert len(sent) == 1
    assert sent[0][0] == "-1"   # falls back to breakout chat id
    # second run same day -> deduped
    res2, *_ = _run(_settings(), {"ANTM": _daily(800)},
                    fetch_map={"ANTM": _snap("ANTM", 300, 300)}, sent=sent,
                    store=store, phase_store=phase_store)
    assert res2 == []
    assert len(sent) == 1


def test_non_ready_markup_does_not_alert_but_records_phase():
    sent = []
    phase_store = PhaseStore(":memory:")
    res, _store, ps = _run(_settings(), {"ANTM": _daily(800)},
                           fetch_map={"ANTM": _snap("ANTM", 300, 700)},  # accumulation
                           sent=sent, phase_store=phase_store)
    assert res == []
    assert sent == []
    assert ps.get_last_phase("ANTM", "2026-07-20") == "A"


def test_prior_accumulation_annotated_in_alert():
    sent = []
    phase_store = PhaseStore(":memory:")
    phase_store.set_phase("ANTM", "2026-07-20", "A")
    res, *_ = _run(_settings(), {"ANTM": _daily(800)},
                   fetch_map={"ANTM": _snap("ANTM", 300, 300)}, sent=sent,
                   phase_store=phase_store)
    assert res == ["ANTM"]
    assert "AKUMULASI" in sent[0][1]


def test_cap_limits_number_of_orderbook_calls():
    sent, calls = [], []
    daily = {t: _daily(800) for t in ("AAA", "BBB", "CCC")}
    fetch_map = {t: _snap(t, 300, 300) for t in daily}
    res, *_ = _run(_settings(orderbook_max_symbols_per_scan=2), daily,
                   fetch_map=fetch_map, sent=sent, calls=calls)
    assert len(calls) == 2      # capped
    assert len(res) == 2


def test_failed_fetch_isolated_from_others():
    sent = []
    daily = {"AAA": _daily(800), "BBB": _daily(800)}
    fetch_map = {"AAA": None, "BBB": _snap("BBB", 300, 300)}  # AAA fetch fails
    res, *_ = _run(_settings(), daily, fetch_map=fetch_map, sent=sent)
    assert res == ["BBB"]
