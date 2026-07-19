# Smart News Curation — Design Spec

- **Date:** 2026-07-19
- **Status:** Approved (design) — pending spec review
- **Owner:** news-breakout
- **Supersedes:** the "send everything + tag corporate action" half of the Option-B portal work (commit `79a1b31`). The **broad fetch** and **materiality/relevance gate** from Option B are **reused** as the foundation.

## 1. Problem & Goal

The portal news feed currently forwards every ticker/keyword-matched item straight to Telegram as `title + link`. Two problems:

1. **No quality curation** — the trader wants only *material* news, not every market recap.
2. **Thin messages** — just a headline + a raw URL; no digest, no signal on tone.

**Goal:** insert a lightweight curation + enrichment stage before sending, so each Telegram message is: a **materially-relevant** item, with a **1–2 sentence summary**, a **sentiment tag**, and a **clickable headline** (no raw URL). Runs 24/7 hourly on the always-on VPS (`hermes-vps`, 2 GB RAM / 2 cores).

## 2. Key Decisions (from brainstorming)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Gate = materiality + relevance** (rule-based). Sentiment is a **tag**, never the gate. | Filtering on positive sentiment would drop material *negative* news (fraud, losses, delisting) — dangerous for a trader. |
| D2 | **Sentiment model:** `w11wo/indonesian-roberta-base-sentiment-classifier` (HF, MIT, ~125M, CPU). | Indonesian finance-specific sentiment models are immature. This is the reliable general-ID choice. Runs locally, light. |
| D3 | **Summary = extractive** (1–2 lead/core sentences from the full article). No abstractive model. | VPS is 2 GB and already ~1 GB into swap; T5-base abstractive is risky. Lead sentences of Indonesian news (inverted pyramid) are a solid summary. Clean upgrade path to T5-via-API later. |
| D4 | **Fetch full article body** via a generic extractor (`trafilatura`); sources unchanged. | RSS descriptions are often truncated/empty. Full text → accurate summary + better gate. No per-site scrapers. |
| D5 | **Cheap gate first, then fetch full body** only for passers. | Bounds full-article fetches to ~30–80/hour instead of 200+. |
| D6 | **Sentiment runs in a subprocess**, fully **optional & degradable**. | Releases torch RAM after each run; keeps the always-on scheduler light. If it fails or is disabled, news still flows untagged. |
| D7 | **Telegram HTML hyperlink** on the headline; drop raw URL; disable web preview. | Native, no third-party shortener. Clickable, compact, brings the headline back as context. |
| D8 | **Cap `max_per_run` (default 20)**; overflow waits for the next hourly run. | Prevents a flood on the first catch-up run. |

## 3. Pipeline (in `run_portal_feed`, hourly on VPS)

```
1. fetch_portal_news(sources, tickers, name_map, corp_keywords)
      parse RSS (title + description)
      CHEAP GATE: keep item iff  match_ticker(...)  OR  has_corp_action(...)
      → ~30–80 relevant/material items (not 200+)      [existing Option-B logic]

2. for each passing item:
      html = http_get(item.url)
      body = fetch_article_text(html)                  # trafilatura; "" on failure
      item.lead = lead_summary(body or item.summary, n=summary_sentences)
      # article fetch failure ⇒ fall back to RSS description; item is NOT dropped

3. labels = classify([ (item.lead or item.title) for item in items ])   # subprocess
      item.sentiment = "positif" | "negatif" | "netral" | ""            # "" if degraded

4. sort key: (not corp_action, -sentiment_strength, timestamp)          # material first

5. cap to max_per_run → dedup by URL (existing) → send(format_portal(item), parse_mode="HTML")
```

**Resilience:** every heavy stage (article fetch, sentiment) degrades gracefully — on failure the item still sends, just without the enrichment.

## 4. Modules & Interfaces

Small, single-purpose units, each testable in isolation via dependency injection.

### `news/extract.py` (NEW)
```python
def fetch_article_text(url: str, *, http_get) -> str:
    """Fetch URL via http_get(url)->html, return trafilatura-extracted main text, or "" on any failure."""

def lead_summary(text: str, n: int = 2, *, max_chars: int = 320) -> str:
    """Pure. Split into sentences, return the first n non-trivial sentences joined, truncated to max_chars."""
```
- `lead_summary` is a pure function → straightforward unit tests (short text, empty, >n sentences, truncation).
- `fetch_article_text` takes an injected `http_get` (same pattern as `fetch_portal_news`) → testable without network; `trafilatura.extract` is the only import (lazy, inside the function, so import failure degrades to "").

### `news/sentiment.py` (NEW)
```python
def classify(texts: list[str], *, runner=_default_runner, min_confidence: float = 0.6) -> list[str]:
    """Return a label per input text, aligned by index.
       label ∈ {"positif","negatif","netral",""}. Below min_confidence ⇒ "netral".
       Any runner failure ⇒ ["" , ...] (all empty) so callers degrade to no tag."""

def _default_runner(texts: list[str]) -> list[dict]:
    """Spawn `python scripts/score_sentiment.py`, send texts as JSON on stdin,
       read [{label, score}, ...] from stdout. Timeout ~60s. Raise on failure."""
```
- Tests inject a fake `runner` → verify label mapping, confidence threshold, and the all-empty degradation path. No torch needed in tests.

### `scripts/score_sentiment.py` (NEW — subprocess entry point)
- Reads a JSON list of strings from stdin.
- Lazy-imports `transformers` + `torch`; loads the cached model once (`sentiment.model`).
- Runs the classifier; maps model labels → `positif/netral/negatif`.
- Writes `[{"label": ..., "score": ...}, ...]` JSON to stdout.
- Isolated process ⇒ all torch RAM is reclaimed on exit.

### `news/portal.py` (MODIFY — mostly already done)
- `parse_rss` (captures `summary` from `<description>`) and the gate (`match_ticker` OR `has_corp_action`) already exist from Option B. Keep as the **cheap pre-gate**.

### `news/feed.py` (MODIFY `run_portal_feed`)
- New injectable params: `extractor=fetch_article_text`, `classifier=classify` (defaults wired to the real ones; tests pass fakes).
- Orchestrates steps 2–5. Passes `parse_mode="HTML"`, `disable_preview=True` to the sender.
- Honors `settings.portal_max_per_run`; overflow items are simply not sent this run (not marked sent → reconsidered next run).

### `news/formatter.py` (MODIFY `format_portal`)
- Emits **HTML**. HTML-escapes every dynamic field (`html.escape`), then wraps the headline as `<a href="{url}">{title}</a>`.
- Header: `🚨 AKSI KORPORASI · {ticker}` if `corp_action` else `📰 {ticker or "Berita Pasar"}`.
- Sentiment chip appended to header only when `sentiment in {"positif","negatif"}` (netral / empty ⇒ hidden): `📈 Positif` / `📉 Negatif`.
- Body: hyperlinked headline, then `item.lead`, then `🕒 {ts} WIB · {source}`. **No raw URL line.**

### `alerts/telegram.py` (MODIFY `send_message`)
- Add `parse_mode: str | None = None` and `disable_preview: bool = False`.
- When set, include `parse_mode` and `disable_web_page_preview` in the payload. Existing callers (IDX disclosures, breakout alerts) unchanged (default None ⇒ plain text as today).

## 5. Data Model

`PortalNews` gains:
```python
lead: str = ""        # displayed extractive summary
sentiment: str = ""   # "positif" | "negatif" | "netral" | ""
```
`summary` (RSS description, used for matching) and `corp_action` already exist.

## 6. Message Format (HTML)

```
🚨 AKSI KORPORASI · ANTM   📈 Positif
<a href="URL">Antam tebar dividen Rp120/saham</a>
Antam mengumumkan dividen tunai Rp120/saham untuk tahun buku 2025. Pembayaran awal Agustus.
🕒 19 Jul 14:30 WIB · cnbcindonesia.com
```
- Headline = clickable (native HTML link). Default link text = **article title**. (Alternatives the user may pick: `🔗 Baca selengkapnya →`, or source name.)
- `disable_web_page_preview: true` for compactness.
- Netral / low-confidence ⇒ no sentiment chip.

## 7. Materiality Gate (reused)

Keep an item iff EITHER:
- `match_ticker(title+summary, universe, name_map)` resolves a ticker (mentions an emiten in watchlist ∪ universe), OR
- `has_corp_action(title+summary, curated_keywords)` — the existing corporate-action keyword list (dividen, rights issue, akuisisi, RUPS, buyback, stock split, kontrak, obligasi, …).

Pure macro/general news that references neither is dropped. `corp_action=True` items are prioritized and get the 🚨 header.

## 8. Error Handling / Degradation

| Failure | Behavior |
|---------|----------|
| Article fetch/extract fails | Fall back to RSS `summary` for `lead`; item still sent. |
| `trafilatura` import missing | `fetch_article_text` returns "" ⇒ RSS-description fallback. |
| Sentiment subprocess errors/timeout | All labels "" ⇒ no chips; news still sent. Logged once. |
| `sentiment.enabled: false` | Sentiment step skipped entirely. |
| Telegram send fails | Existing retry (2×) + not marked sent ⇒ retried next run. |

## 9. Config (new keys)

```yaml
portal:
  summary_sentences: 2     # extractive lead length
  max_per_run: 20          # anti-flood cap per hourly run
sentiment:
  enabled: true
  model: w11wo/indonesian-roberta-base-sentiment-classifier
  min_confidence: 0.6      # below ⇒ treated as netral (chip hidden)
```
Mirrored as `Settings` fields with defaults; validated like existing settings.

## 10. Dependencies & VPS Ops

- **`requirements.txt`:** add `trafilatura` (light, pure-Python-ish).
- **`requirements-ml.txt` (NEW, VPS-only):** `transformers`, `torch` (CPU wheel). Keeps torch out of the GitHub Actions price job (which pins its own deps inline) and out of any light install.
  - Install on VPS: `pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu` (or the CPU index for torch).
- **Model cache:** first run downloads `w11wo/...` (~0.5 GB) into the HF cache on the VPS (15 GB free — fine). Pre-warm once during deploy.
- **RAM:** sentiment only runs inside the short-lived subprocess during the hourly job; the always-on scheduler process never imports torch.

## 11. Scheduling / Volume

- Cadence unchanged: hourly `news_job` (`news_poll_interval_minutes`).
- Expected post-gate volume ~20–50/day; `max_per_run` caps bursts.
- Full-article fetches bounded to passers (~30–80/hour worst case).

## 12. Dedup

- Keep existing **per-URL** dedup (`DedupStore.news_already_sent`).
- Cross-portal near-duplicate (same story, different source) is **out of scope for v1** — revisit if the feed feels repetitive (candidate: normalized `ticker + title` within an N-hour window).

## 13. Testing

- `extract.lead_summary`: pure-function cases (n sentences, short/empty, truncation, Indonesian sentence boundaries).
- `extract.fetch_article_text`: injected `http_get`; extraction happy-path + failure ⇒ "".
- `sentiment.classify`: fake runner ⇒ label mapping, confidence threshold, all-empty degradation.
- `feed.run_portal_feed`: injected fetcher/extractor/classifier/sender ⇒ orchestration, cap, dedup, sort order (corp-action + strong sentiment first), degradation when extractor/classifier fail, and that `parse_mode="HTML"` is passed.
- `formatter.format_portal`: HTML escaping, hyperlinked headline, sentiment chip shown/hidden, corp vs non-corp header, no raw URL.
- Full suite stays green (currently 179 tests).

## 14. Out of Scope / Future

- Abstractive summary (T5 via HF Inference API) — clean upgrade behind the `lead_summary` interface.
- Cross-portal semantic dedup.
- Sentiment applied to IDX disclosures (this spec covers the **portal** feed; disclosures already curated by keyword).
- Expanding portal sources.

## 15. Defaults Chosen (user may veto at review)

1. Sentiment in a subprocess (RAM isolation).
2. `max_per_run = 20`.
3. Per-URL dedup only (no cross-portal dedup in v1).
4. Link text = article title (hyperlinked); raw URL removed; web preview disabled.
