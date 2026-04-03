from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog

from app.database.database import get_db
from app.database.models import User, Repository, UserRepositoryPermission
from app.core.permissions import (
    REPOSITORY_ROLES,
    is_repository_role_assignable_to_global_role,
)
from app.core.security import get_current_user, get_current_admin_user

logger = structlog.get_logger()
router = APIRouter(tags=["permissions"])

VALID_REPOSITORY_ROLES = {str(role["id"]) for role in REPOSITORY_ROLES}


class PermissionCreate(BaseModel):
    repository_id: int
    role: str


class PermissionUpdate(BaseModel):
    role: str


class PermissionResponse(BaseModel):
    id: int
    user_id: int
    repository_id: int
    repository_name: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class PermissionScopeResponse(BaseModel):
    all_repositories_role: Optional[str]


class PermissionScopeUpdate(BaseModel):
    all_repositories_role: Optional[str] = None


def _validate_role(role: str) -> None:
    if role not in VALID_REPOSITORY_ROLES:
        raise HTTPException(
            status_code=422,
            detail={
                "key": "backend.errors.permissions.invalidRole",
                "params": {"roles": ", ".join(sorted(VALID_REPOSITORY_ROLES))},
            },
        )


def _validate_optional_role(role: Optional[str]) -> None:
    if role is None:
        return
    _validate_role(role)


def _resolve_permission_scope_role(user: User, role: Optional[str]) -> Optional[str]:
    _validate_optional_role(role)
    if not is_repository_role_assignable_to_global_role(user.role, role):
        raise HTTPException(
            status_code=422,
            detail={
                "key": "backend.errors.permissions.invalidRole",
                "params": {"roles": ", ".join(sorted(VALID_REPOSITORY_ROLES))},
            },
        )
    return role


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.settings.userNotFound"})
    return user


def _get_repository_or_404(db: Session, repository_id: int) -> Repository:
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(
            status_code=404,
            detail={"key": "backend.errors.repo.repositoryNotFound"},
        )
    return repo


def _list_permission_rows(db: Session, user_id: int) -> list[PermissionResponse]:
    rows = (
        db.query(
            UserRepositoryPermission.id,
            UserRepositoryPermission.user_id,
            UserRepositoryPermission.repository_id,
            UserRepositoryPermission.role,
            UserRepositoryPermission.created_at,
            Repository.name.label("repository_name"),
        )
        .join(Repository, Repository.id == UserRepositoryPermission.repository_id, isouter=True)
        .filter(UserRepositoryPermission.user_id == user_id)
        .all()
    )
    return [
        PermissionResponse(
            id=row.id,
            user_id=row.user_id,
            repository_id=row.repository_id,
            repository_name=row.repository_name or "Unknown",
            role=row.role,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _build_permission_response(
    permission: UserRepositoryPermission,
    repository_name: str,
) -> PermissionResponse:
    return PermissionResponse(
        id=permission.id,
        user_id=permission.user_id,
        repository_id=permission.repository_id,
        repository_name=repository_name,
        role=permission.role,
        created_at=permission.created_at,
    )


@router.get("/settings/permissions/me", response_model=list[PermissionResponse])
async def get_my_permissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _list_permission_rows(db, current_user.id)


@router.get("/settings/permissions/me/scope", response_model=PermissionScopeResponse)
async def get_my_permission_scope(
    current_user: User = Depends(get_current_user),
):
    return PermissionScopeResponse(all_repositories_role=current_user.all_repositories_role)


@router.get(
    "/settings/users/{user_id}/permissions",
    response_model=list[PermissionResponse],
    dependencies=[Depends(get_current_admin_user)],
)
async def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
):
    _get_user_or_404(db, user_id)
    return _list_permission_rows(db, user_id)


@router.get(
    "/settings/users/{user_id}/permissions/scope",
    response_model=PermissionScopeResponse,
    dependencies=[Depends(get_current_admin_user)],
)
async def get_user_permission_scope(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    return PermissionScopeResponse(all_repositories_role=user.all_repositories_role)


@router.put(
    "/settings/users/{user_id}/permissions/scope",
    response_model=PermissionScopeResponse,
    dependencies=[Depends(get_current_admin_user)],
)
async def update_user_permission_scope(
    user_id: int,
    payload: PermissionScopeUpdate,
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    user.all_repositories_role = _resolve_permission_scope_role(
        user,
        payload.all_repositories_role,
    )
    db.commit()
    db.refresh(user)
    return PermissionScopeResponse(all_repositories_role=user.all_repositories_role)


@router.post(
    "/settings/users/{user_id}/permissions",
    response_model=PermissionResponse,
    status_code=201,
    dependencies=[Depends(get_current_admin_user)],
)
async def assign_permission(
    user_id: int,
    payload: PermissionCreate,
    db: Session = Depends(get_db),
):
    _validate_role(payload.role)

    _get_user_or_404(db, user_id)
    repo = _get_repository_or_404(db, payload.repository_id)

    existing = (
        db.query(UserRepositoryPermission)
        .filter_by(user_id=user_id, repository_id=payload.repository_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.permissions.alreadyExists"},
        )

    perm = UserRepositoryPermission(
        user_id=user_id,
        repository_id=payload.repository_id,
        role=payload.role,
        created_at=datetime.now(timezone.utc),
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)

    return _build_permission_response(perm, repo.name)


@router.put(
    "/settings/users/{user_id}/permissions/{repo_id}",
    response_model=PermissionResponse,
    dependencies=[Depends(get_current_admin_user)],
)
async def update_permission(
    user_id: int,
    repo_id: int,
    payload: PermissionUpdate,
    db: Session = Depends(get_db),
):
    _validate_role(payload.role)

    _get_user_or_404(db, user_id)
    perm = (
        db.query(UserRepositoryPermission)
        .filter_by(user_id=user_id, repository_id=repo_id)
        .first()
    )
    if not perm:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.permissions.notFound"})

    repo = _get_repository_or_404(db, repo_id)
    perm.role = payload.role
    db.commit()
    db.refresh(perm)

    return _build_permission_response(perm, repo.name)


@router.delete(
    "/settings/users/{user_id}/permissions/{repo_id}",
    status_code=204,
    dependencies=[Depends(get_current_admin_user)],
)
async def remove_permission(
    user_id: int,
    repo_id: int,
    db: Session = Depends(get_db),
):
    _get_user_or_404(db, user_id)
    perm = (
        db.query(UserRepositoryPermission)
        .filter_by(user_id=user_id, repository_id=repo_id)
        .first()
    )
    if not perm:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.permissions.notFound"})

    db.delete(perm)
    db.commit()
