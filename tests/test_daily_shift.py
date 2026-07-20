from news_breakout.signals.daily_shift import load_daily_universe


def test_load_daily_universe_parses_and_dedupes(tmp_path):
    f = tmp_path / "idx.txt"
    f.write_text("# header comment\nANTM\nbbri\n\nANTM\n  TLKM  \n# trailing\n", encoding="utf-8")
    assert load_daily_universe(str(f)) == ["ANTM", "BBRI", "TLKM"]


def test_load_daily_universe_missing_file_returns_empty(tmp_path):
    assert load_daily_universe(str(tmp_path / "nope.txt")) == []


from datetime import datetime
from zoneinfo import ZoneInfo
from tests.fixtures import make_ohlcv
from news_breakout.config import Settings
from news_breakout.alerts.dedup import DedupStore
from news_breakout.signals.daily_shift import run_daily_scan

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 20, 16, 30, tzinfo=WIB)


def _settings(univ_file, **over):
    base = dict(
        watchlist=["ANTM"], donchian_lookback=3, rvol_threshold=2.0, rvol_window=3,
        history_days=120, range_lookback=3, range_max_width_pct=0.15, intraday_period_days=60,
        telegram_bot_token="t", telegram_breakout_chat_id="-1", dry_run=True,
        market_open="09:00", market_close="16:00", scan_interval_minutes=30,
        weekend_scan_day="sat", holidays=[], universe_candidates=["BBRI"], min_price=50,
        min_daily_value=1e9, telegram_news_chat_id="-2", curated_keywords=["dividen"],
        disclosure_page_size=50, news_poll_interval_minutes=60, idx_proxy="",
        daily_shift_universe_file=univ_file, daily_shift_min_daily_value=1e9,
        daily_shift_min_price=50, daily_shift_max_alerts=15, daily_shift_history_days=90,
    )
    base.update(over)
    return Settings(**base)


def _breakout_liquid(close):
    # high value (Close*Volume) so it passes the Rp liquidity floor
    return make_ohlcv(highs=[110, 108, 110, 116], lows=[100, 101, 102, 108],
                      closes=[100, 100, 100, close],
                      volumes=[10_000_000, 10_000_000, 10_000_000, 30_000_000])


def _no_disc(page_size, *, now, proxy, retries=0):
    return []


def test_run_daily_scan_detect_excludes_intraday_and_alerts(tmp_path):
    f = tmp_path / "idx.txt"
    f.write_text("ANTM\nBBRI\nBMRI\n", encoding="utf-8")  # ANTM=watchlist, BBRI=candidate (both intraday)
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = {"ANTM": _breakout_liquid(121), "BBRI": _breakout_liquid(121), "BMRI": _breakout_liquid(121)}
    out = run_daily_scan(_settings(str(f)), store, now=NOW, mode="detect",
                         daily_fetcher=lambda tickers, days: daily, sender=sender,
                         disclosure_fetcher=_no_disc)
    assert out == ["BMRI"]         # ANTM + BBRI excluded (intraday tier); only BMRI alerts
    assert len(sent) == 1
    store.close()


def test_run_daily_scan_reminder_sends_single_digest_and_dedups(tmp_path):
    f = tmp_path / "idx.txt"
    f.write_text("BMRI\nADRO\n", encoding="utf-8")
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None):
        sent.append(text)
        return True

    daily = {"BMRI": _breakout_liquid(121), "ADRO": _breakout_liquid(121)}
    kw = dict(daily_fetcher=lambda tickers, days: daily, sender=sender, disclosure_fetcher=_no_disc)
    first = run_daily_scan(_settings(str(f)), store, now=NOW, mode="reminder", **kw)
    assert len(sent) == 1 and "Watchlist Pagi" in sent[0]   # ONE digest, not 2 individual
    second = run_daily_scan(_settings(str(f)), store, now=NOW, mode="reminder", **kw)
    assert len(sent) == 1                                    # deduped once/day
    store.close()


def test_run_daily_scan_empty_universe_noops(tmp_path):
    store = DedupStore(":memory:")
    sent = []
    out = run_daily_scan(_settings(str(tmp_path / "missing.txt")), store, now=NOW, mode="detect",
                         daily_fetcher=lambda tickers, days: {},
                         sender=lambda *a, **k: sent.append(1) or True, disclosure_fetcher=_no_disc)
    assert out == [] and sent == []
    store.close()
