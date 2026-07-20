from news_breakout.config import load_settings


def test_load_settings_merges_yaml_and_env(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM, BBRI]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: [\"2026-01-01\"]}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60, booster_window_hours: 72, priority_boost: 4.0}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=abc:123\nTELEGRAM_BREAKOUT_CHAT_ID=-100999\n"
        "TELEGRAM_NEWS_CHAT_ID=-200\n",
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
    assert s.market_open == "09:00"
    assert s.scan_interval_minutes == 30
    assert s.weekend_scan_day == "sat"
    assert s.holidays == ["2026-01-01"]
    assert s.universe_candidates == []
    assert s.min_price == 50
    assert s.min_daily_value == 1000000000
    assert s.telegram_news_chat_id == "-200"
    assert s.curated_keywords == ["dividen"]
    assert s.disclosure_page_size == 50
    assert s.news_poll_interval_minutes == 60
    assert s.idx_proxy == ""
    assert s.news_booster_window_hours == 72
    assert s.news_priority_boost == 4.0
    assert s.portal_enabled is False
    assert s.portal_sources == []
    assert s.portal_name_map == {}


def test_load_settings_reads_portal_section(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM, BBRI]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: [\"2026-01-01\"]}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n"
        "portal: {enabled: true, sources: [\"https://www.kontan.co.id/rss\"], "
        "name_map: {barito pacific: BRPT}}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=abc:123\nTELEGRAM_BREAKOUT_CHAT_ID=-100999\n"
        "TELEGRAM_NEWS_CHAT_ID=-200\n",
        encoding="utf-8",
    )

    s = load_settings(str(cfg), str(env))

    assert s.portal_enabled is True
    assert s.portal_sources == ["https://www.kontan.co.id/rss"]
    assert s.portal_name_map == {"barito pacific": "BRPT"}


def test_load_settings_reads_portal_dict_sources_with_parser(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM, BBRI]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: [\"2026-01-01\"]}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n"
        "portal: {enabled: true, sources: ["
        "{url: \"https://www.kontan.co.id/rss\", parser: rss}, "
        "{url: \"https://emitennews.com/category/emiten\", parser: emitennews}"
        "], name_map: {barito pacific: BRPT}}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=abc:123\nTELEGRAM_BREAKOUT_CHAT_ID=-100999\n"
        "TELEGRAM_NEWS_CHAT_ID=-200\n",
        encoding="utf-8",
    )

    s = load_settings(str(cfg), str(env))

    assert s.portal_enabled is True
    assert s.portal_sources == [
        {"url": "https://www.kontan.co.id/rss", "parser": "rss"},
        {"url": "https://emitennews.com/category/emiten", "parser": "emitennews"},
    ]


def test_load_settings_falls_back_to_booster_defaults_when_absent(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM, BBRI]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: [\"2026-01-01\"]}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=abc:123\nTELEGRAM_BREAKOUT_CHAT_ID=-100999\n"
        "TELEGRAM_NEWS_CHAT_ID=-200\n",
        encoding="utf-8",
    )

    s = load_settings(str(cfg), str(env))

    assert s.news_booster_window_hours == 48
    assert s.news_priority_boost == 3.0


def test_load_settings_reads_curation_keys(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n"
        "portal: {enabled: true, sources: [], summary_sentences: 3, max_per_run: 5}\n"
        "sentiment: {enabled: false, model: acme/x, min_confidence: 0.75}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=a:b\nTELEGRAM_BREAKOUT_CHAT_ID=-1\nTELEGRAM_NEWS_CHAT_ID=-2\n",
                   encoding="utf-8")
    s = load_settings(str(cfg), str(env))
    assert s.portal_summary_sentences == 3
    assert s.portal_max_per_run == 5
    assert s.sentiment_enabled is False
    assert s.sentiment_model == "acme/x"
    assert s.sentiment_min_confidence == 0.75


def test_load_settings_curation_defaults_when_absent(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=a:b\nTELEGRAM_BREAKOUT_CHAT_ID=-1\nTELEGRAM_NEWS_CHAT_ID=-2\n",
                   encoding="utf-8")
    s = load_settings(str(cfg), str(env))
    assert s.portal_summary_sentences == 2
    assert s.portal_max_per_run == 20
    assert s.sentiment_enabled is True
    assert s.sentiment_model == "w11wo/indonesian-roberta-base-sentiment-classifier"
    assert s.sentiment_min_confidence == 0.6


def test_load_settings_reads_daily_shift(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n"
        "daily_shift: {enabled: false, universe_file: config/x.txt, min_daily_value: 3000000000, "
        "min_price: 100, max_alerts: 10, history_days: 60}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=a:b\nTELEGRAM_BREAKOUT_CHAT_ID=-1\nTELEGRAM_NEWS_CHAT_ID=-2\n",
                   encoding="utf-8")
    s = load_settings(str(cfg), str(env))
    assert s.daily_shift_enabled is False
    assert s.daily_shift_universe_file == "config/x.txt"
    assert s.daily_shift_min_daily_value == 3000000000
    assert s.daily_shift_min_price == 100
    assert s.daily_shift_max_alerts == 10
    assert s.daily_shift_history_days == 60


def test_load_settings_daily_shift_defaults_when_absent(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=a:b\nTELEGRAM_BREAKOUT_CHAT_ID=-1\nTELEGRAM_NEWS_CHAT_ID=-2\n",
                   encoding="utf-8")
    s = load_settings(str(cfg), str(env))
    assert s.daily_shift_enabled is True
    assert s.daily_shift_universe_file == "config/idx_all.txt"
    assert s.daily_shift_min_daily_value == 2_000_000_000
    assert s.daily_shift_min_price == 50
    assert s.daily_shift_max_alerts == 15
    assert s.daily_shift_history_days == 90
