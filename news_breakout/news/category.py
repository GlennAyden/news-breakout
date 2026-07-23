from __future__ import annotations

import re

# Drop-only taxonomy (user decision 2026-07-23): governance chatter and market
# recap/opinion pieces carry no tradable catalyst — they are filtered out of the
# portal feed BEFORE the expensive extract/classify stages. Corporate-action
# items are exempted by the caller (see run_portal_feed) so "RUPSLB restui
# buyback" style headlines still flow.
_PATTERNS: dict[str, re.Pattern] = {
    "tata_kelola": re.compile(
        r"rups|direksi|komisaris|direktur utama|\bdirut\b|pengurus"
        r"|(?:direktur|presiden)(?:\s+\S+){0,3}\s+(?:borong|lego|jual|beli)\s+saham",
        re.IGNORECASE),
    "pasar_opini": re.compile(
        r"rekomendasi|target harga|\bihsg\b|top gainers|top losers"
        r"|melesat|melejit|anjlok|ambles|rontok|terbang|ngegas|\bara\b|\barb\b"
        r"|cermati saham|pantau saham|wall street|bursa asia|nasdaq|dow jones",
        re.IGNORECASE),
}


def drop_category(title: str, drops: list[str]) -> str | None:
    """Return the first drop-category matching ``title``, or None to keep it."""
    for name in drops:
        pat = _PATTERNS.get(name)
        if pat is not None and pat.search(title or ""):
            return name
    return None
