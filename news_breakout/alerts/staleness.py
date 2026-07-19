from __future__ import annotations

from datetime import datetime

import pandas as pd


def check_price_staleness(
    daily_data: dict[str, "pd.DataFrame"],
    intraday_data: dict[str, "pd.DataFrame"],
    now: datetime,
    *,
    max_intraday_age_minutes: int = 90,
) -> str | None:
    """Return a warning string if the price data looks stale (fetcher likely failed), else None."""
    freshest = _freshest_timestamp(intraday_data)
    if freshest is None:
        # No intraday bars. Only a *total* outage (no daily either) is worth a
        # warning — a daily-only scan (normal EOD data, always >90m old) must
        # NOT be flagged stale, or every daily-only run would false-alarm.
        if _freshest_timestamp(daily_data) is None:
            return "⚠️ Tidak ada data harga — fetcher/Supabase mungkin gagal"
        return None

    age_minutes = (now - freshest).total_seconds() / 60
    if age_minutes > max_intraday_age_minutes:
        return (
            f"⚠️ Data harga basi — bar 60m terbaru {int(age_minutes)} menit lalu "
            f"(>{max_intraday_age_minutes}m); fetcher GitHub Actions mungkin gagal"
        )
    return None


def _freshest_timestamp(data: dict[str, "pd.DataFrame"]) -> datetime | None:
    freshest: datetime | None = None
    for df in data.values():
        if df is None or len(df.index) == 0:
            continue
        candidate = df.index.max()
        if hasattr(candidate, "to_pydatetime"):
            candidate = candidate.to_pydatetime()
        if freshest is None or candidate > freshest:
            freshest = candidate
    return freshest
