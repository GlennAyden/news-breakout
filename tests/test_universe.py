from tests.fixtures import make_ohlcv
from news_breakout.data.universe import filter_liquid_universe, resolve_scan_tickers


def test_filters_by_price_and_value():
    data = {
        "LIQD": make_ohlcv(  # price 1000, value 1000*2000 = 2M/bar
            highs=[1000] * 5, lows=[1000] * 5, closes=[1000] * 5, volumes=[2000] * 5),
        "CHEAP": make_ohlcv(  # price 40 < 50 -> excluded
            highs=[40] * 5, lows=[40] * 5, closes=[40] * 5, volumes=[100000] * 5),
        "ILLQ": make_ohlcv(  # price 1000 but value 1000*10 = 10k < 1M -> excluded
            highs=[1000] * 5, lows=[1000] * 5, closes=[1000] * 5, volumes=[10] * 5),
    }
    out = filter_liquid_universe(
        ["LIQD", "CHEAP", "ILLQ", "NODATA"], data,
        min_price=50, min_daily_value=1_000_000, value_window=5,
    )
    assert out == ["LIQD"]


def _liquid_bar(price=1000, volume=2000):
    return make_ohlcv(highs=[price] * 5, lows=[price] * 5, closes=[price] * 5, volumes=[volume] * 5)


def test_resolve_scan_tickers_always_includes_full_watchlist():
    # watchlist tickers have no price data at all (illiquid/missing) but must
    # still be included, unfiltered.
    watchlist = ["ANTM", "BUMI"]
    data = {}
    out = resolve_scan_tickers(
        watchlist, candidates=[], daily_data=data,
        min_price=50, min_daily_value=1_000_000,
    )
    assert out == ["ANTM", "BUMI"]


def test_resolve_scan_tickers_appends_liquid_candidate():
    watchlist = ["ANTM"]
    candidates = ["BBCA"]
    data = {"BBCA": _liquid_bar()}
    out = resolve_scan_tickers(
        watchlist, candidates, data,
        min_price=50, min_daily_value=1_000_000,
    )
    assert out == ["ANTM", "BBCA"]


def test_resolve_scan_tickers_drops_illiquid_candidate():
    watchlist = ["ANTM"]
    candidates = ["CHEAP"]
    data = {"CHEAP": make_ohlcv(highs=[40] * 5, lows=[40] * 5, closes=[40] * 5, volumes=[100000] * 5)}
    out = resolve_scan_tickers(
        watchlist, candidates, data,
        min_price=50, min_daily_value=1_000_000,
    )
    assert out == ["ANTM"]


def test_resolve_scan_tickers_no_duplicate_when_candidate_in_watchlist():
    watchlist = ["ANTM", "BBCA"]
    candidates = ["BBCA", "BBRI"]
    data = {"BBCA": _liquid_bar(), "BBRI": _liquid_bar()}
    out = resolve_scan_tickers(
        watchlist, candidates, data,
        min_price=50, min_daily_value=1_000_000,
    )
    assert out == ["ANTM", "BBCA", "BBRI"]
    assert out.count("BBCA") == 1


def test_resolve_scan_tickers_preserves_order_watchlist_then_candidates():
    watchlist = ["BUMI", "ANTM"]
    candidates = ["BBRI", "BBCA"]
    data = {"BBRI": _liquid_bar(), "BBCA": _liquid_bar()}
    out = resolve_scan_tickers(
        watchlist, candidates, data,
        min_price=50, min_daily_value=1_000_000,
    )
    assert out == ["BUMI", "ANTM", "BBRI", "BBCA"]
