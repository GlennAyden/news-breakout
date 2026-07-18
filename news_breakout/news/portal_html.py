from __future__ import annotations

import re
from datetime import datetime, timedelta

from news_breakout.news.portal import WIB, PortalNews

_NAMED_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&nbsp;": " ",
}

_ENTITY_RE = re.compile(r"&#x[0-9a-fA-F]+;|&#\d+;|&amp;|&lt;|&gt;|&quot;|&#39;|&nbsp;")

_MONTHS = {
    "jan": 1, "januari": 1,
    "feb": 2, "februari": 2,
    "mar": 3, "maret": 3,
    "apr": 4, "april": 4,
    "mei": 5,
    "jun": 6, "juni": 6,
    "jul": 7, "juli": 7,
    "agu": 8, "agt": 8, "agustus": 8,
    "sep": 9, "september": 9,
    "okt": 10, "oktober": 10,
    "nov": 11, "november": 11,
    "des": 12, "desember": 12,
}

_UNIT_SECONDS = {
    "detik": 1,
    "menit": 60,
    "jam": 3600,
    "hari": 86400,
    "minggu": 604800,
}

_RELATIVE_RE = re.compile(r"(\d+)\s+(detik|menit|jam|hari|minggu)\s+yang\s+lalu")
_ABS_MONTH_NAME_RE = re.compile(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})\s*[|,]?\s*(\d{1,2}):(\d{2})")
_ABS_SLASH_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4}),?\s*(\d{1,2}):(\d{2})")


def _decode_entity(match: re.Match) -> str:
    token = match.group(0)
    if token in _NAMED_ENTITIES:
        return _NAMED_ENTITIES[token]
    if token.startswith("&#x") or token.startswith("&#X"):
        return chr(int(token[3:-1], 16))
    return chr(int(token[2:-1]))


def _clean(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = _ENTITY_RE.sub(_decode_entity, text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_indo_date(raw: str, now: datetime) -> datetime:
    text = _clean(raw).lower()
    if not text:
        return now
    if "baru saja" in text:
        return now

    m = _RELATIVE_RE.search(text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        return now - timedelta(seconds=amount * _UNIT_SECONDS[unit])

    m = _ABS_MONTH_NAME_RE.search(text)
    if m:
        day, month_name, year, hour, minute = m.groups()
        month = _MONTHS.get(month_name)
        if month:
            try:
                return datetime(int(year), month, int(day), int(hour), int(minute), tzinfo=WIB)
            except ValueError:
                return now

    m = _ABS_SLASH_RE.search(text)
    if m:
        day, month, year, hour, minute = (int(x) for x in m.groups())
        try:
            return datetime(year, month, day, hour, minute, tzinfo=WIB)
        except ValueError:
            return now

    return now


# ---- EmitenNews ---------------------------------------------------------------

_EMITEN_OUTER_RE = re.compile(
    r'<a\b(?=[^>]*\bclass=["\'][^"\']*\bnews-card-2\b[^"\']*\bsearch-result-item\b)'
    r'(?=[^>]*\bhref=["\'](https://emitennews\.com/news/[^"\']+)["\'])'
    r'[^>]*>([\s\S]*?)</a>',
    re.I,
)
_EMITEN_TITLE_RE = re.compile(r'<p\b[^>]*class=["\'][^"\']*\bfs-16\b[^"\']*["\'][^>]*>([\s\S]*?)</p>', re.I)
_EMITEN_DATE_RE = re.compile(r'<span\b[^>]*class=["\'][^"\']*\bsmall\b[^"\']*["\'][^>]*>([\s\S]*?)</span>', re.I)


def parse_emitennews(html: str, source: str, *, now: datetime) -> list[PortalNews]:
    out = []
    for m in _EMITEN_OUTER_RE.finditer(html):
        link, body = m.group(1), m.group(2)
        title_m = _EMITEN_TITLE_RE.search(body)
        title = _clean(title_m.group(1)) if title_m else ""
        if not title:
            continue
        date_m = _EMITEN_DATE_RE.search(body)
        ts = _parse_indo_date(date_m.group(1), now) if date_m else now
        out.append(PortalNews("", title, ts, link, source))
    return out


# ---- Bisnis ---------------------------------------------------------------------

_BISNIS_ITEM_RE = re.compile(
    r'<a\b(?=[^>]*\bhref=["\'](https://market\.bisnis\.com/read/[^"\']+)["\'])'
    r'(?=[^>]*\bclass=["\'][^"\']*\bartLink\b[^"\']*["\'])[^>]*>'
    r'[\s\S]{0,200}?<h4\b[^>]*\bartTitle\b[^>]*>([\s\S]*?)</h4>',
    re.I,
)
_BISNIS_DATE_RE = re.compile(r'<div\b[^>]*class=["\'][^"\']*\bartDate\b[^"\']*["\'][^>]*>([\s\S]*?)</div>', re.I)


def parse_bisnis(html: str, source: str, *, now: datetime) -> list[PortalNews]:
    out = []
    for m in _BISNIS_ITEM_RE.finditer(html):
        link = m.group(1)
        title = _clean(m.group(2))
        if not title:
            continue
        # Bisnis has two templates: the "Berita Terkini" main list puts artDate
        # AFTER the title, inside the anchor; primary cards put it BEFORE the
        # anchor. Check after first, then fall back to before.
        after = html[m.end():m.end() + 400]
        before = html[max(0, m.start() - 900):m.start()]
        date_txt = ""
        am = _BISNIS_DATE_RE.search(after)
        if am:
            date_txt = am.group(1)
        else:
            bms = list(_BISNIS_DATE_RE.finditer(before))
            if bms:
                date_txt = bms[-1].group(1)
        ts = _parse_indo_date(date_txt, now) if date_txt else now
        out.append(PortalNews("", title, ts, link, source))
    return out


# ---- Investor -------------------------------------------------------------------

_INVESTOR_ITEM_RE = re.compile(
    r'<a\b[^>]*\bhref=["\'](/market/\d+/[^"\']+)["\'][^>]*>'
    r'[\s\S]{0,600}?<img\b[^>]*\balt=["\']([^"\']+)["\']',
    re.I,
)


def parse_investor(html: str, source: str, *, now: datetime) -> list[PortalNews]:
    out = []
    for m in _INVESTOR_ITEM_RE.finditer(html):
        path, title = m.group(1), _clean(m.group(2))
        if not title:
            continue
        out.append(PortalNews("", title, now, "https://investor.id" + path, source))
    return out
