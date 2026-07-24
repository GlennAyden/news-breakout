from news_breakout.config import load_settings


def _write(tmp_path, confluence_block: str) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.5, rvol_window: 20,"
        " range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: '09:00', market_close: '16:00',"
        " scan_interval_minutes: 30, weekend_scan_day: sat, holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [], disclosure_page_size: 50, news_poll_interval_minutes: 60}\n"
        + confluence_block,
        encoding="utf-8",
    )
    return str(cfg)


def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "x")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "x")


def test_confluence_defaults_when_block_absent(tmp_path, monkeypatch):
    _env(monkeypatch)
    s = load_settings(config_path=_write(tmp_path, ""), env_path=str(tmp_path / ".env"))
    assert s.confluence_enabled is False
    assert s.confluence_ttl_trading_days == 5
    assert s.confluence_require_orderbook is True
    assert s.telegram_confluence_chat_id == ""


def test_confluence_overrides_and_env_chat_id(tmp_path, monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_CONFLUENCE_CHAT_ID", "-100999")
    block = "confluence: {enabled: true, ttl_trading_days: 3, require_orderbook: false}\n"
    s = load_settings(config_path=_write(tmp_path, block), env_path=str(tmp_path / ".env"))
    assert s.confluence_enabled is True
    assert s.confluence_ttl_trading_days == 3
    assert s.confluence_require_orderbook is False
    assert s.telegram_confluence_chat_id == "-100999"
