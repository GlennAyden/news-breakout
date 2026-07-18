from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from news_breakout.scheduling.market_calendar import is_market_open, parse_holidays


def should_scan_now(now: datetime, settings) -> bool:
    return is_market_open(
        now, parse_holidays(settings.holidays), settings.market_open, settings.market_close
    )


def build_scheduler(settings, *, scan_job, weekend_job, news_job, tz: str = "Asia/Jakarta") -> BlockingScheduler:
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(scan_job, "interval", minutes=settings.scan_interval_minutes, id="scan")
    sched.add_job(weekend_job, "cron", day_of_week=settings.weekend_scan_day, hour=8, id="weekend")
    sched.add_job(news_job, "interval", minutes=settings.news_poll_interval_minutes, id="news")
    return sched
