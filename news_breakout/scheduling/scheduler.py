from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from news_breakout.scheduling.market_calendar import is_market_open, parse_holidays


def should_scan_now(now: datetime, settings) -> bool:
    return is_market_open(
        now, parse_holidays(settings.holidays), settings.market_open, settings.market_close
    )


def build_scheduler(settings, *, scan_job, weekend_job, news_job,
                    daily_detect_job=None, daily_reminder_job=None,
                    tz: str = "Asia/Jakarta") -> BlockingScheduler:
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(scan_job, "interval", minutes=settings.scan_interval_minutes, id="scan")
    sched.add_job(weekend_job, "cron", day_of_week=settings.weekend_scan_day, hour=8, id="weekend")
    sched.add_job(news_job, "interval", minutes=settings.news_poll_interval_minutes, id="news")
    if settings.daily_shift_enabled and daily_detect_job is not None:
        sched.add_job(daily_detect_job, "cron", day_of_week="mon-fri", hour=16, minute=30,
                      id="daily_detect")
    if settings.daily_shift_enabled and daily_reminder_job is not None:
        sched.add_job(daily_reminder_job, "cron", day_of_week="mon-fri", hour=8, minute=0,
                      id="daily_reminder")
    return sched
