from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote, urlencode, urlparse
import base64
import hashlib
import secrets

import httpx
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database.models import SystemSettings


OIDC_STATE_TOKEN_TYPE = "oidc_state"
OIDC_STATE_EXPIRE_MINUTES = 10


@dataclass
class OidcProviderConfiguration:
    provider_name: str
    discovery_url: str
    client_id: str
    client_secret: str
    token_auth_method: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: Optional[str]
    jwks_uri: str
    issuer: str
    scopes: str
    redirect_uri: str
    end_session_endpoint: Optional[str]
    username_claim: str
    email_claim: str
    full_name_claim: str
    group_claim: Optional[str]
    role_claim: Optional[str]
    admin_groups: list[str]
    all_repositories_role_claim: Optional[str]
    new_user_mode: str
    new_user_template_username: Optional[str]
    default_role: str
    default_all_repositories_role: str


def get_system_oidc_settings(db: Session) -> Optional[SystemSettings]:
    settings_row = db.query(SystemSettings).first()
    if settings_row is None or not settings_row.oidc_enabled:
        return None
    return settings_row


def create_oidc_state_token(*, state_id: str, nonce: str) -> str:
    payload = {
        "purpose": OIDC_STATE_TOKEN_TYPE,
        "state_id": state_id,
        "nonce": nonce,
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=OIDC_STATE_EXPIRE_MINUTES),
    }
    return jwt.encode(
        payload, app_settings.secret_key, algorithm=app_settings.algorithm
    )


def verify_oidc_state_token(token: str) -> Optional[dict[str, str]]:
    try:
        payload = jwt.decode(
            token,
            app_settings.secret_key,
            algorithms=[app_settings.algorithm],
        )
    except PyJWTError:
        return None

    if payload.get("purpose") != OIDC_STATE_TOKEN_TYPE:
        return None

    nonce = payload.get("nonce")
    state_id = payload.get("state_id")
    if not isinstance(nonce, str) or not isinstance(state_id, str):
        return None

    return {"nonce": nonce, "state_id": state_id}


def generate_oidc_nonce() -> str:
    return secrets.token_urlsafe(24)


def generate_oidc_state_id() -> str:
    return secrets.token_urlsafe(24)


def generate_pkce_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def generate_pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _request_client_host(request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return ""


def request_uses_trusted_proxy(request) -> bool:
    client_host = _request_client_host(request)
    return client_host in app_settings.trusted_proxies


def build_external_base_url(request) -> str:
    if app_settings.public_base_url:
        return app_settings.public_base_url.strip().rstrip("/")

    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if request_uses_trusted_proxy(request):
        proto = (
            forwarded_proto.split(",")[0].strip()
            if forwarded_proto
            else request.url.scheme
        )
        host = (
            forwarded_host.split(",")[0].strip()
            if forwarded_host
            else request.headers.get("host")
        )
    else:
        proto = request.url.scheme
        host = request.headers.get("host")
    if not host:
        host = request.url.netloc
    return f"{proto}://{host}"


def build_default_post_login_url(request) -> str:
    root_path = (request.scope.get("root_path") or "").rstrip("/")
    return f"{build_external_base_url(request)}{root_path}/login"


def build_post_logout_url(request) -> str:
    return build_default_post_login_url(request)


def is_safe_return_to(return_to: str, request) -> bool:
    if not return_to:
        return False

    parsed = urlparse(return_to)
    if not parsed.scheme or not parsed.netloc:
        return False

    allowed_origins = {build_external_base_url(request)}
    allowed_origins.update(app_settings.oidc_allowed_return_origins)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin in allowed_origins


def resolve_post_login_url(request, return_to: Optional[str]) -> str:
    if return_to and is_safe_return_to(return_to, request):
        return return_to
    return build_default_post_login_url(request)


def build_redirect_uri(request, settings_row: SystemSettings) -> str:
    if settings_row.oidc_redirect_uri_override:
        return settings_row.oidc_redirect_uri_override.strip()

    root_path = (request.scope.get("root_path") or "").rstrip("/")
    return f"{build_external_base_url(request)}{root_path}/api/auth/oidc/callback"


async def discover_oidc_configuration(
    request, settings_row: SystemSettings, client_secret: str
) -> OidcProviderConfiguration:
    discovery_url = (settings_row.oidc_discovery_url or "").strip()
    parsed_discovery = urlparse(discovery_url)
    if parsed_discovery.scheme != "https" and parsed_discovery.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("OIDC discovery URL must use HTTPS outside local development")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(discovery_url)
        response.raise_for_status()
        metadata = response.json()

    authorization_endpoint = metadata["authorization_endpoint"]
    token_endpoint = metadata["token_endpoint"]
    jwks_uri = metadata["jwks_uri"]
    issuer = metadata["issuer"]
    userinfo_endpoint = metadata.get("userinfo_endpoint")

    return OidcProviderConfiguration(
        provider_name=(settings_row.oidc_provider_name or "Single sign-on").strip()
        or "Single sign-on",
        discovery_url=discovery_url,
        client_id=(settings_row.oidc_client_id or "").strip(),
        client_secret=client_secret,
        token_auth_method=(
            settings_row.oidc_token_auth_method or "client_secret_post"
        ).strip()
        or "client_secret_post",
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        userinfo_endpoint=userinfo_endpoint,
        jwks_uri=jwks_uri,
        issuer=issuer,
        scopes=(settings_row.oidc_scopes or "openid profile email").strip()
        or "openid profile email",
        redirect_uri=build_redirect_uri(request, settings_row),
        end_session_endpoint=settings_row.oidc_end_session_endpoint_override
        or metadata.get("end_session_endpoint"),
        username_claim=(
            settings_row.oidc_claim_username or "preferred_username"
        ).strip()
        or "preferred_username",
        email_claim=(settings_row.oidc_claim_email or "email").strip() or "email",
        full_name_claim=(settings_row.oidc_claim_full_name or "name").strip() or "name",
        group_claim=(settings_row.oidc_group_claim or "").strip() or None,
        role_claim=(settings_row.oidc_role_claim or "").strip() or None,
        admin_groups=[
            group.strip().lower()
            for group in (settings_row.oidc_admin_groups or "").split(",")
            if group.strip()
        ],
        all_repositories_role_claim=(
            (settings_row.oidc_all_repositories_role_claim or "").strip() or None
        ),
        new_user_mode=(settings_row.oidc_new_user_mode or "viewer").strip() or "viewer",
        new_user_template_username=(
            (settings_row.oidc_new_user_template_username or "").strip() or None
        ),
        default_role=(settings_row.oidc_default_role or "viewer").strip() or "viewer",
        default_all_repositories_role=(
            (settings_row.oidc_default_all_repositories_role or "viewer").strip()
            or "viewer"
        ),
    )


def build_authorization_url(
    provider: OidcProviderConfiguration,
    *,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": provider.redirect_uri,
            "scope": provider.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{provider.authorization_endpoint}?{query}"


def build_end_session_url(
    provider: OidcProviderConfiguration, request, *, id_token_hint: Optional[str] = None
) -> Optional[str]:
    if not provider.end_session_endpoint:
        return None
    query_params = {"post_logout_redirect_uri": build_post_logout_url(request)}
    if id_token_hint:
        query_params["id_token_hint"] = id_token_hint
    query = urlencode(query_params)
    return f"{provider.end_session_endpoint}?{query}"


async def exchange_code_for_tokens(
    provider: OidcProviderConfiguration, *, code: str, code_verifier: str
) -> dict[str, Any]:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": provider.redirect_uri,
        "client_id": provider.client_id,
        "code_verifier": code_verifier,
    }
    headers = {"Accept": "application/json"}

    if provider.token_auth_method == "client_secret_basic":
        encoded_client_id = quote(provider.client_id, safe="")
        encoded_client_secret = quote(provider.client_secret, safe="")
        basic_value = base64.b64encode(
            f"{encoded_client_id}:{encoded_client_secret}".encode("ascii")
        ).decode("ascii")
        headers["Authorization"] = f"Basic {basic_value}"
    else:
        payload["client_secret"] = provider.client_secret

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            provider.token_endpoint,
            data=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


def verify_id_token(
    provider: OidcProviderConfiguration, id_token: str, *, nonce: str
) -> dict[str, Any]:
    signing_key = PyJWKClient(provider.jwks_uri).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
        audience=provider.client_id,
        issuer=provider.issuer,
        options={"require": ["exp", "iat", "sub"]},
    )

    if claims.get("nonce") != nonce:
        raise ValueError("OIDC nonce mismatch")
    if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
        raise ValueError("OIDC subject claim missing")

    return claims


async def fetch_userinfo(
    provider: OidcProviderConfiguration, access_token: str
) -> dict[str, Any]:
    if not provider.userinfo_endpoint:
        return {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            provider.userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


def extract_claim_value(
    claims: dict[str, Any], claim_name: Optional[str]
) -> Optional[Any]:
    if not claim_name:
        return None

    current: Any = claims
    for part in claim_name.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def normalize_string_claim(value: Any) -> Optional[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def normalize_role_claim(value: Any) -> Optional[str]:
    if isinstance(value, list):
        for item in value:
            normalized = normalize_string_claim(item)
            if normalized:
                return normalized.lower()
        return None
    normalized = normalize_string_claim(value)
    return normalized.lower() if normalized else None


def normalize_groups_claim(value: Any) -> list[str]:
    if isinstance(value, list):
        return [
            normalized
            for item in value
            if (normalized := normalize_string_claim(item)) is not None
        ]
    normalized = normalize_string_claim(value)
    return [normalized] if normalized else []


def merge_claim_sets(*claim_sets: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for claim_set in claim_sets:
        merged.update(claim_set)
    return merged


def normalize_oidc_identity(
    claims: dict[str, Any],
    provider: OidcProviderConfiguration,
) -> dict[str, Any]:
    username = normalize_string_claim(
        extract_claim_value(claims, provider.username_claim)
    )
    email = normalize_string_claim(extract_claim_value(claims, provider.email_claim))
    full_name = normalize_string_claim(
        extract_claim_value(claims, provider.full_name_claim)
    )
    role = normalize_role_claim(extract_claim_value(claims, provider.role_claim))
    groups = [
        group.lower()
        for group in normalize_groups_claim(
            extract_claim_value(claims, provider.group_claim)
        )
    ]
    all_repositories_role = normalize_role_claim(
        extract_claim_value(claims, provider.all_repositories_role_claim)
    )

    if not username:
        fallback_subject = normalize_string_claim(claims.get("sub"))
        if fallback_subject:
            username = fallback_subject
        elif email and "@" in email:
            username = email.split("@", 1)[0]

    if username:
        username = username.strip().lower()

    if email:
        email = email.strip().lower()

    return {
        "username": username,
        "subject": normalize_string_claim(claims.get("sub")),
        "email": email,
        "full_name": full_name,
        "role": role,
        "groups": groups,
        "all_repositories_role": all_repositories_role,
    }


def encode_oidc_error_redirect(return_to: str, *, error_key: str) -> str:
    separator = "&" if "?" in return_to else "?"
    return f"{return_to}{separator}{urlencode({'oidc_error': error_key})}"


def encode_oidc_complete_redirect(return_to: str) -> str:
    separator = "&" if "?" in return_to else "?"
    return f"{return_to}{separator}{urlencode({'oidc': 'complete'})}"
