from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger("news_breakout")


def _strip_bearer(token: str) -> str:
    t = (token or "").strip()
    return t[7:].strip() if t[:7].lower() == "bearer " else t


def _jwt_exp(token: str) -> int | None:
    """Read the `exp` claim from a JWT without verifying it — used only to size
    the bootstrap token's cache lifetime. Returns None if it isn't a readable JWT.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # restore base64 padding
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
        return int(exp) if exp is not None else None
    except Exception:  # noqa: BLE001 — any decode problem just means "unknown expiry"
        return None

# --- SEAMS: confirm against one live capture during the implementation spike ---
# The refresh endpoint + request/response shape are the two unknowns. They are
# isolated here so finalizing them is a one-place change.
REFRESH_URL = "https://exodus.stockbit.com/login/refresh"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS_BASE = {"User-Agent": _UA, "Referer": "https://stockbit.com/", "Origin": "https://stockbit.com"}


def _default_post(url: str, payload: dict, headers: dict) -> tuple[int, dict]:
    with httpx.Client() as client:
        resp = client.post(url, json=payload, headers=headers, timeout=15)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 — non-JSON body still carries the status
            body = {}
        return resp.status_code, body


def _extract_token(body: dict, now: float) -> tuple[str, int]:
    """Pull (access_token, expiry_epoch) from a refresh response.

    ``now`` is the caller's clock so relative-TTL math stays consistent with the
    expiry comparison that uses the same clock.

    SEAM: tolerant of the shapes Stockbit's auth has used; finalize against the
    real capture. Raises so a shape mismatch surfaces loudly instead of caching
    an empty token.
    """
    data = body.get("data", body) if isinstance(body, dict) else {}
    access = data.get("access", data) if isinstance(data, dict) else {}
    token = (
        access.get("token")
        or data.get("access_token")
        or body.get("access_token")
    )
    if not token:
        raise ValueError(f"refresh response missing access token; keys={list(body)[:8]}")
    now = int(now)
    # Distinguish by key name (unambiguous): `expired_time` is an absolute epoch
    # (seconds or ms); `expires_in` is a relative TTL in seconds.
    abs_exp = access.get("expired_time") or data.get("expired_time")
    ttl = data.get("expires_in") or body.get("expires_in")
    if abs_exp is not None:
        abs_exp = int(abs_exp)
        return token, abs_exp // 1000 if abs_exp > 10_000_000_000 else abs_exp
    if ttl is not None:
        return token, now + int(ttl)
    return token, now + 3600  # conservative default TTL


class StockbitAuth:
    """Manages a Stockbit access token from a stored refresh token.

    Caches the access token (with expiry) on disk so process restarts don't
    force a refresh. ``get_access_token`` refreshes lazily; ``refresh`` forces
    one (used on a 401 from a data call).
    """

    def __init__(
        self,
        refresh_token: str,
        *,
        access_token: str = "",
        token_path: str = "data_cache/stockbit_token.json",
        http_post=_default_post,
        clock=time.time,
        skew_seconds: int = 60,
        bootstrap_ttl: int = 3600,
    ):
        self._refresh_token = refresh_token
        self._path = Path(token_path)
        self._post = http_post
        self._clock = clock
        self._skew = skew_seconds
        self._token: str | None = None
        self._expiry: float = 0.0
        self._load_cache()
        # A freshly pasted access token wins over any cache — lets you test the
        # data path immediately without a confirmed refresh endpoint. On expiry
        # or 401 it falls through to refresh() (which needs the refresh token).
        if access_token:
            tok = _strip_bearer(access_token)
            self._token = tok
            exp = _jwt_exp(tok)  # honour the JWT's own lifetime when present
            self._expiry = float(exp) if exp else self._clock() + bootstrap_ttl

    def get_access_token(self) -> str:
        if self._token and self._clock() < self._expiry - self._skew:
            return self._token
        return self.refresh()

    def refresh(self) -> str:
        if not self._refresh_token:
            raise RuntimeError("STOCKBIT_REFRESH_TOKEN is not set")
        status, body = self._post(
            REFRESH_URL, {"refresh_token": self._refresh_token}, dict(_HEADERS_BASE)
        )
        if status != 200:
            raise RuntimeError(f"token refresh failed: HTTP {status}")
        token, expiry = _extract_token(body, self._clock())
        self._token, self._expiry = token, float(expiry)
        self._save_cache()
        return token

    def auth_headers(self) -> dict:
        return {**_HEADERS_BASE, "Authorization": f"Bearer {self.get_access_token()}"}

    def _load_cache(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._token = data.get("access_token")
            self._expiry = float(data.get("expiry", 0.0))
        except (OSError, ValueError, json.JSONDecodeError):
            self._token, self._expiry = None, 0.0

    def _save_cache(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"access_token": self._token, "expiry": self._expiry}),
                encoding="utf-8",
            )
        except OSError as exc:  # non-fatal: caching is an optimization
            logger.warning("could not persist stockbit token: %s", exc)
