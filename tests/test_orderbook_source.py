from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from news_breakout.orderbook.stockbit_source import _parse_orderbook, fetch_orderbook

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 20, 10, 0, tzinfo=WIB)

# Confirmed v2 shape from a live TLKM capture (2026-07-23): string values,
# `volume` in shares (lot = volume/100), `que_num` = order frequency.
_BODY = {
    "data": {
        "symbol": "TLKM",
        "lastprice": 2700,
        "bid": [
            {"price": "2690", "que_num": "1", "volume": "1200", "change_percentage": ""},
            {"price": "2680", "que_num": "737", "volume": "3533600", "change_percentage": ""},
            {"price": "2670", "que_num": "1036", "volume": "5300100", "change_percentage": ""},
        ],
        "offer": [
            {"price": "2700", "que_num": "94", "volume": "3001300", "change_percentage": ""},
            {"price": "2710", "que_num": "132", "volume": "1011300", "change_percentage": ""},
            {"price": "2720", "que_num": "158", "volume": "849700", "change_percentage": ""},
        ],
    }
}


def test_parse_real_shape_converts_shares_to_lots():
    snap = _parse_orderbook(_BODY, "TLKM", NOW)
    # lots = volume / 100, summed over the levels
    assert snap.total_bid_lot == 12 + 35336 + 53001      # 88349
    assert snap.total_offer_lot == 30013 + 10113 + 8497  # 48623
    assert snap.total_bid_freq == 1 + 737 + 1036         # que_num summed
    assert snap.best_bid == 2690
    assert snap.best_offer == 2700
    assert snap.bids[0].lot == 12                        # 1200 shares -> 12 lots
    assert snap.bids[1].freq == 737
    assert snap.last_price == 2700


def test_parse_raises_on_missing_sides():
    with pytest.raises(ValueError):
        _parse_orderbook({"data": {"symbol": "X"}}, "X", NOW)


def test_fetch_retries_once_after_401():
    calls = []

    class FakeAuth:
        def auth_headers(self):
            return {"Authorization": "Bearer x"}

        def refresh(self):
            calls.append("refresh")
            return "new"

    responses = [(401, {}), (200, _BODY)]

    def http_get(url, headers):
        calls.append("get")
        return responses[len([c for c in calls if c == "get"]) - 1]

    snap = fetch_orderbook("TLKM", FakeAuth(), http_get=http_get, now=NOW)
    assert snap is not None
    assert snap.total_bid_lot == 88349
    assert calls == ["get", "refresh", "get"]


def test_fetch_returns_none_on_non_200():
    class FakeAuth:
        def auth_headers(self):
            return {}

    snap = fetch_orderbook("X", FakeAuth(), http_get=lambda u, h: (500, {}), now=NOW)
    assert snap is None
