"""API-key gate. Dev mode (default key, no public host) is open on localhost; the moment a real key or a public
host is configured, every /api and /ws route needs the key."""
from __future__ import annotations

import hmac

from .config import get_settings

DEFAULT_KEY = "change-me"
PUBLIC_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")
ALWAYS_LOCKED: tuple[str, ...] = ()


def locked() -> bool:
    s = get_settings()
    return s.kin_api_key != DEFAULT_KEY or bool(s.public_wss_host)


def key_ok(given: str | None) -> bool:
    return bool(given) and hmac.compare_digest(given, get_settings().kin_api_key)


def check_startup() -> None:
    s = get_settings()
    if s.public_wss_host and s.kin_api_key == DEFAULT_KEY:
        raise RuntimeError("PUBLIC_WSS_HOST is set but KIN_API_KEY is still the default; set a real key before exposing KIN")
