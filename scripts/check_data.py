from news_breakout.config import load_settings
from news_breakout.data.yfinance_source import (
    fetch_daily_ohlcv, fetch_intraday_ohlcv, report_availability,
)

s = load_settings()
daily = fetch_daily_ohlcv(s.watchlist, s.history_days)
intra = fetch_intraday_ohlcv(s.watchlist, s.intraday_period_days)
d_report = report_availability(daily, s.watchlist, min_bars=s.donchian_lookback + 1)
i_report = report_availability(intra, s.watchlist, min_bars=s.donchian_lookback + 1)
print(f"{'ticker':7} {'1D':8} {'1H':8}")
for t in sorted(s.watchlist):
    print(f"{t:7} {d_report[t]:8} {i_report.get(t, 'missing'):8}")
