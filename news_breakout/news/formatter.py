from __future__ import annotations

from news_breakout.news.models import Disclosure


def format_disclosure(d: Disclosure) -> str:
    head = d.ticker if d.ticker else "IDX"
    return (
        f"📰 {head} · Keterbukaan Informasi\n"
        f"{d.title}\n"
        f"🕒 {d.timestamp:%d %b %H:%M} WIB · IDX Disclosure\n"
        f"{d.url}"
    )


def format_portal(item) -> str:
    return (
        f"📰 {item.ticker} · {item.source}\n"
        f"{item.title}\n"
        f"🕒 {item.timestamp:%d %b %H:%M} WIB · Portal News\n"
        f"{item.url}"
    )
