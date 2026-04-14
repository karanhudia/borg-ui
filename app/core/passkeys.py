import json
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import HTTPException, status

from app.config import settings
from app.core.security import decode_token
import jwt


def require_webauthn():
    try:
        from webauthn import (
            generate_authentication_options,
            generate_registration_options,
            options_to_json,
            verify_authentication_response,
            verify_registration_response,
        )
        from webauthn.helpers import base64url_to_bytes
        from webauthn.helpers.parse_registration_credential_json import (
            parse_registration_credential_json,
        )
        from webauthn.helpers.parse_authentication_credential_json import (
            parse_authentication_credential_json,
        )
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            PublicKeyCredentialDescriptor,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "key": "backend.errors.auth.passkeysUnavailable",
                "params": {"error": str(exc)},
            },
        ) from exc

    return {
        "generate_authentication_options": generate_authentication_options,
        "generate_registration_options": generate_registration_options,
        "options_to_json": options_to_json,
        "verify_authentication_response": verify_authentication_response,
        "verify_registration_response": verify_registration_response,
        "base64url_to_bytes": base64url_to_bytes,
        "parse_registration_credential_json": parse_registration_credential_json,
        "parse_authentication_credential_json": parse_authentication_credential_json,
        "AuthenticatorSelectionCriteria": AuthenticatorSelectionCriteria,
        "PublicKeyCredentialDescriptor": PublicKeyCredentialDescriptor,
        "ResidentKeyRequirement": ResidentKeyRequirement,
        "UserVerificationRequirement": UserVerificationRequirement,
    }


def resolve_origin_and_rp_id(request) -> tuple[str, str]:
    origin_header = request.headers.get("origin")
    if origin_header:
        split = urlsplit(origin_header.rstrip("/"))
        origin = f"{split.scheme}://{split.netloc}"
    else:
        base = str(request.base_url).rstrip("/")
        split = urlsplit(base)
        origin = f"{split.scheme}://{split.netloc}"
    rp_id = split.hostname or "localhost"
    return origin, rp_id


def create_passkey_ceremony_token(
    *,
    username: str,
    challenge: str,
    purpose: str,
    expires_minutes: int = 10,
) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    payload = {
        "sub": username,
        "purpose": purpose,
        "challenge": challenge,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_passkey_ceremony_token(token: str, purpose: str) -> Optional[dict[str, Any]]:
    payload = decode_token(token)
    if payload is None or payload.get("purpose") != purpose:
        return None
    username = payload.get("sub")
    challenge = payload.get("challenge")
    if not isinstance(username, str) or not isinstance(challenge, str):
        return None
    return {"username": username, "challenge": challenge}


def parse_options_json(options_json: str) -> dict[str, Any]:
    return json.loads(options_json)
