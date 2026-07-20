from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import load_settings
from news_breakout.logging_setup import setup_logging
from news_breakout.alerts.dedup import DedupStore
from news_breakout.scheduling.scheduler import should_scan_now, build_scheduler
from news_breakout.scheduling.weekend import run_weekend_scan
from news_breakout.news.feed import run_news_feed, run_portal_feed
from news_breakout.data.supabase_source import make_daily_fetcher, make_intraday_fetcher
import run

WIB = ZoneInfo("Asia/Jakarta")


def build_scan_job(settings, store, log):
    daily_fetcher = make_daily_fetcher(settings)
    intraday_fetcher = make_intraday_fetcher(settings)

    def scan_job() -> None:
        now = datetime.now(WIB)
        if not should_scan_now(now, settings):
            return
        alerted = run.run_scan(
            settings, store, now=now,
            daily_fetcher=daily_fetcher, intraday_fetcher=intraday_fetcher,
        )
        log.info("scan complete; alerted: %s", alerted or "none")

    return scan_job


def main() -> None:
    log = setup_logging()
    settings = load_settings()
    import os
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")

    scan_job = build_scan_job(settings, store, log)

    def weekend_job() -> None:
        now = datetime.now(WIB)
        log.info("weekend deep-scan starting")
        # read prices from Supabase (Yahoo is blocked from the VPS datacenter IP)
        run_weekend_scan(settings, now=now, daily_fetcher=make_daily_fetcher(settings))

    def news_job() -> None:
        now = datetime.now(WIB)
        sent = run_news_feed(settings, store, now=now)
        portal_sent = run_portal_feed(settings, store, now=now)
        log.info("news poll complete; sent: %d, portal sent: %d", len(sent), len(portal_sent))

    def daily_detect_job() -> None:
        from news_breakout.signals.daily_shift import run_daily_scan
        run_daily_scan(settings, store, now=datetime.now(WIB), mode="detect",
                       daily_fetcher=make_daily_fetcher(settings))

    def daily_reminder_job() -> None:
        from news_breakout.signals.daily_shift import run_daily_scan
        run_daily_scan(settings, store, now=datetime.now(WIB), mode="reminder",
                       daily_fetcher=make_daily_fetcher(settings))

    sched = build_scheduler(settings, scan_job=scan_job, weekend_job=weekend_job,
                            news_job=news_job, daily_detect_job=daily_detect_job,
                            daily_reminder_job=daily_reminder_job)
    log.info("scheduler started; jobs: %s", [j.id for j in sched.get_jobs()])
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        store.close()


if __name__ == "__main__":
    main()
