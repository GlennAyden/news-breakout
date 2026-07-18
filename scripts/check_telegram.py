"""One-off Telegram connectivity check.

Reads your .env (token stays internal, never printed) and sends ONE test message
to the configured breakout chat, so you can confirm the bot + chat_id + admin
rights are correct. Manual verification tool, not part of the app.

Named check_* (not test_*) so pytest never collects/imports it, and the send is
guarded behind __main__ so importing it never sends anything.

Run from the repo root:
    PYTHONPATH=. .venv/Scripts/python.exe scripts/check_telegram.py
"""

import sys


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252
    except (AttributeError, ValueError):
        pass

    from news_breakout.config import load_settings
    from news_breakout.alerts.telegram import send_message

    s = load_settings()
    ok = send_message(
        s.telegram_bot_token,
        s.telegram_breakout_chat_id,
        "[TEST] news-breakout M1 — koneksi Telegram OK ✅\n"
        "Ini pesan verifikasi, bukan sinyal trading beneran.",
        dry_run=False,  # force a real send for this manual check only
    )
    print(
        "Telegram send result:",
        "OK - cek channel-mu ✅" if ok else "FAILED ❌ (cek TOKEN / CHAT_ID / bot harus admin channel)",
    )


if __name__ == "__main__":
    main()
