from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.config import load_settings
from news_breakout.logging_setup import setup_logging
from news_breakout.alerts.dedup import DedupStore
from news_breakout.news.feed import run_news_feed

WIB = ZoneInfo("Asia/Jakarta")


def main() -> None:
    setup_logging()
    settings = load_settings()
    os.makedirs("data_cache", exist_ok=True)
    store = DedupStore("data_cache/dedup.sqlite")
    try:
        sent = run_news_feed(settings, store, now=datetime.now(WIB))
        print(f"News poll complete. Sent: {len(sent)}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
