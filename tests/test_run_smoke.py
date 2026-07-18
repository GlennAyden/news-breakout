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
        watchlist=["ANTM"],
        donchian_lookback=3,
        rvol_threshold=2.0,
        rvol_window=3,
        history_days=120,
        telegram_bot_token="tok",
        telegram_breakout_chat_id="-100",
        dry_run=True,
    )


def _breakout_data():
    return {
        "ANTM": make_ohlcv(
            highs=[100, 105, 110, 116],
            lows=[90, 95, 100, 108],
            closes=[100, 100, 100, 115],
            volumes=[100, 100, 100, 300],
        )
    }


def test_scan_once_alerts_then_dedups():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append((chat_id, text))
        return True

    first = run.scan_once(_settings(), _breakout_data(), store, now=NOW, sender=sender)
    assert first == ["ANTM"]
    assert len(sent) == 1
    assert "ANTM" in sent[0][1]

    # second pass same day -> deduped, no new send
    second = run.scan_once(_settings(), _breakout_data(), store, now=NOW, sender=sender)
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

    first = run.scan_once(_settings(), _breakout_data(), store, now=NOW, sender=failing_sender)
    assert first == []                       # nothing counted as alerted
    retry = run.scan_once(_settings(), _breakout_data(), store, now=NOW, sender=ok_sender)
    assert retry == ["ANTM"]                 # not deduped, retried successfully
    store.close()
