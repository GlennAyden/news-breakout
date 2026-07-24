from datetime import date, datetime
from zoneinfo import ZoneInfo

from news_breakout.confluence.calendar import add_trading_days

WIB = ZoneInfo("Asia/Jakarta")


def test_one_trading_day_skips_the_weekend():
    start = datetime(2026, 7, 24, 9, 30, tzinfo=WIB)  # a Friday
    assert start.weekday() == 4                       # guard: fixture really is Friday
    out = add_trading_days(start, 1, set())
    assert out.date() == date(2026, 7, 27)            # Monday
    assert (out.hour, out.minute) == (9, 30)          # time-of-day preserved


def test_five_trading_days_from_friday_is_next_friday():
    start = datetime(2026, 7, 24, 12, 0, tzinfo=WIB)  # Friday
    out = add_trading_days(start, 5, set())
    assert out.date() == date(2026, 7, 31)            # Mon..Fri = 5 trading days


def test_holiday_is_skipped():
    start = datetime(2026, 7, 24, 12, 0, tzinfo=WIB)  # Friday
    out = add_trading_days(start, 1, {date(2026, 7, 27)})  # Monday is a holiday
    assert out.date() == date(2026, 7, 28)            # Tuesday


def test_non_positive_n_returns_start():
    start = datetime(2026, 7, 24, 12, 0, tzinfo=WIB)
    assert add_trading_days(start, 0, set()) == start
