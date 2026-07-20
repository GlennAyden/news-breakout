# Riset Aksi Korporasi & Pergerakan Harga Saham di IDX
### Dividen · Stock Split · Right Issue — Sintesis Bukti Event Study (BEI, 2009–2026)

> **Tanggal:** 20 Juli 2026
> **Metode:** Deep-research harness — 6 angle pencarian · 27 sumber diambil · 95 klaim diekstrak → 25 diverifikasi adversarial (18 lolos / 6 gugur / 1 belum terverifikasi).
> **Sifat dokumen:** Rangkuman riset akademik untuk edukasi & analisis. **Bukan** rekomendasi investasi atau nasihat keuangan.

---

## 1. Ringkasan Eksekutif

Efek aksi korporasi terhadap harga saham di IDX **bersifat kondisional, bukan sinyal searah yang otomatis**. Arah dan kekuatannya berbeda tajam antar-jenis aksi dan antar-karakter emiten.

| Aksi Korporasi | Arah kecenderungan | Keyakinan | Inti temuan |
|---|---|---|---|
| **Stock Split** | Bias **NAIK** | Tinggi (4 studi konvergen) | Mayoritas saham naik di sekitar pengumuman; abnormal return signifikan **terutama pada emiten bertumbuh** (konfirmasi teori sinyal) |
| **Dividen / Ex-Date** | Netral / **reaksi fana** | Tinggi | Abnormal return umumnya **tidak signifikan**; harga & volume bereaksi jangka pendek lalu **mean-reverting** |
| **Right Issue** | **Tidak sistematis** | Tinggi (window pendek) | Mayoritas studi: **tidak ada reaksi harga signifikan** pada window pengumuman — muatan informasi rendah di IDX |

**Sintesis timing:**
- **Stock split** → momentum naik menjelang & sesudah *cum date* (sempat merah 1 hari sebelum, lalu naik).
- **Dividen** → reaksi harga & volume nyata di jendela pendek (~t−5…t+5) tetapi cepat luntur (mean-reverting).
- **Right issue** → umumnya tidak ada pergerakan harga sistematis yang bisa diatribusikan ke pengumuman.

---

## 2. Cara Membaca Laporan Ini (3 catatan metodologis)

1. **Window pendek ≠ drift jangka menengah.** Hampir semua studi mengukur *abnormal return* pada jendela hari (mis. t−5 s/d t+5, atau t−7 s/d t+7). Ini menjawab "reaksi seketika di sekitar tanggal aksi", bukan pergerakan berbulan-bulan.
2. **"Tidak ada perbedaan" ≠ "tidak berpengaruh."** Banyak studi menguji *perbedaan* abnormal return sebelum vs sesudah. Hasil "tidak signifikan" berarti pasar sudah mengantisipasi (efisien), bukan berarti aksinya tak punya arti ekonomi.
3. **Verifikasi adversarial & kualitas sumber.** Tiap klaim melewati 3 pemungutan suara skeptis; butuh mayoritas untuk lolos. Notasi: `3-0` = konfirmasi bulat, `0-3` = gugur, `1-0 (2 error)` = belum terverifikasi. Sebagian besar bukti berasal dari **jurnal nasional berjenjang rendah–menengah**; hanya satu peer-review internasional bereputasi (Springer). Baca tiap temuan sebagai *"satu/beberapa studi menemukan X"*, bukan hukum universal.

---

## 3. Stock Split — Bias Naik yang Terkonfirmasi

**Arah: NAIK · Keyakinan: Tinggi · vote 3-0**

Ini kategori dengan bukti paling meyakinkan; empat studi lintas periode (2011–2020) konvergen ke arah yang sama.

**Temuan inti:**
- Di sekitar pengumuman, **18 dari 25 emiten** mengalami kenaikan harga relatif (7 turun).
- Return harian rata-rata naik dari **0,41%** (t−5) menjadi **0,96%** (t+5) — naik ~0,55 poin persentase.
- Pola khas: sempat **negatif satu hari sebelum**, lalu berbalik naik pada **cum date** dan sesudahnya.

| Studi (sampel · periode) | Temuan inti | Uji | Status |
|---|---|---|---|
| 45 emiten *split-up* · 2011–2015 | Abnormal return signifikan **hanya pada 36 emiten bertumbuh**; tidak signifikan pada 9 emiten tidak bertumbuh | t-test | `3-0` |
| 66 emiten · 2015–2019 | Ada perbedaan abnormal return signifikan sebelum vs sesudah split | Wilcoxon | `3-0` |
| 37 emiten · 2017–2020 | Perbedaan abnormal return signifikan sebelum vs sesudah split | event study | `3-0` |
| 25 emiten · 2018–2020 | Harga relatif rata-rata naik ~979 → ~1010; sig. 0,012 | Wilcoxon | `belum (error infra)` |

> **⚠ Mitos yang gugur:** Anggapan "split otomatis menaikkan likuiditas" **tidak didukung**. Studi 66 emiten (2015–2019) menemukan *tidak ada* perbedaan volume perdagangan (TVA) signifikan sebelum vs sesudah split. Klaim "TVA naik signifikan pasca-split" direfutasi bulat `0-3`. Naiknya harga ≠ naiknya likuiditas.

**Kualifikasi penting:** efek terkonsentrasi pada *perusahaan bertumbuh*, dan sebagian metrik masih *raw return* (belum disesuaikan pasar) — jadi sebagian kenaikan bisa mencerminkan tren bull 2011–2020 secara umum, bukan murni efek split.

---

## 4. Dividen & Ex-Date — Reaksi Fana

**Arah: Netral / fana · Keyakinan: Tinggi · vote 3-0**

Reaksi ada, tapi cepat luntur. Untuk abnormal return, mayoritas studi menemukan efek yang lemah/tidak signifikan.

**Temuan inti:** Empat bank besar **BBCA, BBRI, BBNI, BMRI** (2020–2024) — abnormal return *tidak* berbeda signifikan sebelum vs sesudah ex-date, **tetapi** harga saham & volume perdagangan *berbeda signifikan* pada jendela pendek. Ex-date menggerakkan aktivitas dagang sesaat, bukan cuan berlebih yang berkelanjutan.

| Studi (sampel · periode) | Temuan inti | Sig. | Status |
|---|---|---|---|
| 45 emiten · 2015 (pengumuman dividen) | Pasar bereaksi negatif; abnormal return t−7…t+7 **tidak signifikan** | n.s. | `3-0` |
| LQ45 · 2019 vs 2020 (Springer) | Masa COVID: abnormal return negatif **tidak signifikan** | n.s. | `3-0` |
| 252 event dividen · 2020 (COVID) | Ada reaksi pasar pada abnormal return & volume | sig. | `3-0` |
| 26 emiten LQ45 · 2016–2018 (ex-date) | Tidak ada beda abnormal return sebelum vs sesudah | 0,486 | `3-0` |
| 4 bank besar · 2020–2024 (ex-date) | AR tidak beda; harga & volume beda signifikan (jangka pendek) | mixed | `3-0` |

> **"Dividend trap" (praktik pasar, sumber sekunder):** harga cenderung **naik menjelang cum date** (buru dividen), lalu **turun setelah ex date** kira-kira sebesar nilai dividen. Investor yang masuk hanya untuk mengejar dividen sering "terjebak" — capital loss ≥ dividen yang diterima. Konsisten dengan temuan akademik "efek mean-reverting".

> **⚠ Yang gugur:** Klaim "kenaikan *dan* penurunan dividen sama-sama menghasilkan AAR positif signifikan" gagal verifikasi `1-2`. Klaim "harga perbankan turun signifikan setelah ex-date (window 12 hari)" direfutasi `0-3`. Arah efek dividen **tergantung sampel & periode**, tidak searah.

---

## 5. Right Issue — Nyaris Tak Bergerak (di Window Pendek)

**Arah: Tidak sistematis · Keyakinan: Tinggi (window pendek) · vote 3-0**

**Temuan inti:** Mayoritas studi BEI menemukan **tidak ada perbedaan abnormal return signifikan** sebelum vs sesudah pengumuman right issue.

| Studi (sampel · periode) | Temuan inti | Sig. | Status |
|---|---|---|---|
| 89 emiten · window 11 hari | Tidak ada perbedaan abnormal return signifikan | n.s. | `3-0` |
| 27 emiten · 2018–2020 | Pasar tidak bereaksi (Wilcoxon) | 0,218 | `2-0 (1 err)` |
| Manufaktur · 2010–2016 | Beda AR sebelum-sesudah tidak signifikan | n.s. | `3-0` |
| Gabungan RI/split/M&A · 2020–2023 | Tidak ada beda AR signifikan lintas ketiga aksi | n.s. | `2-1` |

Interpretasi: "kejutan pengumuman" right issue di IDX relatif kecil — muatan informasinya rendah, kemungkinan karena dilusi sudah terantisipasi pasar.

> **⚠ Jangan digeneralisasi:** Klaim ekstrem "pasar IDX tidak semi-strong efficient" dan "right issue tanpa muatan informasi (universal)" **direfutasi bulat** `0-3`. Faktanya campur: sebagian emiten tetap bereaksi tergantung tujuan & kualitasnya (mis. penggunaan dana untuk ekspansi vs menambal utang).

---

## 6. Peta Waktu Pergerakan Harga (ilustratif)

Arah kecenderungan relatif terhadap tanggal kunci — berbasis pola agregat, bukan jaminan tiap saham.

```
STOCK SPLIT (relatif Cum Date)
 t-10 ───────────► Cum Date ───────────► t+10
 [ akumulasi/datar ][−1 hari merah][ ▲ momentum naik ]

DIVIDEN (relatif Ex Date)
 t-10 ───────────► Ex Date ───────────► t+10
 [ ▲ naik buru dividen ][ ▼ gap turun ][ normalisasi/mean-revert ]

RIGHT ISSUE (relatif Pengumuman)
 t-5 ───────────► Pengumuman ───────────► t+5
 [ ——— tidak ada arah sistematis pada window pengumuman ——— ]
```

---

## 7. Catatan Verifikasi Price Action & Berita

Agar transparan soal batas riset ini:

- **Belum ada rekonstruksi price action mandiri** dari data harga harian saham spesifik 2020–2026. Seluruh bukti kuantitatif berasal dari *event study* akademik, bukan penarikan data harga tick/harian sendiri.
- **Analisis berita belum menghasilkan klaim terverifikasi** dalam putaran ini. Yang tersedia hanya *sumber sekunder berita* sebagai ilustrasi arah (belum diverifikasi angka):

| Saham / Peristiwa | Aksi | Narasi berita | Sumber |
|---|---|---|---|
| BBCA | Stock split | Harga dilaporkan "melaju" usai stock split | Kontan |
| BMRI | Stock split (1:2, 2023) | Framing "harga bakal melesat" pasca-split | CNBC Indonesia |
| BMRI | Dividen jumbo (2026) | Dividen Rp475,95/saham, yield menarik | Bareksa |
| 8 saham right issue jumbo | Right issue | "Diam-diam tancap gas" (2025) — sebagian rally pasca-aksi | CNBC Indonesia |

---

## 8. Implikasi Taktis

Terjemahan bukti ke kalibrasi ekspektasi (bukan rekomendasi beli/jual):

1. **Stock split — condong ke sisi beli, saring by fundamental.** Bias naik nyata tapi *terkonsentrasi pada emiten bertumbuh*. Prioritaskan emiten dengan pertumbuhan laba/aset, bukan sekadar "murah karena dipecah". Titik merah 1 hari sebelum cum date bisa jadi entry taktis.
2. **Jangan berdagang split demi likuiditas.** Bukti TVA-naik gugur. Tesis "split → ramai → mudah keluar-masuk" tak terdukung data.
3. **Dividen — waspadai dividend trap.** Reaksi harga fana dan mean-reverting. Ukur *total return* (harga + dividen), bukan yield saja.
4. **Right issue — abaikan "kejutan pengumuman".** Window pendek tidak memberi edge sistematis. Fokus geser ke *alasan* right issue: ekspansi produktif & standby buyer kredibel = konstruktif; tambal utang/dilusi murni = hati-hati.

---

## 9. Klaim yang Gugur Verifikasi

Enam klaim yang direfutasi mayoritas suara — penting agar tidak beredar sebagai "fakta":

| Vote | Klaim yang gugur |
|---|---|
| `0-3` | "Pasar BEJ tidak bereaksi ke right issue → IDX bukan pasar semi-strong efficient" (terlalu generalisasi) |
| `0-3` | "Right issue tanpa muatan informasi (universal), pasar tidak bereaksi" (realitanya campur) |
| `0-3` | "Trading volume activity naik signifikan setelah stock split (likuiditas meningkat)" |
| `0-3` | "Harga saham perbankan turun signifikan setelah ex-dividend date (window 12 hari)" |
| `1-2` | "Kenaikan & penurunan dividen (masa pandemi) sama-sama menghasilkan AAR positif signifikan" |
| `1-2` | "Abnormal return right issue di BEJ tak berbeda signifikan → tak ada reaksi arah (versi lama)" |

---

## 10. Keterbatasan & Pertanyaan Terbuka

**Keterbatasan:**
- **Kualitas sumber timpang** — mayoritas jurnal nasional berjenjang rendah–menengah; hanya 1 peer-review internasional bereputasi (Springer). Perlakukan setiap angka sebagai indikatif.
- **Sampel kecil** — beberapa studi n sangat kecil (9 emiten perbankan; 9 emiten tidak-bertumbuh; 25–27 emiten).
- **Raw vs abnormal return** — sebagian angka (mis. 0,41%→0,96%) belum disesuaikan pasar; sebagian gerak bisa cerminan tren bull umum.
- **Sensitif waktu** — periode COVID 2020 anomali (volatilitas & arah beda); jangan dipukul rata dengan periode normal.
- **Belum ada rekonstruksi price action** dari data harga harian saham spesifik, dan **analisis berita belum terverifikasi**.

**Pertanyaan terbuka untuk riset lanjutan:**
- Berapa magnitudo abnormal return *market-adjusted* aktual per saham IDX di sekitar cum/ex/pengumuman 2020–2026?
- Adakah *price run-up* pra-pengumuman (kebocoran info) untuk split & dividen di IDX?
- Mengapa right issue miskin reaksi — antisipasi dilusi, kualitas emiten, atau tujuan dana (ekspansi vs bayar utang)?
- Apakah karakter "bertumbuh vs tidak bertumbuh" adalah prediktor kunci arah abnormal return lintas semua jenis aksi korporasi?

---

## 11. Daftar Sumber

**Jurnal primer (event study):**
- Springer — *Dividend announcement effect pre/during COVID-19, IDX* (SN Business & Economics) — https://link.springer.com/article/10.1007/s43546-021-00198-8
- IJEFM — *252 event dividen di IDX 2020 (COVID)* — https://ijefm.co.in/v7i11/10.php
- Neliti — *Reaksi pasar terhadap pengumuman dividen (45 emiten, 2015)* — https://media.neliti.com/media/publications/254997-reaksi-pasar-terhadap-pengumuman-dividen-2c49474b.pdf
- STIMI — *Abnormal return sekitar ex-dividend date (26 emiten LQ45, 2016–2018)* — https://ejurnal.stimi-bjm.ac.id/index.php/JRIMK/article/view/75
- OJS Pustek — *Perilaku harga, volume, AR sekitar ex-date (Bank Buku 4, 2020–2024)* — https://ojspustek.org/index.php/SJR/article/view/1575
- Politeknik Bosowa (Pabean) — *Ex-dividend date perbankan* — https://journal.politeknikbosowa.ac.id/pabean/article/view/723
- UNTAG Semarang — *Stock split & right issue, harga relatif (25 emiten, 2018–2020)* — https://jurnal2.untagsmg.ac.id/index.php/sa/article/download/1096/995
- UNAS (Oikonamia) — *Stock split, return harian t−5→t+5* — https://journal.unas.ac.id/oikonamia/article/download/502/396/1280
- IJEFB — *Stock split & TVA (66 emiten, 2015–2019, Wilcoxon)* — https://journal.srnintellectual.com/index.php/ijfeb/article/view/4
- DIJEFA (Dinasti) — *Stock split, likuiditas & abnormal return* — https://dinastipub.org/DIJEFA/article/view/546
- JAFM (Dinasti) — *Abnormal return: Right Issue, Stock Split, M&A (IDX 2020–2023)* — https://dinastires.org/JAFM/article/view/1550
- Neliti — *Abnormal return sebelum/sesudah right issue (89 emiten)* — https://www.neliti.com/id/publications/245216/studi-empiris-abnormal-return-sebelum-dan-sesudah-pengumuman-right-issue-pada-pe
- UB (JAB) — *Reaksi right issue, manufaktur 2010–2016* — https://administrasibisnis.studentjournal.ub.ac.id/index.php/jab/article/view/1961

**Berita / edukasi pasar (sekunder — belum diverifikasi angka):**
- Kontan — *Harga BBCA melaju usai stock split* — https://investasi.kontan.co.id/news/harga-saham-bbca-melaju-usai-stock-split-investor-harus-apa
- CNBC Indonesia — *BMRI pecah saham (1:2, 2023)* — https://www.cnbcindonesia.com/research/20230404091338-128-427109/bank-mandiri--bmri--pecah-saham-harganya-bakal-melesat
- Bareksa — *BMRI dividen jumbo Rp475,95/saham (2026)* — https://www.bareksa.com/berita/saham/2026-05-04/bmri-tebar-dividen-jumbo-rp47695-per-saham-yield-menarik
- CNBC Indonesia — *8 saham right issue jumbo "tancap gas" (2025)* — https://www.cnbcindonesia.com/research/20251119161854-128-686683/bukan-sekadar-right-issue-jumbo-8-saham-ini-diam-diam-tancap-gas
- Stockbit Snips — *Mekanika cum/ex date & pola harga* — https://snips.stockbit.com/investasi/kapan-jual-saham-agar-dapat-dividen
- UMSIDA — *Fenomena dividend trap* — https://manajemen.umsida.ac.id/fenomena-dividen-trap-keuntungan/

---

*Disclaimer: Dokumen ini rangkuman riset akademik untuk tujuan edukasi & analisis, bukan rekomendasi investasi, ajakan membeli/menjual, atau nasihat keuangan yang dipersonalisasi. Kinerja masa lalu tidak menjamin hasil masa depan. Angka event study bersifat indikatif dan bergantung sampel, periode, jendela, serta metode uji.*
