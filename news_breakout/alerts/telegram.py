from __future__ import annotations

import time

import httpx

_SEND_DELAYS = [2, 5]


def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    dry_run: bool,
    client=None,
    retries: int = 2,
    sleeper=time.sleep,
    parse_mode: str | None = None,
    disable_preview: bool = False,
) -> bool:
    if dry_run:
        print(f"[DRY-RUN] -> {chat_id}\n{text}\n")
        return True

    close_after = client is None
    if client is None:
        client = httpx.Client()
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_preview:
        payload["disable_web_page_preview"] = True
    try:
        for attempt in range(retries + 1):
            try:
                resp = client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload,
                    timeout=15,
                )
                if resp.status_code == 200:
                    return True
            except Exception:  # noqa: BLE001 — network failures are retryable, never propagate
                pass
            if attempt < retries:
                sleeper(_SEND_DELAYS[min(attempt, len(_SEND_DELAYS) - 1)])
        return False
    finally:
        if close_after:
            client.close()
