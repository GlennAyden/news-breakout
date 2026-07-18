import pandas as pd
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "fetch_to_supabase", Path("scripts/fetch_to_supabase.py")
)
fts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fts)


def _frame(tz):
    idx = pd.to_datetime(["2026-07-17 09:00", "2026-07-17 10:00"])
    if tz:
        idx = idx.tz_localize("Asia/Jakarta")
    return pd.DataFrame(
        {"Open": [1.0, 2.0], "High": [2.0, 3.0], "Low": [1.0, 2.0],
         "Close": [2.0, 3.0], "Volume": [10, 20]}, index=idx)


def test_to_rows_serializes_utc_iso_and_floats():
    rows = fts.to_rows(_frame(tz=True), "ANTM", "60m")
    assert len(rows) == 2
    r = rows[0]
    assert r["ticker"] == "ANTM" and r["interval"] == "60m"
    assert r["ts"].endswith("+00:00")           # tz-aware UTC
    assert r["ts"].startswith("2026-07-17T02")  # 09:00 WIB -> 02:00 UTC
    assert r["close"] == 2.0 and r["volume"] == 10


def test_to_rows_localizes_naive_daily_index():
    rows = fts.to_rows(_frame(tz=False), "ANTM", "1d")
    # naive index is treated as WIB then converted to UTC (no crash, tz-aware out)
    assert rows[0]["ts"].endswith("+00:00")


def test_to_rows_skips_nan_close():
    df = _frame(tz=True)
    df.loc[df.index[1], "Close"] = float("nan")
    rows = fts.to_rows(df, "ANTM", "60m")
    assert len(rows) == 1


def test_fetch_all_covers_both_intervals():
    def fake_downloader(jk, **kw):
        # emulate yfinance group_by="ticker": columns MultiIndex (ticker, field)
        frames = {}
        for sym in jk:
            f = _frame(tz=True)
            f.columns = pd.MultiIndex.from_product([[sym], f.columns])
            frames[sym] = f
        return pd.concat(frames.values(), axis=1)

    rows = fts.fetch_all(["ANTM", "BUMI"], 120, 60, fake_downloader)
    intervals = {r["interval"] for r in rows}
    assert intervals == {"1d", "60m"}
    assert {r["ticker"] for r in rows} == {"ANTM", "BUMI"}


def test_upsert_chunks_and_sets_merge_header():
    sent = []

    def poster(url, headers, json):
        sent.append((url, headers, len(json)))
        return 201

    rows = [{"ticker": "ANTM", "interval": "1d", "ts": "x", "open": 1, "high": 1,
             "low": 1, "close": 1, "volume": 1} for _ in range(1200)]
    fts.upsert(rows, "https://proj.supabase.co", "svc", poster=poster)
    assert sent[0][0] == "https://proj.supabase.co/rest/v1/price_bars"
    assert sent[0][1]["Prefer"] == "resolution=merge-duplicates"
    assert sent[0][1]["Authorization"] == "Bearer svc"
    assert [n for _, _, n in sent] == [500, 500, 200]  # chunked by 500
