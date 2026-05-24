from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.authorization import authorize_request
from app.core.security import get_current_user
from app.database.database import get_db
from app.database.models import RcloneRemote, User
from app.services.rclone_repository_service import normalize_rclone_relative_path
from app.services.rclone_service import RcloneUnavailable, rclone_service

router = APIRouter(tags=["rclone"], dependencies=[Depends(authorize_request)])

RCLONE_REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class RcloneRemoteCreate(BaseModel):
    name: str
    provider: str
    config_source: str = "managed"
    config_path: str | None = None
    redacted_config: dict[str, Any] | None = None


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail={"key": "backend.errors.forbidden"})


def _normalize_remote_name(name: str) -> str:
    normalized = name.strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or ".." in normalized
        or "/" in normalized
        or "\\" in normalized
        or not RCLONE_REMOTE_NAME_RE.fullmatch(normalized)
    ):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidRemoteName"},
        )
    return normalized


def _managed_config_path(config_root: Path, remote_name: str) -> Path:
    root = config_root.resolve()
    config_path = (root / f"{remote_name}.conf").resolve()
    if config_path.parent != root:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidRemoteName"},
        )
    return config_path


def _serialize_remote(remote: RcloneRemote) -> dict[str, Any]:
    return {
        "id": remote.id,
        "name": remote.name,
        "provider": remote.provider,
        "config_source": remote.config_source,
        "config_path": remote.config_path,
        "redacted_config": remote.redacted_config,
        "last_tested_at": _iso(remote.last_tested_at),
        "last_test_status": remote.last_test_status,
        "last_error": remote.last_error,
        "created_at": _iso(remote.created_at),
        "updated_at": _iso(remote.updated_at),
    }


@router.get("/status")
async def get_status(current_user: User = Depends(get_current_user)):
    try:
        return await rclone_service.status()
    except RcloneUnavailable as exc:
        return {"available": False, "version": None, "error": str(exc)}


@router.get("/remotes")
async def list_remotes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    remotes = db.query(RcloneRemote).order_by(RcloneRemote.name).all()
    return {"remotes": [_serialize_remote(remote) for remote in remotes]}


@router.post("/remotes", status_code=status.HTTP_201_CREATED)
async def create_remote(
    payload: RcloneRemoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    remote_name = _normalize_remote_name(payload.name)
    existing = db.query(RcloneRemote).filter(RcloneRemote.name == remote_name).first()
    if existing:
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.rclone.remoteExists"}
        )

    provider = payload.provider.strip()
    remote = RcloneRemote(
        name=remote_name,
        provider=provider,
        config_source=payload.config_source,
        config_path=payload.config_path,
        redacted_config=payload.redacted_config,
    )
    db.add(remote)

    config_file: Path | None = None
    try:
        db.flush()
        if payload.config_source == "managed":
            config_root = Path(settings.rclone_config_root)
            config_root.mkdir(parents=True, exist_ok=True)
            config_file = _managed_config_path(config_root, remote_name)
            remote.config_path = str(config_file)
            config_body = payload.redacted_config or {"type": provider}
            config_file.write_text(json.dumps(config_body, indent=2), encoding="utf-8")
            config_file.chmod(0o600)
        db.commit()
    except Exception as exc:
        db.rollback()
        if config_file is not None:
            config_file.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.rclone.failedToCreateRemote",
                "message": str(exc) or exc.__class__.__name__,
            },
        ) from exc

    db.refresh(remote)
    return _serialize_remote(remote)


@router.post("/remotes/{remote_id}/test")
async def test_remote(
    remote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    remote = db.query(RcloneRemote).filter(RcloneRemote.id == remote_id).first()
    if not remote:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.rclone.remoteNotFound"}
        )
    result = await rclone_service.about(f"{remote.name}:")
    remote.last_tested_at = datetime.now(timezone.utc)
    if result["success"]:
        remote.last_test_status = "connected"
        remote.last_error = None
    else:
        remote.last_test_status = "failed"
        remote.last_error = result.get("stderr") or "rclone remote test failed"
    db.commit()
    db.refresh(remote)
    return {"status": remote.last_test_status, "remote": _serialize_remote(remote)}


@router.get("/remotes/{remote_id}/browse")
async def browse_remote(
    remote_id: int,
    path: str = "",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    remote = db.query(RcloneRemote).filter(RcloneRemote.id == remote_id).first()
    if not remote:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.rclone.remoteNotFound"}
        )
    relative_path = normalize_rclone_relative_path(path) if path else ""
    target = f"{remote.name}:{relative_path}" if relative_path else f"{remote.name}:"
    entries = await rclone_service.lsjson(target)
    return {
        "remote_id": remote.id,
        "path": relative_path,
        "entries": [
            {
                "name": item.get("Name"),
                "path": item.get("Path"),
                "is_dir": bool(item.get("IsDir")),
                "size": item.get("Size"),
                "modified": item.get("ModTime"),
            }
            for item in entries
        ],
    }


def _iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
