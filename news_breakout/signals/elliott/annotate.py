from __future__ import annotations

from news_breakout.signals.elliott.models import WaveContext

_LABEL = {
    "wave_3_start": "kemungkinan awal Wave-3",
    "wave_5_possible_exhaustion": "⚠️ kemungkinan Wave-5 lelah",
    "wave_2_pullback": "kemungkinan pullback Wave-2",
    "wave_4_pullback": "kemungkinan pullback Wave-4",
    "impulse_mid": "impuls berjalan",
    "corrective_or_unresolved": "struktur korektif / belum jelas",
}


def elliott_block(ctx: "WaveContext | None", *, min_conf: float, show_ambiguous: bool) -> list[str]:
    """Label + confidence only: the invalidation price already appears in the
    trade-plan Stop line, and fib targets showed no edge in backtest — neither
    is repeated here."""
    if ctx is None:
        return []

    lines: list[str] = []
    if ctx.position == "none":
        lines = []
    elif ctx.position == "ambiguous":
        if show_ambiguous:
            lines = [f"🌊 Elliott: ambigu ({ctx.note or 'hitungan bertentangan'}) — pakai penilaianmu"]
    elif ctx.confidence >= min_conf:
        label = _LABEL.get(ctx.position, ctx.position)
        lines = [f"🌊 Elliott: {label} (conf {ctx.confidence:.2f})"]

    if getattr(ctx, "from_abc", False):
        lines.append("🌊 Konteks: breakout dari koreksi ABC — historis cenderung lebih lemah")
    return lines
