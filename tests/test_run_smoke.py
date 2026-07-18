from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

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
    )


def _breakout_daily():
    return {"ANTM": make_ohlcv(
        highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
        closes=[100, 100, 100, 115], volumes=[100, 100, 100, 300])}


def _breakout_intraday_1h():
    idx = pd.date_range("2026-01-05 09:00", periods=8, freq="1h")
    return {"ANTM": pd.DataFrame(
        {
            "Open":   [105, 105, 105, 105, 105, 105, 105, 115],
            "High":   [110, 110, 110, 110, 110, 110, 110, 116],
            "Low":    [100, 100, 100, 100, 100, 100, 100, 108],
            "Close":  [105, 105, 105, 105, 105, 105, 105, 115],
            "Volume": [100, 100, 100, 100, 100, 100, 100, 300],
        },
        index=idx,
    )}


def test_scan_once_evaluates_intraday_frames():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    result = run.scan_once(_settings(), _breakout_daily(), _breakout_intraday_1h(),
                           store, now=NOW, sender=sender)
    assert result == ["ANTM"]
    assert len(sent) == 1
    # proves the intraday branch built + resampled + evaluated the 1H frame,
    # and 1D from daily is also present in the aggregated alert
    assert "1H" in sent[0]
    assert "1D" in sent[0]
    store.close()


def test_scan_once_multitf_alerts_then_dedups():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    first = run.scan_once(_settings(), _breakout_daily(), {}, store, now=NOW, sender=sender)
    assert first == ["ANTM"]
    assert len(sent) == 1 and "ANTM" in sent[0]
    second = run.scan_once(_settings(), _breakout_daily(), {}, store, now=NOW, sender=sender)
    assert second == []
    assert len(sent) == 1
    store.close()


def test_failed_send_is_not_marked_and_retries():
    store = DedupStore(":memory:")
    calls = []

    def failing_sender(bot_token, chat_id, text, *, dry_run, client=None):
        calls.append("fail")
        return False

    def ok_sender(bot_token, chat_id, text, *, dry_run, client=None):
        calls.append("ok")
        return True

    first = run.scan_once(_settings(), _breakout_daily(), {}, store, now=NOW, sender=failing_sender)
    assert first == []                       # nothing counted as alerted
    retry = run.scan_once(_settings(), _breakout_daily(), {}, store, now=NOW, sender=ok_sender)
    assert retry == ["ANTM"]                 # not deduped, retried successfully
    store.close()


def test_run_scan_uses_injected_fetchers():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = _breakout_daily()
    result = run.run_scan(
        _settings(), store, now=NOW, sender=sender,
        daily_fetcher=lambda tickers, days: daily,
        intraday_fetcher=lambda tickers, days: {},
    )
    assert result == ["ANTM"]
    assert len(sent) == 1
    store.close()
