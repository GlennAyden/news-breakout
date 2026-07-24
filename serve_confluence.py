from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

import run_confluence
from news_breakout.config import load_settings
from news_breakout.confluence.store import ConfluenceStore
from news_breakout.logging_setup import setup_logging

WIB = ZoneInfo("Asia/Jakarta")


def build_confluence_scheduler(settings, *, job, tz: str = "Asia/Jakarta") -> BlockingScheduler:
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(job, "interval", minutes=settings.scan_interval_minutes, id="confluence")
    return sched


def main() -> None:
    log = setup_logging()
    settings = load_settings()
    if not settings.confluence_enabled:
        log.info("confluence disabled; serve_confluence exiting")
        return
    os.makedirs("data_cache", exist_ok=True)
    store = ConfluenceStore("data_cache/confluence.sqlite")

    def job() -> None:
        sent = run_confluence.run_once(settings, now=datetime.now(WIB), store=store)
        log.info("confluence cycle complete; sent: %s", sent or "none")

    sched = build_confluence_scheduler(settings, job=job)
    log.info("confluence scheduler started; interval=%dm", settings.scan_interval_minutes)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        store.close()


if __name__ == "__main__":
    main()
