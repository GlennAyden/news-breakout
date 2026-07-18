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
    telegram_bot_token: str
    telegram_breakout_chat_id: str
    dry_run: bool


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


def load_settings(
    config_path: str = "config/config.yaml", env_path: str = ".env"
) -> Settings:
    _load_env_file(env_path)
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    signals = raw.get("signals", {})
    data = raw.get("data", {})
    runtime = raw.get("runtime", {})
    return Settings(
        watchlist=raw["watchlist"],
        donchian_lookback=signals["donchian_lookback"],
        rvol_threshold=signals["rvol_threshold"],
        rvol_window=signals["rvol_window"],
        history_days=data["history_days"],
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_breakout_chat_id=os.environ["TELEGRAM_BREAKOUT_CHAT_ID"],
        dry_run=runtime["dry_run"],
    )
