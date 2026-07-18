from __future__ import annotations

from news_breakout.models import BreakoutSignal, TickerAlert


def _rupiah(value: float) -> str:
    """Format a number with '.' as thousands separator (Indonesian style)."""
    return f"{value:,.0f}".replace(",", ".")


def format_breakout(sig: BreakoutSignal) -> str:
    arrow = "🟢" if sig.rvol >= 2.0 else "🟡"
    return (
        f"🚨 BREAKOUT — {sig.ticker}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Sinyal : Resistance breakout (new high) · TF {sig.timeframe}\n"
        f"Harga  : {_rupiah(sig.price)} ({sig.pct_change:+.1f}%)\n"
        f"Level  : tembus resistance {_rupiah(sig.level)}\n"
        f"Volume : RVOL {sig.rvol:.1f}× {arrow}\n"
        f"⏱️ {sig.timestamp:%H:%M} WIB · delay data ~15 mnt"
    )


_SIGNAL_LABEL = {
    "resistance_breakout": "Resistance breakout (new high)",
    "wyckoff_range_breakout": "Wyckoff range breakout",
}


def format_ticker_alert(alert: TickerAlert) -> str:
    price = alert.signals[0].price
    lines = [
        f"🚨 BREAKOUT — {alert.ticker}  ⭐{alert.priority:.0f}",
        "━━━━━━━━━━━━━━━━━━━",
        f"Harga : {_rupiah(price)}",
    ]
    for s in alert.signals:
        arrow = "🟢" if s.rvol >= 2.0 else "🟡"
        label = _SIGNAL_LABEL.get(s.signal_type, s.signal_type)
        lines.append(
            f"• TF {s.timeframe}: {label} · level {_rupiah(s.level)} · RVOL {s.rvol:.1f}× {arrow}"
        )
    lines.append(f"⏱️ {alert.timestamp:%H:%M} WIB · delay data ~15 mnt")
    return "\n".join(lines)
