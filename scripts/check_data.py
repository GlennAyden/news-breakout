from news_breakout.config import load_settings
from news_breakout.data.yfinance_source import fetch_daily_ohlcv, report_availability

s = load_settings()
data = fetch_daily_ohlcv(s.watchlist, s.history_days)
report = report_availability(data, s.watchlist, min_bars=s.donchian_lookback + 1)
for ticker, status in sorted(report.items()):
    print(f"{ticker:6} {status}")
