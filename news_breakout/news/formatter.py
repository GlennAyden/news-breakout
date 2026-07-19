from __future__ import annotations

import html

from news_breakout.news.models import Disclosure


def format_disclosure(d: Disclosure) -> str:
    head = d.ticker if d.ticker else "IDX"
    return (
        f"\U0001F4F0 {head} · Keterbukaan Informasi\n"
        f"{d.title}\n"
        f"\U0001F552 {d.timestamp:%d %b %H:%M} WIB · IDX Disclosure\n"
        f"{d.url}"
    )


_SENTIMENT_CHIP = {"positif": "\U0001F4C8 Positif", "negatif": "\U0001F4C9 Negatif"}


def format_portal(item) -> str:
    ticker = getattr(item, "ticker", "")
    if getattr(item, "corp_action", False):
        head = "\U0001F6A8 AKSI KORPORASI" + (f" · {ticker}" if ticker else "")
    else:
        head = f"\U0001F4F0 {ticker}" if ticker else "\U0001F4F0 Berita Pasar"
    chip = _SENTIMENT_CHIP.get(getattr(item, "sentiment", ""), "")
    if chip:
        head = f"{head}   {chip}"

    url = html.escape(item.url, quote=True)
    title = html.escape(item.title)
    lines = [head, f'<a href="{url}">{title}</a>']
    lead = html.escape(getattr(item, "lead", "") or "")
    if lead:
        lines.append(lead)
    lines.append(f"\U0001F552 {item.timestamp:%d %b %H:%M} WIB · {html.escape(item.source)}")
    return "\n".join(lines)
