"""Scrub secrets from tool data before it leaves the server (spec 5.4)."""

from __future__ import annotations

from typing import Any

from app.utils.redaction import redact_secrets

HIDDEN = "[hidden]"
_SECRET_PARTS = ("passphrase", "password", "private_key", "secret", "token_hash")
_SECRET_NAMES = {
    "token",
    "service_url",
    "webhook_url",
    "key_data",
    "api_key",
    "access_key",
}


def _secret_key(name: str) -> bool:
    lowered = name.lower()
    return lowered in _SECRET_NAMES or any(part in lowered for part in _SECRET_PARTS)


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                HIDDEN
                if _secret_key(str(key))
                and not isinstance(item, bool)
                and item is not None
                else scrub(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    return value
