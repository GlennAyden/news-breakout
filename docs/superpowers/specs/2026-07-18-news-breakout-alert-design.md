# Spec Desain — News-Breakout Alert (IDX)

- **Tanggal:** 2026-07-18
- **Status:** Draft untuk review
- **Pemilik:** trader IDX (paham technical analysis, order book, Elliott Wave, Wyckoff)

## 1. Tujuan & Latar Belakang

Pengguna adalah trader saham IDX yang menguasai analisis teknikal, order book, Elliott Wave, dan
Wyckoff. **Masalah utamanya bukan skill analisis, tapi waktu** untuk memindai pasar dan
*menemukan* saham yang berpotensi naik.

Tool ini mengotomasi proses penemuan itu: mendeteksi **breakout ke atas** (tembus resistance /
keluar dari range akumulasi Wyckoff) yang **dikonfirmasi volume**, lalu mengirim alert ke
**Telegram**. Selain itu, tool mengirim **feed berita mandiri** (keterbukaan informasi IDX yang
price-sensitive) secara terus-menerus, independen dari sinyal breakout.

Tujuannya: pengguna cukup menerima notifikasi terkurasi, bukan memelototi chart seharian.

## 2. Ringkasan Keputusan

| Aspek | Keputusan |
|---|---|
| Timing alert | Real-time intraday via polling near-real-time |
| Sumber data harga | Gratis (`yfinance` ticker `.JK`), delay ~15 menit |
| Timeframe analisis | **1H, 4H, 1D** (bukan scalping 15m) |
| Pola sinyal | (A) Resistance/new-high breakout **dan/atau** (B) breakout range akumulasi Wyckoff |
| Konfirmasi | Volume (RVOL) wajib |
| Universe | Watchlist inti + auto-scan universe likuid |
| Peran news | (1) Booster prioritas untuk breakout **dan** (2) feed berita mandiri terus-menerus |
| Sumber news | IDX Keterbukaan Informasi dulu (v1); portal berita nanti (v2) |
| Filter news | Curated price-sensitive (bukan semua disclosure) |
| Jadwal breakout | Jam bursa: tiap 30 menit; akhir pekan: auto-analisis mingguan |
| Jadwal news | Luar jam bursa: tiap 1 jam; jam bursa: ikut siklus scan |
| Deploy | VPS `hermes-vps` (Ubuntu 24.04, always-on) |
| Bahasa/stack | Python 3.12 |

## 3. Arsitektur

Sistem dipecah jadi komponen terisolasi, tiap komponen punya satu tanggung jawab, berkomunikasi
lewat interface jelas, dan bisa dites independen.

```
┌───────────────────────────────────────────────────────────────────────┐
│  SCHEDULER (APScheduler, timezone Asia/Jakarta, sadar libur bursa)      │
│  - breakout scan: Sen–Jum 09:00–16:00 WIB, tiap 30 mnt                  │
│  - news poll: jam bursa ikut siklus; luar jam bursa tiap 60 mnt         │
│  - weekend deep-scan: Sabtu (analisis mingguan)                         │
└──────────┬───────────────────────────────┬────────────────────────────-┘
           │                               │
           ▼                               ▼
   ┌────────────────┐             ┌────────────────────┐
   │ UNIVERSE FILTER│────────────►│  DATA LAYER        │
   │ - watchlist    │  daftar     │  - yfinance .JK    │
   │ - likuid auto  │  ticker     │  - resample 4H     │
   └────────────────┘             │  - cache ringan    │
                                  └─────────┬──────────┘
                                            │ OHLCV per TF
                                            ▼
   ┌────────────────────┐         ┌────────────────────────┐
   │  NEWS ENGINE       │         │  SIGNAL ENGINE         │
   │  - poll IDX disc.  │         │  - resistance breakout │
   │  - filter curated  │         │  - Wyckoff range b/out │
   │  - dedup           │  cek    │  - konfirmasi RVOL     │
   │  - match ticker    │◄────────│  - multi-timeframe     │
   └───┬────────────┬───┘ katalis └───────────┬────────────┘
       │            │                         │
  (feed mandiri)  (booster)                   │ sinyal
       │            └───────────┐             │
       ▼                        ▼             ▼
                     ┌──────────────────────────────┐
                     │  ALERT DISPATCHER            │
                     │  - dedup (SQLite)            │
                     │  - prioritas + format        │
                     │  - stream BREAKOUT & NEWS    │
                     └──────────────┬───────────────┘
                                    ▼
                            Telegram Bot API (outbound)
```

### Komponen

1. **Scheduler** — orkestrasi job berdasarkan jam bursa & timezone WIB; tahu kalender libur bursa.
2. **Universe Filter** — menghasilkan daftar ticker yang akan discan (watchlist + likuid).
3. **Data Layer** — ambil OHLCV per timeframe dari `yfinance`, resample 4H dari 1H, cache ringan.
4. **Signal Engine** — hitung pola breakout + konfirmasi volume, multi-timeframe.
5. **News Engine** — poll & filter disclosure IDX; dua peran (feed mandiri + booster).
6. **Alert Dispatcher** — dedup, format, prioritas, kirim ke Telegram.

## 4. Data & Timeframe

- **Sumber:** `yfinance`, ticker format `<KODE>.JK` (mis. `BBRI.JK`).
- **Timeframe:**
  - **1D** — native (`interval=1d`).
  - **1H** — native (`interval=1h`, histori ~730 hari, cukup).
  - **4H** — **resample dari 1H** (yfinance tak menyediakan 4H native). Resample memakai jam
    perdagangan (bukan 24 jam) agar bar 4H sesuai sesi bursa.
- **Delay:** ~15 menit (konsekuensi sumber gratis). "Real-time" di sini = near-real-time.
- **Efisiensi memori (constraint VPS):** proses per-batch, jangan tahan seluruh histori semua
  ticker sekaligus. Ambil hanya window yang dibutuhkan indikator (mis. ~60–120 bar terakhir/TF).

## 5. Logika Sinyal (Signal Engine)

Alert breakout dikirim **hanya bila lolos 2 lapis**: (A) pola breakout **DAN** (B) konfirmasi volume.

### A. Pola breakout (salah satu memicu)

1. **Resistance / new-high breakout (Donchian):** harga close terakhir menembus **highest-high N
   bar sebelumnya** (default N=20) pada TF terkait.
2. **Wyckoff range breakout:** deteksi konsolidasi lebih dulu, lalu breakout ke atas.
   - *Deteksi konsolidasi:* dalam lookback (default 30 bar), lebar range
     `(max_high - min_low) / min_low < 15%` **dan** kontraksi volatilitas (ATR menurun).
   - *Trigger:* close menembus di atas batas atas range konsolidasi.
   - *Catatan jujur:* ini **proxy pragmatis** untuk Wyckoff Phase D/E (markup setelah spring),
     bukan pelabelan fase penuh (SC/AR/ST/spring). Pelabelan fase penuh kompleks & rawan salah —
     ditandai sebagai kandidat penyempurnaan v2.

### B. Konfirmasi volume (wajib)

- **RVOL** = volume bar sekarang / rata-rata volume N bar (default N=20) **≥ ambang (default 2.0×)**.
- Membedakan breakout beneran dari *false breakout* yang sepi peminat.

### Multi-timeframe

- Sinyal dievaluasi di **1H, 4H, 1D**.
- Alert mencantumkan TF mana yang trigger. **Breakout di TF lebih tinggi = prioritas lebih tinggi**
  (mis. breakout 1D > 4H > 1H). Konfluensi antar-TF menaikkan skor.

### Anti-spam (dedup)

- State di SQLite. Aturan: **1 ticker × 1 tipe sinyal × 1 TF = maksimal 1 alert per hari**, kecuali
  level resistance baru tertembus (level naik → alert baru boleh).

### Default parameter (didelegasikan; semua tunable via config)

| Parameter | Default |
|---|---|
| Donchian lookback (N) | 20 bar |
| RVOL threshold | 2.0× |
| RVOL average window | 20 bar |
| Range lookback (Wyckoff) | 30 bar |
| Range width maksimum | 15% |
| News booster window | 48 jam |

## 6. Universe & Filter

- **Watchlist inti:** daftar ticker di `config.yaml`. Discan tiap siklus (30 mnt).
- **Universe likuid (auto-filter):** dari daftar emiten IDX, buang yang tak likuid:
  - harga > Rp50 (bukan gocap),
  - rata-rata nilai transaksi harian > ambang (default Rp1 miliar, tunable),
  - tidak sedang disuspensi.
  - Perkiraan ~150–300 saham. Discan tiap siklus dengan batching ramah rate-limit.
- **Sumber daftar ticker:** ambil/refresh daftar emiten dari IDX (mingguan), simpan lokal.

## 7. News Engine

### Sumber & filter

- **v1:** endpoint Keterbukaan Informasi IDX (idx.co.id). Sudah **ter-tag kode saham** → matching
  ke emiten 100% akurat, nol noise.
- **Filter curated price-sensitive:** hanya kategori yang biasanya menggerakkan harga —
  dividen, rights issue / private placement (HMETD), buyback, akuisisi / M&A / divestasi,
  kontrak / ekspansi material, laporan keuangan, UMA (Unusual Market Activity) & suspensi,
  perubahan kepemilikan >5%. Kategori administratif rutin dibuang.
- **Dedup:** per ID disclosure (jangan kirim ulang berita yang sama).

### Dua peran

1. **Feed berita mandiri** — disclosure curated baru dikirim ke stream NEWS Telegram, seluruh
   market (bukan cuma watchlist). Jadwal: **jam bursa** ikut siklus scan; **luar jam bursa** tiap
   **60 menit** (window luas, mis. 06:00–23:00 WIB, karena disclosure sering terbit setelah bursa
   tutup).
2. **Booster breakout** — saat ada sinyal breakout, cek apakah emiten punya disclosure curated
   dalam **48 jam** terakhir. Jika ya → label 🔥 prioritas tinggi + lampirkan headline.

### v2 (nanti)

- Adapter portal berita (Kontan / CNBC Indonesia / IQPlus dll) sebagai sumber sekunder, dengan
  logika matching nama emiten → ticker.

## 8. Alert Dispatcher & Telegram

- **Dua stream:** BREAKOUT dan NEWS. Rekomendasi: **dua channel/topik Telegram terpisah** biar
  tidak campur (chat ID dikonfigurasi di `.env`). Alternatif: satu channel dengan prefix jelas.
- **Push-only:** hanya outbound ke `api.telegram.org` (Bot API). Tidak perlu inbound/webhook/tunnel.
- **Prioritas:** alert dengan katalis berita dikirim lebih dulu / ditandai 🔥.
- **Format contoh (breakout):**

  ```
  🔥 BREAKOUT + KATALIS — BBRI
  ━━━━━━━━━━━━━━━━━━━
  Sinyal   : Resistance breakout (new 20-day high) · TF 1D
  Harga    : 4.850 (+3.2%)
  Level    : tembus resistance 4.780
  Volume   : RVOL 3.4× 🟢 (konfirmasi kuat)
  Wyckoff  : keluar range akumulasi 4.500–4.780 (28 hari)
  📰 News  : "BBRI bagikan dividen interim Rp135/saham" (IDX, 6 jam lalu)
  ⏱️ 10:47 WIB · delay data ~15 mnt
  ```

- **Format contoh (news mandiri):**

  ```
  📰 NEWS — TLKM · Aksi Korporasi
  "TLKM umumkan buyback saham senilai Rp3 triliun"
  Kategori: Buyback · IDX Disclosure · 18:20 WIB
  ```

## 9. Tech Stack

- **Bahasa:** Python 3.12 (sesuai VPS).
- **Library inti:** `yfinance`, `pandas`, `numpy`, `APScheduler`, `httpx`/`requests`,
  `python-telegram-bot` (atau Bot API langsung), `SQLite` (state/dedup), `pydantic` + `PyYAML`
  (config), `pytest` (test), logging terstruktur.
- **Struktur repo (rencana):**

  ```
  news-breakout/
    config/          # config.yaml, .env.example
    data/            # data layer (yfinance adapter, resample, cache)
    signals/         # signal engine (breakout, wyckoff, volume)
    news/            # news engine (idx adapter, filter, matcher)
    alerts/          # dispatcher, telegram, formatter, dedup store
    scheduler/       # job orchestration
    backtest/        # kalibrasi threshold
    tests/
    run.py           # entrypoint
  ```

## 10. Deployment

- **Target:** VPS `hermes-vps` (43.156.128.91, Tencent Cloud SG, Ubuntu 24.04, 2 vCPU, 1.9 GB RAM).
- **Akses:** SSH via key `~/.ssh/glenn.pem` (`ssh -i ~/.ssh/glenn.pem ubuntu@43.156.128.91`).
  Alias `hermes-vps` di config lokal memaksa password/menonaktifkan pubkey — akses memakai key
  di-override manual. (Opsional: buat alias baru yang pakai key agar mulus.)
- **Model deploy:** **systemd service + venv** (lebih ringan dari Docker; RAM VPS ketat karena
  sudah dipakai stack `hermes` ~1.3 GB). Alternatif: container slim. Diputuskan saat setup.
- **Config:** `.env` (rahasia: `TELEGRAM_BOT_TOKEN`, chat IDs) + `config.yaml` (watchlist, threshold,
  jam operasi, ambang likuiditas).
- **Coexist:** berjalan berdampingan dengan stack `hermes` + `cloudflared` yang sudah ada.
- **Budget resource:** target < 300 MB RAM lewat batch processing.
- **Observability:** logging ke file; heartbeat harian ke Telegram (opsional) untuk memastikan
  service hidup.

## 11. Constraint & Risiko (jujur)

| Risiko | Mitigasi |
|---|---|
| Data `yfinance` delay ~15 mnt & bisa rate-limit / berubah | Batch + backoff + cache; adapter pattern agar mudah ganti sumber |
| Endpoint disclosure IDX bisa berubah / anti-scrape | Isolasi di adapter, retry + error handling, alert kalau adapter gagal |
| False positive sinyal | Kalibrasi threshold via backtest; konfirmasi volume + multi-TF |
| RAM VPS ketat (~640 MB free) | Batch processing, window histori terbatas, target < 300 MB |
| Libur bursa / weekend | Kalender libur IDX; skip scan saat non-trading day |
| Timezone | Semua waktu Asia/Jakarta (WIB) eksplisit |

## 12. Testing

- **Unit test** logika sinyal atas fixture OHLCV (kasus: breakout valid, false breakout volume
  rendah, range terlalu lebar, dsb).
- **Backtest harness** atas data harian historis untuk kalibrasi threshold (Donchian N, RVOL).
- **Dry-run mode** — log alert alih-alih kirim ke Telegram (untuk testing tanpa spam).

## 13. Ruang Lingkup

### v1 (MVP)

Resistance breakout + Wyckoff range breakout, konfirmasi RVOL, multi-TF (1H/4H/1D),
watchlist + universe likuid, news IDX disclosure (feed mandiri + booster), Telegram teks (2 stream),
dedup anti-spam, config YAML, weekend auto-analysis, backtest sederhana, dry-run mode.

### Ditunda (v2+) — YAGNI

Portal berita, mini-chart image di alert, sinyal bounce-from-support & MA/volatility-squeeze,
analisis order-book/bid-offer, dashboard web, multi-user.

## 14. Item Terbuka (diputuskan saat setup/plan)

- Ambang likuiditas persis (default Rp1 miliar nilai transaksi harian) — bisa dikalibrasi.
- Telegram: dua channel vs satu channel prefix (rekomendasi: dua channel).
- Deploy: systemd+venv vs container slim (rekomendasi: systemd+venv).
- Sumber & cara refresh daftar emiten IDX (mingguan).

## Appendix A — Watchlist inti awal (24 emiten)

Disediakan pengguna (2026-07-18). Akan masuk ke `config.yaml` sebagai watchlist inti (discan tiap
siklus, lebih diprioritaskan dari universe likuid).

```
ANTM, ARCI, BREN, BRMS, BRPT, BUMI, BUVA, CUAN, DEWA, DSSA,
ENRG, HRUM, IMPC, MEDC, MINA, PANI, PTRO, RATU, RAJA, TINS,
TOBA, TPIA, VKTR, WIFI
```

Catatan:
- Komposisi didominasi energi/pertambangan/komoditas + saham grup konglomerasi besar → cenderung
  bergerak berkelompok pada sentimen sektor. Dedup + ranking prioritas alert jadi penting.
- Sebagian emiten IPO relatif baru / likuiditas bervariasi → **ketersediaan data historis intraday
  `yfinance` harus diverifikasi di langkah pertama implementasi** (butuh cukup bar untuk Donchian &
  deteksi range Wyckoff). Emiten dengan data tipis di-handle khusus (skip TF tertentu / fallback 1D).

