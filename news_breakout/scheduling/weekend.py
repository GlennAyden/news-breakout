from __future__ import annotations

from news_breakout.models import TickerAlert


def build_weekend_summary(alerts: list[TickerAlert], top_n: int = 10) -> str:
    if not alerts:
        return "📊 WEEKEND DEEP-SCAN (1D)\nTidak ada setup breakout terdeteksi."
    ranked = sorted(alerts, key=lambda a: (a.priority, a.max_rvol), reverse=True)[:top_n]
    lines = ["📊 WEEKEND DEEP-SCAN (1D)", "━━━━━━━━━━━━━━━━━━━"]
    for a in ranked:
        tfs = "+".join(sorted({s.timeframe for s in a.signals}))
        lines.append(f"⭐{a.priority:.0f}  {a.ticker}  [{tfs}]  RVOL {a.max_rvol:.1f}×")
    return "\n".join(lines)
