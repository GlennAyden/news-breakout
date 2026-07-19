from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from news_breakout.alerts.staleness import check_price_staleness

TZ = ZoneInfo("Asia/Jakarta")


def _frame(ts: datetime) -> pd.DataFrame:
    idx = pd.DatetimeIndex([ts], tz=TZ)
    return pd.DataFrame(
        {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.5], "Volume": [1000]},
        index=idx,
    )


def test_fresh_intraday_returns_none():
    now = datetime(2026, 7, 17, 15, 30, tzinfo=TZ)
    intraday_data = {"ANTM": _frame(now)}
    daily_data = {"ANTM": _frame(now - timedelta(days=1))}
    assert check_price_staleness(daily_data, intraday_data, now) is None


def test_stale_intraday_returns_warning_with_basi():
    now = datetime(2026, 7, 17, 15, 30, tzinfo=TZ)
    stale_ts = now - timedelta(hours=3)
    intraday_data = {"ANTM": _frame(stale_ts)}
    daily_data = {"ANTM": _frame(now - timedelta(days=1))}
    warning = check_price_staleness(daily_data, intraday_data, now)
    assert warning is not None
    assert "basi" in warning


def test_both_empty_returns_warning():
    now = datetime(2026, 7, 17, 15, 30, tzinfo=TZ)
    warning = check_price_staleness({}, {}, now)
    assert warning is not None
    assert "⚠️" in warning


def test_no_crash_with_tz_aware_jakarta_index():
    now = datetime(2026, 7, 17, 15, 30, tzinfo=TZ)
    intraday_data = {
        "ANTM": _frame(now - timedelta(minutes=10)),
        "BBRI": _frame(now - timedelta(minutes=5)),
    }
    daily_data = {"ANTM": _frame(now - timedelta(days=1))}
    result = check_price_staleness(daily_data, intraday_data, now)
    assert result is None


def test_daily_only_no_intraday_does_not_flag():
    # A daily-only scan (no intraday bars) must NOT be flagged stale even though
    # the daily bar is >90m old — daily is EOD data, that's normal.
    now = datetime(2026, 7, 17, 15, 30, tzinfo=TZ)
    daily_data = {"ANTM": _frame(now - timedelta(days=1))}
    assert check_price_staleness(daily_data, {}, now) is None


def test_custom_max_age_threshold():
    now = datetime(2026, 7, 17, 15, 30, tzinfo=TZ)
    intraday_data = {"ANTM": _frame(now - timedelta(minutes=45))}
    daily_data: dict[str, pd.DataFrame] = {}
    assert check_price_staleness(daily_data, intraday_data, now, max_intraday_age_minutes=90) is None
    assert check_price_staleness(daily_data, intraday_data, now, max_intraday_age_minutes=30) is not None
