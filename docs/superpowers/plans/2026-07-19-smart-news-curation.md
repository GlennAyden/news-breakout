# Smart News Curation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Curate the portal news feed so each Telegram message is a materially-relevant item with a 1–2 sentence extractive summary, an optional sentiment tag, and a clickable (hyperlinked) headline instead of a raw URL.

**Architecture:** Reuse the existing rule-based materiality gate (mentions an emiten OR a corporate-action keyword) to decide send/drop. For each passing item, fetch the full article body (`trafilatura`) and take the first 1–2 sentences as the summary; attach an optional sentiment tag from a HF Indonesian sentiment classifier that runs in a throwaway subprocess (so torch RAM is reclaimed and the always-on process never imports torch). Render as Telegram HTML with the headline as a native hyperlink. Every heavy stage degrades gracefully — a failure never drops the news item.

**Tech Stack:** Python 3.12, pytest (TDD), `trafilatura` (article extraction), `transformers`+`torch` CPU (subprocess only), Telegram Bot API (HTML parse mode), existing `httpx`/`curl_cffi`.

## Global Constraints

- Run tests with: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q` (Windows dev box; VPS is Linux).
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- **No network in tests.** Inject `http_get` / `extractor` / `classifier` / Telegram `client`.
- **`torch`/`transformers` must never be imported at module top level or in the always-on scheduler process.** They are imported ONLY inside `scripts/score_sentiment.py` (the subprocess). `news/sentiment.py` imports only stdlib.
- **Graceful degradation is mandatory:** article-fetch failure ⇒ fall back to the RSS description; sentiment failure/disabled ⇒ no tag. Neither drops the item.
- HTML-escape every dynamic field before putting it in an HTML Telegram message.
- Branch: `feat/smart-news-curation` (already checked out; baseline `efddc4e`).
- Current `PortalNews(ticker, title, timestamp, url, source, summary="", corp_action=False)`; `fetch_portal_news(sources, watchlist, name_map, *, now, http_get=None, corp_keywords=None)`; `match_ticker`, `has_corp_action`, `_default_http_get` already exist in `news/portal.py`.

---

### Task 1: Article fetch + extractive summary (`news/extract.py`)

**Files:**
- Create: `news_breakout/news/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `lead_summary(text: str, n: int = 2, *, max_chars: int = 320) -> str`
  - `fetch_article_text(url: str, *, http_get, extractor=None) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extract.py`:
```python
from news_breakout.news.extract import lead_summary, fetch_article_text


# ---- lead_summary (pure) ----------------------------------------------------

def test_lead_summary_takes_first_two_sentences():
    text = "Antam tebar dividen Rp120. Pembayaran awal Agustus. Rapat sudah setuju."
    out = lead_summary(text, 2)
    assert out == "Antam tebar dividen Rp120. Pembayaran awal Agustus."


def test_lead_summary_single_sentence_returns_it():
    assert lead_summary("Hanya satu kalimat saja", 2) == "Hanya satu kalimat saja"


def test_lead_summary_empty_returns_empty():
    assert lead_summary("", 2) == ""
    assert lead_summary(None, 2) == ""


def test_lead_summary_collapses_whitespace():
    assert lead_summary("  a\n\n  b.  c d.  ", 1) == "a b."


def test_lead_summary_truncates_to_max_chars():
    long = "kata " * 200  # one very long "sentence"
    out = lead_summary(long, 2, max_chars=50)
    assert len(out) <= 51 and out.endswith("…")


# ---- fetch_article_text (injected http_get + extractor) ---------------------

def test_fetch_article_text_extracts_body():
    out = fetch_article_text(
        "https://x/1",
        http_get=lambda u: "<html>..</html>",
        extractor=lambda html: "  isi artikel  ",
    )
    assert out == "isi artikel"


def test_fetch_article_text_http_failure_returns_empty():
    def boom(u):
        raise RuntimeError("net down")
    assert fetch_article_text("https://x/1", http_get=boom, extractor=lambda h: "x") == ""


def test_fetch_article_text_extractor_failure_returns_empty():
    def boom(html):
        raise ValueError("bad html")
    assert fetch_article_text("https://x/1", http_get=lambda u: "<html>", extractor=boom) == ""


def test_fetch_article_text_extractor_returns_none_becomes_empty():
    assert fetch_article_text("https://x/1", http_get=lambda u: "<html>",
                              extractor=lambda h: None) == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_extract.py -q`
Expected: FAIL — `ModuleNotFoundError: news_breakout.news.extract`.

- [ ] **Step 3: Write the implementation**

Create `news_breakout/news/extract.py`:
```python
from __future__ import annotations

import re

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def lead_summary(text: str, n: int = 2, *, max_chars: int = 320) -> str:
    """Return the first ``n`` sentences of ``text`` as a compact summary.

    Pure function. Collapses whitespace, splits on sentence boundaries, joins the
    first ``n`` non-trivial sentences, and truncates to ``max_chars`` (adding an
    ellipsis) so a single run-on sentence can't produce a wall of text.
    """
    text = " ".join((text or "").split())
    if not text:
        return ""
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if len(s.strip()) > 1]
    summary = " ".join(sentences[:n]).strip() if sentences else text
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "…"
    return summary


def fetch_article_text(url: str, *, http_get, extractor=None) -> str:
    """Fetch ``url`` via ``http_get`` and return the extracted main article text.

    ``extractor`` maps raw HTML -> main text (defaults to trafilatura, imported
    lazily so a missing dependency degrades to ""). Any failure returns "".
    """
    if extractor is None:
        extractor = _trafilatura_extract
    try:
        html = http_get(url)
    except Exception:  # noqa: BLE001 — network errors must never propagate
        return ""
    try:
        return (extractor(html) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _trafilatura_extract(html: str):
    import trafilatura
    return trafilatura.extract(html)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_extract.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/extract.py tests/test_extract.py
git commit -m "feat(news): article fetch + extractive lead summary"
```

---

### Task 2: Sentiment classify + label normalization (`news/sentiment.py`)

**Files:**
- Create: `news_breakout/news/sentiment.py`
- Test: `tests/test_sentiment.py`

**Interfaces:**
- Consumes: nothing at test time (inject `runner`); at runtime calls `scripts/score_sentiment.py` (Task 3).
- Produces:
  - `classify(texts: list[str], *, runner=None, min_confidence: float = 0.6) -> list[str]` — one label per text, aligned by index; label ∈ `{"positif","negatif","netral",""}`. `""` only on failure.
  - `_normalize_label(raw: str) -> str`
  - `_default_runner(texts: list[str]) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sentiment.py`:
```python
from news_breakout.news.sentiment import classify, _normalize_label


def test_normalize_label_variants():
    assert _normalize_label("positive") == "positif"
    assert _normalize_label("LABEL positif") == "positif"
    assert _normalize_label("negative") == "negatif"
    assert _normalize_label("neutral") == "netral"
    assert _normalize_label("netral") == "netral"
    assert _normalize_label("") == ""
    assert _normalize_label("weird") == ""


def test_classify_confident_positive():
    runner = lambda texts: [{"label": "positive", "score": 0.92}]
    assert classify(["x"], runner=runner) == ["positif"]


def test_classify_confident_negative():
    runner = lambda texts: [{"label": "negative", "score": 0.81}]
    assert classify(["x"], runner=runner) == ["negatif"]


def test_classify_low_confidence_becomes_netral():
    runner = lambda texts: [{"label": "positive", "score": 0.40}]
    assert classify(["x"], runner=runner, min_confidence=0.6) == ["netral"]


def test_classify_neutral_label_is_netral():
    runner = lambda texts: [{"label": "neutral", "score": 0.99}]
    assert classify(["x"], runner=runner) == ["netral"]


def test_classify_runner_exception_degrades_to_empty():
    def boom(texts):
        raise RuntimeError("subprocess died")
    assert classify(["a", "b"], runner=boom) == ["", ""]


def test_classify_length_mismatch_degrades_to_empty():
    runner = lambda texts: [{"label": "positive", "score": 0.9}]  # 1 for 2 inputs
    assert classify(["a", "b"], runner=runner) == ["", ""]


def test_classify_empty_input_returns_empty_list():
    assert classify([], runner=lambda t: []) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_sentiment.py -q`
Expected: FAIL — `ModuleNotFoundError: news_breakout.news.sentiment`.

- [ ] **Step 3: Write the implementation**

Create `news_breakout/news/sentiment.py`:
```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPT = str(Path(__file__).resolve().parents[2] / "scripts" / "score_sentiment.py")


def _normalize_label(raw: str) -> str:
    r = (raw or "").lower()
    if "pos" in r:
        return "positif"
    if "neg" in r:
        return "negatif"
    if "neu" in r or "net" in r:
        return "netral"
    return ""


def _default_runner(texts: list[str]) -> list[dict]:
    """Score ``texts`` by shelling out to the model subprocess (torch isolated there)."""
    proc = subprocess.run(
        [sys.executable, _SCRIPT],
        input=json.dumps(texts),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sentiment subprocess failed: {proc.stderr[-500:]}")
    return json.loads(proc.stdout)


def classify(texts: list[str], *, runner=None, min_confidence: float = 0.6) -> list[str]:
    """Return one sentiment label per input text, aligned by index.

    Labels: "positif"/"negatif" only when confident, else "netral". On ANY runner
    failure or a length mismatch, returns all "" so callers degrade to no tag.
    """
    if not texts:
        return []
    if runner is None:
        runner = _default_runner
    try:
        raw = runner(texts)
    except Exception:  # noqa: BLE001 — model failures must never propagate
        return [""] * len(texts)
    if not isinstance(raw, list) or len(raw) != len(texts):
        return [""] * len(texts)
    out = []
    for item in raw:
        item = item or {}
        label = _normalize_label(item.get("label", ""))
        score = float(item.get("score", 0.0) or 0.0)
        if label in ("positif", "negatif") and score >= min_confidence:
            out.append(label)
        else:
            out.append("netral")
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_sentiment.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/sentiment.py tests/test_sentiment.py
git commit -m "feat(news): sentiment classify with graceful degradation"
```

---

### Task 3: Sentiment model subprocess (`scripts/score_sentiment.py`)

**Files:**
- Create: `scripts/score_sentiment.py`

**Interfaces:**
- Consumes: stdin = JSON list of strings.
- Produces: stdout = JSON list of `{"label": <raw model label>, "score": <float>}`, aligned by index. Normalization/thresholding happens in `news/sentiment.py` (Task 2).

> **Note:** This script requires the ML extras (`transformers`+`torch`, Task 8) and is verified manually on the VPS, not in the unit suite — the pure mapping/threshold logic it feeds is already covered by Task 2.

- [ ] **Step 1: Write the script**

Create `scripts/score_sentiment.py`:
```python
"""Score Indonesian text sentiment in an isolated process.

Reads a JSON list of strings from stdin, prints a JSON list of
{"label", "score"} to stdout (aligned by index). Runs in a throwaway process so
torch RAM is reclaimed on exit and the always-on scheduler never imports torch.
Requires the ML extras (see requirements-ml.txt). Override the model with the
SENTIMENT_MODEL env var.
"""
import json
import os
import sys

DEFAULT_MODEL = "w11wo/indonesian-roberta-base-sentiment-classifier"


def main() -> int:
    texts = json.load(sys.stdin)
    if not texts:
        sys.stdout.write("[]")
        return 0
    from transformers import pipeline

    model = os.environ.get("SENTIMENT_MODEL", DEFAULT_MODEL)
    clf = pipeline("sentiment-analysis", model=model, truncation=True, max_length=256)
    results = clf([t[:1000] for t in texts])
    out = [{"label": r["label"], "score": float(r["score"])} for r in results]
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Sanity-check the JSON contract locally without the model**

Run: `echo '[]' | PYTHONPATH=. .venv/Scripts/python.exe scripts/score_sentiment.py`
Expected: prints `[]` and exits 0 (the empty-input branch never imports transformers).

- [ ] **Step 3: Commit**

```bash
git add scripts/score_sentiment.py
git commit -m "feat(news): sentiment scoring subprocess (torch-isolated)"
```

> Full model run is verified on the VPS in Task 9 after the ML extras are installed:
> `echo '["Laba bersih perusahaan melonjak tajam"]' | .venv/bin/python scripts/score_sentiment.py`
> Expected (approx): `[{"label": "positive", "score": 0.9...}]`.

---

### Task 4: PortalNews fields + HTML `format_portal`

**Files:**
- Modify: `news_breakout/news/portal.py` (dataclass only)
- Modify: `news_breakout/news/formatter.py`
- Test: `tests/test_portal.py`

**Interfaces:**
- Consumes: `PortalNews` (existing).
- Produces:
  - `PortalNews` gains `lead: str = ""` and `sentiment: str = ""`.
  - `format_portal(item) -> str` returns Telegram **HTML** (headline hyperlinked, sentiment chip, no raw URL line).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portal.py` (near the existing `format_portal` test):
```python
def test_format_portal_hyperlinks_headline_no_raw_url():
    item = PortalNews("ANTM", "Antam tebar dividen", datetime(2026, 7, 19, 14, 30, tzinfo=WIB),
                      "https://cnbc/x", "cnbcindonesia.com", lead="Ringkasan singkat.")
    msg = format_portal(item)
    assert '<a href="https://cnbc/x">Antam tebar dividen</a>' in msg
    assert "Ringkasan singkat." in msg
    assert "\nhttps://cnbc/x" not in msg  # raw URL line removed


def test_format_portal_shows_positive_chip():
    item = PortalNews("ANTM", "judul", datetime(2026, 7, 19, 14, 30, tzinfo=WIB),
                      "u", "s", sentiment="positif")
    assert "\U0001F4C8 Positif" in format_portal(item)


def test_format_portal_shows_negative_chip():
    item = PortalNews("BBRI", "judul", datetime(2026, 7, 19, 14, 30, tzinfo=WIB),
                      "u", "s", sentiment="negatif")
    assert "\U0001F4C9 Negatif" in format_portal(item)


def test_format_portal_hides_netral_and_empty_chip():
    for sent in ("netral", ""):
        item = PortalNews("X", "judul", datetime(2026, 7, 19, 14, 30, tzinfo=WIB),
                          "u", "s", sentiment=sent)
        msg = format_portal(item)
        assert "\U0001F4C8" not in msg and "\U0001F4C9" not in msg


def test_format_portal_corp_action_header():
    item = PortalNews("ANTM", "judul", datetime(2026, 7, 19, 14, 30, tzinfo=WIB),
                      "u", "s", corp_action=True)
    assert "\U0001F6A8 AKSI KORPORASI · ANTM" in format_portal(item)


def test_format_portal_escapes_html_in_dynamic_fields():
    item = PortalNews("X", "Laba <b>naik</b> & untung", datetime(2026, 7, 19, 14, 30, tzinfo=WIB),
                      "https://x/a?b=1&c=2", "s")
    msg = format_portal(item)
    assert "&lt;b&gt;naik&lt;/b&gt; &amp; untung" in msg
    assert "b=1&amp;c=2" in msg
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_portal.py -q`
Expected: FAIL — `PortalNews` has no `lead`/`sentiment`, and `format_portal` emits no `<a>` tag.

- [ ] **Step 3: Add the dataclass fields**

In `news_breakout/news/portal.py`, extend `PortalNews`:
```python
@dataclass
class PortalNews:
    ticker: str
    title: str
    timestamp: datetime
    url: str
    source: str
    summary: str = ""       # RSS description, used for matching (not displayed)
    corp_action: bool = False  # title/body mentions a corporate-action keyword
    lead: str = ""          # displayed extractive summary (1-2 sentences)
    sentiment: str = ""     # "positif" | "negatif" | "netral" | ""
```

- [ ] **Step 4: Rewrite the formatter**

Replace the body of `news_breakout/news/formatter.py` `format_portal` (and add the imports/table) so the file reads:
```python
from __future__ import annotations

import html

from news_breakout.news.models import Disclosure


def format_disclosure(d: Disclosure) -> str:
    head = d.ticker if d.ticker else "IDX"
    return (
        f"\U0001F4F0 {head} · Keterbukaan Informasi\n"
        f"{d.title}\n"
        f"\U0001F552 {d.timestamp:%d %b %H:%M} WIB · IDX Disclosure\n"
        f"{d.url}"
    )


_SENTIMENT_CHIP = {"positif": "\U0001F4C8 Positif", "negatif": "\U0001F4C9 Negatif"}


def format_portal(item) -> str:
    ticker = getattr(item, "ticker", "")
    if getattr(item, "corp_action", False):
        head = "\U0001F6A8 AKSI KORPORASI" + (f" · {ticker}" if ticker else "")
    else:
        head = f"\U0001F4F0 {ticker}" if ticker else "\U0001F4F0 Berita Pasar"
    chip = _SENTIMENT_CHIP.get(getattr(item, "sentiment", ""), "")
    if chip:
        head = f"{head}   {chip}"

    url = html.escape(item.url, quote=True)
    title = html.escape(item.title)
    lines = [head, f'<a href="{url}">{title}</a>']
    lead = html.escape(getattr(item, "lead", "") or "")
    if lead:
        lines.append(lead)
    lines.append(f"\U0001F552 {item.timestamp:%d %b %H:%M} WIB · {html.escape(item.source)}")
    return "\n".join(lines)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_portal.py -q`
Expected: PASS (existing `test_format_portal_contains_key_fields` still passes — the raw URL substring survives inside the `href`).

- [ ] **Step 6: Commit**

```bash
git add news_breakout/news/portal.py news_breakout/news/formatter.py tests/test_portal.py
git commit -m "feat(news): HTML portal message with hyperlinked headline + sentiment chip"
```

---

### Task 5: Telegram HTML parse mode (`send_message`)

**Files:**
- Modify: `news_breakout/alerts/telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Produces: `send_message(..., parse_mode: str | None = None, disable_preview: bool = False) -> bool`. When set, the POST payload includes `parse_mode` and `disable_web_page_preview`. Existing callers (default `None`/`False`) are unaffected.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram.py`:
```python
def test_send_message_includes_parse_mode_and_disable_preview():
    fake = FakeClient()
    ok = send_message("tok", "-100", "<b>hi</b>", dry_run=False, client=fake,
                      parse_mode="HTML", disable_preview=True)
    assert ok is True
    payload = fake.calls[0]["json"]
    assert payload["parse_mode"] == "HTML"
    assert payload["disable_web_page_preview"] is True


def test_send_message_omits_parse_mode_by_default():
    fake = FakeClient()
    send_message("tok", "-100", "hi", dry_run=False, client=fake)
    payload = fake.calls[0]["json"]
    assert "parse_mode" not in payload
    assert "disable_web_page_preview" not in payload
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_telegram.py -q`
Expected: FAIL — `send_message()` got an unexpected keyword argument `parse_mode`.

- [ ] **Step 3: Update `send_message`**

Replace `news_breakout/alerts/telegram.py` `send_message` with:
```python
def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    dry_run: bool,
    client=None,
    retries: int = 2,
    sleeper=time.sleep,
    parse_mode: str | None = None,
    disable_preview: bool = False,
) -> bool:
    if dry_run:
        print(f"[DRY-RUN] -> {chat_id}\n{text}\n")
        return True

    close_after = client is None
    if client is None:
        client = httpx.Client()
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_preview:
        payload["disable_web_page_preview"] = True
    try:
        for attempt in range(retries + 1):
            try:
                resp = client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload,
                    timeout=15,
                )
                if resp.status_code == 200:
                    return True
            except Exception:  # noqa: BLE001 — network failures are retryable, never propagate
                pass
            if attempt < retries:
                sleeper(_SEND_DELAYS[min(attempt, len(_SEND_DELAYS) - 1)])
        return False
    finally:
        if close_after:
            client.close()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_telegram.py -q`
Expected: PASS (all telegram tests, old + 2 new).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/alerts/telegram.py tests/test_telegram.py
git commit -m "feat(telegram): optional parse_mode + disable_web_page_preview"
```

---

### Task 6: Config keys for curation (`config.py` + example)

**Files:**
- Modify: `news_breakout/config.py`
- Modify: `config/config.example.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces on `Settings`: `portal_summary_sentences: int = 2`, `portal_max_per_run: int = 20`, `sentiment_enabled: bool = True`, `sentiment_model: str = "w11wo/indonesian-roberta-base-sentiment-classifier"`, `sentiment_min_confidence: float = 0.6`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:
```python
def test_load_settings_reads_curation_keys(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n"
        "portal: {enabled: true, sources: [], summary_sentences: 3, max_per_run: 5}\n"
        "sentiment: {enabled: false, model: acme/x, min_confidence: 0.75}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=a:b\nTELEGRAM_BREAKOUT_CHAT_ID=-1\nTELEGRAM_NEWS_CHAT_ID=-2\n",
                   encoding="utf-8")
    s = load_settings(str(cfg), str(env))
    assert s.portal_summary_sentences == 3
    assert s.portal_max_per_run == 5
    assert s.sentiment_enabled is False
    assert s.sentiment_model == "acme/x"
    assert s.sentiment_min_confidence == 0.75


def test_load_settings_curation_defaults_when_absent(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "watchlist: [ANTM]\n"
        "signals: {donchian_lookback: 20, rvol_threshold: 2.0, rvol_window: 20, "
        "range_lookback: 30, range_max_width_pct: 0.15}\n"
        "data: {history_days: 120, intraday_period_days: 60}\n"
        "runtime: {dry_run: true}\n"
        "schedule: {market_open: \"09:00\", market_close: \"16:00\", scan_interval_minutes: 30, "
        "weekend_scan_day: \"sat\", holidays: []}\n"
        "universe: {candidates: [], min_price: 50, min_daily_value: 1000000000}\n"
        "news: {curated_keywords: [dividen], disclosure_page_size: 50, "
        "news_poll_interval_minutes: 60}\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=a:b\nTELEGRAM_BREAKOUT_CHAT_ID=-1\nTELEGRAM_NEWS_CHAT_ID=-2\n",
                   encoding="utf-8")
    s = load_settings(str(cfg), str(env))
    assert s.portal_summary_sentences == 2
    assert s.portal_max_per_run == 20
    assert s.sentiment_enabled is True
    assert s.sentiment_model == "w11wo/indonesian-roberta-base-sentiment-classifier"
    assert s.sentiment_min_confidence == 0.6
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL — `Settings` has no `portal_summary_sentences` (AttributeError).

- [ ] **Step 3: Add the fields and loader wiring**

In `news_breakout/config.py`, add to `Settings` (after `price_staleness_max_minutes`):
```python
    portal_summary_sentences: int = 2
    portal_max_per_run: int = 20
    sentiment_enabled: bool = True
    sentiment_model: str = "w11wo/indonesian-roberta-base-sentiment-classifier"
    sentiment_min_confidence: float = 0.6
```

In `load_settings`, add after `portal = raw.get("portal", {})`:
```python
    sentiment = raw.get("sentiment", {})
```
and add these keyword args to the `Settings(...)` construction (after `portal_name_map=...`):
```python
        portal_summary_sentences=portal.get("summary_sentences", 2),
        portal_max_per_run=portal.get("max_per_run", 20),
        sentiment_enabled=sentiment.get("enabled", True),
        sentiment_model=sentiment.get("model", "w11wo/indonesian-roberta-base-sentiment-classifier"),
        sentiment_min_confidence=sentiment.get("min_confidence", 0.6),
```

- [ ] **Step 4: Update the example config**

In `config/config.example.yaml`, under `portal:` add these two keys (alongside `enabled`):
```yaml
  summary_sentences: 2    # extractive lead length (sentences)
  max_per_run: 20         # anti-flood cap: max NEW items sent per hourly run
```
and add a new top-level section:
```yaml
sentiment:
  enabled: true
  model: w11wo/indonesian-roberta-base-sentiment-classifier
  min_confidence: 0.6     # below this, an item is treated as netral (chip hidden)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS (existing + 2 new).

- [ ] **Step 6: Commit**

```bash
git add news_breakout/config.py config/config.example.yaml tests/test_config.py
git commit -m "feat(config): curation + sentiment settings"
```

---

### Task 7: Feed orchestration (`run_portal_feed`)

**Files:**
- Modify: `news_breakout/news/feed.py`
- Test: `tests/test_portal.py`

**Interfaces:**
- Consumes: `fetch_article_text`+`lead_summary` (T1), `classify` (T2), `PortalNews.lead/sentiment` (T4), `send_message(..., parse_mode, disable_preview)` (T5), `settings.portal_summary_sentences/portal_max_per_run/sentiment_enabled/sentiment_min_confidence` (T6), `_default_http_get`+`fetch_portal_news` (existing).
- Produces: `run_portal_feed(settings, store, *, now, sender=send_message, fetcher=fetch_portal_news, extractor=None, classifier=None) -> list[str]`.

- [ ] **Step 1: Update the existing enabled-feed test and add new tests**

In `tests/test_portal.py`, REPLACE `test_run_portal_feed_enabled_sends_and_dedups_on_second_run` with a version that injects `extractor`/`classifier` and whose `sender` accepts the new kwargs:
```python
def test_run_portal_feed_enabled_sends_and_dedups_on_second_run():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None, **kwargs):
        sent.append((chat_id, text))
        return True

    def fetcher(sources, watchlist, name_map, *, now, http_get=None, corp_keywords=None):
        return [
            PortalNews("BRPT", "Barito Pacific catat kinerja positif", NOW,
                       "https://www.kontan.co.id/news/barito-pacific-1", "kontan.co.id"),
            PortalNews("ANTM", "ANTM naik signifikan hari ini", NOW,
                       "https://www.kontan.co.id/news/antm-naik", "kontan.co.id"),
        ]

    settings = _settings(portal_enabled=True, portal_sources=["https://www.kontan.co.id/rss"],
                          portal_name_map={"barito pacific": "BRPT"})
    kw = dict(extractor=lambda url: "", classifier=lambda texts, **k: [""] * len(texts))

    first = run_portal_feed(settings, store, now=NOW, sender=sender, fetcher=fetcher, **kw)
    assert len(first) == 2
    assert len(sent) == 2
    assert all(chat_id == "-200" for chat_id, _ in sent)

    second = run_portal_feed(settings, store, now=NOW, sender=sender, fetcher=fetcher, **kw)
    assert second == []
    assert len(sent) == 2   # no new sends
    store.close()
```

Then append these new tests:
```python
def test_run_portal_feed_enriches_lead_and_sentiment_and_sends_html():
    store = DedupStore(":memory:")
    calls = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None, **kwargs):
        calls.append({"text": text, "kwargs": kwargs})
        return True

    def fetcher(sources, watchlist, name_map, *, now, http_get=None, corp_keywords=None):
        return [PortalNews("ANTM", "Antam tebar dividen", NOW, "https://x/1", "cnbc")]

    settings = _settings(portal_enabled=True, portal_sources=["x"])
    run_portal_feed(
        settings, store, now=NOW, sender=sender, fetcher=fetcher,
        extractor=lambda url: "Antam bagi dividen Rp120. Bayar Agustus.",
        classifier=lambda texts, **k: ["positif"] * len(texts),
    )
    assert len(calls) == 1
    assert "Antam bagi dividen Rp120." in calls[0]["text"]
    assert "\U0001F4C8 Positif" in calls[0]["text"]
    assert calls[0]["kwargs"].get("parse_mode") == "HTML"
    assert calls[0]["kwargs"].get("disable_preview") is True
    store.close()


def test_run_portal_feed_extractor_failure_falls_back_to_rss_summary():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None, **kwargs):
        sent.append(text)
        return True

    def fetcher(sources, watchlist, name_map, *, now, http_get=None, corp_keywords=None):
        return [PortalNews("ANTM", "judul", NOW, "https://x/1", "cnbc",
                           summary="Ringkasan dari deskripsi RSS.")]

    def boom(url):
        raise RuntimeError("fetch down")

    settings = _settings(portal_enabled=True, portal_sources=["x"])
    run_portal_feed(settings, store, now=NOW, sender=sender, fetcher=fetcher,
                    extractor=boom, classifier=lambda texts, **k: [""] * len(texts))
    assert len(sent) == 1
    assert "Ringkasan dari deskripsi RSS." in sent[0]
    store.close()


def test_run_portal_feed_classifier_failure_still_sends_without_chip():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None, **kwargs):
        sent.append(text)
        return True

    def fetcher(sources, watchlist, name_map, *, now, http_get=None, corp_keywords=None):
        return [PortalNews("ANTM", "judul", NOW, "https://x/1", "cnbc")]

    def boom(texts, **k):
        raise RuntimeError("subprocess died")

    settings = _settings(portal_enabled=True, portal_sources=["x"])
    run_portal_feed(settings, store, now=NOW, sender=sender, fetcher=fetcher,
                    extractor=lambda url: "isi", classifier=boom)
    assert len(sent) == 1
    assert "\U0001F4C8" not in sent[0] and "\U0001F4C9" not in sent[0]
    store.close()


def test_run_portal_feed_caps_sends_per_run():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None, **kwargs):
        sent.append(text)
        return True

    def fetcher(sources, watchlist, name_map, *, now, http_get=None, corp_keywords=None):
        return [PortalNews(f"T{i}", f"judul {i}", NOW, f"https://x/{i}", "cnbc") for i in range(5)]

    settings = _settings(portal_enabled=True, portal_sources=["x"], portal_max_per_run=2)
    run_portal_feed(settings, store, now=NOW, sender=sender, fetcher=fetcher,
                    extractor=lambda url: "", classifier=lambda texts, **k: [""] * len(texts))
    assert len(sent) == 2
    store.close()


def test_run_portal_feed_orders_corp_then_strong_sentiment_then_rest():
    store = DedupStore(":memory:")
    sent = []

    def sender(bot_token, chat_id, text, *, dry_run, client=None, **kwargs):
        sent.append(text)
        return True

    def fetcher(sources, watchlist, name_map, *, now, http_get=None, corp_keywords=None):
        return [
            PortalNews("AAA", "biasa netral", NOW, "https://x/1", "s", corp_action=False),
            PortalNews("BBB", "aksi korporasi", NOW, "https://x/2", "s", corp_action=True),
            PortalNews("CCC", "kabar positif", NOW, "https://x/3", "s", corp_action=False),
        ]

    def classifier(texts, **k):
        m = {"biasa netral": "netral", "aksi korporasi": "netral", "kabar positif": "positif"}
        return [m.get(t, "netral") for t in texts]

    settings = _settings(portal_enabled=True, portal_sources=["x"])
    run_portal_feed(settings, store, now=NOW, sender=sender, fetcher=fetcher,
                    extractor=lambda url: "", classifier=classifier)
    assert "aksi korporasi" in sent[0]   # corp action first
    assert "kabar positif" in sent[1]     # then strong sentiment
    assert "biasa netral" in sent[2]      # then the rest
    store.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_portal.py -q`
Expected: FAIL — `run_portal_feed()` got an unexpected keyword argument `extractor` (plus the new assertions).

- [ ] **Step 3: Rewrite `run_portal_feed`**

Replace `run_portal_feed` in `news_breakout/news/feed.py` with:
```python
def run_portal_feed(settings, store, *, now, sender=send_message, fetcher=fetch_portal_news,
                    extractor=None, classifier=None) -> list[str]:
    if not settings.portal_enabled:
        return []
    from news_breakout.news.extract import fetch_article_text, lead_summary
    from news_breakout.news.portal import _default_http_get
    from news_breakout.news.sentiment import classify as _classify

    if extractor is None:
        def extractor(url):
            return fetch_article_text(url, http_get=_default_http_get)
    if classifier is None:
        classifier = _classify

    # match against the full universe (watchlist + candidates), not just the watchlist,
    # so market news about any scanned liquid stock gets surfaced too
    tickers = list(dict.fromkeys(settings.watchlist + settings.universe_candidates))
    items = fetcher(settings.portal_sources, tickers, settings.portal_name_map, now=now,
                    corp_keywords=settings.curated_keywords)

    # extractive summary from the full article body (fall back to the RSS description)
    for it in items:
        try:
            body = extractor(it.url)
        except Exception:  # noqa: BLE001 — a fetch failure must not drop the item
            body = ""
        it.lead = lead_summary(body or it.summary, settings.portal_summary_sentences)

    # optional sentiment tag; any failure degrades to no tag, news still flows
    if settings.sentiment_enabled and items:
        try:
            labels = classifier([it.lead or it.title for it in items],
                                min_confidence=settings.sentiment_min_confidence)
        except Exception:  # noqa: BLE001
            labels = [""] * len(items)
        if len(labels) == len(items):
            for it, lab in zip(items, labels):
                it.sentiment = lab

    # corporate actions first, then strong sentiment, then oldest -> newest
    strong = {"positif": 0, "negatif": 0}
    items.sort(key=lambda i: (not i.corp_action, strong.get(i.sentiment, 1), i.timestamp))

    sent = []
    for it in items:
        if len(sent) >= settings.portal_max_per_run:
            break
        if store.news_already_sent(it.url):
            continue
        if not sender(settings.telegram_bot_token, settings.telegram_news_chat_id,
                      format_portal(it), dry_run=settings.dry_run,
                      parse_mode="HTML", disable_preview=True):
            continue
        store.news_mark_sent(it.url)
        sent.append(it.url)
    logger.info("portal feed: %d matched, %d newly sent", len(items), len(sent))
    return sent
```

- [ ] **Step 4: Run the full suite to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all tests, including the untouched `test_run_portal_feed_disabled...` and `..._passes_watchlist_plus_universe...`, which short-circuit on `[]`).

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/feed.py tests/test_portal.py
git commit -m "feat(news): curate portal feed (summary + sentiment + cap + HTML send)"
```

---

### Task 8: Dependencies + ML extras file

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-ml.txt`

**Interfaces:** none (packaging). `serve.py` needs NO change — `run_portal_feed(settings, store, now=now)` still works because `extractor`/`classifier` default to the real implementations.

- [ ] **Step 1: Add trafilatura to the base requirements**

Append to `requirements.txt`:
```
trafilatura==1.12.2
```
(If that exact version fails to resolve on the VPS Python 3.12, use the latest `1.12.x`.)

- [ ] **Step 2: Create the VPS-only ML extras file**

Create `requirements-ml.txt`:
```
# VPS-only extras for the sentiment subprocess (scripts/score_sentiment.py).
# NOT used by the GitHub Actions price job (which pins its own deps inline).
# Install on the VPS with the CPU torch index:
#   pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu
transformers==4.44.2
torch==2.4.1
```
(Adjust the `torch` pin to the newest CPU wheel available for the VPS's Python if 2.4.1 is unavailable.)

- [ ] **Step 3: Verify the base install still resolves (dev box)**

Run: `.venv/Scripts/python.exe -m pip install -r requirements.txt`
Expected: installs `trafilatura` (and its lxml dep) with no conflicts; suite still green:
`PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt requirements-ml.txt
git commit -m "build: add trafilatura + VPS-only ML extras (transformers, torch cpu)"
```

---

### Task 9: VPS integration & deploy (manual)

**Files:** none (ops). Run on `hermes-vps` over SSH (`ssh -i ~/.ssh/glenn.pem ubuntu@43.156.128.91`). Use SHORT, spaced-out commands (fail2ban rate-limits rapid SSH).

- [ ] **Step 1: Pull the branch on the VPS** (after it is merged to `main`, or check out the feature branch)

```bash
cd ~/news-breakout && git fetch && git checkout main && git pull
```

- [ ] **Step 2: Install base + ML extras into the VPS venv**

```bash
cd ~/news-breakout && . .venv/bin/activate && pip install -r requirements.txt
pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

- [ ] **Step 3: Pre-warm (download) the sentiment model once + smoke-test the subprocess**

```bash
echo '["Laba bersih perusahaan melonjak tajam"]' | .venv/bin/python scripts/score_sentiment.py
```
Expected: one-time model download, then approx `[{"label": "positive", "score": 0.9...}]`.

- [ ] **Step 4: Add the `sentiment:` section + portal curation keys to the VPS `config.yaml`**

The VPS `config/config.yaml` is a gitignored copy. Add the `sentiment:` block and `portal.summary_sentences`/`portal.max_per_run` (mirror `config/config.example.yaml`). If omitted, the built-in defaults apply (enabled, 2, 20, 0.6) — so this step is only needed to override.

- [ ] **Step 5: Restart the service and confirm it is healthy**

```bash
sudo systemctl restart news-breakout && sleep 3 && systemctl is-active news-breakout
git rev-parse --short HEAD
```
Expected: `active`, HEAD at the merged commit.

- [ ] **Step 6: Watch one news cycle**

```bash
journalctl -u news-breakout -n 40 --no-pager | grep -i portal
```
Expected: a `portal feed: N matched, M newly sent` line; the News channel receives curated messages with hyperlinked headlines + (where confident) sentiment chips.

---

## Self-Review

**Spec coverage:**
- Materiality gate (spec §7) → reused (baseline `efddc4e`) + exercised in Task 7.
- Full-article fetch + extractive summary (§3 D4/D3) → Task 1.
- Sentiment classifier + subprocess isolation (§4 D2/D6) → Tasks 2 & 3.
- HTML hyperlinked headline, chip hidden when netral (§6 D7) → Tasks 4 & 5.
- Config keys (§9) → Task 6.
- Orchestration: gate→fetch→summary→sentiment→sort→cap→dedup→HTML send (§3, D5/D8) → Task 7.
- Deps split base vs ML (§10) → Task 8. Deploy/pre-warm (§10) → Task 9.
- Error handling matrix (§8) → Task 1 (fetch), Task 2 (classify), Task 7 (per-item try/except + cap + retry via existing sender).
- Out of scope (§14): abstractive summary, cross-portal dedup, disclosure sentiment — intentionally not planned.

**Placeholder scan:** none — every code/test step contains complete code and exact commands.

**Type consistency:** `lead_summary`/`fetch_article_text` (T1) signatures match their T7 calls; `classify(texts, *, runner, min_confidence)` (T2) matches the `classifier(..., min_confidence=...)` call and the injected test fakes' `**k`; `PortalNews.lead/sentiment` (T4) set in T7 and read in `format_portal` (T4); `send_message(..., parse_mode, disable_preview)` (T5) matches the T7 call; `Settings.portal_summary_sentences/portal_max_per_run/sentiment_enabled/sentiment_min_confidence` (T6) match their T7 reads. Consistent.
