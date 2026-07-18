from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import load_settings
from news_breakout.logging_setup import setup_logging
from news_breakout.alerts.dedup import DedupStore
from news_breakout.scheduling.scheduler import should_scan_now, build_scheduler
from news_breakout.scheduling.weekend import run_weekend_scan
import run

WIB = ZoneInfo("Asia/Jakarta")


def main() -> None:
    log = setup_logging()
    settings = load_settings()
    import os
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")

    def scan_job() -> None:
        now = datetime.now(WIB)
        if not should_scan_now(now, settings):
            return
        alerted = run.run_scan(settings, store, now=now)
        log.info("scan complete; alerted: %s", alerted or "none")

    def weekend_job() -> None:
        now = datetime.now(WIB)
        log.info("weekend deep-scan starting")
        run_weekend_scan(settings, now=now)

    sched = build_scheduler(settings, scan_job=scan_job, weekend_job=weekend_job)
    log.info("scheduler started; jobs: %s", [j.id for j in sched.get_jobs()])
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        store.close()


if __name__ == "__main__":
    main()
