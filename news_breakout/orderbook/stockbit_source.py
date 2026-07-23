from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from news_breakout.orderbook.auth import StockbitAuth
from news_breakout.orderbook.models import OrderbookLevel, OrderbookSnapshot

logger = logging.getLogger("news_breakout")
WIB = ZoneInfo("Asia/Jakarta")

ORDERBOOK_URL = "https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{symbol}"
SESSION_URL = "https://exodus.stockbit.com/company-price-feed/market-time/session"

# IDX regular market: 1 lot = 100 shares. Stockbit's orderbook `volume` is in
# shares; the playbook (and Stockbit's own "Lot" column) works in lots.
SHARES_PER_LOT = 100


def _default_get(url: str, headers: dict) -> tuple[int, dict]:
    with httpx.Client() as client:
        resp = client.get(url, headers=headers, timeout=15)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 — non-JSON body still carries the status
            body = {}
        return resp.status_code, body


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _level(item: dict) -> OrderbookLevel:
    # Confirmed v2 shape (live TLKM capture, 2026-07-23): {price, volume, que_num}
    # as strings; `volume` is in shares, `que_num` is the order frequency.
    price = _num(item.get("price"))
    lot = int(_num(item.get("volume")) // SHARES_PER_LOT)
    freq = int(_num(item.get("que_num")))
    return OrderbookLevel(price=price, lot=lot, freq=freq)


def _parse_orderbook(body: dict, symbol: str, ts: datetime) -> OrderbookSnapshot:
    """Map Stockbit's v2 orderbook JSON to an OrderbookSnapshot.

    Shape confirmed against a live capture: ``data.bid`` / ``data.offer`` are the
    full depth (every price level, not just the visible 10); summing their lots
    reproduces Stockbit's total row exactly. Raises on a shape mismatch so it
    fails loudly rather than emitting an empty book.
    """
    data = body.get("data", body) if isinstance(body, dict) else {}
    bids_raw = data.get("bid")
    offers_raw = data.get("offer")
    if not isinstance(bids_raw, list) or not isinstance(offers_raw, list):
        raise ValueError(f"orderbook shape unexpected for {symbol}; keys={list(data)[:10]}")

    bids = [_level(x) for x in bids_raw if isinstance(x, dict)]
    offers = [_level(x) for x in offers_raw if isinstance(x, dict)]
    last = data.get("lastprice")
    last_price = _num(last) if last not in (None, "") else None
    # Totals are summed from the full-depth levels (matches Stockbit's total row).
    return OrderbookSnapshot.from_levels(symbol, ts, bids, offers, last_price=last_price)


def fetch_orderbook(
    symbol: str, auth: StockbitAuth, *, http_get=_default_get, now: datetime | None = None
) -> OrderbookSnapshot | None:
    """Fetch one symbol's orderbook. Returns None on any failure (never raises)."""
    ts = now or datetime.now(WIB)
    url = ORDERBOOK_URL.format(symbol=symbol)
    try:
        status, body = http_get(url, auth.auth_headers())
        if status == 401:  # token stale → refresh once, retry once
            auth.refresh()
            status, body = http_get(url, auth.auth_headers())
        if status != 200:
            logger.warning("orderbook %s: HTTP %s", symbol, status)
            return None
        return _parse_orderbook(body, symbol, ts)
    except Exception as exc:  # noqa: BLE001 — degrade to None; one bad symbol never aborts the scan
        logger.warning("orderbook %s failed: %s", symbol, exc)
        return None


def is_market_open(auth: StockbitAuth, *, http_get=_default_get) -> bool:
    """Best-effort market-session check. Fails open (True) on any uncertainty so
    a session-endpoint hiccup never silently disables the feature.

    SEAM: response shape is the documented assumption; finalize from capture.
    """
    try:
        status, body = http_get(SESSION_URL, auth.auth_headers())
        if status != 200 or not isinstance(body, dict):
            return True
        data = body.get("data", body)
        state = str(data.get("session") or data.get("status") or "").upper()
        if not state:
            return True
        return "CLOSE" not in state  # e.g. SESSION_CLOSED / MARKET_CLOSE → closed
    except Exception:  # noqa: BLE001 — uncertainty means proceed, not silently skip
        return True
