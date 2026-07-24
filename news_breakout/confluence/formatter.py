from __future__ import annotations

import html
from datetime import datetime


def _rupiah(value: float) -> str:
    """Indonesian thousands separator: 4850 -> '4.850'."""
    return f"{value:,.0f}".replace(",", ".")


def format_confluence_alert(
    *, ticker: str, stage: str, catalyst_text: str, catalyst_source: str,
    catalyst_ts: datetime, breakout: dict, orderbook: dict | None, now: datetime,
) -> str:
    """HTML Telegram body for a staged confluence alert (2/3 or 3/3)."""
    is_final = stage == "3of3"
    ticker_e = html.escape(ticker)
    head = "⭐ CONFLUENCE 3/3" if is_final else "🔸 CONFLUENCE 2/3"
    ob_mark = "✅ READY MARKUP" if is_final else "⏳ (menunggu jam bursa / ready markup)"
    lines = [
        f"<b>{head} — {ticker_e}</b>",
        f"📰 NEWS ✅ · 📈 BREAKOUT ✅ · 📊 ORDERBOOK {ob_mark}",
        "",
        f"📰 {catalyst_ts:%H:%M} {html.escape(catalyst_text)}  ({html.escape(catalyst_source)})",
        (f"📈 TF {breakout['tf']} · harga {_rupiah(breakout['price'])} "
         f"({breakout['pct_change']:+.1f}%) · tembus {_rupiah(breakout['level'])} · "
         f"RVOL {breakout['rvol']:.1f}× · Q{breakout['quality']:.0f}"),
    ]
    if is_final:
        lines.append(
            f"📊 bid/offer {_rupiah(orderbook['bid_lot'])}/{_rupiah(orderbook['offer_lot'])} "
            f"({orderbook['ratio']:.2f})"
        )
    lines.append(f"🔗 https://stockbit.com/symbol/{ticker_e}")
    return "\n".join(lines)
