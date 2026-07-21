from __future__ import annotations

from datetime import datetime

from news_breakout.models import TF_WEIGHT, BreakoutSignal, TickerAlert
from news_breakout.news.models import Disclosure
from news_breakout.signals.elliott.annotate import elliott_block
from news_breakout.signals.elliott.trade_plan import trail_plan


def _rupiah(value: float) -> str:
    """Format a number with '.' as thousands separator (Indonesian style)."""
    return f"{value:,.0f}".replace(",", ".")


def _time_ago(ts: datetime, now: datetime) -> str:
    seconds = (now - ts).total_seconds()
    if seconds < 3600:
        return f"{int(seconds // 60)} menit lalu"
    if seconds < 86400:
        return f"{int(seconds // 3600)} jam lalu"
    return f"{int(seconds // 86400)} hari lalu"


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

def _primary_signal(signals: list[BreakoutSignal]) -> BreakoutSignal:
    """Pick the signal with the highest timeframe weight (1D>4H>1H); tie-break by highest level."""
    return max(
        signals,
        key=lambda s: (TF_WEIGHT.get(s.timeframe, 0.0), s.level),
    )


def _trade_plan_line(alert: TickerAlert) -> str:
    primary = _primary_signal(alert.signals)
    entry = primary.price
    stop = getattr(alert, "structure_stop", None)
    atr = getattr(alert, "atr", None)
    if stop is not None and stop < entry and atr is not None and atr > 0:
        p = trail_plan(entry, stop, atr)
        return (
            f"📍 Rencana: Entry ~{_rupiah(entry)} · Stop (EW) <{_rupiah(stop)} "
            f"· Risk {p['risk_pct']:.1f}% · Trail 2.5×ATR ~{_rupiah(p['trail_dist'])} "
            f"stlh +1R (~{_rupiah(p['activate'])})"
        )
    if stop is not None and stop < entry:
        risk = (entry - stop) / entry * 100
        target = entry + 2 * (entry - stop)
        return (
            f"📍 Rencana: Entry ~{_rupiah(entry)} · Invalidasi (EW) <{_rupiah(stop)} "
            f"· Risk {risk:.1f}% · Target 2R ~{_rupiah(target)}"
        )
    # fallback: the original broken-level plan (unchanged / byte-identical)
    level = primary.level
    if level >= entry:
        return f"📍 Entry ~{_rupiah(entry)}"
    risk = (entry - level) / entry * 100
    target = entry + 2 * (entry - level)
    return (
        f"📍 Rencana: Entry ~{_rupiah(entry)} · Invalidasi <{_rupiah(level)} "
        f"· Risk {risk:.1f}% · Target 2R ~{_rupiah(target)}"
    )


def _score_line(alert: TickerAlert) -> str:
    parts = [f"🏅 Skor {alert.quality_score:.1f}"]
    if alert.above_sma50 is True:
        parts.append("tren↑")
    elif alert.above_sma50 is False:
        parts.append("tren↓")
    if alert.ext_pct > 0:
        parts.append(f"+{alert.ext_pct:.1f}% dari level")
    return " · ".join(parts)


def format_ticker_alert(alert: TickerAlert, catalyst: Disclosure | None = None, *,
                        min_conf: float = 0.45, show_ambiguous: bool = False) -> str:
    price = alert.signals[0].price
    marker = "🔥" if catalyst is not None else "🚨"
    lines = [
        f"{marker} BREAKOUT — {alert.ticker}  ⭐{alert.priority:.0f}",
        "━━━━━━━━━━━━━━━━━━━",
        f"Harga : {_rupiah(price)}",
    ]
    for s in alert.signals:
        arrow = "🟢" if s.rvol >= 2.0 else "🟡"
        label = _SIGNAL_LABEL.get(s.signal_type, s.signal_type)
        lines.append(
            f"• TF {s.timeframe}: {label} · level {_rupiah(s.level)} · RVOL {s.rvol:.1f}× {arrow}"
        )
    lines.append(_trade_plan_line(alert))
    lines.append(_score_line(alert))
    for ln in elliott_block(
        getattr(alert, "wave_context", None),
        min_conf=min_conf, show_ambiguous=show_ambiguous, rupiah=_rupiah,
    ):
        lines.append(ln)
    if catalyst is not None:
        lines.append(
            f"📰 Katalis: {catalyst.title} ({_time_ago(catalyst.timestamp, alert.timestamp)})"
        )
    lines.append(f"⏱️ {alert.timestamp:%H:%M} WIB · delay data ~15 mnt")
    return "\n".join(lines)


def format_daily_digest(alerts: list[TickerAlert], *, now: datetime) -> str:
    lines = [
        f"🗓️ Watchlist Pagi — EOD Breakout ({now:%d %b %Y})",
        "━━━━━━━━━━━━━━━━━━━",
    ]
    for i, a in enumerate(alerts, 1):
        primary = _primary_signal(a.signals)
        trend = "↑" if a.above_sma50 is True else ("↓" if a.above_sma50 is False else "·")
        lines.append(
            f"{i}. {a.ticker} · 🏅{a.quality_score:.1f} {trend} · "
            f"{_rupiah(primary.price)} (level {_rupiah(primary.level)})"
        )
    lines.append("⏱️ ringkasan breakout harian · delay data ~15 mnt")
    return "\n".join(lines)
