import serve
from news_breakout.config import load_settings


def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "svc")
    return load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))


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

    class _Log:
        def info(self, *a, **k): pass

    job = serve.build_scan_job(s, store=object(), log=_Log())
    job()
    # the injected fetchers are callables with the drop-in (tickers, N) signature
    assert callable(captured["daily"]) and callable(captured["intraday"])
    # and they are the Supabase-backed ones (closures over settings), not yfinance
    assert captured["daily"].__qualname__.startswith("make_daily_fetcher")
