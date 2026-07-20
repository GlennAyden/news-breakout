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


def elliott_block(ctx: "WaveContext | None", *, min_conf: float, show_ambiguous: bool, rupiah) -> list[str]:
    if ctx is None or ctx.position == "none":
        return []
    if ctx.position == "ambiguous":
        if not show_ambiguous:
            return []
        return [f"🌊 Elliott: ambigu ({ctx.note or 'hitungan bertentangan'}) — pakai penilaianmu"]
    if ctx.confidence < min_conf:
        return []

    label = _LABEL.get(ctx.position, ctx.position)
    head = f"🌊 Elliott: {label} (conf {ctx.confidence:.2f})"
    if ctx.invalidation is not None:
        head += f" · invalidasi <{rupiah(ctx.invalidation)}"
    lines = [head]
    if ctx.fib_targets:
        parts = " · ".join(f"{k}×→{rupiah(v)}" for k, v in ctx.fib_targets.items())
        lines.append(f"📐 Fib: target {parts}")
    return lines
