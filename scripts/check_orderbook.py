"""Manual verification harness for the orderbook Ready-Markup feature.

Two modes (this is a check_* tool, so pytest never collects it):

    # No credentials — proves the signal + formatter pipeline runs:
    python scripts/check_orderbook.py --demo

    # Live — hits Stockbit with YOUR token (set STOCKBIT_REFRESH_TOKEN in .env):
    python scripts/check_orderbook.py --live BBCA

The live mode is the end-to-end confirmation: it fetches one symbol's real
orderbook, classifies the phase, and prints the alert that would be sent. It is
also how the two remaining seams (JSON field names, refresh endpoint) get
finalized — run it once and share any parse/HTTP error output.
"""
from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")


def _fix_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def run_demo(now: datetime) -> None:
    from news_breakout.orderbook.models import OrderbookSnapshot
    from news_breakout.orderbook.phase import PhaseConfig, classify_phase
    from news_breakout.orderbook.formatter import format_orderbook_alert
    from news_breakout.orderbook.volume_filter import VolumeResult

    cfg = PhaseConfig(rm_balance_min_ratio=0.85)
    vol = VolumeResult(True, 800_000, 1_000_000, 0.8)
    cases = {
        "AKUMULASI (300k/700k)": (300_000, 700_000, None),
        "READY MARKUP dari A (300k/300k)": (300_000, 300_000, "A"),
        "READY MARKUP dari BM (300k/300k)": (300_000, 300_000, "BM"),
        "BEFORE MARKDOWN (500k/300k)": (500_000, 300_000, None),
    }
    for label, (bid, offer, prev) in cases.items():
        snap = OrderbookSnapshot(symbol="DEMO", ts=now, total_bid_lot=bid,
                                 total_offer_lot=offer, last_price=1500)
        res = classify_phase(snap, cfg)
        print(f"\n=== {label} -> phase={res.phase.name} (ratio {res.ratio:.2f}) ===")
        if res.is_ready_markup:
            print(format_orderbook_alert(snap, res, prev, vol, now=now, minutes_after_open=30))
        else:
            print("(bukan Ready Markup — tidak ada alert)")


def run_live(symbol: str, now: datetime) -> None:
    import logging
    import os

    from news_breakout.config import _load_env_file
    from news_breakout.orderbook.auth import StockbitAuth
    from news_breakout.orderbook.stockbit_source import fetch_orderbook
    from news_breakout.orderbook.phase import PhaseConfig, classify_phase
    from news_breakout.orderbook.formatter import format_orderbook_alert
    from news_breakout.orderbook.volume_filter import VolumeResult

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _load_env_file(".env")  # only needs the Stockbit token, not the full bot config
    access = os.environ.get("STOCKBIT_ACCESS_TOKEN", "").strip()
    refresh = os.environ.get("STOCKBIT_REFRESH_TOKEN", "").strip()
    if not access and not refresh:
        print("STOCKBIT_ACCESS_TOKEN / STOCKBIT_REFRESH_TOKEN belum di-set di .env.")
        print("Tempel salah satu ke .env, atau jalankan `--demo` untuk cek tanpa kredensial.")
        return

    auth = StockbitAuth(refresh, access_token=access)
    print(f"Fetching orderbook {symbol} from Stockbit ...")
    snap = fetch_orderbook(symbol.upper(), auth, now=now)
    if snap is None:
        print("Gagal ambil orderbook (lihat log warning di atas: HTTP status / parse / token).")
        return
    cfg = PhaseConfig(rm_balance_min_ratio=0.85)
    res = classify_phase(snap, cfg)
    print(f"total_bid_lot={snap.total_bid_lot:,}  total_offer_lot={snap.total_offer_lot:,}")
    print(f"best_bid={snap.best_bid}  best_offer={snap.best_offer}  last={snap.last_price}")
    print(f"phase={res.phase.name}  ratio={res.ratio:.3f}")
    if res.is_ready_markup:
        vol = VolumeResult(True, 0, 0, 0.0)  # volume filter is separate; demo the alert text
        print("\n--- alert yang akan dikirim ---")
        print(format_orderbook_alert(snap, res, None, vol, now=now))


def main() -> None:
    _fix_console()
    now = datetime.now(WIB)
    args = sys.argv[1:]
    if args and args[0] == "--live" and len(args) >= 2:
        run_live(args[1], now)
    else:
        run_demo(now)


if __name__ == "__main__":
    main()
