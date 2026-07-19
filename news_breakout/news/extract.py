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
