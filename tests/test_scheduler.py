from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import Settings
from news_breakout.scheduling.scheduler import should_scan_now, build_scheduler

WIB = ZoneInfo("Asia/Jakarta")


def _settings(**over):
    base = dict(
        watchlist=["ANTM"], donchian_lookback=20, rvol_threshold=2.0, rvol_window=20,
        history_days=120, range_lookback=30, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=["2026-07-17"],
        universe_candidates=[], min_price=50, min_daily_value=1_000_000_000,
    )
    base.update(over)
    return Settings(**base)


def test_should_scan_now_true_during_session():
    now = datetime(2026, 7, 16, 10, 30, tzinfo=WIB)  # Thursday 10:30
    assert should_scan_now(now, _settings()) is True


def test_should_scan_now_false_on_holiday_and_offhours():
    assert should_scan_now(datetime(2026, 7, 17, 10, 0, tzinfo=WIB), _settings()) is False  # holiday
    assert should_scan_now(datetime(2026, 7, 16, 7, 0, tzinfo=WIB), _settings()) is False   # pre-open


def test_build_scheduler_registers_two_jobs():
    sched = build_scheduler(_settings(), scan_job=lambda: None, weekend_job=lambda: None)
    ids = {j.id for j in sched.get_jobs()}
    assert ids == {"scan", "weekend"}
