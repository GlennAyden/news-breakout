import pandas as pd
from news_breakout.config import load_settings
from news_breakout.data import supabase_source as ss


def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "svc")
    return load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))


def test_rows_become_yfinance_shaped_frames(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)
    rows = [
        {"ticker": "ANTM", "ts": "2026-07-16T02:00:00+00:00", "open": 1, "high": 3, "low": 1, "close": 2, "volume": 100},
        {"ticker": "ANTM", "ts": "2026-07-17T02:00:00+00:00", "open": 2, "high": 4, "low": 2, "close": 3, "volume": 200},
        {"ticker": "BUMI", "ts": "2026-07-17T02:00:00+00:00", "open": 5, "high": 6, "low": 4, "close": 5, "volume": 50},
    ]
    captured = {}

    def fake_get(url, headers, params):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return rows

    out = ss.load_daily_bars(s, ["ANTM", "BUMI"], http_get=fake_get)

    # correct endpoint + auth + filters
    assert captured["url"] == "https://proj.supabase.co/rest/v1/price_bars"
    assert captured["headers"]["apikey"] == "svc"
    assert captured["headers"]["Authorization"] == "Bearer svc"
    assert captured["params"]["interval"] == "eq.1d"
    assert captured["params"]["ticker"] == "in.(ANTM,BUMI)"

    # shape contract
    assert set(out) == {"ANTM", "BUMI"}
    df = out["ANTM"]
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "Asia/Jakarta"
    assert len(df) == 2
    assert df["Close"].tolist() == [2.0, 3.0]
    # chronological
    assert df.index.is_monotonic_increasing


def test_missing_creds_returns_empty(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)
    object.__setattr__(s, "supabase_url", "")
    called = {"n": 0}

    def fake_get(url, headers, params):
        called["n"] += 1
        return []

    out = ss.load_intraday_bars(s, ["ANTM"], http_get=fake_get)
    assert out == {}
    assert called["n"] == 0  # never hits the network without creds


def test_http_error_degrades_to_empty(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)

    def boom(url, headers, params):
        raise RuntimeError("network down")

    assert ss.load_daily_bars(s, ["ANTM"], http_get=boom) == {}


def test_make_daily_fetcher_has_dropin_signature(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path)

    def fake_get(url, headers, params):
        return [{"ticker": "ANTM", "ts": "2026-07-17T02:00:00+00:00",
                 "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]

    fetch = ss.make_daily_fetcher(s, http_get=fake_get)
    out = fetch(["ANTM"], 120)  # same (tickers, history_days) call as run_scan uses
    assert "ANTM" in out and list(out["ANTM"].columns) == ["Open", "High", "Low", "Close", "Volume"]
