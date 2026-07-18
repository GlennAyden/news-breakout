from news_breakout.config import load_settings


def test_load_settings_merges_yaml_and_env(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM, BBRI]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=abc:123\nTELEGRAM_BREAKOUT_CHAT_ID=-100999\n",
        encoding="utf-8",
    )

    s = load_settings(str(cfg), str(env))

    assert s.watchlist == ["ANTM", "BBRI"]
    assert s.donchian_lookback == 20
    assert s.rvol_threshold == 2.0
    assert s.rvol_window == 20
    assert s.history_days == 120
    assert s.range_lookback == 30
    assert s.range_max_width_pct == 0.15
    assert s.intraday_period_days == 60
    assert s.dry_run is True
    assert s.telegram_bot_token == "abc:123"
    assert s.telegram_breakout_chat_id == "-100999"
