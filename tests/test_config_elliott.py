import os
from news_breakout.config import load_settings


def _write(tmp_path):
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
        "elliott: {enabled: true, atr_scales: [2.0, 4.0], min_confidence: 0.5}\n",
        encoding="utf-8",
    )
    return cfg


def test_elliott_settings_load_with_overrides_and_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "x")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "x")
    s = load_settings(config_path=str(_write(tmp_path)), env_path=str(tmp_path / ".env"))
    assert s.elliott_enabled is True
    assert s.elliott_atr_scales == [2.0, 4.0]        # overridden
    assert s.elliott_min_confidence == 0.5           # overridden
    assert s.elliott_atr_window == 14                # default
    assert s.elliott_show_ambiguous is False         # default
