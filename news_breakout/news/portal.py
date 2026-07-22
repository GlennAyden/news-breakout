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
    summary: str = ""       # RSS description, used for matching (not displayed)
    corp_action: bool = False  # title/body mentions a corporate-action keyword
    lead: str = ""          # displayed extractive summary (1-2 sentences)
    sentiment: str = ""     # "positif" | "negatif" | "netral" | ""


def _parse_pubdate(raw: str, now: datetime) -> datetime:
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(WIB) if dt.tzinfo else dt.replace(tzinfo=WIB)
    except Exception:  # noqa: BLE001
        return now


_ATOM = "{http://www.w3.org/2005/Atom}"


def _parse_iso(raw: str, now: datetime) -> datetime:
    try:
        dt = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
        return dt.astimezone(WIB) if dt.tzinfo else dt.replace(tzinfo=WIB)
    except ValueError:
        return now


def _atom_link(entry) -> str:
    links = entry.findall(f"{_ATOM}link")
    for ln in links:
        if ln.get("rel", "alternate") == "alternate" and ln.get("href"):
            return ln.get("href").strip()
    return (links[0].get("href", "").strip() if links else "")


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
        summary = re.sub(r"<[^>]+>", " ", item.findtext("description") or "").strip()
        out.append(PortalNews("", title, _parse_pubdate(item.findtext("pubDate") or "", now),
                              link, source, summary=summary))
    for entry in root.iter(f"{_ATOM}entry"):
        title = (entry.findtext(f"{_ATOM}title") or "").strip()
        link = _atom_link(entry)
        if not title or not link:
            continue
        raw_sum = entry.findtext(f"{_ATOM}summary") or entry.findtext(f"{_ATOM}content") or ""
        summary = re.sub(r"<[^>]+>", " ", raw_sum).strip()
        raw_ts = entry.findtext(f"{_ATOM}published") or entry.findtext(f"{_ATOM}updated") or ""
        out.append(PortalNews("", title, _parse_iso(raw_ts, now), link, source, summary=summary))
    return out


def match_ticker(text: str, watchlist: list[str], name_map: dict[str, str]) -> str:
    low = text.lower()
    for name, tk in name_map.items():          # company name first (higher precision)
        if re.search(rf"\b{re.escape(name.lower())}\b", low):
            return tk
    for tk in watchlist:                         # then ticker code as a whole word
        if re.search(rf"\b{re.escape(tk)}\b", text):
            return tk
    return ""


def has_corp_action(text: str, keywords: list[str]) -> bool:
    from news_breakout.news.curated import keyword_match
    return keyword_match(text, keywords)


def _default_http_get(url: str, proxy: str = "") -> str:
    from curl_cffi import requests as creq
    kwargs = {"impersonate": "chrome120"}
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    return creq.Session(**kwargs).get(url, timeout=30).text


def fetch_portal_news(sources, watchlist, name_map, *, now, http_get=None,
                      corp_keywords=None, global_proxy: str = "") -> list[PortalNews]:
    # Local import avoids a circular import: portal_html.py imports PortalNews
    # from this module, so this module cannot import portal_html at load time.
    from news_breakout.news.portal_html import parse_bisnis, parse_emitennews, parse_investor

    corp_keywords = corp_keywords or []
    parsers = {
        "rss": parse_rss,
        "emitennews": parse_emitennews,
        "bisnis": parse_bisnis,
        "investor": parse_investor,
    }
    if http_get is None:
        http_get = _default_http_get
    out = []
    for src in sources:
        url = src if isinstance(src, str) else src.get("url")
        if not url:
            continue
        parser_name = "rss" if isinstance(src, str) else src.get("parser", "rss")
        proxy = (src.get("proxy", "") if isinstance(src, dict) else "") or global_proxy
        try:
            text = http_get(url, proxy)
        except Exception:  # noqa: BLE001
            logger.warning("portal fetch failed: %s", url)
            continue
        parser = parsers.get(parser_name, parse_rss)
        for item in parser(text, _source_name(url), now=now):
            # match against title AND body so an emiten named only in the article
            # text (not the headline) still gets tagged
            blob = f"{item.title} {item.summary}".strip()
            tk = match_ticker(blob, watchlist, name_map)
            is_corp = has_corp_action(blob, corp_keywords)
            # keep anything that mentions an emiten OR is a corporate action;
            # drop only pure macro/general news that references neither
            if not (tk or is_corp):
                continue
            item.ticker = tk
            item.corp_action = is_corp
            out.append(item)
    return out
