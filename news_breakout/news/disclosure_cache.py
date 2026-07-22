from __future__ import annotations

import logging
from datetime import datetime, timedelta

from news_breakout.news.idx_source import fetch_disclosures_ex
from news_breakout.news.models import Disclosure

logger = logging.getLogger("news_breakout")


class DisclosureCache:
    """One canonical IDX disclosure fetch shared by the news feed and scan booster.

    - Always fetches ``page_size`` rows (the caller-passed size is ignored) so the
      48h booster window is fully covered and both consumers share one fetch.
    - Within ``ttl_minutes`` of the last SUCCESSFUL fetch, returns the cached list.
    - On fetch failure: serves the last good list (stale-while-error) and bumps
      ``consecutive_failures``; a success resets it. A failure never refreshes the
      TTL clock, so the next tick tries again.
    """

    def __init__(self, page_size: int, ttl_minutes: int, *, fetcher=fetch_disclosures_ex):
        self._page_size = page_size
        self._ttl = timedelta(minutes=ttl_minutes)
        self._fetcher = fetcher
        self._cached: list[Disclosure] = []
        self._fetched_at: datetime | None = None
        self.consecutive_failures = 0

    def fetch(self, page_size, *, now, proxy: str = "", retries=None, **_) -> list[Disclosure]:
        if self._fetched_at is not None and now - self._fetched_at < self._ttl:
            return self._cached
        kwargs = {"now": now, "proxy": proxy}
        if retries is not None:
            kwargs["retries"] = retries
        try:
            items, ok = self._fetcher(self._page_size, **kwargs)
        except Exception:  # noqa: BLE001 — a fetch crash degrades like a failed fetch
            items, ok = [], False
        if ok:
            self._cached = items
            self._fetched_at = now
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            logger.warning("disclosure cache: fetch failed (%d consecutive); serving %d stale items",
                           self.consecutive_failures, len(self._cached))
        return self._cached if not ok else items
