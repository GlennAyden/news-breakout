from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import load_settings
from news_breakout.logging_setup import setup_logging
from news_breakout.alerts.dedup import DedupStore
from news_breakout.scheduling.scheduler import should_scan_now, build_scheduler, should_poll_news
from news_breakout.scheduling.weekend import run_weekend_scan
from news_breakout.news.feed import run_news_feed, run_portal_feed
from news_breakout.news.disclosure_cache import DisclosureCache
from news_breakout.data.supabase_source import make_daily_fetcher, make_intraday_fetcher
import run

WIB = ZoneInfo("Asia/Jakarta")


def build_scan_job(settings, store, log, cache):
    daily_fetcher = make_daily_fetcher(settings)
    intraday_fetcher = make_intraday_fetcher(settings)

    def scan_job() -> None:
        now = datetime.now(WIB)
        if not should_scan_now(now, settings):
            return
        alerted = run.run_scan(
            settings, store, now=now,
            daily_fetcher=daily_fetcher, intraday_fetcher=intraday_fetcher,
            disclosure_fetcher=cache.fetch,
        )
        log.info("scan complete; alerted: %s", alerted or "none")

    return scan_job


def build_news_job(settings, store, log, cache, *, now_fn=None):
    if now_fn is None:
        now_fn = lambda: datetime.now(WIB)  # noqa: E731
    last_run = {"t": None}

    def news_job() -> None:
        now = now_fn()
        if not should_poll_news(now, last_run["t"],
                                market_open=should_scan_now(now, settings),
                                offhours_minutes=settings.poll_interval_offhours_minutes):
            return
        last_run["t"] = now
        sent = run_news_feed(settings, store, now=now, fetcher=cache.fetch,
                             failure_streak=lambda: cache.consecutive_failures)
        portal_sent = run_portal_feed(settings, store, now=now)
        store.prune_news(settings.news_dedup_retention_days, now=now)
        log.info("news poll complete; sent: %d, portal sent: %d", len(sent), len(portal_sent))

    return news_job


def main() -> None:
    log = setup_logging()
    settings = load_settings()
    import os
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")

    cache = DisclosureCache(settings.news_booster_page_size,
                            settings.news_fetch_cache_ttl_minutes)
    scan_job = build_scan_job(settings, store, log, cache)
    news_job = build_news_job(settings, store, log, cache)

    def weekend_job() -> None:
        now = datetime.now(WIB)
        log.info("weekend deep-scan starting")
        # read prices from Supabase (Yahoo is blocked from the VPS datacenter IP)
        run_weekend_scan(settings, now=now, daily_fetcher=make_daily_fetcher(settings))

    def daily_detect_job() -> None:
        from news_breakout.signals.daily_shift import run_daily_scan
        run_daily_scan(settings, store, now=datetime.now(WIB), mode="detect",
                       daily_fetcher=make_daily_fetcher(settings),
                       disclosure_fetcher=cache.fetch)

    def daily_reminder_job() -> None:
        from news_breakout.signals.daily_shift import run_daily_scan
        run_daily_scan(settings, store, now=datetime.now(WIB), mode="reminder",
                       daily_fetcher=make_daily_fetcher(settings),
                       disclosure_fetcher=cache.fetch)

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
