from datetime import datetime, timedelta
from typing import Optional
import jwt
from jwt.exceptions import PyJWTError as JWTError
import bcrypt
import hashlib
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
import structlog
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
import base64

from app.config import settings
from app.core.permissions import (
    GLOBAL_ROLE_RANK,
    REPOSITORY_ROLE_RANK,
    default_repository_role_for_global_role,
    normalize_repository_role_for_global_role,
)
from app.database.database import get_db
from app.database.models import Repository, User, UserRepositoryPermission

logger = structlog.get_logger()

ROLE_RANK = GLOBAL_ROLE_RANK
REPO_ROLE_RANK = REPOSITORY_ROLE_RANK
DEFAULT_PROXY_AUTH_HEADER = "X-Forwarded-User"
FALLBACK_PROXY_AUTH_HEADERS = (
    "X-Remote-User",
    "Remote-User",
    "X-authentik-username",
    DEFAULT_PROXY_AUTH_HEADER,
)

# JWT token security
security = HTTPBearer()

LOGIN_CHALLENGE_TOKEN_TYPE = "login_challenge"
TOTP_SETUP_TOKEN_TYPE = "totp_setup"
LOGIN_CHALLENGE_EXPIRE_MINUTES = 10
TOTP_SETUP_EXPIRE_MINUTES = 15


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire, "purpose": "access"})
    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode a JWT token and return its payload."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def verify_token(token: str) -> Optional[str]:
    """Verify and decode a JWT access token."""
    payload = decode_token(token)
    if payload is None:
        return None
    purpose = payload.get("purpose")
    if purpose not in (None, "access"):
        return None
    username: str = payload.get("sub")
    if username is None:
        return None
    return username


def create_login_challenge_token(username: str) -> str:
    """Create a short-lived token for completing TOTP login."""
    expire = datetime.utcnow() + timedelta(minutes=LOGIN_CHALLENGE_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "purpose": "totp_login",
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_login_challenge_token(token: str) -> Optional[str]:
    payload = decode_token(token)
    if payload is None or payload.get("purpose") != "totp_login":
        return None
    username = payload.get("sub")
    return username if isinstance(username, str) else None


def create_totp_setup_token(
    username: str, secret: str, recovery_codes: list[str]
) -> str:
    expire = datetime.utcnow() + timedelta(minutes=TOTP_SETUP_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "purpose": "totp_setup",
        "secret": secret,
        "recovery_codes": recovery_codes,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_totp_setup_token(token: str) -> Optional[dict]:
    payload = decode_token(token)
    if payload is None or payload.get("purpose") != "totp_setup":
        return None
    secret = payload.get("secret")
    recovery_codes = payload.get("recovery_codes")
    username = payload.get("sub")
    if (
        not isinstance(username, str)
        or not isinstance(secret, str)
        or not isinstance(recovery_codes, list)
        or not all(isinstance(code, str) for code in recovery_codes)
    ):
        return None
    return {
        "username": username,
        "secret": secret,
        "recovery_codes": recovery_codes,
    }


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Get the current authenticated user (supports both JWT and proxy auth)"""
    cached_user = getattr(request.state, "current_user", None)
    if cached_user is not None:
        return cached_user

    # Check if proxy authentication is enabled
    if settings.disable_authentication:
        # Use proxy authentication
        user = await get_current_user_proxy(request, db)
        request.state.current_user = user
        return user

    # Use JWT authentication
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Prefer X-Borg-Authorization so reverse proxies can still use Authorization.
    auth_header = request.headers.get("X-Borg-Authorization") or request.headers.get(
        "Authorization"
    )
    if not auth_header or not auth_header.startswith("Bearer "):
        raise credentials_exception

    token = auth_header.split(" ")[1]
    user = _get_active_user_from_token(token, db, credentials_exception)
    request.state.current_user = user
    return user


async def get_current_user_proxy(request: Request, db: Session) -> User:
    """
    Get the current authenticated user from reverse proxy headers.
    Used when DISABLE_AUTHENTICATION is enabled.

    Security: Ensure Borg UI is only accessible through your reverse proxy
    by binding to localhost (127.0.0.1) or using firewall rules.
    """

    username = _resolve_proxy_username(request)

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "key": "backend.errors.auth.proxyHeaderRequired",
                "params": {"header": settings.proxy_auth_header},
            },
        )

    # Normalize username
    username = username.strip().lower()

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty username in proxy header",
        )

    proxy_role = _resolve_proxy_global_role(request)
    proxy_all_repositories_role = _resolve_proxy_all_repositories_role(
        request, proxy_role
    )
    proxy_email = _resolve_proxy_email(request)
    proxy_full_name = _resolve_proxy_full_name(request)

    # Check if user exists
    user = db.query(User).filter(User.username == username).first()

    # Auto-create user if they don't exist
    if not user:
        logger.info("Auto-creating user from proxy authentication", username=username)

        user_email = proxy_email or f"{username}@proxy.local"
        if proxy_email and not _proxy_email_is_available(db, proxy_email):
            logger.warning(
                "Ignoring proxy email header because the value is already in use",
                username=username,
                email=proxy_email,
            )
            user_email = f"{username}@proxy.local"

        user = User(
            username=username,
            password_hash="",  # No password for proxy auth users
            email=user_email,
            full_name=proxy_full_name,
            role=proxy_role or "viewer",
            all_repositories_role=proxy_all_repositories_role
            or default_repository_role_for_global_role(proxy_role or "viewer"),
            is_active=True,
            must_change_password=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info("User auto-created successfully", username=username)

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled"
        )

    if proxy_role and user.role != proxy_role:
        user.role = proxy_role
        user.all_repositories_role = normalize_repository_role_for_global_role(
            proxy_role,
            proxy_all_repositories_role
            or default_repository_role_for_global_role(proxy_role),
        )
    elif (
        proxy_all_repositories_role is not None
        and user.role in ROLE_RANK
        and user.all_repositories_role != proxy_all_repositories_role
    ):
        user.all_repositories_role = normalize_repository_role_for_global_role(
            user.role, proxy_all_repositories_role
        )

    if proxy_email and user.email != proxy_email:
        if _proxy_email_is_available(db, proxy_email, current_user_id=user.id):
            user.email = proxy_email
        else:
            logger.warning(
                "Ignoring proxy email header because the value is already in use",
                username=username,
                email=proxy_email,
            )

    if proxy_full_name and user.full_name != proxy_full_name:
        user.full_name = proxy_full_name

    # Update last login timestamp
    from datetime import timezone

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    return user


def _resolve_proxy_username(request: Request) -> Optional[str]:
    configured_header = settings.proxy_auth_header.strip()
    username = request.headers.get(configured_header)
    if username:
        return username

    # If a custom identity header is configured, trust only that header.
    if configured_header.lower() != DEFAULT_PROXY_AUTH_HEADER.lower():
        return None

    for header in FALLBACK_PROXY_AUTH_HEADERS:
        if header.lower() == configured_header.lower():
            continue
        username = request.headers.get(header)
        if username:
            logger.debug("Found username in fallback proxy header", header=header)
            return username
    return None


def _get_optional_proxy_header(
    request: Request, header_name: Optional[str]
) -> Optional[str]:
    if not header_name:
        return None
    value = request.headers.get(header_name)
    if value is None:
        return None
    value = value.strip().lower()
    return value or None


def _get_optional_proxy_text_header(
    request: Request, header_name: Optional[str]
) -> Optional[str]:
    if not header_name:
        return None
    value = request.headers.get(header_name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _resolve_proxy_global_role(request: Request) -> Optional[str]:
    raw_role = _get_optional_proxy_header(request, settings.proxy_auth_role_header)
    if not raw_role:
        return None
    if raw_role not in ROLE_RANK:
        logger.warning(
            "Ignoring invalid proxy role header value",
            header=settings.proxy_auth_role_header,
            value=raw_role,
        )
        return None
    return raw_role


def _resolve_proxy_all_repositories_role(
    request: Request, proxy_role: Optional[str]
) -> Optional[str]:
    raw_role = _get_optional_proxy_header(
        request, settings.proxy_auth_all_repositories_role_header
    )
    if not raw_role:
        return (
            default_repository_role_for_global_role(proxy_role)
            if proxy_role is not None
            else None
        )

    target_global_role = proxy_role or "viewer"
    normalized_role = normalize_repository_role_for_global_role(
        target_global_role, raw_role
    )
    if normalized_role != raw_role:
        logger.warning(
            "Ignoring invalid proxy all-repositories role header value",
            header=settings.proxy_auth_all_repositories_role_header,
            value=raw_role,
            normalized=normalized_role,
        )
    return normalized_role


def _resolve_proxy_email(request: Request) -> Optional[str]:
    return _get_optional_proxy_header(request, settings.proxy_auth_email_header)


def _resolve_proxy_full_name(request: Request) -> Optional[str]:
    return _get_optional_proxy_text_header(
        request, settings.proxy_auth_full_name_header
    )


def _proxy_email_is_available(
    db: Session, email: Optional[str], current_user_id: Optional[int] = None
) -> bool:
    if not email:
        return True
    query = db.query(User).filter(User.email == email)
    if current_user_id is not None:
        query = query.filter(User.id != current_user_id)
    return query.first() is None


def _get_active_user_from_token(
    token: Optional[str], db: Session, invalid_exception: HTTPException
) -> User:
    """Resolve an active user from a JWT token."""
    if not token:
        raise invalid_exception

    username = verify_token(token)
    if username is None:
        raise invalid_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise invalid_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"key": "backend.errors.auth.inactiveUser"},
        )

    return user


async def get_current_download_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """Authenticate download endpoints for both JWT and proxy-auth modes."""
    if settings.disable_authentication:
        return await get_current_user_proxy(request, db)

    auth_header = request.headers.get("X-Borg-Authorization") or request.headers.get(
        "Authorization"
    )
    token: Optional[str] = None

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    else:
        token = request.query_params.get("token")

    invalid_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"key": "backend.errors.auth.invalidOrExpiredToken"},
    )
    return _get_active_user_from_token(token, db, invalid_exception)


async def get_current_active_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """Get the current active user"""
    current_user = await get_current_user(request, db)
    if not current_user.is_active:
        raise HTTPException(
            status_code=400, detail={"key": "backend.errors.auth.inactiveUser"}
        )
    return current_user


async def get_current_admin_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """Get the current admin user"""
    current_user = await get_current_user(request, db)
    require_any_role(current_user, "admin")
    return current_user


def require_any_role(
    user: User,
    *allowed_roles: str,
    detail_key: str = "backend.errors.auth.notEnoughPermissions",
) -> User:
    """Raise HTTP 403 unless the user has one of the allowed roles."""
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"key": detail_key}
        )
    return user


def require_role_dependency(
    *allowed_roles: str, detail_key: str = "backend.errors.auth.notEnoughPermissions"
):
    """Create a FastAPI dependency that resolves the user and enforces role membership."""

    async def dependency(request: Request, db: Session = Depends(get_db)) -> User:
        current_user = await get_current_user(request, db)
        return require_any_role(current_user, *allowed_roles, detail_key=detail_key)

    return dependency


def check_repo_access(db: Session, user: User, repo, required_role: str) -> None:
    """Raise HTTP 403 if user lacks required_role on the given repository.

    Admin users always pass. For operator/viewer, checks UserRepositoryPermission.
    required_role is 'viewer' or 'operator'.
    """
    if user.role == "admin":
        return

    effective_role = getattr(user, "all_repositories_role", None)
    perm = (
        db.query(UserRepositoryPermission)
        .filter_by(user_id=user.id, repository_id=repo.id)
        .first()
    )
    if perm and (
        effective_role is None
        or REPO_ROLE_RANK.get(perm.role, 0) > REPO_ROLE_RANK.get(effective_role, 0)
    ):
        effective_role = perm.role

    if effective_role is None or REPO_ROLE_RANK.get(
        effective_role, 0
    ) < REPO_ROLE_RANK.get(required_role, 0):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.auth.notEnoughPermissions"},
        )


def get_repository_by_path_or_404(
    db: Session,
    repository_path: Optional[str],
    *,
    detail_key: str = "backend.errors.restore.repositoryNotFound",
) -> Repository:
    """Resolve a repository by ID or path or raise a standardized 404."""
    repo = None
    if repository_path:
        try:
            repo_id = int(repository_path)
        except (TypeError, ValueError):
            repo_id = None

        if repo_id is not None:
            repo = db.query(Repository).filter(Repository.id == repo_id).first()

        if repo is None:
            repo = (
                db.query(Repository).filter(Repository.path == repository_path).first()
            )
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": detail_key},
        )
    return repo


def require_repository_access_by_path(
    db: Session,
    user: User,
    repository_path: Optional[str],
    required_role: str,
    *,
    detail_key: str = "backend.errors.restore.repositoryNotFound",
) -> Repository:
    """Resolve a repository by path and enforce repo-scoped access."""
    repo = get_repository_by_path_or_404(db, repository_path, detail_key=detail_key)
    check_repo_access(db, user, repo, required_role)
    return repo


async def authenticate_user(
    db: Session, username: str, password: str
) -> Optional[User]:
    """Authenticate a user with username and password"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def create_first_user():
    """Create the first admin user if no users exist"""
    db = next(get_db())
    try:
        # Check if admin user already exists
        admin_user = db.query(User).filter(User.username == "admin").first()
        if admin_user:
            logger.info("Admin user already exists", username="admin")
            return

        # Check if any users exist
        user_count = db.query(User).count()
        if user_count == 0:
            # Create default admin user
            # Use environment variable if set, otherwise use default
            import os

            default_password = os.getenv("INITIAL_ADMIN_PASSWORD", "admin123")
            hashed_password = get_password_hash(default_password)

            admin_user = User(
                username="admin",
                password_hash=hashed_password,
                email="admin@borg.local",
                is_active=True,
                role="admin",
                must_change_password=True,  # Force password change on first login
            )

            db.add(admin_user)
            db.commit()

            logger.info("Created default admin user", username="admin")
            if default_password == "admin123":
                logger.warning(
                    "⚠️  SECURITY: Using default admin password 'admin123'. "
                    "CHANGE IT IMMEDIATELY or set INITIAL_ADMIN_PASSWORD env var!",
                    username="admin",
                )
            else:
                logger.info(
                    "Using custom initial admin password from INITIAL_ADMIN_PASSWORD env var",
                    username="admin",
                )
    except Exception as e:
        # Check if it's a duplicate key error
        if "UNIQUE constraint failed" in str(e) or "duplicate key" in str(e).lower():
            logger.info(
                "Admin user already exists (caught constraint error)", username="admin"
            )
        else:
            logger.error("Failed to create first user", error=str(e))
        db.rollback()
    finally:
        db.close()


def create_user(
    db: Session, username: str, password: str, email: str = None, role: str = "viewer"
) -> User:
    """Create a new user"""
    hashed_password = get_password_hash(password)
    user = User(
        username=username,
        password_hash=hashed_password,
        email=email,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_password(db: Session, user_id: int, new_password: str) -> bool:
    """Update a user's password"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False

    user.password_hash = get_password_hash(new_password)
    db.commit()
    return True


# Secret encryption/decryption utilities
# Uses Fernet symmetric encryption (same mechanism as SSH keys)


def _build_fernet_from_secret(secret: str) -> Fernet:
    """Build a stable Fernet instance from any SECRET_KEY length."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _build_legacy_fernet_from_secret(secret: str) -> Optional[Fernet]:
    """Backward-compatible Fernet derivation used by older releases."""
    encryption_key = secret.encode("utf-8")[:32]
    if len(encryption_key) != 32:
        return None
    return Fernet(base64.urlsafe_b64encode(encryption_key))


def get_secret_fernet() -> Fernet:
    """Return the current Fernet cipher for app secret encryption."""
    return _build_fernet_from_secret(settings.secret_key)


def encrypt_secret(value: str) -> str:
    """
    Encrypt a secret value (e.g., password, token, API key).

    Args:
        value: Plain text secret to encrypt

    Returns:
        Base64-encoded encrypted string

    Raises:
        ValueError: If value is empty or None
    """
    if not value:
        raise ValueError("Cannot encrypt empty or None value")

    cipher = get_secret_fernet()
    encrypted_value = cipher.encrypt(value.encode()).decode()
    return encrypted_value


def decrypt_secret(encrypted_value: str) -> str:
    """
    Decrypt a secret value that was encrypted with encrypt_secret().

    Args:
        encrypted_value: Base64-encoded encrypted string

    Returns:
        Decrypted plain text string

    Raises:
        ValueError: If encrypted_value is empty or None
        cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data)
    """
    if not encrypted_value:
        raise ValueError("Cannot decrypt empty or None value")

    cipher = get_secret_fernet()
    try:
        decrypted_value = cipher.decrypt(encrypted_value.encode()).decode()
        return decrypted_value
    except InvalidToken:
        legacy_cipher = _build_legacy_fernet_from_secret(settings.secret_key)
        if legacy_cipher is None:
            raise
        decrypted_value = legacy_cipher.decrypt(encrypted_value.encode()).decode()
        return decrypted_value
