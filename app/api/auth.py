import base64
from datetime import timedelta, datetime, timezone
import hmac
import json
from typing import Any, Optional
from urllib.parse import urlencode, urlparse
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog

from app.database.database import get_db
from app.database.models import (
    AuthEvent,
    OidcExchangeGrant,
    OidcLoginState,
    PasskeyCredential,
    SystemSettings,
    User,
    UserRepositoryPermission,
)
from app.core.auth_rate_limits import (
    clear_auth_rate_limit,
    enforce_auth_rate_limit,
    get_passkey_login_policy,
    get_password_login_policy,
    get_request_client_ip,
    get_totp_login_policy,
    record_auth_failure,
)
from app.core.oidc import (
    build_authorization_url,
    build_end_session_url,
    build_external_base_url,
    create_oidc_state_token,
    discover_oidc_configuration,
    encode_oidc_complete_redirect,
    encode_oidc_error_redirect,
    exchange_code_for_tokens,
    fetch_userinfo,
    generate_oidc_nonce,
    generate_oidc_state_id,
    generate_pkce_code_challenge,
    generate_pkce_code_verifier,
    get_system_oidc_settings,
    merge_claim_sets,
    normalize_oidc_identity,
    resolve_post_login_url,
    verify_id_token,
    verify_oidc_state_token,
)
from app.core.security import (
    authenticate_user,
    create_access_token,
    create_login_challenge_token,
    create_totp_setup_token,
    get_current_user,
    get_current_admin_user,
    create_user,
    decrypt_secret,
    encrypt_secret,
    update_user_password,
    verify_login_challenge_token,
    verify_password,
    verify_totp_setup_token,
)
from app.core.user_deletion import detach_user_delete_references
from app.core.passkeys import (
    create_passkey_ceremony_token,
    parse_options_json,
    require_webauthn,
    resolve_origin_and_rp_id,
    verify_passkey_ceremony_token,
)
from app.core.permissions import (
    get_global_permissions_for_role,
    serialize_authorization_model,
    default_repository_role_for_global_role,
    normalize_repository_role_for_global_role,
)
from app.core.totp import (
    build_totp_uri,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    verify_totp_code,
)
from app.config import settings
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter()
OIDC_EXCHANGE_COOKIE_NAME = "oidc_exchange_grant"
OIDC_EXCHANGE_GRANT_EXPIRE_MINUTES = 5


# Pydantic models for request/response
class Token(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None
    must_change_password: bool = False
    totp_required: bool = False
    login_challenge_token: Optional[str] = None


class AuthConfig(BaseModel):
    proxy_auth_enabled: bool
    insecure_no_auth_enabled: bool
    authentication_required: bool
    oidc_enabled: bool = False
    oidc_provider_name: Optional[str] = None
    oidc_disable_local_auth: bool = False
    oidc_link_supported: bool = False
    oidc_unlink_supported: bool = False
    oidc_account_linking_supported: bool = False
    proxy_auth_header: Optional[str] = None
    proxy_auth_role_header: Optional[str] = None
    proxy_auth_all_repositories_role_header: Optional[str] = None
    proxy_auth_email_header: Optional[str] = None
    proxy_auth_full_name_header: Optional[str] = None
    proxy_auth_health: dict


class LogoutResponse(BaseModel):
    message: str
    logout_url: Optional[str] = None


class AuthEventResponse(BaseModel):
    id: int
    event_type: str
    auth_source: str
    username: Optional[str] = None
    email: Optional[str] = None
    success: bool
    detail: Optional[str] = None
    actor_user_id: Optional[int] = None
    created_at: datetime


class OidcLinkStartRequest(BaseModel):
    return_to: Optional[str] = None


class OidcLinkStartResponse(BaseModel):
    authorization_url: str


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    is_admin: bool = False
    role: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    role: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class PasswordSetupCompleteResponse(BaseModel):
    must_change_password: bool = False


class TotpLoginVerification(BaseModel):
    login_challenge_token: str
    code: str


class TotpSetupRequest(BaseModel):
    current_password: str


class TotpEnableRequest(BaseModel):
    setup_token: str
    code: str


class TotpDisableRequest(BaseModel):
    current_password: str
    code: str


class TotpStatusResponse(BaseModel):
    enabled: bool
    recovery_codes_remaining: int = 0


class TotpSetupResponse(BaseModel):
    setup_token: str
    secret: str
    otpauth_uri: str
    recovery_codes: list[str]


class TotpEnableResponse(BaseModel):
    enabled: bool
    recovery_codes: list[str]


class PasskeyCredentialResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class PasskeyBeginRegistrationRequest(BaseModel):
    current_password: str


class PasskeyFinishRegistrationRequest(BaseModel):
    ceremony_token: str
    credential: dict
    name: Optional[str] = None


class PasskeyBeginRegistrationResponse(BaseModel):
    ceremony_token: str
    options: dict


class PasskeyBeginAuthenticationResponse(BaseModel):
    ceremony_token: str
    options: dict


class PasskeyFinishAuthenticationRequest(BaseModel):
    ceremony_token: str
    credential: dict


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    deployment_type: Optional[str] = None
    enterprise_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    auth_source: str = "local"
    oidc_subject: Optional[str] = None
    role: str
    all_repositories_role: Optional[str] = None
    must_change_password: bool = False
    totp_enabled: bool = False
    passkey_count: int = 0
    last_login: Optional[datetime] = None
    created_at: datetime
    global_permissions: list[str] = []

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AuthorizationModelResponse(BaseModel):
    global_roles: list[dict]
    repository_roles: list[dict]
    global_permission_rules: dict[str, str]
    repository_action_rules: dict[str, str]
    assignable_repository_roles_by_global_role: dict[str, list[str]]


def _build_user_response(
    user: User,
    deployment_type: Optional[str] = None,
    enterprise_name: Optional[str] = None,
) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": getattr(user, "full_name", None),
        "deployment_type": deployment_type,
        "enterprise_name": enterprise_name,
        "email": getattr(user, "email", None),
        "is_active": user.is_active,
        "auth_source": getattr(user, "auth_source", "local"),
        "oidc_subject": getattr(user, "oidc_subject", None),
        "role": user.role,
        "all_repositories_role": getattr(user, "all_repositories_role", None),
        "must_change_password": getattr(user, "must_change_password", False),
        "totp_enabled": getattr(user, "totp_enabled", False),
        "passkey_count": len(getattr(user, "passkeys", []) or []),
        "last_login": getattr(user, "last_login", None),
        "created_at": user.created_at,
        "global_permissions": get_global_permissions_for_role(user.role),
    }


def _resolve_legacy_role(
    role: Optional[str],
    is_admin: Optional[bool],
) -> str:
    if role:
        return role
    if is_admin is not None:
        return "admin" if is_admin else "viewer"
    return "viewer"


def _get_totp_secret(user: User) -> Optional[str]:
    if not user.totp_enabled or not user.totp_secret_encrypted:
        return None
    return decrypt_secret(user.totp_secret_encrypted)


def _get_recovery_code_hashes(user: User) -> list[str]:
    if not user.totp_recovery_codes_hashes:
        return []
    try:
        data = json.loads(user.totp_recovery_codes_hashes)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


def _store_recovery_code_hashes(user: User, hashes: list[str]) -> None:
    user.totp_recovery_codes_hashes = json.dumps(hashes)


def _consume_recovery_code(user: User, code: str) -> bool:
    normalized_hash = hash_recovery_code(code)
    existing_hashes = _get_recovery_code_hashes(user)
    if normalized_hash not in existing_hashes:
        return False
    remaining = [item for item in existing_hashes if item != normalized_hash]
    _store_recovery_code_hashes(user, remaining)
    return True


def _verify_totp_or_recovery_code(user: User, code: str) -> bool:
    totp_secret = _get_totp_secret(user)
    if totp_secret and verify_totp_code(totp_secret, code):
        return True
    return _consume_recovery_code(user, code)


def _ensure_local_password_user(user: User) -> None:
    if (
        settings.disable_authentication
        or settings.allow_insecure_no_auth
        or not user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.localPasswordRequired"},
        )


def _get_auth_settings_row(db: Session) -> Optional[SystemSettings]:
    return db.query(SystemSettings).first()


def _local_auth_disabled_for_oidc(settings_row: Optional[SystemSettings]) -> bool:
    return bool(
        settings_row
        and settings_row.oidc_enabled
        and settings_row.oidc_disable_local_auth
    )


def _ensure_local_login_allowed(settings_row: Optional[SystemSettings]) -> None:
    if _local_auth_disabled_for_oidc(settings_row):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.auth.localLoginDisabled"},
        )


def _serialize_passkey_credential(credential: PasskeyCredential) -> dict:
    return {
        "id": credential.id,
        "name": credential.name,
        "created_at": credential.created_at,
        "last_used_at": credential.last_used_at,
    }


def _raise_passkey_verification_error(exc: Exception) -> None:
    message = str(exc).lower()
    detail_key = "backend.errors.auth.invalidPasskey"

    if "user verification is required" in message and "was not verified" in message:
        detail_key = "backend.errors.auth.passkeyUserVerificationRequired"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"key": detail_key},
    ) from exc


def _record_auth_event(
    db: Session,
    *,
    event_type: str,
    auth_source: str,
    success: bool,
    username: Optional[str] = None,
    email: Optional[str] = None,
    detail: Optional[str] = None,
    actor_user_id: Optional[int] = None,
) -> None:
    db.add(
        AuthEvent(
            event_type=event_type,
            auth_source=auth_source,
            username=username,
            email=email,
            success=success,
            detail=detail,
            actor_user_id=actor_user_id,
        )
    )
    db.commit()


def _record_rate_limit_failure(
    db: Session,
    *,
    scope: str,
    subject: str,
    client_ip: str,
    policy,
    event_type: str,
    auth_source: str,
    username: Optional[str] = None,
    email: Optional[str] = None,
    detail: str,
) -> None:
    rate_limit_exception = record_auth_failure(
        db,
        scope=scope,
        subject=subject,
        client_ip=client_ip,
        policy=policy,
    )
    if rate_limit_exception is None:
        return

    _record_auth_event(
        db,
        event_type=event_type,
        auth_source=auth_source,
        success=False,
        username=username,
        email=email,
        detail=detail,
    )
    raise rate_limit_exception


def _clear_local_session_artifacts(user: User) -> None:
    user.auth_source = "local"
    user.oidc_last_id_token_encrypted = None


def _normalize_oidc_groups(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        group.strip().lower()
        for group in value
        if isinstance(group, str) and group.strip()
    ]


def _coerce_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _prune_expired_oidc_artifacts(db: Session) -> None:
    now = datetime.now(timezone.utc)
    deleted_login_states = (
        db.query(OidcLoginState).filter(OidcLoginState.expires_at <= now).delete()
    )
    deleted_exchange_grants = (
        db.query(OidcExchangeGrant).filter(OidcExchangeGrant.expires_at <= now).delete()
    )
    if deleted_login_states or deleted_exchange_grants:
        db.commit()


def _create_oidc_login_state(
    db: Session,
    *,
    state_id: str,
    nonce: str,
    code_verifier: str,
    return_to: str,
    flow: str = "login",
    user_id: Optional[int] = None,
) -> OidcLoginState:
    state = OidcLoginState(
        state_id=state_id,
        nonce=nonce,
        code_verifier=code_verifier,
        return_to=return_to,
        flow=flow,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _create_oidc_exchange_grant(
    db: Session,
    *,
    identity: dict[str, Any],
    id_token_hint: Optional[str],
) -> OidcExchangeGrant:
    grant = OidcExchangeGrant(
        grant_id=generate_oidc_state_id(),
        username=identity["username"],
        oidc_subject=identity.get("subject"),
        email=identity.get("email"),
        full_name=identity.get("full_name"),
        groups_json=json.dumps(_normalize_oidc_groups(identity.get("groups"))),
        role=identity.get("role"),
        all_repositories_role=identity.get("all_repositories_role"),
        id_token_hint_encrypted=(
            encrypt_secret(id_token_hint) if id_token_hint else None
        ),
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=OIDC_EXCHANGE_GRANT_EXPIRE_MINUTES),
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def _consume_oidc_exchange_grant(
    db: Session, *, grant_id: str
) -> Optional[OidcExchangeGrant]:
    grant = (
        db.query(OidcExchangeGrant)
        .filter(OidcExchangeGrant.grant_id == grant_id)
        .first()
    )
    if grant is None or grant.used_at is not None:
        return None

    expires_at = _coerce_utc_datetime(grant.expires_at)
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        return None

    grant.used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(grant)
    return grant


def _build_oidc_exchange_identity(grant: OidcExchangeGrant) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "username": grant.username,
        "subject": grant.oidc_subject,
        "email": grant.email,
        "full_name": grant.full_name,
        "groups": json.loads(grant.groups_json) if grant.groups_json else [],
        "role": grant.role,
        "all_repositories_role": grant.all_repositories_role,
    }
    if grant.id_token_hint_encrypted:
        identity["id_token_hint"] = decrypt_secret(grant.id_token_hint_encrypted)
    return identity


def _require_oidc_subject(identity: dict[str, Any]) -> str:
    subject = identity.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.oidcSubjectClaimMissing"},
        )
    return subject.strip()


def _find_user_by_oidc_subject(db: Session, subject: str) -> Optional[User]:
    return db.query(User).filter(User.oidc_subject == subject).first()


def _link_oidc_identity_to_user(
    db: Session, *, user: User, identity: dict[str, Any], id_token_hint: Optional[str]
) -> User:
    subject = _require_oidc_subject(identity)
    subject_user = _find_user_by_oidc_subject(db, subject)
    if subject_user is not None and subject_user.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.auth.oidcIdentityConflict"},
        )

    incoming_email = identity.get("email")
    if incoming_email and user.email != incoming_email:
        existing_email_user = (
            db.query(User)
            .filter(User.email == incoming_email, User.id != user.id)
            .first()
        )
        if existing_email_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"key": "backend.errors.auth.oidcEmailAlreadyInUse"},
            )
        user.email = incoming_email

    incoming_full_name = identity.get("full_name")
    if incoming_full_name:
        user.full_name = incoming_full_name

    user.auth_source = "oidc"
    user.oidc_subject = subject
    if id_token_hint:
        user.oidc_last_id_token_encrypted = encrypt_secret(id_token_hint)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def _is_same_origin_request(request: Request) -> bool:
    expected_origin = build_external_base_url(request).rstrip("/")
    header_value = request.headers.get("origin") or request.headers.get("referer")
    if not header_value:
        return False

    parsed = urlparse(header_value)
    received_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return hmac.compare_digest(received_origin, expected_origin)


def _append_redirect_params(return_to: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in return_to else "?"
    return f"{return_to}{separator}{urlencode(params)}"


def _consume_oidc_login_state(
    db: Session, *, state_id: str, nonce: str
) -> Optional[OidcLoginState]:
    state = db.query(OidcLoginState).filter(OidcLoginState.state_id == state_id).first()
    if state is None:
        return None
    if not hmac.compare_digest(state.nonce, nonce) or state.used_at is not None:
        return None
    expires_at = _coerce_utc_datetime(state.expires_at)
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        return None

    state.used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    return state


@router.get("/config", response_model=AuthConfig)
async def get_auth_config():
    """Get authentication configuration for frontend"""
    from app.core.proxy_auth import inspect_proxy_auth_config

    proxy_auth_enabled = (
        settings.disable_authentication and not settings.allow_insecure_no_auth
    )
    oidc_settings = None
    proxy_auth_health = {"enabled": False, "warnings": []}

    db = next(get_db())
    try:
        oidc_settings = get_system_oidc_settings(db)
    finally:
        db.close()

    if proxy_auth_enabled:
        proxy_auth_health = inspect_proxy_auth_config()

    return {
        "proxy_auth_enabled": proxy_auth_enabled,
        "insecure_no_auth_enabled": settings.allow_insecure_no_auth,
        "authentication_required": not (
            settings.disable_authentication or settings.allow_insecure_no_auth
        ),
        "oidc_enabled": bool(oidc_settings),
        "oidc_provider_name": (
            (oidc_settings.oidc_provider_name or "Single sign-on")
            if oidc_settings
            else None
        ),
        "oidc_disable_local_auth": bool(
            oidc_settings and oidc_settings.oidc_disable_local_auth
        ),
        "oidc_link_supported": bool(oidc_settings),
        "oidc_unlink_supported": bool(oidc_settings),
        "oidc_account_linking_supported": bool(oidc_settings),
        "proxy_auth_header": (
            settings.proxy_auth_header if proxy_auth_enabled else None
        ),
        "proxy_auth_role_header": (
            settings.proxy_auth_role_header if proxy_auth_enabled else None
        ),
        "proxy_auth_all_repositories_role_header": (
            settings.proxy_auth_all_repositories_role_header
            if proxy_auth_enabled
            else None
        ),
        "proxy_auth_email_header": (
            settings.proxy_auth_email_header if proxy_auth_enabled else None
        ),
        "proxy_auth_full_name_header": (
            settings.proxy_auth_full_name_header if proxy_auth_enabled else None
        ),
        "proxy_auth_health": proxy_auth_health,
    }


@router.get("/authorization-model", response_model=AuthorizationModelResponse)
async def get_authorization_model():
    """Expose the backend authorization model as the source of truth for the frontend."""
    return serialize_authorization_model()


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate user and return access token"""
    _ensure_local_login_allowed(_get_auth_settings_row(db))
    client_ip = get_request_client_ip(request)
    password_subject = form_data.username.strip().lower() or "unknown"
    enforce_auth_rate_limit(
        db,
        scope="password_login",
        subject=password_subject,
        client_ip=client_ip,
        policy=get_password_login_policy(),
    )
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        logger.warning("Failed login attempt", username=form_data.username)
        _record_rate_limit_failure(
            db,
            scope="password_login",
            subject=password_subject,
            client_ip=client_ip,
            policy=get_password_login_policy(),
            event_type="local_login_rate_limited",
            auth_source="local",
            username=form_data.username,
            detail="backend.errors.auth.incorrectCredentials",
        )
        _record_auth_event(
            db,
            event_type="local_login_failed",
            auth_source="local",
            success=False,
            username=form_data.username,
            detail="backend.errors.auth.incorrectCredentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.incorrectCredentials"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.inactiveUser"},
        )

    clear_auth_rate_limit(
        db,
        scope="password_login",
        subject=password_subject,
        client_ip=client_ip,
    )

    if user.totp_enabled:
        challenge_token = create_login_challenge_token(user.username)
        logger.info("Password verified, awaiting TOTP", username=user.username)
        return {
            "totp_required": True,
            "login_challenge_token": challenge_token,
            "must_change_password": user.must_change_password,
        }

    _clear_local_session_artifacts(user)
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    logger.info("User logged in successfully", username=user.username)
    _record_auth_event(
        db,
        event_type="local_login_succeeded",
        auth_source="local",
        success=True,
        username=user.username,
        email=user.email,
        actor_user_id=user.id,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "must_change_password": user.must_change_password,
    }


def _resolve_oidc_role(identity: dict[str, Any], settings_row: SystemSettings) -> str:
    candidate = identity.get("role")
    if candidate in {"viewer", "operator", "admin"}:
        if candidate == "admin":
            admin_groups = {
                group.strip().lower()
                for group in (settings_row.oidc_admin_groups or "").split(",")
                if group.strip()
            }
            identity_groups = set(_normalize_oidc_groups(identity.get("groups")))
            if not admin_groups or identity_groups.isdisjoint(admin_groups):
                logger.warning(
                    "Ignoring OIDC admin role claim without matching admin group allow-list",
                    username=identity.get("username"),
                    subject=identity.get("subject"),
                    configured_groups=sorted(admin_groups),
                    identity_groups=sorted(identity_groups),
                )
                return (settings_row.oidc_default_role or "viewer").strip() or "viewer"
        return candidate
    return (settings_row.oidc_default_role or "viewer").strip() or "viewer"


def _resolve_oidc_all_repositories_role(
    identity: dict[str, Any], global_role: str, settings_row: SystemSettings
) -> str:
    candidate = identity.get("all_repositories_role")
    if candidate:
        return normalize_repository_role_for_global_role(global_role, candidate)
    configured_default = (
        settings_row.oidc_default_all_repositories_role
        or default_repository_role_for_global_role(global_role)
    )
    return normalize_repository_role_for_global_role(global_role, configured_default)


def _find_user_for_oidc_identity(
    db: Session, *, username: str, subject: Optional[str]
) -> Optional[User]:
    if subject:
        subject_user = db.query(User).filter(User.oidc_subject == subject).first()
        if subject_user is not None:
            return subject_user
    return db.query(User).filter(User.username == username).first()


def _clone_template_permissions(
    db: Session, *, source_user: User, target_user: User
) -> None:
    template_permissions = (
        db.query(UserRepositoryPermission)
        .filter(UserRepositoryPermission.user_id == source_user.id)
        .all()
    )
    for permission in template_permissions:
        db.add(
            UserRepositoryPermission(
                user_id=target_user.id,
                repository_id=permission.repository_id,
                role=permission.role,
            )
        )


def _provision_oidc_user(
    db: Session, settings_row: SystemSettings, identity: dict[str, Any]
) -> User:
    username = identity.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.oidcUsernameClaimMissing"},
        )

    subject = _require_oidc_subject(identity)
    user = _find_user_for_oidc_identity(db, username=username, subject=subject)
    if user is not None and not user.oidc_subject and user.auth_source != "oidc":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.auth.oidcAccountLinkRequired"},
        )
    if (
        user is not None
        and subject
        and user.oidc_subject
        and not hmac.compare_digest(user.oidc_subject, subject)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.auth.oidcIdentityConflict"},
        )
    if user is None:
        new_user_mode = (
            settings_row.oidc_new_user_mode or "viewer"
        ).strip() or "viewer"
        if new_user_mode == "deny":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"key": "backend.errors.auth.oidcUserAccessDenied"},
            )

        template_user = None
        if new_user_mode == "template":
            template_username = settings_row.oidc_new_user_template_username
            template_user = (
                db.query(User).filter(User.username == template_username).first()
                if template_username
                else None
            )
            if template_user is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"key": "backend.errors.auth.oidcTemplateUserNotFound"},
                )

        role = _resolve_oidc_role(identity, settings_row)
        all_repositories_role = _resolve_oidc_all_repositories_role(
            identity, role, settings_row
        )
        requested_email = identity.get("email")
        existing_email_user = (
            db.query(User).filter(User.email == requested_email).first()
            if requested_email
            else None
        )
        if existing_email_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"key": "backend.errors.auth.oidcEmailAlreadyInUse"},
            )
        user = User(
            username=username,
            password_hash="",
            email=requested_email,
            full_name=identity.get("full_name"),
            auth_source="oidc",
            oidc_subject=subject,
            role=role,
            all_repositories_role=all_repositories_role,
            is_active=new_user_mode != "pending",
            must_change_password=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        if new_user_mode == "template":
            user.role = template_user.role
            user.all_repositories_role = normalize_repository_role_for_global_role(
                template_user.role,
                template_user.all_repositories_role
                or default_repository_role_for_global_role(template_user.role),
            )
            _clone_template_permissions(db, source_user=template_user, target_user=user)
            db.commit()
            db.refresh(user)

        if new_user_mode == "pending":
            _record_auth_event(
                db,
                event_type="oidc_user_pending",
                auth_source="oidc",
                success=False,
                username=username,
                email=identity.get("email"),
                detail="backend.errors.auth.oidcPendingApproval",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"key": "backend.errors.auth.oidcPendingApproval"},
            )
        _record_auth_event(
            db,
            event_type="oidc_user_provisioned",
            auth_source="oidc",
            success=True,
            username=username,
            email=identity.get("email"),
            detail=f"mode:{new_user_mode}",
        )

    if not user.is_active:
        _record_auth_event(
            db,
            event_type="oidc_user_denied",
            auth_source="oidc",
            success=False,
            username=username,
            email=identity.get("email"),
            detail="backend.errors.auth.inactiveUser",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.auth.inactiveUser"},
        )

    if identity.get("role"):
        role = _resolve_oidc_role(identity, settings_row)
        user.role = role
    else:
        role = user.role

    if identity.get("all_repositories_role"):
        user.all_repositories_role = _resolve_oidc_all_repositories_role(
            identity, role, settings_row
        )
    else:
        user.all_repositories_role = normalize_repository_role_for_global_role(
            role,
            user.all_repositories_role or default_repository_role_for_global_role(role),
        )

    incoming_email = identity.get("email")
    if incoming_email and user.email != incoming_email:
        existing_email_user = (
            db.query(User).filter(User.email == incoming_email).first()
        )
        if existing_email_user is not None and existing_email_user.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"key": "backend.errors.auth.oidcEmailAlreadyInUse"},
            )
        user.email = incoming_email

    incoming_full_name = identity.get("full_name")
    if incoming_full_name:
        user.full_name = incoming_full_name

    user.auth_source = "oidc"
    if subject:
        user.oidc_subject = subject
    if identity.get("id_token_hint"):
        user.oidc_last_id_token_encrypted = encrypt_secret(identity["id_token_hint"])

    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


async def _create_oidc_authorization_url(
    request: Request,
    db: Session,
    *,
    return_to: Optional[str],
    flow: str,
    user_id: Optional[int] = None,
) -> str:
    settings_row = get_system_oidc_settings(db)
    if settings_row is None or not settings_row.oidc_client_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.auth.oidcNotConfigured"},
        )

    _prune_expired_oidc_artifacts(db)
    provider = await discover_oidc_configuration(
        request,
        settings_row,
        decrypt_secret(settings_row.oidc_client_secret_encrypted),
    )
    nonce = generate_oidc_nonce()
    state_id = generate_oidc_state_id()
    code_verifier = generate_pkce_code_verifier()
    _create_oidc_login_state(
        db,
        state_id=state_id,
        nonce=nonce,
        code_verifier=code_verifier,
        return_to=resolve_post_login_url(request, return_to),
        flow=flow,
        user_id=user_id,
    )
    state = create_oidc_state_token(state_id=state_id, nonce=nonce)
    return build_authorization_url(
        provider,
        state=state,
        nonce=nonce,
        code_challenge=generate_pkce_code_challenge(code_verifier),
    )


async def _begin_oidc_flow(
    request: Request,
    db: Session,
    *,
    return_to: Optional[str],
    flow: str,
    user_id: Optional[int] = None,
) -> RedirectResponse:
    authorization_url = await _create_oidc_authorization_url(
        request,
        db,
        return_to=return_to,
        flow=flow,
        user_id=user_id,
    )
    return RedirectResponse(
        authorization_url,
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/oidc/login")
async def begin_oidc_login(
    request: Request,
    return_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return await _begin_oidc_flow(
        request,
        db,
        return_to=return_to,
        flow="login",
    )


@router.get("/oidc/link")
async def begin_oidc_account_link(
    request: Request,
    return_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.oidc_subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.oidcAlreadyLinked"},
        )
    return await _begin_oidc_flow(
        request,
        db,
        return_to=return_to,
        flow="link",
        user_id=current_user.id,
    )


@router.post("/oidc/link", response_model=OidcLinkStartResponse)
async def begin_oidc_account_link_api(
    payload: OidcLinkStartRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.oidc_subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.oidcAlreadyLinked"},
        )
    authorization_url = await _create_oidc_authorization_url(
        request,
        db,
        return_to=payload.return_to,
        flow="link",
        user_id=current_user.id,
    )
    return {"authorization_url": authorization_url}


@router.get("/oidc/callback")
async def complete_oidc_login(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    settings_row = get_system_oidc_settings(db)
    default_return_to = resolve_post_login_url(request, None)
    if settings_row is None or not settings_row.oidc_client_secret_encrypted:
        return RedirectResponse(
            encode_oidc_error_redirect(
                default_return_to,
                error_key="backend.errors.auth.oidcNotConfigured",
            ),
            status_code=status.HTTP_302_FOUND,
        )

    if error:
        return RedirectResponse(
            encode_oidc_error_redirect(
                default_return_to,
                error_key="backend.errors.auth.oidcAuthenticationCancelled",
            ),
            status_code=status.HTTP_302_FOUND,
        )

    verified_state = verify_oidc_state_token(state or "")
    if verified_state is None or not code:
        return RedirectResponse(
            encode_oidc_error_redirect(
                default_return_to,
                error_key="backend.errors.auth.invalidOrExpiredToken",
            ),
            status_code=status.HTTP_302_FOUND,
        )

    login_state = _consume_oidc_login_state(
        db,
        state_id=verified_state["state_id"],
        nonce=verified_state["nonce"],
    )
    if login_state is None:
        return RedirectResponse(
            encode_oidc_error_redirect(
                default_return_to,
                error_key="backend.errors.auth.invalidOrExpiredToken",
            ),
            status_code=status.HTTP_302_FOUND,
        )

    return_to = resolve_post_login_url(request, login_state.return_to)

    try:
        provider = await discover_oidc_configuration(
            request,
            settings_row,
            decrypt_secret(settings_row.oidc_client_secret_encrypted),
        )
        token_response = await exchange_code_for_tokens(
            provider, code=code, code_verifier=login_state.code_verifier
        )
        id_token = token_response.get("id_token")
        if not isinstance(id_token, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"key": "backend.errors.auth.oidcIdTokenInvalid"},
            )
        id_claims = verify_id_token(
            provider,
            id_token,
            nonce=verified_state["nonce"],
        )
        userinfo_claims = {}
        access_token = token_response.get("access_token")
        if isinstance(access_token, str) and provider.userinfo_endpoint:
            userinfo_claims = await fetch_userinfo(provider, access_token)
        identity = normalize_oidc_identity(
            merge_claim_sets(id_claims, userinfo_claims),
            provider,
        )
        identity["subject"] = id_claims["sub"]
        if not identity.get("username"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"key": "backend.errors.auth.oidcUsernameClaimMissing"},
            )
        if login_state.flow == "link":
            if login_state.user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
                )
            link_user = db.query(User).filter(User.id == login_state.user_id).first()
            if link_user is None or not link_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"key": "backend.errors.auth.inactiveUser"},
                )
            linked_user = _link_oidc_identity_to_user(
                db,
                user=link_user,
                identity=identity,
                id_token_hint=id_token,
            )
            _record_auth_event(
                db,
                event_type="oidc_account_linked",
                auth_source="oidc",
                success=True,
                username=linked_user.username,
                email=linked_user.email,
                actor_user_id=linked_user.id,
            )
            return RedirectResponse(
                _append_redirect_params(return_to, {"oidc_link": "complete"}),
                status_code=status.HTTP_302_FOUND,
            )
        _record_auth_event(
            db,
            event_type="oidc_callback_success",
            auth_source="oidc",
            success=True,
            username=identity.get("username"),
            email=identity.get("email"),
        )
        exchange_grant = _create_oidc_exchange_grant(
            db,
            identity=identity,
            id_token_hint=id_token,
        )
        redirect_response = RedirectResponse(
            encode_oidc_complete_redirect(return_to),
            status_code=status.HTTP_302_FOUND,
        )
        redirect_response.set_cookie(
            key=OIDC_EXCHANGE_COOKIE_NAME,
            value=exchange_grant.grant_id,
            httponly=True,
            samesite="lax",
            secure=build_external_base_url(request).startswith("https://"),
            max_age=OIDC_EXCHANGE_GRANT_EXPIRE_MINUTES * 60,
            path="/",
        )
        return redirect_response
    except HTTPException as exc:
        _record_auth_event(
            db,
            event_type="oidc_callback_failed",
            auth_source="oidc",
            success=False,
            detail=(
                exc.detail.get("key")
                if isinstance(exc.detail, dict)
                else str(exc.detail)
            ),
        )
        error_key = (
            exc.detail.get("key")
            if isinstance(exc.detail, dict)
            else "backend.errors.auth.oidcAuthenticationFailed"
        )
        return RedirectResponse(
            encode_oidc_error_redirect(return_to, error_key=error_key),
            status_code=status.HTTP_302_FOUND,
        )
    except Exception:
        _record_auth_event(
            db,
            event_type="oidc_callback_failed",
            auth_source="oidc",
            success=False,
            detail="backend.errors.auth.oidcAuthenticationFailed",
        )
        return RedirectResponse(
            encode_oidc_error_redirect(
                return_to,
                error_key="backend.errors.auth.oidcAuthenticationFailed",
            ),
            status_code=status.HTTP_302_FOUND,
        )


@router.post("/oidc/exchange", response_model=Token)
async def exchange_oidc_login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    settings_row = get_system_oidc_settings(db)
    if settings_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.auth.oidcNotConfigured"},
        )

    if not _is_same_origin_request(request):
        _record_auth_event(
            db,
            event_type="oidc_exchange_failed",
            auth_source="oidc",
            success=False,
            detail="backend.errors.auth.invalidAuthentication",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.auth.invalidAuthentication"},
        )

    grant_id = request.cookies.get(OIDC_EXCHANGE_COOKIE_NAME)
    if not grant_id:
        _record_auth_event(
            db,
            event_type="oidc_exchange_failed",
            auth_source="oidc",
            success=False,
            detail="backend.errors.auth.invalidOrExpiredToken",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
        )

    _prune_expired_oidc_artifacts(db)
    exchange_grant = _consume_oidc_exchange_grant(db, grant_id=grant_id)
    if exchange_grant is None:
        _record_auth_event(
            db,
            event_type="oidc_exchange_failed",
            auth_source="oidc",
            success=False,
            detail="backend.errors.auth.invalidOrExpiredToken",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
        )

    identity = _build_oidc_exchange_identity(exchange_grant)

    user = _provision_oidc_user(db, settings_row, identity)
    response.delete_cookie(OIDC_EXCHANGE_COOKIE_NAME, path="/")
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    _record_auth_event(
        db,
        event_type="oidc_login_succeeded",
        auth_source="oidc",
        success=True,
        username=user.username,
        email=user.email,
        actor_user_id=user.id,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "must_change_password": user.must_change_password,
    }


@router.post("/oidc/unlink")
@router.delete("/oidc/link")
async def unlink_oidc_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings_row = get_system_oidc_settings(db)
    if settings_row and settings_row.oidc_disable_local_auth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.oidcCannotUnlinkWhenLocalAuthDisabled"},
        )
    if not current_user.oidc_subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.oidcNotLinked"},
        )
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.localPasswordRequired"},
        )

    current_user.auth_source = "local"
    current_user.oidc_subject = None
    current_user.oidc_last_id_token_encrypted = None
    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    _record_auth_event(
        db,
        event_type="oidc_account_unlinked",
        auth_source="local",
        success=True,
        username=current_user.username,
        email=current_user.email,
        actor_user_id=current_user.id,
    )
    return {"message": "backend.success.auth.oidcUnlinked"}


@router.post("/login/totp", response_model=Token)
async def complete_login_with_totp(
    request: Request,
    payload: TotpLoginVerification,
    db: Session = Depends(get_db),
):
    _ensure_local_login_allowed(_get_auth_settings_row(db))
    client_ip = get_request_client_ip(request)
    username = verify_login_challenge_token(payload.login_challenge_token)
    totp_subject = (username or "unknown").strip().lower() or "unknown"
    enforce_auth_rate_limit(
        db,
        scope="totp_login",
        subject=totp_subject,
        client_ip=client_ip,
        policy=get_totp_login_policy(),
    )
    if not username:
        _record_rate_limit_failure(
            db,
            scope="totp_login",
            subject=totp_subject,
            client_ip=client_ip,
            policy=get_totp_login_policy(),
            event_type="totp_login_rate_limited",
            auth_source="local",
            detail="backend.errors.auth.invalidOrExpiredToken",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or not user.totp_enabled:
        _record_rate_limit_failure(
            db,
            scope="totp_login",
            subject=totp_subject,
            client_ip=client_ip,
            policy=get_totp_login_policy(),
            event_type="totp_login_rate_limited",
            auth_source="local",
            username=username,
            detail="backend.errors.auth.invalidTotpCode",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidTotpCode"},
        )

    if not _verify_totp_or_recovery_code(user, payload.code):
        db.commit()
        _record_rate_limit_failure(
            db,
            scope="totp_login",
            subject=totp_subject,
            client_ip=client_ip,
            policy=get_totp_login_policy(),
            event_type="totp_login_rate_limited",
            auth_source="local",
            username=username,
            email=user.email,
            detail="backend.errors.auth.invalidTotpCode",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidTotpCode"},
        )

    clear_auth_rate_limit(
        db,
        scope="totp_login",
        subject=totp_subject,
        client_ip=client_ip,
    )
    _clear_local_session_artifacts(user)
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    logger.info("User completed TOTP login successfully", username=user.username)
    _record_auth_event(
        db,
        event_type="totp_login_succeeded",
        auth_source="local",
        success=True,
        username=user.username,
        email=user.email,
        actor_user_id=user.id,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "must_change_password": user.must_change_password,
    }


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Logout user (client should discard token)"""
    logger.info("User logged out", username=current_user.username)
    settings_row = get_system_oidc_settings(db)
    logout_url: Optional[str] = None
    id_token_hint: Optional[str] = None

    if current_user.auth_source == "oidc" and current_user.oidc_last_id_token_encrypted:
        try:
            id_token_hint = decrypt_secret(current_user.oidc_last_id_token_encrypted)
        except Exception:
            logger.warning(
                "Failed to decrypt stored OIDC id_token for logout hint",
                username=current_user.username,
            )

    if (
        current_user.auth_source == "oidc"
        and id_token_hint
        and settings_row
        and settings_row.oidc_client_secret_encrypted
    ):
        try:
            provider = await discover_oidc_configuration(
                request,
                settings_row,
                decrypt_secret(settings_row.oidc_client_secret_encrypted),
            )
            logout_url = build_end_session_url(
                provider, request, id_token_hint=id_token_hint
            )
        except Exception:
            logger.warning(
                "Failed to build OIDC end-session URL",
                username=current_user.username,
            )

    if current_user.oidc_last_id_token_encrypted is not None:
        current_user.oidc_last_id_token_encrypted = None
        db.commit()

    _record_auth_event(
        db,
        event_type="logout",
        auth_source=current_user.auth_source or "local",
        success=True,
        username=current_user.username,
        email=current_user.email,
        actor_user_id=current_user.id,
    )

    return {
        "message": "backend.success.auth.loggedOut",
        "logout_url": logout_url,
    }


@router.get("/events", response_model=list[AuthEventResponse])
async def list_auth_events(
    limit: int = 50,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    safe_limit = max(1, min(limit, 200))
    events = (
        db.query(AuthEvent)
        .order_by(AuthEvent.created_at.desc(), AuthEvent.id.desc())
        .limit(safe_limit)
        .all()
    )
    logger.info("Auth events viewed", username=current_user.username, limit=safe_limit)
    return [
        {
            "id": event.id,
            "event_type": event.event_type,
            "auth_source": event.auth_source,
            "username": event.username,
            "email": event.email,
            "success": event.success,
            "detail": event.detail,
            "actor_user_id": event.actor_user_id,
            "created_at": event.created_at,
        }
        for event in events
    ]


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user information"""
    settings_row = db.query(SystemSettings).first()
    deployment_type = settings_row.deployment_type if settings_row else "individual"
    enterprise_name = settings_row.enterprise_name if settings_row else None
    return _build_user_response(current_user, deployment_type, enterprise_name)


@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: User = Depends(get_current_user)):
    """Refresh access token"""
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": current_user.username}, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.get("/totp", response_model=TotpStatusResponse)
async def get_totp_status(current_user: User = Depends(get_current_user)):
    return {
        "enabled": bool(current_user.totp_enabled),
        "recovery_codes_remaining": len(_get_recovery_code_hashes(current_user)),
    }


@router.post("/totp/setup", response_model=TotpSetupResponse)
async def begin_totp_setup(
    payload: TotpSetupRequest,
    current_user: User = Depends(get_current_user),
):
    _ensure_local_password_user(current_user)

    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.currentPasswordIncorrect"},
        )

    secret = generate_totp_secret()
    recovery_codes = generate_recovery_codes()
    return {
        "setup_token": create_totp_setup_token(
            current_user.username, secret, recovery_codes
        ),
        "secret": secret,
        "otpauth_uri": build_totp_uri(secret, current_user.username),
        "recovery_codes": recovery_codes,
    }


@router.post("/totp/enable", response_model=TotpEnableResponse)
async def enable_totp(
    payload: TotpEnableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_local_password_user(current_user)
    setup_data = verify_totp_setup_token(payload.setup_token)
    if not setup_data or setup_data["username"] != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
        )

    if not verify_totp_code(setup_data["secret"], payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.invalidTotpCode"},
        )

    current_user.totp_secret_encrypted = encrypt_secret(setup_data["secret"])
    current_user.totp_enabled = True
    current_user.totp_enabled_at = datetime.now(timezone.utc)
    _store_recovery_code_hashes(
        current_user,
        [hash_recovery_code(code) for code in setup_data["recovery_codes"]],
    )
    db.commit()

    logger.info("TOTP enabled", username=current_user.username)
    return {"enabled": True, "recovery_codes": setup_data["recovery_codes"]}


@router.post("/totp/disable")
async def disable_totp(
    payload: TotpDisableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_local_password_user(current_user)

    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.totpNotEnabled"},
        )

    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.currentPasswordIncorrect"},
        )

    if not _verify_totp_or_recovery_code(current_user, payload.code):
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.invalidTotpCode"},
        )

    current_user.totp_secret_encrypted = None
    current_user.totp_enabled = False
    current_user.totp_enabled_at = None
    current_user.totp_recovery_codes_hashes = None
    db.commit()

    logger.info("TOTP disabled", username=current_user.username)
    return {"message": "backend.success.auth.totpDisabled"}


@router.get("/passkeys", response_model=list[PasskeyCredentialResponse])
async def list_passkeys(current_user: User = Depends(get_current_user)):
    return [
        _serialize_passkey_credential(credential)
        for credential in current_user.passkeys
    ]


@router.post(
    "/passkeys/register/options", response_model=PasskeyBeginRegistrationResponse
)
async def begin_passkey_registration(
    payload: PasskeyBeginRegistrationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    _ensure_local_password_user(current_user)
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.currentPasswordIncorrect"},
        )

    webauthn = require_webauthn()
    origin, rp_id = resolve_origin_and_rp_id(request)
    existing_credentials = [
        webauthn["PublicKeyCredentialDescriptor"](
            id=webauthn["base64url_to_bytes"](credential.credential_id)
        )
        for credential in current_user.passkeys
    ]
    options = webauthn["generate_registration_options"](
        rp_id=rp_id,
        rp_name="Borg UI",
        user_id=str(current_user.id).encode("utf-8"),
        user_name=current_user.username,
        user_display_name=current_user.full_name or current_user.username,
        exclude_credentials=existing_credentials,
        authenticator_selection=webauthn["AuthenticatorSelectionCriteria"](
            resident_key=webauthn["ResidentKeyRequirement"].REQUIRED,
            user_verification=webauthn["UserVerificationRequirement"].PREFERRED,
        ),
    )
    options_json = webauthn["options_to_json"](options)
    options_dict = parse_options_json(options_json)
    ceremony_token = create_passkey_ceremony_token(
        username=current_user.username,
        challenge=options_dict["challenge"],
        purpose="passkey_register",
    )
    logger.info(
        "Passkey registration started", username=current_user.username, origin=origin
    )
    return {"ceremony_token": ceremony_token, "options": options_dict}


@router.post("/passkeys/register/verify", response_model=PasskeyCredentialResponse)
async def finish_passkey_registration(
    payload: PasskeyFinishRegistrationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_local_password_user(current_user)
    ceremony = verify_passkey_ceremony_token(payload.ceremony_token, "passkey_register")
    if not ceremony or ceremony["username"] != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
        )

    webauthn = require_webauthn()
    origin, rp_id = resolve_origin_and_rp_id(request)
    try:
        verification = webauthn["verify_registration_response"](
            credential=webauthn["parse_registration_credential_json"](
                json.dumps(payload.credential)
            ),
            expected_challenge=webauthn["base64url_to_bytes"](ceremony["challenge"]),
            expected_origin=origin,
            expected_rp_id=rp_id,
            require_user_verification=True,
        )
    except webauthn["InvalidRegistrationResponse"] as exc:
        _raise_passkey_verification_error(exc)

    credential_id = payload.credential.get("id")
    if not isinstance(credential_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.invalidPasskey"},
        )

    existing = (
        db.query(PasskeyCredential)
        .filter(PasskeyCredential.credential_id == credential_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.passkeyAlreadyRegistered"},
        )

    transports = None
    if isinstance(payload.credential.get("response"), dict):
        transports_value = payload.credential["response"].get("transports")
        if isinstance(transports_value, list):
            transports = json.dumps(transports_value)

    new_passkey = PasskeyCredential(
        user_id=current_user.id,
        name=(payload.name or "Passkey").strip() or "Passkey",
        credential_id=credential_id,
        public_key=base64.urlsafe_b64encode(verification.credential_public_key).decode(
            "ascii"
        ),
        sign_count=verification.sign_count,
        transports=transports,
        device_type=getattr(verification, "credential_device_type", None),
        backed_up=bool(getattr(verification, "credential_backed_up", False)),
    )
    db.add(new_passkey)
    db.commit()
    db.refresh(new_passkey)

    logger.info(
        "Passkey registered", username=current_user.username, passkey_id=new_passkey.id
    )
    return _serialize_passkey_credential(new_passkey)


@router.delete("/passkeys/{passkey_id}")
async def delete_passkey(
    passkey_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    passkey = (
        db.query(PasskeyCredential)
        .filter(
            PasskeyCredential.id == passkey_id,
            PasskeyCredential.user_id == current_user.id,
        )
        .first()
    )
    if not passkey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.auth.passkeyNotFound"},
        )

    db.delete(passkey)
    db.commit()
    logger.info(
        "Passkey deleted", username=current_user.username, passkey_id=passkey_id
    )
    return {"message": "backend.success.auth.passkeyDeleted"}


@router.post(
    "/passkeys/authenticate/options", response_model=PasskeyBeginAuthenticationResponse
)
async def begin_passkey_authentication(request: Request, db: Session = Depends(get_db)):
    _ensure_local_login_allowed(_get_auth_settings_row(db))
    webauthn = require_webauthn()
    origin, rp_id = resolve_origin_and_rp_id(request)
    options = webauthn["generate_authentication_options"](
        rp_id=rp_id,
        user_verification=webauthn["UserVerificationRequirement"].PREFERRED,
    )
    options_json = webauthn["options_to_json"](options)
    options_dict = parse_options_json(options_json)
    ceremony_token = create_passkey_ceremony_token(
        username="passkey-user",
        challenge=options_dict["challenge"],
        purpose="passkey_authenticate",
        expires_minutes=5,
    )
    logger.info("Passkey authentication started", origin=origin)
    return {"ceremony_token": ceremony_token, "options": options_dict}


@router.post("/passkeys/authenticate/verify", response_model=Token)
async def finish_passkey_authentication(
    payload: PasskeyFinishAuthenticationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _ensure_local_login_allowed(_get_auth_settings_row(db))
    client_ip = get_request_client_ip(request)
    raw_id = payload.credential.get("id")
    passkey_subject = raw_id.strip().lower() if isinstance(raw_id, str) else "unknown"
    enforce_auth_rate_limit(
        db,
        scope="passkey_login",
        subject=passkey_subject,
        client_ip=client_ip,
        policy=get_passkey_login_policy(),
    )
    ceremony = verify_passkey_ceremony_token(
        payload.ceremony_token, "passkey_authenticate"
    )
    if not ceremony:
        _record_rate_limit_failure(
            db,
            scope="passkey_login",
            subject=passkey_subject,
            client_ip=client_ip,
            policy=get_passkey_login_policy(),
            event_type="passkey_login_rate_limited",
            auth_source="local",
            detail="backend.errors.auth.invalidOrExpiredToken",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
        )

    webauthn = require_webauthn()
    origin, rp_id = resolve_origin_and_rp_id(request)
    passkey = (
        db.query(PasskeyCredential)
        .filter(PasskeyCredential.credential_id == raw_id)
        .first()
    )
    if not passkey or not passkey.user or not passkey.user.is_active:
        _record_rate_limit_failure(
            db,
            scope="passkey_login",
            subject=passkey_subject,
            client_ip=client_ip,
            policy=get_passkey_login_policy(),
            event_type="passkey_login_rate_limited",
            auth_source="local",
            detail="backend.errors.auth.invalidPasskey",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidPasskey"},
        )

    try:
        verification = webauthn["verify_authentication_response"](
            credential=webauthn["parse_authentication_credential_json"](
                json.dumps(payload.credential)
            ),
            expected_challenge=webauthn["base64url_to_bytes"](ceremony["challenge"]),
            expected_origin=origin,
            expected_rp_id=rp_id,
            credential_public_key=base64.urlsafe_b64decode(
                passkey.public_key.encode("ascii")
            ),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except webauthn["InvalidAuthenticationResponse"] as exc:
        _record_rate_limit_failure(
            db,
            scope="passkey_login",
            subject=passkey_subject,
            client_ip=client_ip,
            policy=get_passkey_login_policy(),
            event_type="passkey_login_rate_limited",
            auth_source="local",
            username=passkey.user.username,
            email=passkey.user.email,
            detail="backend.errors.auth.invalidPasskey",
        )
        _raise_passkey_verification_error(exc)

    clear_auth_rate_limit(
        db,
        scope="passkey_login",
        subject=passkey_subject,
        client_ip=client_ip,
    )
    _clear_local_session_artifacts(passkey.user)
    passkey.sign_count = verification.new_sign_count
    passkey.last_used_at = datetime.now(timezone.utc)
    passkey.user.last_login = datetime.now(timezone.utc)
    db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": passkey.user.username}, expires_delta=access_token_expires
    )
    logger.info("User logged in with passkey", username=passkey.user.username)
    _record_auth_event(
        db,
        event_type="passkey_login_succeeded",
        auth_source="local",
        success=True,
        username=passkey.user.username,
        email=passkey.user.email,
        actor_user_id=passkey.user.id,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "must_change_password": passkey.user.must_change_password,
    }


@router.get("/users", response_model=list[UserResponse])
async def get_users(
    current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """Get all users (admin only)"""
    users = db.query(User).all()
    return users


@router.post("/users", response_model=UserResponse)
async def create_new_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Create a new user (admin only)"""
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.usernameAlreadyRegistered"},
        )

    # Check if email already exists (if provided)
    if user_data.email:
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"key": "backend.errors.auth.emailAlreadyRegistered"},
            )

    resolved_role = _resolve_legacy_role(user_data.role, user_data.is_admin)

    user = create_user(
        db=db,
        username=user_data.username,
        password=user_data.password,
        email=user_data.email,
        role=resolved_role,
    )
    user.all_repositories_role = default_repository_role_for_global_role(resolved_role)
    db.commit()
    db.refresh(user)

    logger.info(
        "User created", username=user.username, created_by=current_user.username
    )
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Update user information (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.auth.userNotFound"},
        )

    # Update fields if provided
    if user_data.email is not None:
        # Check if email is already taken by another user
        if user_data.email != user.email:
            existing_email = (
                db.query(User)
                .filter(User.email == user_data.email, User.id != user_id)
                .first()
            )
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"key": "backend.errors.auth.emailAlreadyRegistered"},
                )
        user.email = user_data.email

    if user_data.is_active is not None:
        user.is_active = user_data.is_active

    next_role = _resolve_legacy_role(user_data.role, user_data.is_admin)
    if user_data.role is not None or user_data.is_admin is not None:
        user.role = next_role
        user.all_repositories_role = normalize_repository_role_for_global_role(
            user.role,
            user.all_repositories_role,
        )

    db.commit()
    db.refresh(user)

    logger.info("User updated", user_id=user_id, updated_by=current_user.username)
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Delete a user (admin only)"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.cannotDeleteSelf"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.auth.userNotFound"},
        )

    detach_user_delete_references(db, user.id)
    db.delete(user)
    db.commit()

    logger.info("User deleted", user_id=user_id, deleted_by=current_user.username)
    return {"message": "backend.success.auth.userDeleted"}


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change user password"""
    from app.core.security import verify_password

    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.currentPasswordIncorrect"},
        )

    # Update password
    success = update_user_password(db, current_user.id, password_data.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.auth.failedUpdatePassword"},
        )

    # Clear must_change_password flag after successful password change
    current_user.must_change_password = False
    db.commit()

    logger.info("Password changed", username=current_user.username)
    return {"message": "backend.success.auth.passwordChanged"}


@router.post("/password-setup/skip", response_model=PasswordSetupCompleteResponse)
async def skip_password_setup(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark the first-login password setup step as completed without changing the password."""
    current_user.must_change_password = False
    db.commit()

    logger.info("Password setup skipped", username=current_user.username)
    return {"must_change_password": False}
