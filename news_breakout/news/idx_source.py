from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.models import Disclosure

WIB = ZoneInfo("Asia/Jakarta")
_DISCLOSURE_URL = "https://www.idx.co.id/en/listed-companies/disclosure/"


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
        rec = reply.get("pengumuman", reply) if isinstance(reply, dict) else {}
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
