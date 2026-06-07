from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_admin_user
from app.database.database import get_db
from app.database.models import RemoteBackendClient, User
from app.utils.datetime_utils import serialize_datetime

router = APIRouter(tags=["Remote Clients"])

RemoteBackendStatus = Literal["unknown", "checking", "online", "offline"]
RemoteBackendCompatibility = Literal["compatible", "incompatible", "unknown"]


class RemoteClientCreate(BaseModel):
    id: Optional[str] = Field(default=None, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    backend_url: str = Field(min_length=1, max_length=2048)


class RemoteClientUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    backend_url: str = Field(min_length=1, max_length=2048)


class RemoteClientHealthUpdate(BaseModel):
    status: RemoteBackendStatus
    checked_at: Optional[datetime] = None
    app_version: Optional[str] = None
    borg_version: Optional[str] = None
    borg2_version: Optional[str] = None
    error: Optional[str] = None
    compatibility: RemoteBackendCompatibility
    compatibility_message: Optional[str] = None


class RemoteClientHealthResponse(BaseModel):
    status: RemoteBackendStatus
    checked_at: Optional[str] = None
    app_version: Optional[str] = None
    borg_version: Optional[str] = None
    borg2_version: Optional[str] = None
    error: Optional[str] = None
    compatibility: RemoteBackendCompatibility
    compatibility_message: Optional[str] = None


class RemoteClientResponse(BaseModel):
    id: str
    name: str
    api_base_url: str
    web_base_url: str
    created_at: str
    updated_at: str
    health: RemoteClientHealthResponse


def _is_http_private_host(hostname: str) -> bool:
    normalized = hostname.lower()
    if (
        normalized == "localhost"
        or normalized == "::1"
        or normalized.endswith(".local")
        or normalized.startswith("127.")
    ):
        return True

    octets = normalized.split(".")
    if len(octets) != 4:
        return False

    try:
        first, second, *_ = [int(part) for part in octets]
    except ValueError:
        return False

    return (
        first == 10
        or (first == 192 and second == 168)
        or (first == 172 and 16 <= second <= 31)
    )


def _ensure_url_protocol(raw_input: str) -> str:
    if re.match(r"^[a-z][a-z\d+.-]*://", raw_input, re.IGNORECASE):
        return raw_input

    if raw_input.startswith("/"):
        raise ValueError("Enter a valid server URL.")

    host_part = re.split(r"[/?#]", raw_input, maxsplit=1)[0] or ""
    if host_part.startswith("["):
        closing = host_part.find("]")
        hostname = host_part[1:closing] if closing > 0 else host_part
    else:
        hostname = host_part.split(":", 1)[0]

    protocol = "http" if _is_http_private_host(hostname) else "https"
    return f"{protocol}://{raw_input}"


def normalize_remote_backend_url(backend_url: str) -> tuple[str, str]:
    trimmed = backend_url.strip()
    if not trimmed:
        raise ValueError("Enter a server URL.")

    parsed = urlsplit(_ensure_url_protocol(trimmed))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Server URL must use HTTP or HTTPS.")

    origin = f"{parsed.scheme}://{parsed.netloc}"
    clean_path = parsed.path.rstrip("/")
    api_path = clean_path if clean_path.endswith("/api") else f"{clean_path}/api"
    normalized_api_path = "/api" if api_path == "/api" else re.sub(r"/+", "/", api_path)
    web_path = (
        normalized_api_path[:-4]
        if normalized_api_path.endswith("/api")
        else normalized_api_path
    )

    return (
        f"{origin}{normalized_api_path}",
        f"{origin}{web_path}" if web_path else origin,
    )


def _remote_client_error(status_code: int, key: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"key": key})


def _get_client_or_404(db: Session, client_id: str) -> RemoteBackendClient:
    client = (
        db.query(RemoteBackendClient)
        .filter(RemoteBackendClient.id == client_id)
        .first()
    )
    if not client:
        raise _remote_client_error(
            status.HTTP_404_NOT_FOUND, "backend.errors.remoteClients.notFound"
        )
    return client


def _serialize_client(client: RemoteBackendClient) -> RemoteClientResponse:
    return RemoteClientResponse(
        id=client.id,
        name=client.name,
        api_base_url=client.api_base_url,
        web_base_url=client.web_base_url,
        created_at=serialize_datetime(client.created_at) or "",
        updated_at=serialize_datetime(client.updated_at) or "",
        health=RemoteClientHealthResponse(
            status=client.health_status,
            checked_at=serialize_datetime(client.health_checked_at),
            app_version=client.app_version,
            borg_version=client.borg_version,
            borg2_version=client.borg2_version,
            error=client.health_error,
            compatibility=client.compatibility,
            compatibility_message=client.compatibility_message,
        ),
    )


def _normalize_or_422(backend_url: str) -> tuple[str, str]:
    try:
        return normalize_remote_backend_url(backend_url)
    except ValueError as exc:
        raise _remote_client_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "backend.errors.remoteClients.invalidUrl",
        ) from exc


@router.get("", response_model=list[RemoteClientResponse])
async def list_remote_clients(
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    clients = (
        db.query(RemoteBackendClient).order_by(RemoteBackendClient.name.asc()).all()
    )
    return [_serialize_client(client) for client in clients]


@router.post(
    "",
    response_model=RemoteClientResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_remote_client(
    payload: RemoteClientCreate,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    client_id = (payload.id or str(uuid4())).strip()
    if not client_id:
        raise _remote_client_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "backend.errors.remoteClients.invalidId",
        )
    if (
        db.query(RemoteBackendClient)
        .filter(RemoteBackendClient.id == client_id)
        .first()
    ):
        raise _remote_client_error(
            status.HTTP_409_CONFLICT, "backend.errors.remoteClients.alreadyExists"
        )

    api_base_url, web_base_url = _normalize_or_422(payload.backend_url)
    timestamp = datetime.now(timezone.utc)
    client = RemoteBackendClient(
        id=client_id,
        name=payload.name.strip(),
        api_base_url=api_base_url,
        web_base_url=web_base_url,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return _serialize_client(client)


@router.put("/{client_id}", response_model=RemoteClientResponse)
async def update_remote_client(
    client_id: str,
    payload: RemoteClientUpdate,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    client = _get_client_or_404(db, client_id)
    api_base_url, web_base_url = _normalize_or_422(payload.backend_url)

    client.name = payload.name.strip()
    client.api_base_url = api_base_url
    client.web_base_url = web_base_url
    client.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(client)
    return _serialize_client(client)


@router.patch("/{client_id}/health", response_model=RemoteClientResponse)
async def update_remote_client_health(
    client_id: str,
    payload: RemoteClientHealthUpdate,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    client = _get_client_or_404(db, client_id)
    client.health_status = payload.status
    client.health_checked_at = payload.checked_at
    client.app_version = payload.app_version
    client.borg_version = payload.borg_version
    client.borg2_version = payload.borg2_version
    client.health_error = payload.error
    client.compatibility = payload.compatibility
    client.compatibility_message = payload.compatibility_message
    client.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(client)
    return _serialize_client(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_remote_client(
    client_id: str,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    client = _get_client_or_404(db, client_id)
    db.delete(client)
    db.commit()
