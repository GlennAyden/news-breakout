from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from tests.fixtures import make_ohlcv
from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
from news_breakout.news.models import Disclosure
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
        disclosure_fetcher=lambda page_size, *, now, proxy, retries=0: [],
    )
    assert result == ["ANTM"]
    # empty intraday mid-session also emits a staleness warning; isolate the alert
    alerts = [m for m in sent if "🚨" in m]
    assert len(alerts) == 1
    store.close()


def test_scan_once_attaches_catalyst_and_boosts_priority():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    catalyst = Disclosure(
        ticker="ANTM", title="Rights Issue", timestamp=NOW,
        disclosure_id="1", url="https://example.com",
    )
    result = run.scan_once(_settings(), _breakout_daily(), {}, store, now=NOW,
                           sender=sender, catalysts={"ANTM": catalyst})
    assert result == ["ANTM"]
    assert len(sent) == 1
    assert "🔥" in sent[0]
    assert "Katalis" in sent[0]
    assert "Rights Issue" in sent[0]
    # _breakout_daily() triggers a resistance signal on 1D (base priority 3.0)
    # + news_priority_boost default 3.0 = 6
    assert "⭐6" in sent[0]
    store.close()


def test_scan_once_ranks_by_quality_score_when_priority_tied():
    # Both tickers fire a single 1D breakout (priority 3.0 each), but HIGHX thrusts far
    # above its level (ext ~10%, capped) while LOWX barely clears it (ext ~0.9%) -- the
    # quality score (not raw priority) must decide the order.
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = {
        "HIGHX": make_ohlcv(
            highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
            closes=[100, 100, 100, 121], volumes=[100, 100, 100, 300]),
        "LOWX": make_ohlcv(
            highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
            closes=[100, 100, 100, 111], volumes=[100, 100, 100, 300]),
    }
    result = run.scan_once(_settings(), daily, {}, store, now=NOW, sender=sender,
                           tickers=["HIGHX", "LOWX"])
    assert result == ["HIGHX", "LOWX"]
    store.close()


def test_scan_once_catalyst_boost_can_flip_ranking():
    # Same setup as above, but LOWX (the marginal breakout) gets a news catalyst.
    # The boost must raise its quality_score enough to overtake HIGHX's ranking.
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = {
        "HIGHX": make_ohlcv(
            highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
            closes=[100, 100, 100, 121], volumes=[100, 100, 100, 300]),
        "LOWX": make_ohlcv(
            highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
            closes=[100, 100, 100, 111], volumes=[100, 100, 100, 300]),
    }
    catalyst = Disclosure(
        ticker="LOWX", title="Rights Issue", timestamp=NOW,
        disclosure_id="1", url="https://example.com",
    )
    result = run.scan_once(_settings(), daily, {}, store, now=NOW, sender=sender,
                           tickers=["HIGHX", "LOWX"], catalysts={"LOWX": catalyst})
    assert result == ["LOWX", "HIGHX"]
    store.close()


def test_run_scan_attaches_catalysts_from_disclosure_fetcher():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = _breakout_daily()
    disc = [Disclosure(ticker="ANTM", title="Rights Issue", timestamp=NOW,
                       disclosure_id="1", url="https://example.com")]
    result = run.run_scan(
        _settings(), store, now=NOW, sender=sender,
        daily_fetcher=lambda tickers, days: daily,
        intraday_fetcher=lambda tickers, days: {},
        disclosure_fetcher=lambda page_size, *, now, proxy, retries=0: disc,
    )
    assert result == ["ANTM"]
    # catalyst-boosted alerts use the 🔥 header; isolate it from the staleness warning
    alerts = [m for m in sent if "Katalis" in m]
    assert len(alerts) == 1
    assert "🔥" in alerts[0]
    store.close()


def test_run_scan_tolerates_disclosure_fetch_failure():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = _breakout_daily()

    def failing_disclosure_fetcher(page_size, *, now, proxy, retries=0):
        raise RuntimeError("IDX unreachable")

    result = run.run_scan(
        _settings(), store, now=NOW, sender=sender,
        daily_fetcher=lambda tickers, days: daily,
        intraday_fetcher=lambda tickers, days: {},
        disclosure_fetcher=failing_disclosure_fetcher,
    )
    assert result == ["ANTM"]
    alerts = [m for m in sent if "🚨" in m]
    assert len(alerts) == 1
    assert "🔥" not in alerts[0]
    store.close()


def test_run_scan_scans_liquid_universe():
    # a liquid universe candidate (not in the watchlist) that breaks out gets alerted
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    s = _settings().model_copy(update={"universe_candidates": ["BBCA"]})
    # BBCA: liquid (value >> min_daily_value) + breakout; watchlist ANTM has no data this run
    bbca = make_ohlcv(
        highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
        closes=[100, 100, 100, 115],
        volumes=[10_000_000, 10_000_000, 10_000_000, 30_000_000])
    result = run.run_scan(
        s, store, now=NOW, sender=sender,
        daily_fetcher=lambda tickers, days: {"BBCA": bbca},
        intraday_fetcher=lambda tickers, days: {},
        disclosure_fetcher=lambda page_size, *, now, proxy, retries=0: [])
    assert "BBCA" in result
    store.close()


def test_run_scan_sends_staleness_warning():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    stale_idx = pd.DatetimeIndex([NOW - timedelta(hours=3)])
    intraday = {"ANTM": pd.DataFrame(
        {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.0], "Volume": [100]},
        index=stale_idx)}
    run.run_scan(
        _settings(), store, now=NOW, sender=sender,
        daily_fetcher=lambda tickers, days: {},
        intraday_fetcher=lambda tickers, days: intraday,
        disclosure_fetcher=lambda page_size, *, now, proxy, retries=0: [])
    assert any("basi" in m for m in sent)
    store.close()


def test_run_scan_skips_staleness_during_morning_grace():
    # 15 min after open (within the grace window): even empty data must NOT warn stale,
    # because a working fetcher hasn't produced today's first 60m bar yet.
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    early = datetime(2026, 7, 17, 9, 15, tzinfo=WIB)
    run.run_scan(
        _settings(), store, now=early, sender=sender,
        daily_fetcher=lambda tickers, days: {},
        intraday_fetcher=lambda tickers, days: {},
        disclosure_fetcher=lambda page_size, *, now, proxy, retries=0: [])
    assert not any(("basi" in m or "Tidak ada data" in m) for m in sent)
    store.close()


def test_run_scan_warns_when_no_data(caplog):
    import logging
    store = DedupStore(":memory:")
    with caplog.at_level(logging.WARNING):
        result = run.run_scan(_settings(), store, now=NOW, sender=lambda *a, **k: True,
                              daily_fetcher=lambda t, d: {}, intraday_fetcher=lambda t, d: {},
                              disclosure_fetcher=lambda page_size, *, now, proxy, retries=0: [])
    assert result == []
    assert any("0 tickers" in r.message for r in caplog.records)
    store.close()
