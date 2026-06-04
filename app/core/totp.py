import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote


def generate_totp_secret() -> str:
    """Generate a base32 TOTP secret without padding."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _normalize_base32_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(f"{normalized}{padding}", casefold=True)


def _hotp(secret: str, counter: int, digits: int = 6) -> str:
    key = _normalize_base32_secret(secret)
    counter_bytes = struct.pack(">Q", counter)
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def verify_totp_code(
    secret: str,
    code: str,
    *,
    timestamp: Optional[int] = None,
    step_seconds: int = 30,
    valid_window: int = 1,
    digits: int = 6,
) -> bool:
    normalized_code = "".join(ch for ch in code if ch.isdigit())
    if len(normalized_code) != digits:
        return False

    ts = int(time.time() if timestamp is None else timestamp)
    counter = ts // step_seconds

    for offset in range(-valid_window, valid_window + 1):
        if hmac.compare_digest(
            _hotp(secret, counter + offset, digits=digits), normalized_code
        ):
            return True
    return False


def build_totp_uri(secret: str, username: str, issuer: str = "Borg UI") -> str:
    label = quote(f"{issuer}:{username}")
    issuer_q = quote(issuer)
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret}&issuer={issuer_q}&algorithm=SHA1&digits=6&period=30"
    )


def generate_recovery_codes(count: int = 8) -> list[str]:
    codes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    return code.strip().replace(" ", "").replace("-", "").upper()


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalize_recovery_code(code).encode("utf-8")).hexdigest()
