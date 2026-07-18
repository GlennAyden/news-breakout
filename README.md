# news-breakout

Alert **breakout saham IDX** — tembus resistance/new-high **atau** keluar dari range akumulasi
(Wyckoff) — dengan **konfirmasi volume (RVOL)** di timeframe **1H / 4H / 1D**, plus **feed berita**
keterbukaan informasi IDX yang price-sensitive. Semua dikirim ke **Telegram**.

Dibuat untuk trader IDX yang tak punya waktu memindai pasar seharian: tool memunculkan kandidat,
trader yang memutuskan.

## Status

Tahap desain. Lihat spec: [`docs/superpowers/specs/2026-07-18-news-breakout-alert-design.md`](docs/superpowers/specs/2026-07-18-news-breakout-alert-design.md).

## Stack

Python 3.12 · `yfinance` · `pandas` · `APScheduler` · SQLite · Telegram Bot API

## Catatan

- Data harga: `yfinance` (gratis, ticker `.JK`, delay ~15 menit) — **tanpa API key**.
- News: keterbukaan informasi IDX (publik) — **tanpa API key**.
- Deploy: VPS (systemd + venv).
