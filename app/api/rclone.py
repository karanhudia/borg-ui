from __future__ import annotations

import configparser
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


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip()
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidProvider"},
        )
    return normalized


def _managed_config_path(config_root: Path) -> Path:
    root = config_root.resolve()
    config_path = (root / "rclone.conf").resolve()
    if config_path.parent != root:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidRemoteName"},
        )
    return config_path


def _new_config_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    return parser


def _load_config(config_path: Path) -> configparser.ConfigParser:
    parser = _new_config_parser()
    if config_path.exists():
        parser.read(config_path, encoding="utf-8")
    return parser


def _stringify_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _managed_config_values(
    provider: str, redacted_config: dict[str, Any] | None
) -> dict[str, str]:
    values = dict(redacted_config or {})
    values["type"] = str(values.get("type") or provider).strip()
    return {
        str(key): _stringify_config_value(value)
        for key, value in values.items()
        if value is not None and str(key).strip()
    }


def _write_config_file(config_path: Path, parser: configparser.ConfigParser) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = config_path.with_name(f".{config_path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    temp_path.chmod(0o600)
    temp_path.replace(config_path)
    config_path.chmod(0o600)


def _write_managed_remote_config(
    config_path: Path,
    *,
    remote_name: str,
    provider: str,
    redacted_config: dict[str, Any] | None,
) -> None:
    parser = _load_config(config_path)
    if not parser.has_section(remote_name):
        parser.add_section(remote_name)
    for key, value in _managed_config_values(provider, redacted_config).items():
        parser.set(remote_name, key, value)
    _write_config_file(config_path, parser)


def _remove_managed_remote_config(config_path: Path, remote_name: str) -> None:
    parser = _load_config(config_path)
    if not parser.remove_section(remote_name):
        return
    if parser.sections():
        _write_config_file(config_path, parser)
    else:
        config_path.unlink(missing_ok=True)


def _serialize_remote(remote: RcloneRemote) -> dict[str, Any]:
    return {
        "id": remote.id,
        "name": remote.name,
        "provider": remote.provider,
        "usage_count": sum(
            1 for storage in remote.storages if storage.backend == "rclone"
        ),
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

    provider = _normalize_provider(payload.provider)
    remote = RcloneRemote(
        name=remote_name,
        provider=provider,
        config_source=payload.config_source,
        config_path=payload.config_path,
        redacted_config=payload.redacted_config,
    )
    db.add(remote)

    config_file: Path | None = None
    wrote_config = False
    try:
        db.flush()
        if payload.config_source == "managed":
            config_root = Path(settings.rclone_config_root)
            config_root.mkdir(parents=True, exist_ok=True)
            config_file = _managed_config_path(config_root)
            remote.config_path = str(config_file)
            _write_managed_remote_config(
                config_file,
                remote_name=remote_name,
                provider=provider,
                redacted_config=payload.redacted_config,
            )
            wrote_config = True
        db.commit()
    except Exception as exc:
        db.rollback()
        if config_file is not None and wrote_config:
            _remove_managed_remote_config(config_file, remote_name)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.rclone.failedToCreateRemote"},
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
