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
    if getattr(item, "corp_action", False):
        head = "🚨 AKSI KORPORASI" + (f" · {item.ticker}" if item.ticker else "")
    else:
        head = f"📰 {item.ticker}" if item.ticker else "📰 Berita Pasar"
    return (
        f"{head}\n"
        f"{item.title}\n"
        f"🕒 {item.timestamp:%d %b %H:%M} WIB · {item.source}\n"
        f"{item.url}"
    )
