from __future__ import annotations

from datetime import datetime

from news_breakout.models import TF_WEIGHT, BreakoutSignal, TickerAlert
from news_breakout.news.models import Disclosure
from news_breakout.news.corp_action import CAUTION_LINES, classify_corp_action
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


def _strength(score: float) -> str:
    """Translate the quality score into an at-a-glance tier (send floor is 5.5)."""
    if score >= 9.0:
        return "⭐⭐⭐"
    if score >= 7.0:
        return "⭐⭐"
    return "⭐"


def _tf_header(signals: list[BreakoutSignal]) -> str:
    tfs = sorted({s.timeframe for s in signals}, key=lambda tf: -TF_WEIGHT.get(tf, 0.0))
    return "+".join(tfs)


def _action_block(alert: TickerAlert) -> list[str]:
    """The decision lines: buy / stop / manage. Same tiering as before
    (ATR-trailing > EW fixed-2R > broken-level fallback > entry-only)."""
    primary = _primary_signal(alert.signals)
    entry = primary.price
    stop = getattr(alert, "structure_stop", None)
    atr = getattr(alert, "atr", None)
    lines = [f"💰 Beli  : ~{_rupiah(entry)}"]
    if stop is not None and stop < entry:
        risk = (entry - stop) / entry * 100
        lines.append(f"🛑 Stop  : {_rupiah(stop)} (EW, risiko {risk:.1f}%)")
        if atr is not None and atr > 0:
            p = trail_plan(entry, stop, atr)
            lines.append(
                f"🎯 Kelola: capai +1R (~{_rupiah(p['activate'])}) "
                f"→ trailing stop ~{_rupiah(p['trail_dist'])} di bawah harga"
            )
        else:
            target = entry + 2 * (entry - stop)
            lines.append(f"🎯 Target: 2R ~{_rupiah(target)}")
        return lines
    level = primary.level
    if level >= entry:
        return lines  # degenerate level: entry only, no stop/target math
    risk = (entry - level) / entry * 100
    target = entry + 2 * (entry - level)
    lines.append(f"🛑 Stop  : <{_rupiah(level)} (risiko {risk:.1f}%)")
    lines.append(f"🎯 Target: 2R ~{_rupiah(target)}")
    return lines


def _signal_line(alert: TickerAlert) -> str:
    primary = _primary_signal(alert.signals)
    arrow = "🟢" if primary.rvol >= 2.0 else "🟡"
    ext = f" (+{alert.ext_pct:.1f}%)" if alert.ext_pct > 0 else ""
    return (
        f"Sinyal : tembus resistance {_rupiah(primary.level)}{ext} "
        f"· RVOL {primary.rvol:.1f}× {arrow}"
    )


def _trend_line(alert: TickerAlert) -> str | None:
    parts = []
    if alert.above_sma50 is True:
        parts.append("di atas SMA50 ↑")
    elif alert.above_sma50 is False:
        parts.append("di bawah SMA50 ↓")
    if getattr(alert, "long_channel", None) is True:
        parts.append("🏔️ high 3 bulan baru")
    return ("Tren   : " + " · ".join(parts)) if parts else None


def format_ticker_alert(alert: TickerAlert, catalyst: Disclosure | None = None, *,
                        min_conf: float = 0.45, show_ambiguous: bool = False,
                        corp_action_caution: bool = True) -> str:
    marker = "🔥" if catalyst is not None else "🚨"
    lines = [
        f"{marker} BREAKOUT — {alert.ticker} · {_tf_header(alert.signals)} "
        f"· {_strength(alert.quality_score)} skor {alert.quality_score:.1f}",
        "━━━━━━━━━━━━━━━━━━━",
        *_action_block(alert),
        "━━━━━━━━━━━━━━━━━━━",
        _signal_line(alert),
    ]
    trend = _trend_line(alert)
    if trend is not None:
        lines.append(trend)
    for ln in elliott_block(
        getattr(alert, "wave_context", None),
        min_conf=min_conf, show_ambiguous=show_ambiguous,
    ):
        lines.append(ln)
    if catalyst is not None:
        lines.append(
            f"📰 Katalis: {catalyst.title} ({_time_ago(catalyst.timestamp, alert.timestamp)})"
        )
        if corp_action_caution:
            caution = CAUTION_LINES.get(classify_corp_action(catalyst.title))
            if caution:
                lines.append(caution)
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
