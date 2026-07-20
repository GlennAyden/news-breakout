from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("news_breakout")


def load_daily_universe(path: str) -> list[str]:
    """Read the broad daily-shift ticker list (one code per line; '#' comments
    and blanks ignored). Uppercased, de-duped, order-preserving. Missing file -> []."""
    p = Path(path)
    if not p.exists():
        logger.warning("daily shift: universe file not found: %s", path)
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().upper()
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out
