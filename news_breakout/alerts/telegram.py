from __future__ import annotations

import httpx


def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    dry_run: bool,
    client=None,
) -> bool:
    if dry_run:
        print(f"[DRY-RUN] -> {chat_id}\n{text}\n")
        return True

    close_after = client is None
    if client is None:
        client = httpx.Client()
    try:
        resp = client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        return resp.status_code == 200
    finally:
        if close_after:
            client.close()
