from __future__ import annotations

from datetime import datetime

from news_breakout.orderbook.models import OrderbookSnapshot
from news_breakout.orderbook.phase import Phase, PhaseResult
from news_breakout.orderbook.volume_filter import VolumeResult

_PRIOR_NOTE = {
    "A": "Fase sebelumnya: AKUMULASI ✅ (supply terserap → RM valid)",
    "BM": "Fase sebelumnya: BEFORE MARKDOWN ⚠️ (waspada tipuan, bisa balik ke A)",
    "RM": "Fase sebelumnya: masih RM (menahan keseimbangan)",
}


def _num(v: float | int | None) -> str:
    if v is None:
        return "-"
    return f"{int(round(v)):,}"


def format_orderbook_alert(
    snapshot: OrderbookSnapshot,
    result: PhaseResult,
    prev_phase: str | None,
    volume: VolumeResult,
    *,
    now: datetime,
    minutes_after_open: int | None = None,
) -> str:
    """Telegram text for a Ready-Markup alert."""
    lines = [
        f"🟰 READY MARKUP — {snapshot.symbol}",
        "Bid ≈ Offer (setara) → potensi markup",
        f"Bid lot: {_num(result.bid_lot)}  |  Offer lot: {_num(result.offer_lot)}"
        f"  (rasio {result.ratio:.2f})",
    ]

    note = _PRIOR_NOTE.get(prev_phase or "")
    if note:
        lines.append(note)

    when = f" (~{minutes_after_open} mnt setelah open)" if minutes_after_open is not None else ""
    if volume.prev_vol > 0:
        lines.append(
            f"Volume hari ini {_num(volume.today_vol)} = {volume.ratio:.2f}× kemarin"
            f" (≥ 0.5 ✅){when}"
        )

    price_bits = []
    if snapshot.last_price is not None:
        price_bits.append(f"Harga: {_num(snapshot.last_price)}")
    if snapshot.best_bid is not None and snapshot.best_offer is not None:
        price_bits.append(f"Best bid/offer: {_num(snapshot.best_bid)}/{_num(snapshot.best_offer)}")
    if price_bits:
        lines.append("  ".join(price_bits))

    lines.append(now.strftime("%Y-%m-%d %H:%M WIB"))
    return "\n".join(lines)
