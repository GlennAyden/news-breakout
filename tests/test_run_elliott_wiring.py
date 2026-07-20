# tests/test_run_elliott_wiring.py
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.fixtures import make_ohlcv
from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
import run

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 17, 16, 0, tzinfo=WIB)


def _settings():
    return Settings(
        watchlist=["ANTM"], donchian_lookback=3, rvol_threshold=2.0, rvol_window=3,
        history_days=120, range_lookback=3, range_max_width_pct=0.15,
        intraday_period_days=60,
        telegram_bot_token="tok", telegram_breakout_chat_id="-100", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[],
        universe_candidates=[], min_price=50, min_daily_value=1_000_000_000,
        telegram_news_chat_id="-200", curated_keywords=["dividen"],
        disclosure_page_size=50, news_poll_interval_minutes=60, idx_proxy="",
        elliott_enabled=False, elliott_atr_scales=[1.1, 2.2], elliott_atr_window=99,
        elliott_max_pivots=42, elliott_fib_tolerance=0.12,
    )


def _daily():
    return {"ANTM": make_ohlcv(
        highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
        closes=[100, 100, 100, 115], volumes=[100, 100, 100, 300])}


def test_scan_once_forwards_elliott_config_to_evaluate_ticker(monkeypatch):
    settings = _settings()
    store = DedupStore(":memory:")
    recorded = []

    def stub_evaluate_ticker(ticker, frames, **kwargs):
        recorded.append(kwargs)
        return None

    monkeypatch.setattr(run, "evaluate_ticker", stub_evaluate_ticker)

    result = run.scan_once(settings, _daily(), {}, store, now=NOW, sender=lambda *a, **k: True)
    assert result == []
    assert len(recorded) == 1
    kwargs = recorded[0]
    assert kwargs["elliott_enabled"] == settings.elliott_enabled
    assert kwargs["elliott_scales"] == tuple(settings.elliott_atr_scales)
    assert kwargs["elliott_atr_window"] == settings.elliott_atr_window
    assert kwargs["elliott_max_pivots"] == settings.elliott_max_pivots
    assert kwargs["elliott_fib_tolerance"] == settings.elliott_fib_tolerance
    store.close()
