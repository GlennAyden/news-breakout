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
