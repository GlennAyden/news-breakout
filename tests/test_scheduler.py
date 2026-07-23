from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.config import Settings
from news_breakout.scheduling.scheduler import should_scan_now, should_poll_news, build_scheduler

WIB = ZoneInfo("Asia/Jakarta")


def _settings(**over):
    base = dict(
        watchlist=["ANTM"], donchian_lookback=20, rvol_threshold=2.0, rvol_window=20,
        history_days=120, range_lookback=30, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=["2026-07-17"],
        universe_candidates=[], min_price=50, min_daily_value=1_000_000_000,
        telegram_news_chat_id="-200", curated_keywords=["dividen"],
        disclosure_page_size=50, news_poll_interval_minutes=60, idx_proxy="",
    )
    base.update(over)
    return Settings(**base)


def test_should_scan_now_true_during_session():
    now = datetime(2026, 7, 16, 10, 30, tzinfo=WIB)  # Thursday 10:30
    assert should_scan_now(now, _settings()) is True


def test_should_scan_now_false_on_holiday_and_offhours():
    assert should_scan_now(datetime(2026, 7, 17, 10, 0, tzinfo=WIB), _settings()) is False  # holiday
    assert should_scan_now(datetime(2026, 7, 16, 7, 0, tzinfo=WIB), _settings()) is False   # pre-open


def test_build_scheduler_core_jobs_without_daily():
    sched = build_scheduler(_settings(daily_shift_enabled=False),
                            scan_job=lambda: None, weekend_job=lambda: None, news_job=lambda: None)
    assert {j.id for j in sched.get_jobs()} == {"scan", "weekend", "news"}


def test_build_scheduler_registers_daily_jobs_when_enabled():
    sched = build_scheduler(_settings(daily_shift_enabled=True),
                            scan_job=lambda: None, weekend_job=lambda: None, news_job=lambda: None,
                            daily_detect_job=lambda: None, daily_reminder_job=lambda: None)
    assert {j.id for j in sched.get_jobs()} == {
        "scan", "weekend", "news", "daily_detect", "daily_reminder"}


T0 = datetime(2026, 7, 22, 20, 0, tzinfo=ZoneInfo("Asia/Jakarta"))   # evening, off-hours


def test_poll_always_during_market_hours():
    assert should_poll_news(T0, T0 - timedelta(minutes=1),
                            market_open=True, offhours_minutes=60) is True


def test_poll_offhours_gated_by_elapsed_time():
    assert should_poll_news(T0, None, market_open=False, offhours_minutes=60) is True
    assert should_poll_news(T0, T0 - timedelta(minutes=59),
                            market_open=False, offhours_minutes=60) is False
    assert should_poll_news(T0, T0 - timedelta(minutes=60),
                            market_open=False, offhours_minutes=60) is True


def test_news_job_scheduled_at_market_cadence():
    sched = build_scheduler(_settings(), scan_job=lambda: None,
                            weekend_job=lambda: None, news_job=lambda: None)
    news = next(j for j in sched.get_jobs() if j.id == "news")
    assert news.trigger.interval == timedelta(minutes=15)
