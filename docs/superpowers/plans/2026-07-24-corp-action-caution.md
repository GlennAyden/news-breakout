# Corporate-Action Caution Tag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Append an advisory ⚠️ caution line to a breakout alert when its news catalyst is a material corporate action (rights issue / private placement / acquisition / dividend), per `docs/superpowers/specs/2026-07-24-corp-action-caution-design.md`.

**Architecture:** A pure title-classifier (`news/corp_action.py`) maps a disclosure title to a corp-action category. The catalyst attached to each alert is chosen to prefer the most-material disclosure in the booster window (`booster.pick_catalyst`), and the shared `format_ticker_alert` appends a per-category caution line when that catalyst classifies as bearish-material. No scoring/ranking/booster-trigger change.

**Tech Stack:** Python 3.12, pydantic Settings, pytest, stdlib `re`.

## Global Constraints

- **Informational only** — no change to `quality_score`, `priority`, the `min_quality_score` floor, or which tickers get the +3.0 boost. The boosted-ticker set must stay identical.
- **Buyback is detected but gets NO caution line** (data: buyback-on-breakout is mildly positive).
- **No network in tests**; pure functions + existing fixtures.
- All new config keys defaulted so an un-edited `config.yaml` keeps working.
- Byte-identical output when there is no catalyst, when the catalyst is routine/buyback, or when the toggle is off.
- Exact caution wording (verbatim, including the `–` en-dash and `⚠️`):
  - rights_issue: `⚠️ Peringatan: rights issue — risiko dilusi, historis cenderung melemah 5–10 hari pasca-breakout`
  - private_placement: `⚠️ Peringatan: private placement — risiko dilusi, historis cenderung melemah`
  - akuisisi: `⚠️ Peringatan: akuisisi/divestasi — pola beli-rumor-jual-berita, gerakan sering sudah selesai`
  - dividen: `⚠️ Peringatan: katalis dividen — run-up sering sudah lelah saat breakout, historis melemah ~10 hari`
- Run tests from repo root: `python -m pytest tests/<file> -v` (full suite: `python -m pytest -q`).
- Commit after every green task; message style `feat(news): ...`.

---

### Task 1: `news/corp_action.py` — classifier + caution lines

**Files:**
- Create: `news_breakout/news/corp_action.py`
- Test: `tests/test_corp_action.py`

**Interfaces:**
- Produces: `classify_corp_action(title: str) -> str | None` (keys: `"rights_issue"`, `"private_placement"`, `"akuisisi"`, `"dividen"`, `"buyback"`); `CATEGORY_PRIORITY: list[str]` (same order, most-material first); `CAUTION_LINES: dict[str, str]` (the four bearish keys only — no `buyback`).

- [ ] **Step 1: Write the failing tests** (`tests/test_corp_action.py`)

```python
from news_breakout.news.corp_action import (
    CATEGORY_PRIORITY, CAUTION_LINES, classify_corp_action)


def test_classifies_each_category():
    cases = [
        ("rights_issue", "PADI ajukan pencatatan saham baru hasil rights issue"),
        ("rights_issue", "Jadwal HMETD dan pelaksanaan penambahan modal"),
        ("private_placement", "HATM siapkan private placement 800 juta saham"),
        ("akuisisi", "BTN incar akuisisi kredit konsumer bank lain"),
        ("dividen", "ANTM bagikan dividen Rp5,05 triliun"),
        ("buyback", "Astra International ASII restu buyback saham Rp8 triliun"),
    ]
    for expected, title in cases:
        assert classify_corp_action(title) == expected, title


def test_routine_titles_return_none():
    for title in [
        "Laporan Bulanan Registrasi Pemegang Efek",
        "Laporan Hasil Pelaksanaan Konversi ESOP MSOP",
        "Pemanggilan Rapat Umum Pemegang Saham Luar Biasa",
        "Penyampaian Bukti Iklan",
        "",
    ]:
        assert classify_corp_action(title) is None, title


def test_priority_order_rights_beats_dividen_in_mixed_title():
    # a title mentioning both must classify as the more-material rights_issue
    assert classify_corp_action("Rights issue untuk danai dividen") == "rights_issue"
    assert CATEGORY_PRIORITY.index("rights_issue") < CATEGORY_PRIORITY.index("dividen")


def test_caution_lines_cover_bearish_only():
    assert set(CAUTION_LINES) == {"rights_issue", "private_placement", "akuisisi", "dividen"}
    assert "buyback" not in CAUTION_LINES
    assert CAUTION_LINES["rights_issue"].startswith("⚠️ Peringatan: rights issue")


def test_word_boundary_no_false_positive():
    # "dividennya" still matches (enclitic) but an unrelated substring must not
    assert classify_corp_action("Pembagian dividennya tahun ini") == "dividen"
    assert classify_corp_action("Laporan kinerja triwulan") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_corp_action.py -v`
Expected: FAIL (`ModuleNotFoundError: news_breakout.news.corp_action`)

- [ ] **Step 3: Implement** (`news_breakout/news/corp_action.py`)

```python
from __future__ import annotations

import re

# Most-material first. classify_corp_action returns the first matching key, so a
# title mentioning several corp actions gets the most-material label.
CATEGORY_PRIORITY = ["rights_issue", "private_placement", "akuisisi", "dividen", "buyback"]

_PATTERNS = {
    "rights_issue": r"rights?\s+issue|hmetd",
    "private_placement": r"private\s+placement",
    "akuisisi": r"akuisisi|divestasi|caplok|ambil\s?alih|pengambilalihan",
    "dividen": r"dividen",
    "buyback": r"buyback|pembelian\s+kembali|beli\s+kembali",
}
# lookaround boundaries (not \b) so multi-word / punctuated keywords still match,
# tolerating the Indonesian -nya enclitic (dividennya) — mirrors news/curated.py.
_COMPILED = {
    k: re.compile(rf"(?<!\w)(?:{p})(?:nya)?(?!\w)", re.IGNORECASE)
    for k, p in _PATTERNS.items()
}

CAUTION_LINES = {
    "rights_issue": "⚠️ Peringatan: rights issue — risiko dilusi, historis cenderung melemah 5–10 hari pasca-breakout",
    "private_placement": "⚠️ Peringatan: private placement — risiko dilusi, historis cenderung melemah",
    "akuisisi": "⚠️ Peringatan: akuisisi/divestasi — pola beli-rumor-jual-berita, gerakan sering sudah selesai",
    "dividen": "⚠️ Peringatan: katalis dividen — run-up sering sudah lelah saat breakout, historis melemah ~10 hari",
}


def classify_corp_action(title: str) -> str | None:
    """Return the most-material corp-action category for a disclosure title, or None."""
    text = title or ""
    for key in CATEGORY_PRIORITY:
        if _COMPILED[key].search(text):
            return key
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_corp_action.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/corp_action.py tests/test_corp_action.py
git commit -m "feat(news): corp-action title classifier and caution lines"
```

---

### Task 2: `booster.pick_catalyst` — prefer most-material disclosure

**Files:**
- Modify: `news_breakout/news/booster.py`
- Modify: `run.py`
- Modify: `news_breakout/signals/daily_shift.py`
- Test: `tests/test_booster.py`

**Interfaces:**
- Consumes: `classify_corp_action`, `CATEGORY_PRIORITY` (Task 1).
- Produces: `pick_catalyst(disclosures, *, now, window_hours) -> dict[str, Disclosure]` — same key set as `recent_by_ticker`, but the value per ticker is the most-material disclosure in the window (ties / all-routine → most recent).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_booster.py`)

```python
from news_breakout.news.booster import pick_catalyst


def test_pick_catalyst_prefers_material_over_more_recent_routine():
    routine = _disc("ANTM", 1, disclosure_id="routine",
                    title="Laporan Bulanan Registrasi Pemegang Efek")   # newer
    material = _disc("ANTM", 5, disclosure_id="rights",
                     title="Jadwal rights issue ANTM")                  # older but material
    result = pick_catalyst([routine, material], now=NOW, window_hours=48)
    assert result["ANTM"].disclosure_id == "rights"


def test_pick_catalyst_falls_back_to_most_recent_when_all_routine():
    older = _disc("ANTM", 10, disclosure_id="old", title="Penyampaian Bukti Iklan")
    newer = _disc("ANTM", 2, disclosure_id="new", title="Laporan Bulanan Registrasi")
    result = pick_catalyst([older, newer], now=NOW, window_hours=48)
    assert result["ANTM"].disclosure_id == "new"


def test_pick_catalyst_same_keyset_as_recent_by_ticker():
    discs = [_disc("ANTM", 1, title="Rights issue"),
             _disc("BBRI", 2, title="Laporan Bulanan"),
             _disc("TINS", 60, title="Dividen")]   # out of window
    assert set(pick_catalyst(discs, now=NOW, window_hours=48)) == \
           set(recent_by_ticker(discs, now=NOW, window_hours=48))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_booster.py -v -k pick_catalyst`
Expected: FAIL (`ImportError: cannot import name 'pick_catalyst'`)

- [ ] **Step 3: Implement**

Append to `news_breakout/news/booster.py`:

```python
def pick_catalyst(disclosures, *, now, window_hours):
    """Most-material disclosure per ticker within the window (ties/all-routine →
    most recent). Same key set as recent_by_ticker (any ticker with a disclosure
    in the window); only the chosen disclosure differs when a ticker has several."""
    from news_breakout.news.corp_action import CATEGORY_PRIORITY, classify_corp_action

    def materiality(d):
        cat = classify_corp_action(d.title)
        # lower rank = more material; routine (None) sorts last
        rank = CATEGORY_PRIORITY.index(cat) if cat in CATEGORY_PRIORITY else len(CATEGORY_PRIORITY)
        return (rank, -d.timestamp.timestamp())   # then newest first

    cutoff = now - timedelta(hours=window_hours)
    best: dict[str, Disclosure] = {}
    for d in disclosures:
        if not d.ticker or d.timestamp < cutoff:
            continue
        cur = best.get(d.ticker)
        if cur is None or materiality(d) < materiality(cur):
            best[d.ticker] = d
    return best
```

In `run.py`, change the catalyst construction (currently
`catalysts = recent_by_ticker(disc, now=now, window_hours=settings.news_booster_window_hours)`):

```python
    catalysts = pick_catalyst(disc, now=now, window_hours=settings.news_booster_window_hours)
```

and replace the import at the top of `run.py` (`from news_breakout.news.booster import recent_by_ticker`) — `recent_by_ticker` is no longer used there, so swap it entirely:

```python
from news_breakout.news.booster import pick_catalyst
```

In `news_breakout/signals/daily_shift.py`, change line ~50
(`catalysts = recent_by_ticker(disc, now=now, window_hours=settings.news_booster_window_hours)`):

```python
    catalysts = pick_catalyst(disc, now=now, window_hours=settings.news_booster_window_hours)
```

and replace its import (line 10, `from news_breakout.news.booster import recent_by_ticker`) — also now unused there:

```python
from news_breakout.news.booster import pick_catalyst
```

(`recent_by_ticker` stays defined and tested in `booster.py`; it is simply no longer imported by these two callers.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_booster.py tests/test_run_smoke.py tests/test_daily_shift.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/news/booster.py run.py news_breakout/signals/daily_shift.py tests/test_booster.py
git commit -m "feat(news): pick_catalyst prefers the most-material disclosure"
```

---

### Task 3: config — `news_corp_action_caution`

**Files:**
- Modify: `news_breakout/config.py`
- Modify: `config/config.example.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.news_corp_action_caution: bool = True`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_config.py`; reuse the file's `_MINIMAL_YAML` and `_load(cfg, monkeypatch)` helpers)

```python
def test_corp_action_caution_defaults_true_and_reads_false(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(_MINIMAL_YAML, encoding="utf-8")
    assert _load(cfg, monkeypatch).news_corp_action_caution is True

    cfg2 = tmp_path / "c2.yaml"
    cfg2.write_text(_MINIMAL_YAML.replace(
        "news_poll_interval_minutes: 60",
        "news_poll_interval_minutes: 60, corp_action_caution: false"), encoding="utf-8")
    assert _load(cfg2, monkeypatch).news_corp_action_caution is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v -k corp_action_caution`
Expected: FAIL (`AttributeError: news_corp_action_caution`)

- [ ] **Step 3: Implement**

In `news_breakout/config.py`, add to `Settings` (after `portal_drop_categories`):

```python
    news_corp_action_caution: bool = True
```

In `load_settings(...)`, add to the `Settings(...)` construction (near the other `news.get(...)` lines):

```python
        news_corp_action_caution=news.get("corp_action_caution", True),
```

In `config/config.example.yaml`, add to the `news:` block (after `dedup_retention_days: 90`):

```yaml
  corp_action_caution: true         # advisory ⚠️ line when a breakout's catalyst is a material corp action
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add news_breakout/config.py config/config.example.yaml tests/test_config.py
git commit -m "feat(news): news_corp_action_caution config flag"
```

---

### Task 4: formatter caution line + scan_core wiring

**Files:**
- Modify: `news_breakout/alerts/formatter.py`
- Modify: `news_breakout/signals/scan_core.py:66-71`
- Test: `tests/test_formatter.py`

**Interfaces:**
- Consumes: `classify_corp_action`, `CAUTION_LINES` (Task 1); `Settings.news_corp_action_caution` (Task 3).
- Produces: `format_ticker_alert(alert, catalyst=None, *, min_conf=0.45, show_ambiguous=False, corp_action_caution=True)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_formatter.py`; `Disclosure` is already imported there)

```python
def _alert_with(catalyst_title):
    ts = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
    sig = BreakoutSignal("ANTM", "1D", "resistance_breakout", 1500.0, 3.4, 1480.0, 2.7, ts)
    alert = TickerAlert("ANTM", [sig], priority=5.0, timestamp=ts)
    alert.quality_score = 6.5
    cat = Disclosure("ANTM", catalyst_title, ts - timedelta(hours=3), "d1", "http://x")
    return alert, cat


def test_caution_line_shown_for_rights_issue():
    alert, cat = _alert_with("Jadwal rights issue ANTM")
    msg = format_ticker_alert(alert, catalyst=cat)
    assert "⚠️ Peringatan: rights issue" in msg
    assert "📰 Katalis:" in msg                 # catalyst line still present


def test_caution_line_wording_per_category():
    for title, needle in [
        ("HATM private placement 800 juta saham", "private placement — risiko dilusi"),
        ("BTN akuisisi bank lain", "akuisisi/divestasi — pola beli-rumor"),
        ("ANTM bagikan dividen", "katalis dividen — run-up sering sudah lelah"),
    ]:
        alert, cat = _alert_with(title)
        assert needle in format_ticker_alert(alert, catalyst=cat), title


def test_no_caution_for_buyback_routine_or_no_catalyst():
    for title in ["ASII buyback saham Rp8 triliun", "Laporan Bulanan Registrasi Pemegang Efek"]:
        alert, cat = _alert_with(title)
        assert "⚠️ Peringatan" not in format_ticker_alert(alert, catalyst=cat), title
    alert, _ = _alert_with("x")
    assert "⚠️ Peringatan" not in format_ticker_alert(alert, catalyst=None)


def test_caution_suppressed_when_toggle_off():
    alert, cat = _alert_with("Jadwal rights issue ANTM")
    msg = format_ticker_alert(alert, catalyst=cat, corp_action_caution=False)
    assert "⚠️ Peringatan" not in msg
    assert "📰 Katalis:" in msg                 # catalyst line unaffected by the toggle
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_formatter.py -v -k "caution"`
Expected: FAIL (caution line not present)

- [ ] **Step 3: Implement**

In `news_breakout/alerts/formatter.py`, add the import near the top (after the existing `from news_breakout.news.models import Disclosure`):

```python
from news_breakout.news.corp_action import CAUTION_LINES, classify_corp_action
```

Change the `format_ticker_alert` signature and the catalyst block. Current:

```python
def format_ticker_alert(alert: TickerAlert, catalyst: Disclosure | None = None, *,
                        min_conf: float = 0.45, show_ambiguous: bool = False) -> str:
    ...
    if catalyst is not None:
        lines.append(
            f"📰 Katalis: {catalyst.title} ({_time_ago(catalyst.timestamp, alert.timestamp)})"
        )
    lines.append(f"⏱️ {alert.timestamp:%H:%M} WIB · delay data ~15 mnt")
    return "\n".join(lines)
```

becomes:

```python
def format_ticker_alert(alert: TickerAlert, catalyst: Disclosure | None = None, *,
                        min_conf: float = 0.45, show_ambiguous: bool = False,
                        corp_action_caution: bool = True) -> str:
    ...
    if catalyst is not None:
        lines.append(
            f"📰 Katalis: {catalyst.title} ({_time_ago(catalyst.timestamp, alert.timestamp)})"
        )
        if corp_action_caution:
            caution = CAUTION_LINES.get(classify_corp_action(catalyst.title))
            if caution:
                lines.append(caution)
    lines.append(f"⏱️ {alert.timestamp:%H:%M} WIB · delay data ~15 mnt")
    return "\n".join(lines)
```

(The `...` is the unchanged body between the signature and the catalyst block — do not alter it.)

In `news_breakout/signals/scan_core.py`, the `format_ticker_alert(...)` call (lines 67-71) gains the toggle:

```python
        text = format_ticker_alert(
            alert, catalyst=catalyst,
            min_conf=settings.elliott_min_confidence,
            show_ambiguous=settings.elliott_show_ambiguous,
            corp_action_caution=settings.news_corp_action_caution,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_formatter.py tests/test_scan_core.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all PASS

```bash
git add news_breakout/alerts/formatter.py news_breakout/signals/scan_core.py tests/test_formatter.py
git commit -m "feat(news): advisory caution line for material corp-action catalysts"
```
