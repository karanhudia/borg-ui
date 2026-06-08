from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_runtime_app_version
from app.core.security import (
    get_current_admin_user,
    get_current_download_user,
    require_any_role,
)
from app.database.database import get_db
from app.database.models import RemoteBackendClient, User
from app.utils.datetime_utils import serialize_datetime

router = APIRouter(tags=["Remote Clients"])

RemoteBackendStatus = Literal["unknown", "checking", "online", "offline"]
RemoteBackendCompatibility = Literal["compatible", "incompatible", "unknown"]
REMOTE_CLIENT_CHECK_TIMEOUT_SECONDS = 10.0
REMOTE_CLIENT_PROXY_TIMEOUT_SECONDS = 300.0
REMOTE_TARGET_AUTH_HEADER = "X-Borg-Remote-Authorization"
REMOTE_TARGET_AUTH_QUERY_PARAM = "target_token"
AUTH_TOKEN_HEADER = "X-Borg-Authorization"
FORWARDED_REQUEST_HEADERS = {"accept", "content-type"}
FORWARDED_RESPONSE_HEADERS = {
    "cache-control",
    "content-disposition",
    "content-type",
    "etag",
    "last-modified",
}


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


def _parse_major_version(version: Optional[str]) -> Optional[int]:
    if not version:
        return None
    match = re.match(r"^v?(\d+)(?:\.|$)", version, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _compare_backend_versions(
    frontend_version: Optional[str], backend_version: Optional[str]
) -> tuple[RemoteBackendCompatibility, str]:
    if not backend_version:
        return "unknown", "Remote client server version is unavailable."

    frontend_major = _parse_major_version(frontend_version)
    backend_major = _parse_major_version(backend_version)
    if frontend_major is None or backend_major is None:
        return "unknown", "Remote client server version could not be compared."

    if frontend_major != backend_major:
        return (
            "incompatible",
            f"Borg UI {backend_version} uses a different major version than this frontend.",
        )

    return "compatible", f"Borg UI {backend_version} is compatible with this frontend."


def _extract_remote_target_auth(request: Request) -> Optional[str]:
    header_value = request.headers.get(REMOTE_TARGET_AUTH_HEADER)
    if header_value:
        return header_value

    token = request.query_params.get(REMOTE_TARGET_AUTH_QUERY_PARAM)
    if not token:
        return None
    return token if token.startswith("Bearer ") else f"Bearer {token}"


def _remote_check_error_message(error: Exception) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "Remote client health check timed out."
    return str(error) or "Remote client server could not be reached."


def _apply_client_health(
    client: RemoteBackendClient,
    *,
    status_value: RemoteBackendStatus,
    checked_at: datetime,
    app_version: Optional[str] = None,
    borg_version: Optional[str] = None,
    borg2_version: Optional[str] = None,
    error: Optional[str] = None,
    compatibility: RemoteBackendCompatibility,
    compatibility_message: Optional[str] = None,
) -> None:
    client.health_status = status_value
    client.health_checked_at = checked_at
    client.app_version = app_version
    client.borg_version = borg_version
    client.borg2_version = borg2_version
    client.health_error = error
    client.compatibility = compatibility
    client.compatibility_message = compatibility_message
    client.updated_at = datetime.now(timezone.utc)


async def _fetch_remote_system_info(
    client: RemoteBackendClient, remote_auth: Optional[str]
) -> dict:
    async with httpx.AsyncClient(timeout=REMOTE_CLIENT_CHECK_TIMEOUT_SECONDS) as http:
        health_response = await http.get(
            f"{client.web_base_url.rstrip('/')}/health",
            headers={"Accept": "application/json"},
        )
        if health_response.status_code >= 400:
            raise RuntimeError(
                f"Health check failed with HTTP {health_response.status_code}."
            )

        headers = {"Accept": "application/json"}
        if remote_auth:
            headers[AUTH_TOKEN_HEADER] = remote_auth

        system_info_response = await http.get(
            f"{client.api_base_url.rstrip('/')}/system/info",
            headers=headers,
        )
        if system_info_response.status_code >= 400:
            raise RuntimeError(
                f"Version check failed with HTTP {system_info_response.status_code}."
            )

        try:
            body = system_info_response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Remote client returned invalid system info JSON."
            ) from exc

        return body if isinstance(body, dict) else {}


def _build_proxy_request_headers(
    request: Request, remote_auth: Optional[str]
) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        normalized = key.lower()
        if normalized in FORWARDED_REQUEST_HEADERS:
            headers[key] = value

    if remote_auth:
        headers[AUTH_TOKEN_HEADER] = remote_auth
    return headers


def _build_proxy_response_headers(response: httpx.Response) -> dict[str, str]:
    return {
        key: value
        for key, value in response.headers.items()
        if key.lower() in FORWARDED_RESPONSE_HEADERS
    }


def _proxy_query_params(request: Request) -> list[tuple[str, str]]:
    return [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key not in {"token", REMOTE_TARGET_AUTH_QUERY_PARAM}
    ]


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


@router.post("/{client_id}/check", response_model=RemoteClientResponse)
async def check_remote_client(
    client_id: str,
    request: Request,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    client = _get_client_or_404(db, client_id)
    checked_at = datetime.now(timezone.utc)
    remote_auth = _extract_remote_target_auth(request)

    try:
        system_info = await _fetch_remote_system_info(client, remote_auth)
        app_version = system_info.get("app_version")
        app_version = app_version if isinstance(app_version, str) else None
        borg_version = system_info.get("borg_version")
        borg_version = borg_version if isinstance(borg_version, str) else None
        borg2_version = system_info.get("borg2_version")
        borg2_version = borg2_version if isinstance(borg2_version, str) else None
        compatibility, compatibility_message = _compare_backend_versions(
            get_runtime_app_version(), app_version
        )

        _apply_client_health(
            client,
            status_value="online",
            checked_at=checked_at,
            app_version=app_version,
            borg_version=borg_version,
            borg2_version=borg2_version,
            error=None,
            compatibility=compatibility,
            compatibility_message=compatibility_message,
        )
    except Exception as exc:
        _apply_client_health(
            client,
            status_value="offline",
            checked_at=checked_at,
            error=_remote_check_error_message(exc),
            compatibility="unknown",
            compatibility_message="Remote client server compatibility could not be checked.",
        )

    db.commit()
    db.refresh(client)
    return _serialize_client(client)


@router.api_route(
    "/{client_id}/proxy/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_remote_client_request(
    client_id: str,
    path: str,
    request: Request,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    require_any_role(current_user, "admin")
    client = _get_client_or_404(db, client_id)
    target_url = f"{client.web_base_url.rstrip('/')}/{path.lstrip('/')}"
    remote_auth = _extract_remote_target_auth(request)
    body = await request.body()

    try:
        async with httpx.AsyncClient(
            timeout=REMOTE_CLIENT_PROXY_TIMEOUT_SECONDS
        ) as http:
            remote_response = await http.request(
                request.method,
                target_url,
                params=_proxy_query_params(request),
                content=body if body else None,
                headers=_build_proxy_request_headers(request, remote_auth),
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "key": "backend.errors.remoteClients.proxyUnavailable",
                "params": {"error": str(exc)},
            },
        ) from exc

    return Response(
        content=remote_response.content,
        status_code=remote_response.status_code,
        headers=_build_proxy_response_headers(remote_response),
    )


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_remote_client(
    client_id: str,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    client = _get_client_or_404(db, client_id)
    db.delete(client)
    db.commit()
