from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger("news_breakout")

# --- SEAMS: confirm against one live capture during the durability spike ---
# The refresh endpoint + request/response shape are the unknowns (token values
# were redacted during inspection). Isolated here so finalizing is one place.
REFRESH_URL = "https://ht2.ajaib.co.id/api/v7/refresh/"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS_BASE = {"User-Agent": _UA, "Origin": "https://trade.ajaib.co.id",
                 "Referer": "https://trade.ajaib.co.id/"}


def _default_post(url: str, payload: dict, headers: dict) -> tuple[int, dict]:
    with httpx.Client() as client:
        resp = client.post(url, json=payload, headers=headers, timeout=15)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 — non-JSON body still carries the status
            body = {}
        return resp.status_code, body


def _extract_tokens(body: dict, now: float) -> tuple[str, str | None, int]:
    """Pull (access_token, new_refresh_token_or_None, expiry_epoch) from a refresh
    response. Tolerant of nested/flat shapes; raises if no access token is present."""
    data = body.get("data", body) if isinstance(body, dict) else {}
    access = data.get("access", data) if isinstance(data, dict) else {}
    token = (
        (access.get("token") if isinstance(access, dict) else None)
        or data.get("access_token")
        or body.get("access_token")
    )
    if not token:
        raise ValueError(f"refresh response missing access token; keys={list(body)[:8]}")
    new_rt = (
        data.get("refresh_token")
        or body.get("refresh_token")
        or (access.get("refresh_token") if isinstance(access, dict) else None)
    )
    now = int(now)
    abs_exp = (access.get("expired_time") if isinstance(access, dict) else None) or data.get("expired_time")
    ttl = data.get("expires_in") or body.get("expires_in")
    if abs_exp is not None:
        abs_exp = int(abs_exp)
        expiry = abs_exp // 1000 if abs_exp > 10_000_000_000 else abs_exp
    elif ttl is not None:
        expiry = now + int(ttl)
    else:
        expiry = now + 3600  # conservative default
    return token, new_rt, expiry


class AjaibAuth:
    """Manages an Ajaib session token from a stored refresh token.

    Refreshes lazily; persists a rotated refresh token via ``token_writer`` so a
    GitHub Actions run survives token rotation. In-memory only (each Actions run
    is a fresh short-lived process)."""

    def __init__(self, refresh_token: str, *, token_writer=None,
                 http_post=_default_post, clock=time.time, skew_seconds: int = 60):
        self._refresh_token = refresh_token
        self._token_writer = token_writer
        self._post = http_post
        self._clock = clock
        self._skew = skew_seconds
        self._token: str | None = None
        self._expiry: float = 0.0

    def get_access_token(self) -> str:
        if self._token and self._clock() < self._expiry - self._skew:
            return self._token
        return self.refresh()

    def refresh(self) -> str:
        if not self._refresh_token:
            raise RuntimeError("AJAIB_REFRESH_TOKEN is not set")
        status, body = self._post(
            REFRESH_URL, {"refresh_token": self._refresh_token}, dict(_HEADERS_BASE)
        )
        if status != 200:
            raise RuntimeError(f"ajaib token refresh failed: HTTP {status}")
        token, new_rt, expiry = _extract_tokens(body, self._clock())
        self._token, self._expiry = token, float(expiry)
        if new_rt and new_rt != self._refresh_token:
            self._refresh_token = new_rt
            if self._token_writer is not None:
                try:
                    self._token_writer(new_rt)
                except Exception as exc:  # noqa: BLE001 — persist failure must be loud, not fatal here
                    logger.warning("could not persist rotated ajaib refresh token: %s", exc)
        return token

    def auth_headers(self) -> dict:
        return {**_HEADERS_BASE, "Authorization": f"Bearer {self.get_access_token()}"}
