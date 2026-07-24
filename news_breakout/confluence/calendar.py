from __future__ import annotations

from datetime import date, datetime, timedelta

from news_breakout.scheduling.market_calendar import is_trading_day


def add_trading_days(start: datetime, n: int, holidays: set[date]) -> datetime:
    """Advance ``start`` by ``n`` trading days (weekends + holidays skipped).

    Time-of-day is preserved. ``n <= 0`` returns ``start`` unchanged.
    """
    if n <= 0:
        return start
    d = start
    remaining = n
    while remaining > 0:
        d = d + timedelta(days=1)
        if is_trading_day(d.date(), holidays):
            remaining -= 1
    return d
