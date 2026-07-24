import pandas as pd
from news_breakout.data.ajaib_source import (
    parse_candlestick, fetch_candlestick, fetch_many, countback_for_days,
)


_BODY = {"err_code": "EC0000000", "err_message": "APPROVED/OK", "result": {"points": [
    {"from_time": 1782276300000, "to_time": 1782277198992, "open": 6075, "high": 6100,
     "low": 6050, "close": 6090, "volume": 2133300},
    {"from_time": 1782282600000, "to_time": 1782283497813, "open": 6090, "high": 6120,
     "low": 6080, "close": 6110, "volume": 1800000},
]}}


def test_parse_candlestick_builds_ohlcv_utc_ascending():
    df = parse_candlestick(_BODY)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 2
    assert str(df.index.tz) == "UTC"
    assert df.index.is_monotonic_increasing
    assert df["Close"].iloc[0] == 6090 and df["Volume"].iloc[1] == 1800000


def test_parse_candlestick_empty_points_is_empty_frame():
    assert parse_candlestick({"result": {"points": []}}).empty


def test_parse_candlestick_dedupes_duplicate_from_time():
    body = {"result": {"points": [
        {"from_time": 1782276300000, "to_time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 10},
        {"from_time": 1782276300000, "to_time": 2, "open": 2, "high": 2, "low": 2, "close": 2, "volume": 20},
    ]}}
    df = parse_candlestick(body)
    assert len(df) == 1
    assert df["Close"].iloc[0] == 2 and df["Volume"].iloc[0] == 20  # keeps the last


def test_fetch_candlestick_calls_endpoint_with_params_and_jwt_scheme():
    seen = {}
    def http_get(url, headers, params):
        seen["url"] = url; seen["headers"] = headers; seen["params"] = params
        return 200, _BODY
    df = fetch_candlestick("BBCA", "AT", resolution="1D", countback=800, http_get=http_get)
    assert df is not None and len(df) == 2
    assert seen["url"].endswith("/stock/detail/BBCA/candlestick/")
    assert seen["params"] == {"resolution": "1D", "countback": 800}
    assert seen["headers"]["Authorization"] == "jwt AT"  # scheme is 'jwt', not 'Bearer'


def test_fetch_candlestick_returns_none_on_401_no_retry():
    calls = {"n": 0}
    def http_get(url, headers, params):
        calls["n"] += 1
        return 401, {"non_field_errors": ["Your session has expired"]}
    df = fetch_candlestick("BBCA", "AT", resolution="1D", countback=10, http_get=http_get)
    assert df is None and calls["n"] == 1  # no unattended refresh/retry


def test_fetch_candlestick_returns_none_on_error_status():
    def http_get(url, headers, params):
        return 500, {}
    assert fetch_candlestick("BBCA", "AT", resolution="1D", countback=10, http_get=http_get) is None


def test_fetch_candlestick_returns_none_on_bad_shape():
    def http_get(url, headers, params):
        return 200, {"unexpected": True}
    assert fetch_candlestick("BBCA", "AT", resolution="1D", countback=10, http_get=http_get) is None


def test_fetch_many_skips_empty_and_throttles():
    slept = []
    def http_get(url, headers, params):
        return (200, _BODY) if "BBCA" in url else (200, {"result": {"points": []}})
    out = fetch_many(["BBCA", "EMPTY"], "AT", resolution="1D", countback=10,
                     http_get=http_get, sleeper=slept.append, delay=0.3)
    assert set(out) == {"BBCA"}
    assert slept == [0.3, 0.3]  # throttled once per ticker


def test_countback_for_days_covers_trading_days_with_buffer():
    assert countback_for_days(90, "1D") >= 90
    assert countback_for_days(5, "15M") > 90  # intraday needs many bars per day
