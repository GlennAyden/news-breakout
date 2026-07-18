from tests.fixtures import make_ohlcv
from news_breakout.data.universe import filter_liquid_universe


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
