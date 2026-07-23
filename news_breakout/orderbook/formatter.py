from __future__ import annotations

import html
from datetime import datetime

from news_breakout.orderbook.models import OrderbookSnapshot
from news_breakout.orderbook.phase import PhaseResult
from news_breakout.orderbook.volume_filter import VolumeResult

_SYMBOL_URL = "https://stockbit.com/symbol/{symbol}"

# Line 2 tagline + the 🔀 transition line, keyed by the prior-cycle phase.
_TAGLINE = {
    "A": "Orderbook seimbang → supply terserap, siap markup.",
    "BM": "Orderbook seimbang → siap markup, tapi hati-hati.",
}
_DEFAULT_TAGLINE = "Orderbook seimbang → potensi markup."

_TRANSITION = {
    "A": "🔀 AKUMULASI → READY MARKUP  ✅ valid",
    "BM": "🔀 BEFORE MARKDOWN → READY MARKUP  ⚠️ bisa balik ke Akumulasi (tipuan)",
    "RM": "🔀 READY MARKUP (menahan keseimbangan)",
}
_DEFAULT_TRANSITION = "🔀 Fase: READY MARKUP"


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
    """Telegram **HTML** text for a Ready-Markup alert (send with parse_mode=HTML).

    Ticker + "Buka orderbook" are tappable links to the Stockbit symbol page.
    """
    sym = html.escape(snapshot.symbol)
    url = _SYMBOL_URL.format(symbol=sym)
    balance_pct = round(result.ratio * 100)
    key = prev_phase or ""

    header = f'🟰 <b>READY MARKUP</b> — <a href="{url}">{sym}</a>'
    if snapshot.last_price is not None:
        header += f"  ·  {_num(snapshot.last_price)}"

    lines = [
        header,
        _TAGLINE.get(key, _DEFAULT_TAGLINE),
        "",
        f"⚖️ Bid <b>{_num(result.bid_lot)}</b>  ⇄  Offer <b>{_num(result.offer_lot)}</b> lot"
        f"   (balance {balance_pct}%)",
        _TRANSITION.get(key, _DEFAULT_TRANSITION),
    ]

    if volume.prev_vol > 0:
        when = f"  ·  ~{minutes_after_open} mnt setelah open" if minutes_after_open is not None else ""
        lines.append(f"📈 Volume {volume.ratio:.2f}× kemarin{when}")

    lines.append("")
    lines.append(f'🔗 <a href="{url}">Buka orderbook</a> · 🕒 {now.strftime("%d %b %H:%M WIB")}')
    return "\n".join(lines)
