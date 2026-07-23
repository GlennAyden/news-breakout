# Corporate-Action Caution Tag — Design Spec

- **Date:** 2026-07-24
- **Status:** Approved (design) — pending spec review
- **Owner:** news-breakout
- **Scope:** Add an advisory caution line to breakout alerts whose news catalyst is a material corporate action. Informational only — no scoring/ranking change.

## 1. Problem & Goal

Event-study + gate-backtest (2026-07-23/24) found that when a breakout coincides
with a **material corporate-action** catalyst, forward returns are worse than a
clean breakout: aggregate corp-action-on-breakout f10 −7.25% (t=−4.1) vs clean
+3.50% (t=+4.3). Per category on a breakout: rights issue f10 −15.7% (t=−3.5,
win 17%), dividend −4.07% (t=−2.5), acquisition −3.85% (n=5 thin). Buyback is the
exception: mildly **positive** (f10 +2.6%).

The live +3.0 news booster keys on **any** IDX disclosure (mostly routine
filings, which the audit showed are neutral/mildly-positive) and is **not**
changed here — the faithful disclosure audit did not support removing or
flipping it. What the evidence *does* support is a low-risk, informational
caution so the trader knows a breakout's catalyst is a historically-weak type.

**Goal:** when a breakout alert's attached catalyst is a material corp-action,
append one advisory caution line (per-type wording), mirroring the existing ABC
`🌊 Konteks: …` advisory. No change to `quality_score`, `priority`, the send
floor, or which tickers get the +3.0 boost.

## 2. Key Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Informational only** — no scoring/ranking/floor change. | User decision; the booster audit (n small, one regime) does not support a scoring change. Zero risk to backtested numbers. |
| D2 | **Buyback is detected but gets NO caution line.** | Data: buyback-on-breakout is mildly positive (f10 +2.6%), not a caution. Flagging it would be data-wrong. |
| D3 | **Caution categories: rights issue, private placement, acquisition/divestiture, dividend** — each with its own wording. | The four material-bearish types from the gate. Aggregate is significant (t=−4.1); rights issue and dividend individually significant. |
| D4 | **Catalyst selection changes to "prefer most-material".** | The booster attaches the *most-recent* disclosure; a rights issue is often followed by a routine registration filing that would mask it. Preferring the material disclosure fixes detection AND improves the displayed `📰 Katalis` line. The **set** of boosted tickers is unchanged (still any-disclosure-in-window), so the booster is untouched. |
| D5 | **Config toggle `news.corp_action_caution` (default true).** | The line is more subjective than the ABC caution; a cheap off-switch if it feels noisy. |
| D6 | **Applies via the shared `format_ticker_alert`** (intraday + daily-detect individual alerts). The one-line `format_daily_digest` is untouched. | Single formatter path; digest has no room and is a compact ranking list. |

## 3. Design

### 3.1 `news/corp_action.py` (NEW)

```python
def classify_corp_action(title: str) -> str | None:
    """Return a corp-action category key for a disclosure title, or None.

    Keys (priority order, most-material first):
      "rights_issue" | "private_placement" | "akuisisi" | "dividen" | "buyback"
    Routine filings (registration, ESOP report, RUPS notice, monthly report) → None.
    """

CATEGORY_PRIORITY: list[str]   # ["rights_issue","private_placement","akuisisi","dividen","buyback"]

CAUTION_LINES: dict[str, str]  # per bearish category → the advisory line (buyback absent)
```

- Word-boundary regex per category (reuse the lookaround style from
  `news/curated.py` to avoid false positives). Case-insensitive.
- Category detection order = `CATEGORY_PRIORITY`; first match wins (so a title
  mentioning both rights issue and dividend classifies as rights_issue).
- `CAUTION_LINES` has entries for the four bearish categories only; `buyback`
  and `None` produce no line.

Wording (exact):
- `rights_issue`: `⚠️ Peringatan: rights issue — risiko dilusi, historis cenderung melemah 5–10 hari pasca-breakout`
- `private_placement`: `⚠️ Peringatan: private placement — risiko dilusi, historis cenderung melemah`
- `akuisisi`: `⚠️ Peringatan: akuisisi/divestasi — pola beli-rumor-jual-berita, gerakan sering sudah selesai`
- `dividen`: `⚠️ Peringatan: katalis dividen — run-up sering sudah lelah saat breakout, historis melemah ~10 hari`

### 3.2 `news/booster.py` — `pick_catalyst` (NEW, alongside `recent_by_ticker`)

```python
def pick_catalyst(disclosures, *, now, window_hours) -> dict[str, Disclosure]:
    """Like recent_by_ticker, but per ticker prefers the most-material disclosure
    in the window (by CATEGORY_PRIORITY); ties and all-routine fall back to most
    recent. Same key set as recent_by_ticker (any ticker with a disclosure)."""
```

- `recent_by_ticker` is kept (unchanged, still tested). `run.py` and
  `signals/daily_shift.py` switch their catalyst construction from
  `recent_by_ticker` to `pick_catalyst`. The boosted-ticker set is identical;
  only the chosen `Disclosure` differs when a ticker has multiple.

### 3.3 `alerts/formatter.py` — caution line

- `format_ticker_alert(alert, catalyst, *, min_conf, show_ambiguous, corp_action_caution=True)`.
- After the existing `📰 Katalis: …` line, if `corp_action_caution` and
  `catalyst is not None`, look up `CAUTION_LINES.get(classify_corp_action(catalyst.title))`
  and append it when present.
- `scan_core.py` passes `corp_action_caution=settings.news_corp_action_caution`
  into `format_ticker_alert`.

### 3.4 Config

```yaml
news:
  corp_action_caution: true   # advisory ⚠️ line when a breakout's catalyst is a material corp action
```

`Settings.news_corp_action_caution: bool = True`; loaded via
`news.get("corp_action_caution", True)`.

## 4. Data Flow

```
run_scan / run_daily_scan
  disc = disclosure_fetcher(...)                 # unchanged
  catalysts = pick_catalyst(disc, window_hours)  # was recent_by_ticker — prefer-material
  → scan_once/evaluate_scan: +3.0 boost to any ticker in catalysts   # UNCHANGED
  → format_ticker_alert(alert, catalyst, corp_action_caution=…)
        📰 Katalis: <material-or-recent title>
        ⚠️ Peringatan: <per-type line>   ← only when catalyst classifies bearish-material
```

## 5. Error Handling

- `classify_corp_action` is a pure function; a non-matching/empty title → None →
  no line. No exceptions propagate.
- Fully degradable: if catalyst is None (no news), behaviour is byte-identical to
  today. Toggle off → byte-identical to today.

## 6. Testing

- `tests/test_corp_action.py` (NEW): each category classifies correctly from
  representative IDX/portal titles; routine titles → None; priority order (rights
  beats dividend in a mixed title); `CAUTION_LINES` has the four bearish keys and
  not buyback; `pick_catalyst` prefers material over a more-recent routine filing
  and falls back to most-recent when all routine.
- `tests/test_formatter.py` (EXTEND): caution line appears with correct wording
  for each bearish category; absent for buyback, routine catalyst, and no
  catalyst; absent when `corp_action_caution=False`; the `📰 Katalis` line and
  all existing lines are unchanged.
- `tests/test_config.py` (EXTEND): `news_corp_action_caution` defaults true and
  reads an explicit false.
- No network in tests; pure functions + existing alert fixtures.

## 7. Out of Scope

- Any change to `quality_score`, `priority`, the `min_quality_score` floor, or
  the +3.0 booster trigger (audit does not support it; revisit with multi-regime
  data).
- Widening the 48h catalyst window.
- Buyback positive-tagging (weak evidence; not worth a claim).
- The daily digest one-liner.

## 8. Rollout

Merge to `main` (fetch + rebase first — concurrent sessions are active on
main/VPS), deploy to hermes-vps (git pull + restart). `config.yaml` on the VPS
gains `news.corp_action_caution: true` (defaulted, so an un-edited config still
works). No `.env` change.
