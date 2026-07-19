import pandas as pd
import importlib.util
import textwrap
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "fetch_to_supabase", Path("scripts/fetch_to_supabase.py")
)
fts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fts)


def test_load_config_returns_watchlist_history_intraday_and_universe_candidates(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(textwrap.dedent("""\
        watchlist:
          - ANTM
          - BUMI
        data:
          history_days: 120
          intraday_period_days: 60
        universe:
          candidates:
            - BBCA
            - BBRI
        """), encoding="utf-8")
    watchlist, history_days, intraday_days, universe_candidates = fts.load_config(str(cfg))
    assert watchlist == ["ANTM", "BUMI"]
    assert history_days == 120
    assert intraday_days == 60
    assert universe_candidates == ["BBCA", "BBRI"]


def test_load_config_defaults_universe_candidates_to_empty_list(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(textwrap.dedent("""\
        watchlist:
          - ANTM
        data:
          history_days: 120
          intraday_period_days: 60
        """), encoding="utf-8")
    _, _, _, universe_candidates = fts.load_config(str(cfg))
    assert universe_candidates == []


def test_normalize_supabase_url():
    assert fts._normalize_supabase_url("plqegxlzzedwwsluykxo") == "https://plqegxlzzedwwsluykxo.supabase.co"
    assert fts._normalize_supabase_url("proj.supabase.co") == "https://proj.supabase.co"
    assert fts._normalize_supabase_url("https://proj.supabase.co/") == "https://proj.supabase.co"
    assert fts._normalize_supabase_url("") == ""


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


def test_fetch_all_dedupes_duplicate_timestamps():
    def fake_downloader(jk, **kw):
        # yfinance's still-forming last bar can repeat a timestamp.
        idx = pd.to_datetime(
            ["2026-07-17 09:00", "2026-07-17 10:00", "2026-07-17 10:00"]
        ).tz_localize("Asia/Jakarta")
        frames = {}
        for sym in jk:
            f = pd.DataFrame(
                {"Open": [1.0, 2.0, 2.5], "High": [2.0, 3.0, 3.5], "Low": [1.0, 2.0, 2.5],
                 "Close": [2.0, 3.0, 3.5], "Volume": [10, 20, 25]}, index=idx)
            f.columns = pd.MultiIndex.from_product([[sym], f.columns])
            frames[sym] = f
        return pd.concat(frames.values(), axis=1)

    rows = fts.fetch_all(["ANTM"], 120, 60, fake_downloader)
    daily_rows = [r for r in rows if r["ticker"] == "ANTM" and r["interval"] == "1d"]
    ts_list = [r["ts"] for r in daily_rows]

    assert len(ts_list) == len(set(ts_list))
    # the kept row for the duplicated timestamp must be the last one (Close 3.5)
    dup_ts = max(ts_list)
    dup_row = next(r for r in daily_rows if r["ts"] == dup_ts)
    assert dup_row["close"] == 3.5


def test_upsert_chunks_and_sets_merge_header():
    sent = []

    def poster(url, headers, json):
        sent.append((url, headers, len(json)))
        return 201

    rows = [{"ticker": "ANTM", "interval": "1d", "ts": "x", "open": 1, "high": 1,
             "low": 1, "close": 1, "volume": 1} for _ in range(1200)]
    assert fts.upsert(rows, "https://proj.supabase.co", "svc", poster=poster) is True
    assert sent[0][0] == "https://proj.supabase.co/rest/v1/price_bars"
    assert sent[0][1]["Prefer"] == "resolution=merge-duplicates"
    assert sent[0][1]["Authorization"] == "Bearer svc"
    assert [n for _, _, n in sent] == [500, 500, 200]  # chunked by 500


def test_upsert_returns_false_on_non_2xx():
    def poster(url, headers, json):
        return 500

    rows = [{"ticker": "ANTM", "interval": "1d", "ts": "x", "open": 1, "high": 1,
             "low": 1, "close": 1, "volume": 1}]
    assert fts.upsert(rows, "https://p.supabase.co", "svc", poster=poster) is False
