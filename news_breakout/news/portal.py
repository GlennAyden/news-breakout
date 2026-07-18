from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

logger = logging.getLogger("news_breakout")
WIB = ZoneInfo("Asia/Jakarta")


@dataclass
class PortalNews:
    ticker: str
    title: str
    timestamp: datetime
    url: str
    source: str


def _parse_pubdate(raw: str, now: datetime) -> datetime:
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(WIB) if dt.tzinfo else dt.replace(tzinfo=WIB)
    except Exception:  # noqa: BLE001
        return now


def _source_name(url: str) -> str:
    host = urlparse(url).netloc or url
    return host.replace("www.", "")


def parse_rss(xml_text: str, source: str, *, now: datetime) -> list[PortalNews]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append(PortalNews("", title, _parse_pubdate(item.findtext("pubDate") or "", now), link, source))
    return out


def match_ticker(text: str, watchlist: list[str], name_map: dict[str, str]) -> str:
    low = text.lower()
    for name, tk in name_map.items():          # company name first (higher precision)
        if name.lower() in low:
            return tk
    for tk in watchlist:                         # then ticker code as a whole word
        if re.search(rf"\b{re.escape(tk)}\b", text):
            return tk
    return ""


def _default_http_get(url: str) -> str:
    from curl_cffi import requests as creq
    return creq.Session(impersonate="chrome120").get(url, timeout=30).text


def fetch_portal_news(sources, watchlist, name_map, *, now, http_get=None) -> list[PortalNews]:
    if http_get is None:
        http_get = _default_http_get
    out = []
    for src in sources:
        try:
            xml = http_get(src)
        except Exception:  # noqa: BLE001
            logger.warning("portal fetch failed: %s", src)
            continue
        for item in parse_rss(xml, _source_name(src), now=now):
            tk = match_ticker(item.title, watchlist, name_map)
            if tk:
                item.ticker = tk
                out.append(item)
    return out
