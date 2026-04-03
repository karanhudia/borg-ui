from datetime import timedelta, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog

from app.database.database import get_db
from app.database.models import User
from app.core.security import (
    authenticate_user, create_access_token, get_current_user,
    get_current_admin_user, create_user, update_user_password
)
from app.core.permissions import get_global_permissions_for_role, serialize_authorization_model
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()

# Pydantic models for request/response
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    must_change_password: bool = False


class AuthConfig(BaseModel):
    proxy_auth_enabled: bool
    authentication_required: bool


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    is_admin: bool = False

class UserUpdate(BaseModel):
    email: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    deployment_type: Optional[str] = None
    enterprise_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    role: str
    must_change_password: bool = False
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


def _build_user_response(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": getattr(user, "full_name", None),
        "deployment_type": getattr(user, "deployment_type", None),
        "enterprise_name": getattr(user, "enterprise_name", None),
        "email": getattr(user, "email", None),
        "is_active": user.is_active,
        "role": user.role,
        "must_change_password": getattr(user, "must_change_password", False),
        "last_login": getattr(user, "last_login", None),
        "created_at": user.created_at,
        "global_permissions": get_global_permissions_for_role(user.role),
    }


@router.get("/config", response_model=AuthConfig)
async def get_auth_config():
    """Get authentication configuration for frontend"""
    return {
        "proxy_auth_enabled": settings.disable_authentication,
        "authentication_required": not settings.disable_authentication
    }


@router.get("/authorization-model", response_model=AuthorizationModelResponse)
async def get_authorization_model():
    """Expose the backend authorization model as the source of truth for the frontend."""
    return serialize_authorization_model()


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
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
            detail={"key": "backend.errors.auth.inactiveUser"}
        )

    # Update last login timestamp
    from datetime import timezone
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
        "must_change_password": user.must_change_password
    }

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Logout user (client should discard token)"""
    logger.info("User logged out", username=current_user.username)
    return {"message": "backend.success.auth.loggedOut"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return _build_user_response(current_user)

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
        "expires_in": settings.access_token_expire_minutes * 60
    }

@router.get("/users", response_model=list[UserResponse])
async def get_users(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get all users (admin only)"""
    users = db.query(User).all()
    return users

@router.post("/users", response_model=UserResponse)
async def create_new_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new user (admin only)"""
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.usernameAlreadyRegistered"}
        )

    # Check if email already exists (if provided)
    if user_data.email:
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"key": "backend.errors.auth.emailAlreadyRegistered"}
            )
    
    user = create_user(
        db=db,
        username=user_data.username,
        password=user_data.password,
        email=user_data.email,
        is_admin=user_data.is_admin
    )
    
    logger.info("User created", username=user.username, created_by=current_user.username)
    return user

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Update user information (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.auth.userNotFound"}
        )

    # Update fields if provided
    if user_data.email is not None:
        # Check if email is already taken by another user
        if user_data.email != user.email:
            existing_email = db.query(User).filter(
                User.email == user_data.email,
                User.id != user_id
            ).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"key": "backend.errors.auth.emailAlreadyRegistered"}
                )
        user.email = user_data.email
    
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    
    if user_data.is_admin is not None:
        user.is_admin = user_data.is_admin
    
    db.commit()
    db.refresh(user)
    
    logger.info("User updated", user_id=user_id, updated_by=current_user.username)
    return user

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Delete a user (admin only)"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.cannotDeleteSelf"}
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.auth.userNotFound"}
        )
    
    db.delete(user)
    db.commit()
    
    logger.info("User deleted", user_id=user_id, deleted_by=current_user.username)
    return {"message": "backend.success.auth.userDeleted"}

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    from app.core.security import verify_password
    
    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.auth.currentPasswordIncorrect"}
        )

    # Update password
    success = update_user_password(db, current_user.id, password_data.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.auth.failedUpdatePassword"}
        )

    # Clear must_change_password flag after successful password change
    current_user.must_change_password = False
    db.commit()

    logger.info("Password changed", username=current_user.username)
    return {"message": "backend.success.auth.passwordChanged"}
