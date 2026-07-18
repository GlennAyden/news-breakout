from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.models import Disclosure

logger = logging.getLogger("news_breakout")

WIB = ZoneInfo("Asia/Jakarta")
_DISCLOSURE_URL = "https://www.idx.co.id/en/listed-companies/disclosure/"

_API = ("https://www.idx.co.id/primary/ListedCompany/GetAnnouncement"
        "?emitenType=s&indexFrom=1&pageSize={page_size}&dateFrom=&dateTo=&lang=id&keyword=")
_PAGE = "https://www.idx.co.id/en/listed-companies/disclosure/"
_HEADERS = {
    "Referer": _PAGE,
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}


def _first(record: dict, keys: list[str]) -> str:
    for k in keys:
        v = record.get(k)
        if v:
            return str(v).strip()
    return ""


def _parse_ts(raw: str, now: datetime) -> datetime:
    try:
        naive = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return now
    return naive.replace(tzinfo=WIB) if naive.tzinfo is None else naive.astimezone(WIB)


def parse_disclosures(data: dict, *, now: datetime) -> list[Disclosure]:
    out: list[Disclosure] = []
    for reply in (data or {}).get("Replies", []) or []:
        rec = reply.get("pengumuman", reply) if isinstance(reply, dict) else reply
        if not isinstance(rec, dict):
            continue
        title = _first(rec, ["JudulPengumuman", "Title", "title"])
        disc_id = _first(rec, ["Id2", "NoPengumuman"])
        if not title or not disc_id:
            continue
        out.append(Disclosure(
            ticker=_first(rec, ["KodeEmiten", "kodeEmiten", "kode", "Kode"]),
            title=title,
            timestamp=_parse_ts(_first(rec, ["TglPengumuman"]), now),
            disclosure_id=disc_id,
            url=_DISCLOSURE_URL,
        ))
    return out


def _default_http_get(url: str, proxy: str) -> str:
    from curl_cffi import requests as creq

    kwargs = {"impersonate": "chrome120"}
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    session = creq.Session(**kwargs)
    try:
        session.get(_PAGE, headers=_HEADERS, timeout=30)  # warm up Cloudflare cookies
    except Exception:  # noqa: BLE001
        pass
    return session.get(url, headers=_HEADERS, timeout=30).text


def fetch_disclosures(page_size: int = 50, *, now, proxy: str = "", retries: int = 3,
                      http_get=None, sleeper=time.sleep) -> list[Disclosure]:
    if http_get is None:
        http_get = _default_http_get
    url = _API.format(page_size=page_size)
    _RETRY_DELAYS = [5, 15, 30]
    for attempt in range(retries + 1):
        try:
            text = http_get(url, proxy)
            data = json.loads(text)
        except Exception:  # noqa: BLE001 — Cloudflare HTML / network / decode failure
            data = None
        if isinstance(data, dict) and isinstance(data.get("Replies"), list):
            return parse_disclosures(data, now=now)
        if attempt < retries:
            sleeper(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
    logger.warning("IDX disclosure fetch failed after %d attempts (Cloudflare/block?)", retries + 1)
    return []
