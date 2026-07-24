from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import run_confluence
from news_breakout.confluence.store import ConfluenceStore

WIB = ZoneInfo("Asia/Jakarta")


def _settings():
    return SimpleNamespace(
        confluence_enabled=True, confluence_require_orderbook=False,
        confluence_ttl_trading_days=5, watchlist=["BBRI"], universe_candidates=[],
        history_days=120, intraday_period_days=60, disclosure_page_size=50,
        idx_proxy="", portal_enabled=False, sentiment_enabled=False,
        curated_keywords=["kontrak"], holidays=[], stockbit_refresh_token="",
        stockbit_access_token="", telegram_confluence_chat_id="-1",
        telegram_bot_token="t", dry_run=True, min_quality_score=None,
        market_open="09:00", market_close="16:00",
        orderbook_window_after_open_minutes=30,
        orderbook_phase_rm_balance_min_ratio=0.85,
        portal_sources=[], portal_name_map={}, portal_proxy="",
        sentiment_min_confidence=0.6,
    )


def test_run_once_fetches_and_delegates_to_engine(monkeypatch):
    now = datetime(2026, 7, 25, 20, 0, tzinfo=WIB)
    store = ConfluenceStore(":memory:")

    # stub the network-bound collaborators
    monkeypatch.setattr(run_confluence, "fetch_disclosures", lambda *a, **k: [])
    monkeypatch.setattr(run_confluence, "_collect_portal_items", lambda s, *, now: [])
    monkeypatch.setattr(run_confluence, "make_daily_fetcher",
                        lambda s: (lambda syms, days: {}))
    monkeypatch.setattr(run_confluence, "make_intraday_fetcher",
                        lambda s: (lambda syms, days: {}))
    captured = {}
    def fake_cycle(settings, st, **kw):
        captured.update(kw)
        return [("BBRI", "2of3")]
    monkeypatch.setattr(run_confluence, "run_confluence_cycle", fake_cycle)

    out = run_confluence.run_once(_settings(), now=now, store=store)

    assert out == [("BBRI", "2of3")]
    assert "portal_items" in captured and "disclosures" in captured
