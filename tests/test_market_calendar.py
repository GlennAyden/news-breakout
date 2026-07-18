from datetime import date, datetime
from zoneinfo import ZoneInfo

from news_breakout.scheduling.market_calendar import (
    parse_holidays, is_trading_day, is_market_open,
)

WIB = ZoneInfo("Asia/Jakarta")


def test_parse_holidays():
    hs = parse_holidays(["2026-01-01", "2026-03-31"])
    assert date(2026, 1, 1) in hs and date(2026, 3, 31) in hs


def test_trading_day_weekday_vs_weekend_vs_holiday():
    hs = parse_holidays(["2026-07-17"])  # a Friday, marked holiday
    assert is_trading_day(date(2026, 7, 16), hs) is True   # Thursday
    assert is_trading_day(date(2026, 7, 18), hs) is False  # Saturday
    assert is_trading_day(date(2026, 7, 17), hs) is False  # holiday Friday


def test_market_open_within_and_outside_hours():
    hs = set()
    # 2026-07-16 is a Thursday
    assert is_market_open(datetime(2026, 7, 16, 10, 0, tzinfo=WIB), hs, "09:00", "16:00") is True
    assert is_market_open(datetime(2026, 7, 16, 8, 0, tzinfo=WIB), hs, "09:00", "16:00") is False
    assert is_market_open(datetime(2026, 7, 16, 16, 30, tzinfo=WIB), hs, "09:00", "16:00") is False
    # Saturday -> closed regardless of time
    assert is_market_open(datetime(2026, 7, 18, 10, 0, tzinfo=WIB), hs, "09:00", "16:00") is False
