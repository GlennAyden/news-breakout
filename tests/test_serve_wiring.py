from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import serve
from news_breakout.config import load_settings
from news_breakout.alerts.dedup import DedupStore

WIB = ZoneInfo("Asia/Jakarta")


def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "svc")
    return load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))


class _Log:
    def info(self, *a, **k): pass


def _log():
    return _Log()


class _FakeCache:
    def __init__(self):
        self.consecutive_failures = 0
        self.calls = 0

    def fetch(self, page_size, *, now, proxy="", retries=None, **_):
        self.calls += 1
        return []


def test_scan_job_injects_supabase_fetchers(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)
    captured = {}

    # capture what run_scan is called with, and force the scan to actually run
    def fake_run_scan(settings, store, *, now, daily_fetcher, intraday_fetcher, **kw):
        captured["daily"] = daily_fetcher
        captured["intraday"] = intraday_fetcher
        return []

    monkeypatch.setattr(serve.run, "run_scan", fake_run_scan)
    monkeypatch.setattr(serve, "should_scan_now", lambda now, settings: True)

    job = serve.build_scan_job(s, store=object(), log=_log(), cache=_FakeCache())
    job()
    # the injected fetchers are callables with the drop-in (tickers, N) signature
    assert callable(captured["daily"]) and callable(captured["intraday"])
    # and they are the Supabase-backed ones (closures over settings), not yfinance
    assert captured["daily"].__qualname__.startswith("make_daily_fetcher")


def test_news_job_gates_offhours_and_wires_cache(monkeypatch, tmp_path):
    settings = _settings(monkeypatch, tmp_path)  # market_open="09:00", close="16:00"
    store = DedupStore(":memory:")
    cache = _FakeCache()
    seen = {"feed": 0, "portal": 0, "prune": 0}

    def fake_feed(s, st, *, now, fetcher=None, failure_streak=0, **_):
        seen["feed"] += 1
        assert fetcher == cache.fetch
        assert callable(failure_streak)
        return []

    def fake_portal(s, st, *, now, **_):
        seen["portal"] += 1
        return []

    monkeypatch.setattr(serve, "run_news_feed", fake_feed)
    monkeypatch.setattr(serve, "run_portal_feed", fake_portal)
    monkeypatch.setattr(DedupStore, "prune_news",
                        lambda self, days, *, now: seen.__setitem__("prune", seen["prune"] + 1))

    evening = datetime(2026, 7, 22, 20, 0, tzinfo=WIB)
    clock = {"now": evening}
    job = serve.build_news_job(settings, store, _log(), cache,
                               now_fn=lambda: clock["now"])
    job()                                        # first off-hours tick runs
    clock["now"] = evening + timedelta(minutes=15)
    job()                                        # second tick within 60m is gated
    assert seen["feed"] == 1 and seen["portal"] == 1 and seen["prune"] == 1
    clock["now"] = evening + timedelta(minutes=61)
    job()
    assert seen["feed"] == 2
    store.close()
