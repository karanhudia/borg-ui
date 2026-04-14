import base64
from datetime import timedelta, datetime, timezone
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog

from app.database.database import get_db
from app.database.models import PasskeyCredential, User, SystemSettings
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

logger = structlog.get_logger()
router = APIRouter()


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
    authentication_required: bool
    proxy_auth_header: Optional[str] = None


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
    if settings.disable_authentication or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.localPasswordRequired"},
        )


def _serialize_passkey_credential(credential: PasskeyCredential) -> dict:
    return {
        "id": credential.id,
        "name": credential.name,
        "created_at": credential.created_at,
        "last_used_at": credential.last_used_at,
    }


@router.get("/config", response_model=AuthConfig)
async def get_auth_config():
    """Get authentication configuration for frontend"""
    return {
        "proxy_auth_enabled": settings.disable_authentication,
        "authentication_required": not settings.disable_authentication,
        "proxy_auth_header": (
            settings.proxy_auth_header if settings.disable_authentication else None
        ),
    }


@router.get("/authorization-model", response_model=AuthorizationModelResponse)
async def get_authorization_model():
    """Expose the backend authorization model as the source of truth for the frontend."""
    return serialize_authorization_model()


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """Authenticate user and return access token"""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        logger.warning("Failed login attempt", username=form_data.username)
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

    if user.totp_enabled:
        challenge_token = create_login_challenge_token(user.username)
        logger.info("Password verified, awaiting TOTP", username=user.username)
        return {
            "totp_required": True,
            "login_challenge_token": challenge_token,
            "must_change_password": user.must_change_password,
        }

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    logger.info("User logged in successfully", username=user.username)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "must_change_password": user.must_change_password,
    }


@router.post("/login/totp", response_model=Token)
async def complete_login_with_totp(
    payload: TotpLoginVerification, db: Session = Depends(get_db)
):
    username = verify_login_challenge_token(payload.login_challenge_token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidTotpCode"},
        )

    if not _verify_totp_or_recovery_code(user, payload.code):
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidTotpCode"},
        )

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    logger.info("User completed TOTP login successfully", username=user.username)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "must_change_password": user.must_change_password,
    }


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Logout user (client should discard token)"""
    logger.info("User logged out", username=current_user.username)
    return {"message": "backend.success.auth.loggedOut"}


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
    verification = webauthn["verify_registration_response"](
        credential=webauthn["parse_registration_credential_json"](
            json.dumps(payload.credential)
        ),
        expected_challenge=webauthn["base64url_to_bytes"](ceremony["challenge"]),
        expected_origin=origin,
        expected_rp_id=rp_id,
        require_user_verification=True,
    )

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
async def begin_passkey_authentication(request: Request):
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
    ceremony = verify_passkey_ceremony_token(
        payload.ceremony_token, "passkey_authenticate"
    )
    if not ceremony:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
        )

    webauthn = require_webauthn()
    origin, rp_id = resolve_origin_and_rp_id(request)
    raw_id = payload.credential.get("id")
    passkey = (
        db.query(PasskeyCredential)
        .filter(PasskeyCredential.credential_id == raw_id)
        .first()
    )
    if not passkey or not passkey.user or not passkey.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.invalidPasskey"},
        )

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

    passkey.sign_count = verification.new_sign_count
    passkey.last_used_at = datetime.now(timezone.utc)
    passkey.user.last_login = datetime.now(timezone.utc)
    db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": passkey.user.username}, expires_delta=access_token_expires
    )
    logger.info("User logged in with passkey", username=passkey.user.username)
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
