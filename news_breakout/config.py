from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class Settings(BaseModel):
    watchlist: list[str]
    donchian_lookback: int
    rvol_threshold: float
    rvol_window: int
    min_quality_score: float | None = None
    history_days: int
    range_lookback: int
    range_max_width_pct: float
    intraday_period_days: int
    telegram_bot_token: str
    telegram_breakout_chat_id: str
    dry_run: bool
    market_open: str
    market_close: str
    scan_interval_minutes: int
    weekend_scan_day: str
    holidays: list[str]
    universe_candidates: list[str]
    min_price: float
    min_daily_value: float
    telegram_news_chat_id: str
    curated_keywords: list[str]
    disclosure_page_size: int
    news_poll_interval_minutes: int
    idx_proxy: str
    news_booster_window_hours: int = 48
    news_priority_boost: float = 3.0
    portal_enabled: bool = False
    portal_sources: list = []  # each item is a url string, or {"url": ..., "parser": ...}
    portal_name_map: dict[str, str] = {}
    supabase_url: str = ""
    supabase_key: str = ""
    price_staleness_max_minutes: int = 150
    portal_summary_sentences: int = 2
    portal_max_per_run: int = 20
    sentiment_enabled: bool = True
    sentiment_model: str = "w11wo/indonesian-roberta-base-sentiment-classifier"
    sentiment_min_confidence: float = 0.6
    elliott_enabled: bool = True
    elliott_atr_scales: list[float] = [2.0, 3.5, 5.0]
    elliott_atr_window: int = 14
    elliott_max_pivots: int = 9
    elliott_fib_tolerance: float = 0.06
    elliott_min_confidence: float = 0.45
    elliott_show_ambiguous: bool = False
    daily_shift_enabled: bool = True
    daily_shift_universe_file: str = "config/idx_all.txt"
    daily_shift_min_daily_value: float = 2_000_000_000
    daily_shift_min_price: float = 50
    daily_shift_max_alerts: int = 15
    daily_shift_history_days: int = 90
    news_booster_page_size: int = 200
    news_fetch_cache_ttl_minutes: int = 10
    news_outage_max_failures: int = 4
    poll_interval_market_minutes: int = 15
    poll_interval_offhours_minutes: int = 60
    news_watchlist_passthrough: bool = True
    news_dedup_retention_days: int = 90
    portal_dup_title_threshold: float = 0.55
    portal_fetch_workers: int = 4
    portal_proxy: str = ""
    portal_name_map_file: str = "config/name_map.yaml"
    portal_drop_categories: list[str] = ["tata_kelola", "pasar_opini"]
    orderbook_enabled: bool = False
    orderbook_max_symbols_per_scan: int = 15
    orderbook_request_delay_seconds: float = 0.7
    orderbook_window_after_open_minutes: int = 30
    orderbook_early_volume_min_ratio: float = 0.5
    orderbook_phase_rm_balance_min_ratio: float = 0.85
    stockbit_refresh_token: str = ""
    stockbit_access_token: str = ""
    telegram_orderbook_chat_id: str = ""


def _load_env_file(env_path: str) -> None:
    """Minimal .env loader: KEY=VALUE lines into os.environ (no override)."""
    p = Path(env_path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _load_name_map_file(path: str) -> dict[str, str]:
    """Optional YAML file of lowercase company name -> ticker; missing/null -> {}."""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip().lower(): str(v).strip().upper() for k, v in data.items()}


def _normalize_supabase_url(raw: str) -> str:
    """Tolerate a bare project ref or a scheme-less host in SUPABASE_URL.

    Supabase project URLs are always ``https://<ref>.supabase.co``; users often
    paste just the ref or drop the scheme. Normalize to a full URL (empty stays
    empty so the reader's missing-creds short-circuit still applies).
    """
    u = (raw or "").strip().rstrip("/")
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    host = u.split("://", 1)[-1]
    if "." not in host:  # bare project ref -> full supabase host
        u = f"https://{host}.supabase.co"
    return u


def load_settings(
    config_path: str = "config/config.yaml", env_path: str = ".env"
) -> Settings:
    _load_env_file(env_path)
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    signals = raw.get("signals", {})
    data = raw.get("data", {})
    runtime = raw.get("runtime", {})
    schedule = raw.get("schedule", {})
    universe = raw.get("universe", {})
    news = raw.get("news", {})
    portal = raw.get("portal", {})
    sentiment = raw.get("sentiment", {})
    elliott = raw.get("elliott", {})
    daily_shift = raw.get("daily_shift", {})
    orderbook = raw.get("orderbook", {})
    ob_volume = orderbook.get("early_volume", {})
    ob_phase = orderbook.get("phase", {})
    return Settings(
        watchlist=raw["watchlist"],
        donchian_lookback=signals["donchian_lookback"],
        rvol_threshold=signals["rvol_threshold"],
        rvol_window=signals["rvol_window"],
        min_quality_score=signals.get("min_quality_score"),
        history_days=data["history_days"],
        range_lookback=signals["range_lookback"],
        range_max_width_pct=signals["range_max_width_pct"],
        intraday_period_days=data["intraday_period_days"],
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_breakout_chat_id=os.environ["TELEGRAM_BREAKOUT_CHAT_ID"],
        dry_run=runtime["dry_run"],
        market_open=schedule["market_open"],
        market_close=schedule["market_close"],
        scan_interval_minutes=schedule["scan_interval_minutes"],
        weekend_scan_day=schedule["weekend_scan_day"],
        holidays=schedule["holidays"],
        universe_candidates=universe["candidates"],
        min_price=universe["min_price"],
        min_daily_value=universe["min_daily_value"],
        telegram_news_chat_id=os.environ["TELEGRAM_NEWS_CHAT_ID"],
        curated_keywords=news["curated_keywords"],
        disclosure_page_size=news["disclosure_page_size"],
        news_poll_interval_minutes=news["news_poll_interval_minutes"],
        idx_proxy=os.environ.get("IDX_PROXY", ""),
        news_booster_window_hours=news.get("booster_window_hours", 48),
        news_priority_boost=news.get("priority_boost", 3.0),
        portal_enabled=portal.get("enabled", False),
        portal_sources=portal.get("sources", []),
        portal_name_map={
            **_load_name_map_file(portal.get("name_map_file", "config/name_map.yaml") or ""),
            **portal.get("name_map", {}),
        },
        portal_name_map_file=portal.get("name_map_file", "config/name_map.yaml") or "",
        portal_summary_sentences=portal.get("summary_sentences", 2),
        portal_max_per_run=portal.get("max_per_run", 20),
        sentiment_enabled=sentiment.get("enabled", True),
        sentiment_model=sentiment.get("model", "w11wo/indonesian-roberta-base-sentiment-classifier"),
        sentiment_min_confidence=sentiment.get("min_confidence", 0.6),
        elliott_enabled=elliott.get("enabled", True),
        elliott_atr_scales=elliott.get("atr_scales", [2.0, 3.5, 5.0]),
        elliott_atr_window=elliott.get("atr_window", 14),
        elliott_max_pivots=elliott.get("max_pivots", 9),
        elliott_fib_tolerance=elliott.get("fib_tolerance", 0.06),
        elliott_min_confidence=elliott.get("min_confidence", 0.45),
        elliott_show_ambiguous=elliott.get("show_ambiguous", False),
        daily_shift_enabled=daily_shift.get("enabled", True),
        daily_shift_universe_file=daily_shift.get("universe_file", "config/idx_all.txt"),
        daily_shift_min_daily_value=daily_shift.get("min_daily_value", 2_000_000_000),
        daily_shift_min_price=daily_shift.get("min_price", 50),
        daily_shift_max_alerts=daily_shift.get("max_alerts", 15),
        daily_shift_history_days=daily_shift.get("history_days", 90),
        news_booster_page_size=news.get("booster_page_size", 200),
        news_fetch_cache_ttl_minutes=news.get("fetch_cache_ttl_minutes", 10),
        news_outage_max_failures=news.get("news_outage_max_failures", 4),
        poll_interval_market_minutes=news.get("poll_interval_market_minutes", 15),
        poll_interval_offhours_minutes=news.get(
            "poll_interval_offhours_minutes", news["news_poll_interval_minutes"]),
        news_watchlist_passthrough=news.get("watchlist_passthrough", True),
        news_dedup_retention_days=news.get("dedup_retention_days", 90),
        portal_dup_title_threshold=portal.get("dup_title_threshold", 0.55),
        portal_fetch_workers=portal.get("fetch_workers", 4),
        portal_proxy=portal.get("proxy", ""),
        portal_drop_categories=portal.get("drop_categories", ["tata_kelola", "pasar_opini"]),
        orderbook_enabled=orderbook.get("enabled", False),
        orderbook_max_symbols_per_scan=orderbook.get("max_symbols_per_scan", 15),
        orderbook_request_delay_seconds=orderbook.get("request_delay_seconds", 0.7),
        orderbook_window_after_open_minutes=orderbook.get("window_after_open_minutes", 30),
        orderbook_early_volume_min_ratio=ob_volume.get("min_ratio_prev_day", 0.5),
        orderbook_phase_rm_balance_min_ratio=ob_phase.get("rm_balance_min_ratio", 0.85),
        stockbit_refresh_token=os.environ.get("STOCKBIT_REFRESH_TOKEN", "").strip(),
        stockbit_access_token=os.environ.get("STOCKBIT_ACCESS_TOKEN", "").strip(),
        telegram_orderbook_chat_id=os.environ.get("TELEGRAM_ORDERBOOK_CHAT_ID", "").strip(),
        supabase_url=_normalize_supabase_url(os.environ.get("SUPABASE_URL", "")),
        supabase_key=os.environ.get("SUPABASE_KEY", "").strip(),
        price_staleness_max_minutes=raw.get("monitoring", {}).get("price_staleness_max_minutes", 90),
    )
