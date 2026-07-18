from __future__ import annotations

from datetime import date, datetime, time


def parse_holidays(items: list[str]) -> set[date]:
    return {date.fromisoformat(x) for x in items}


def is_trading_day(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def is_market_open(
    dt: datetime, holidays: set[date], open_str: str, close_str: str
) -> bool:
    if not is_trading_day(dt.date(), holidays):
        return False
    return time.fromisoformat(open_str) <= dt.time() <= time.fromisoformat(close_str)
