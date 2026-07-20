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
    daily_shift_enabled: bool = True
    daily_shift_universe_file: str = "config/idx_all.txt"
    daily_shift_min_daily_value: float = 2_000_000_000
    daily_shift_min_price: float = 50
    daily_shift_max_alerts: int = 15
    daily_shift_history_days: int = 90


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
    daily_shift = raw.get("daily_shift", {})
    return Settings(
        watchlist=raw["watchlist"],
        donchian_lookback=signals["donchian_lookback"],
        rvol_threshold=signals["rvol_threshold"],
        rvol_window=signals["rvol_window"],
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
        portal_name_map=portal.get("name_map", {}),
        portal_summary_sentences=portal.get("summary_sentences", 2),
        portal_max_per_run=portal.get("max_per_run", 20),
        sentiment_enabled=sentiment.get("enabled", True),
        sentiment_model=sentiment.get("model", "w11wo/indonesian-roberta-base-sentiment-classifier"),
        sentiment_min_confidence=sentiment.get("min_confidence", 0.6),
        daily_shift_enabled=daily_shift.get("enabled", True),
        daily_shift_universe_file=daily_shift.get("universe_file", "config/idx_all.txt"),
        daily_shift_min_daily_value=daily_shift.get("min_daily_value", 2_000_000_000),
        daily_shift_min_price=daily_shift.get("min_price", 50),
        daily_shift_max_alerts=daily_shift.get("max_alerts", 15),
        daily_shift_history_days=daily_shift.get("history_days", 90),
        supabase_url=_normalize_supabase_url(os.environ.get("SUPABASE_URL", "")),
        supabase_key=os.environ.get("SUPABASE_KEY", "").strip(),
        price_staleness_max_minutes=raw.get("monitoring", {}).get("price_staleness_max_minutes", 90),
    )
