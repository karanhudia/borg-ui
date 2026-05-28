from __future__ import annotations

import asyncio
import configparser
import json
import logging
import math
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.authorization import authorize_request
from app.core.security import get_current_user
from app.database.database import get_db
from app.database.models import RepositoryStorage, RcloneRemote, User
from app.services.rclone_repository_service import normalize_rclone_relative_path
from app.services.rclone_service import RcloneUnavailable, rclone_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rclone"], dependencies=[Depends(authorize_request)])

RCLONE_REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
RCLONE_OAUTH_URL_RE = re.compile(r"https?://[^\s<>]+")
RCLONE_OAUTH_START_TIMEOUT_SECONDS = 15
REDACTED_CONFIG_VALUE = "***"
SAFE_CONFIG_KEY_EXCEPTIONS = {
    "key_file",
    "private_key_file",
    "service_account_file",
}
SENSITIVE_CONFIG_KEYS = {
    "access_key",
    "access_key_id",
    "account",
    "account_key",
    "application_key",
    "client_secret",
    "key",
    "password",
    "pass",
    "refresh_token",
    "sas_url",
    "secret",
    "secret_access_key",
    "service_account_credentials",
    "token",
}
SENSITIVE_CONFIG_FRAGMENTS = (
    "access_token",
    "client_secret",
    "password",
    "refresh_token",
    "secret",
    "token",
)

RCLONE_PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "type": "drive",
        "label": "Google Drive",
        "description": "Google Drive and shared drives through rclone's drive backend.",
        "auth_type": "oauth_token",
        "type_editable": False,
        "docs_url": "https://rclone.org/drive/",
        "config_template": {"type": "drive", "scope": "drive", "token": ""},
        "fields": [
            {
                "name": "token",
                "label": "OAuth token JSON",
                "kind": "json",
                "required": True,
                "secret": True,
                "helper": "Start browser authorization from Borg UI, then check authorization.",
            },
            {
                "name": "scope",
                "label": "Scope",
                "kind": "text",
                "required": False,
                "secret": False,
                "helper": "Default is drive. Use drive.readonly only for read-only imports.",
            },
            {
                "name": "root_folder_id",
                "label": "Root folder ID",
                "kind": "text",
                "required": False,
                "secret": False,
                "helper": "Optional folder or shared drive root ID.",
            },
        ],
    },
    {
        "type": "onedrive",
        "label": "Microsoft OneDrive",
        "description": "OneDrive personal, business, and SharePoint document libraries.",
        "auth_type": "oauth_token",
        "type_editable": False,
        "docs_url": "https://rclone.org/onedrive/",
        "config_template": {"type": "onedrive", "token": ""},
        "fields": [
            {
                "name": "token",
                "label": "OAuth token JSON",
                "kind": "json",
                "required": True,
                "secret": True,
                "helper": "Start browser authorization from Borg UI, then check authorization.",
            },
            {
                "name": "drive_type",
                "label": "Drive type",
                "kind": "text",
                "required": False,
                "secret": False,
                "helper": "Optional rclone drive type when pinning a specific drive.",
            },
            {
                "name": "drive_id",
                "label": "Drive ID",
                "kind": "text",
                "required": False,
                "secret": False,
                "helper": "Optional drive ID for a selected OneDrive or SharePoint drive.",
            },
        ],
    },
    {
        "type": "dropbox",
        "label": "Dropbox",
        "description": "Dropbox accounts through rclone's OAuth backend.",
        "auth_type": "oauth_token",
        "type_editable": False,
        "docs_url": "https://rclone.org/dropbox/",
        "config_template": {"type": "dropbox", "token": ""},
        "fields": [
            {
                "name": "token",
                "label": "OAuth token JSON",
                "kind": "json",
                "required": True,
                "secret": True,
                "helper": "Start browser authorization from Borg UI, then check authorization.",
            }
        ],
    },
    {
        "type": "box",
        "label": "Box",
        "description": "Box cloud storage through rclone's OAuth backend.",
        "auth_type": "oauth_token",
        "type_editable": False,
        "docs_url": "https://rclone.org/box/",
        "config_template": {"type": "box", "token": ""},
        "fields": [
            {
                "name": "token",
                "label": "OAuth token JSON",
                "kind": "json",
                "required": True,
                "secret": True,
                "helper": "Start browser authorization from Borg UI, then check authorization.",
            }
        ],
    },
    {
        "type": "s3",
        "label": "Amazon S3 / S3-compatible",
        "description": "AWS S3, MinIO, Wasabi, Cloudflare R2, and compatible object stores.",
        "auth_type": "access_key",
        "type_editable": False,
        "docs_url": "https://rclone.org/s3/",
        "config_template": {
            "type": "s3",
            "provider": "AWS",
            "access_key_id": "",
            "secret_access_key": "",
            "region": "",
            "endpoint": "",
        },
        "fields": [
            {
                "name": "provider",
                "label": "Provider",
                "kind": "text",
                "required": True,
                "secret": False,
                "helper": "Example: AWS, Minio, Wasabi, Cloudflare.",
            },
            {
                "name": "access_key_id",
                "label": "Access key ID",
                "kind": "text",
                "required": True,
                "secret": True,
                "helper": "Stored only in the managed rclone config.",
            },
            {
                "name": "secret_access_key",
                "label": "Secret access key",
                "kind": "password",
                "required": True,
                "secret": True,
                "helper": "Stored only in the managed rclone config.",
            },
            {
                "name": "endpoint",
                "label": "Endpoint",
                "kind": "text",
                "required": False,
                "secret": False,
                "helper": "Required for many S3-compatible providers.",
            },
        ],
    },
    {
        "type": "b2",
        "label": "Backblaze B2",
        "description": "Backblaze B2 buckets through rclone.",
        "auth_type": "access_key",
        "type_editable": False,
        "docs_url": "https://rclone.org/b2/",
        "config_template": {"type": "b2", "account": "", "key": ""},
        "fields": [
            {
                "name": "account",
                "label": "Account ID",
                "kind": "text",
                "required": True,
                "secret": True,
                "helper": "Stored only in the managed rclone config.",
            },
            {
                "name": "key",
                "label": "Application key",
                "kind": "password",
                "required": True,
                "secret": True,
                "helper": "Stored only in the managed rclone config.",
            },
        ],
    },
    {
        "type": "azureblob",
        "label": "Azure Blob Storage",
        "description": "Azure Blob containers through rclone.",
        "auth_type": "access_key",
        "type_editable": False,
        "docs_url": "https://rclone.org/azureblob/",
        "config_template": {"type": "azureblob", "account": "", "key": ""},
        "fields": [
            {
                "name": "account",
                "label": "Storage account",
                "kind": "text",
                "required": True,
                "secret": False,
                "helper": "Azure storage account name.",
            },
            {
                "name": "key",
                "label": "Storage account key",
                "kind": "password",
                "required": True,
                "secret": True,
                "helper": "Stored only in the managed rclone config.",
            },
        ],
    },
    {
        "type": "webdav",
        "label": "WebDAV",
        "description": "Generic WebDAV and provider-specific WebDAV endpoints.",
        "auth_type": "basic",
        "type_editable": False,
        "docs_url": "https://rclone.org/webdav/",
        "config_template": {
            "type": "webdav",
            "url": "",
            "vendor": "other",
            "user": "",
            "pass": "",
        },
        "fields": [
            {
                "name": "url",
                "label": "URL",
                "kind": "text",
                "required": True,
                "secret": False,
                "helper": "Base WebDAV URL.",
            },
            {
                "name": "user",
                "label": "Username",
                "kind": "text",
                "required": False,
                "secret": False,
                "helper": "Optional WebDAV username.",
            },
            {
                "name": "pass",
                "label": "Password",
                "kind": "password",
                "required": False,
                "secret": True,
                "helper": "Stored only in the managed rclone config.",
            },
        ],
    },
    {
        "type": "sftp",
        "label": "SFTP",
        "description": "SFTP targets managed by rclone, separate from Borg-over-SSH repositories.",
        "auth_type": "basic",
        "type_editable": False,
        "docs_url": "https://rclone.org/sftp/",
        "config_template": {
            "type": "sftp",
            "host": "",
            "user": "",
            "port": "22",
            "pass": "",
            "key_file": "",
        },
        "fields": [
            {
                "name": "host",
                "label": "Host",
                "kind": "text",
                "required": True,
                "secret": False,
                "helper": "SFTP host name.",
            },
            {
                "name": "user",
                "label": "Username",
                "kind": "text",
                "required": True,
                "secret": False,
                "helper": "SFTP username.",
            },
            {
                "name": "pass",
                "label": "Password",
                "kind": "password",
                "required": False,
                "secret": True,
                "helper": "Use either password or key_file.",
            },
            {
                "name": "key_file",
                "label": "Key file",
                "kind": "text",
                "required": False,
                "secret": False,
                "helper": "Server-side private key path available to rclone.",
            },
        ],
    },
    {
        "type": "local",
        "label": "Local filesystem",
        "description": "A local path remote for testing and mounted storage.",
        "auth_type": "none",
        "type_editable": False,
        "docs_url": "https://rclone.org/local/",
        "config_template": {"type": "local"},
        "fields": [],
    },
    {
        "type": "custom",
        "label": "Custom rclone backend",
        "description": "Manual setup for any rclone backend not listed above.",
        "auth_type": "manual",
        "type_editable": True,
        "docs_url": "https://rclone.org/docs/",
        "config_template": {"type": ""},
        "fields": [],
    },
]

RCLONE_OAUTH_SESSIONS: dict[str, dict[str, Any]] = {}


class RcloneRemoteCreate(BaseModel):
    name: str
    provider: str
    config_source: str = "managed"
    config_path: str | None = None
    redacted_config: dict[str, Any] | None = None


class RcloneRemoteUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    config_source: str | None = None
    redacted_config: dict[str, Any] | None = None


class RcloneOAuthStart(BaseModel):
    provider: str
    config: dict[str, Any] | None = None
    client_id: str | None = None
    client_secret: str | None = None


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


def _provider_catalog_entry(provider: str) -> dict[str, Any] | None:
    for entry in RCLONE_PROVIDER_CATALOG:
        if entry["type"] == provider:
            return entry
    return None


def _require_oauth_provider(provider: str) -> dict[str, Any]:
    entry = _provider_catalog_entry(provider)
    if not entry or entry.get("auth_type") != "oauth_token":
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.oauthUnsupported"},
        )
    return entry


def _managed_config_path(config_root: Path) -> Path:
    root = config_root.resolve()
    config_path = (root / "rclone.conf").resolve()
    if config_path.parent != root:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidRemoteName"},
        )
    return config_path


def _extract_oauth_authorization_url(text: str) -> str | None:
    urls = [
        match.group(0).rstrip(").,;\"'") for match in RCLONE_OAUTH_URL_RE.finditer(text)
    ]
    if not urls:
        return None
    for url in urls:
        lowered = url.lower()
        if "/auth" in lowered or "oauth" in lowered:
            return url
    return urls[0]


def _iter_json_objects(text: str):
    depth = 0
    start: int | None = None
    in_string = False
    escaped = False
    for index, character in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
            continue
        if character == "{":
            if depth == 0:
                start = index
            depth += 1
        elif character == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : index + 1]
                start = None


def _extract_oauth_token(output: str) -> str | None:
    for candidate in _iter_json_objects(output):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        if {"access_token", "refresh_token", "token_type", "expiry"} & set(parsed):
            return json.dumps(parsed, separators=(",", ":"))
    return None


def _oauth_session_response(session_id: str) -> dict[str, Any]:
    session = RCLONE_OAUTH_SESSIONS[session_id]
    return {
        "session_id": session_id,
        "provider": session["provider"],
        "status": session["status"],
        "authorization_url": session.get("authorization_url"),
        "config": session.get("config"),
        "error": session.get("error"),
    }


async def _start_oauth_process(
    provider: str,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
):
    command = rclone_service.authorize_command(
        provider,
        client_id=client_id.strip() if client_id else None,
        client_secret=client_secret.strip() if client_secret else None,
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (FileNotFoundError, OSError) as exc:
        raise RcloneUnavailable(f"rclone binary not found: {exc}") from exc
    if process.stdout is None:
        raise RcloneUnavailable("rclone authorization output stream unavailable")
    return process


async def _consume_oauth_process(session_id: str, process) -> None:
    session = RCLONE_OAUTH_SESSIONS.get(session_id)
    if session is None:
        return
    output: list[str] = session["output"]
    ready_event: asyncio.Event = session["ready_event"]
    try:
        while True:
            raw_line = await process.stdout.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace")
            output.append(line)
            session["updated_at"] = datetime.now(timezone.utc)
            authorization_url = _extract_oauth_authorization_url(line)
            if authorization_url and not session.get("authorization_url"):
                session["authorization_url"] = authorization_url
                session["status"] = "awaiting_callback"
                ready_event.set()
            token = _extract_oauth_token("".join(output[-20:]))
            if token:
                session["status"] = "authorized"
                session["config"] = {"type": session["provider"], "token": token}
                session["error"] = None
                ready_event.set()
        return_code = await process.wait()
        if session["status"] != "authorized":
            session["status"] = "failed"
            tail = "".join(output[-12:]).strip()
            if return_code == 0:
                session["error"] = (
                    "rclone authorization finished without returning a token"
                )
            else:
                session["error"] = tail or "rclone authorization failed"
            ready_event.set()
    except Exception as exc:  # pragma: no cover - defensive background task guard
        logger.exception("rclone OAuth session failed")
        session["status"] = "failed"
        session["error"] = str(exc)
        ready_event.set()
    finally:
        session["process"] = None


def _new_config_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    return parser


def _load_config(config_path: Path) -> configparser.ConfigParser:
    parser = _new_config_parser()
    if config_path.exists():
        try:
            parser.read(config_path, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError) as exc:
            # Malformed config (e.g. JSON written where INI was expected). Treat as
            # empty so callers can still complete cleanup; the orphan file remains
            # on disk for manual inspection.
            logger.warning(
                "Failed to parse rclone config at %s; treating as empty: %s",
                config_path,
                exc,
            )
            return _new_config_parser()
    return parser


def _stringify_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _is_sensitive_config_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in SAFE_CONFIG_KEY_EXCEPTIONS:
        return False
    if normalized in SENSITIVE_CONFIG_KEYS:
        return True
    return any(fragment in normalized for fragment in SENSITIVE_CONFIG_FRAGMENTS)


def _is_redacted_config_value(value: Any) -> bool:
    return isinstance(value, str) and value == REDACTED_CONFIG_VALUE


def _redact_config_values(values: dict[str, Any] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if _is_sensitive_config_key(str(key)) and value not in (None, ""):
            redacted[str(key)] = REDACTED_CONFIG_VALUE
        elif isinstance(value, dict):
            redacted[str(key)] = _redact_config_values(value)
        elif isinstance(value, list):
            redacted[str(key)] = [
                _redact_config_values(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[str(key)] = value
    return redacted


def _config_section_values(
    parser: configparser.ConfigParser, remote_name: str
) -> dict[str, str]:
    if not parser.has_section(remote_name):
        return {}
    return {key: value for key, value in parser.items(remote_name)}


def _preserve_redacted_config_values(
    incoming: dict[str, Any], existing: dict[str, str]
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key, value in incoming.items():
        key_text = str(key)
        if (
            _is_sensitive_config_key(key_text)
            and _is_redacted_config_value(value)
            and key_text in existing
        ):
            resolved[key_text] = existing[key_text]
        else:
            resolved[key_text] = value
    return resolved


def _normalize_browse_entry_path(value: Any) -> str:
    return "/".join(part for part in str(value or "").strip().split("/") if part)


def _compose_browse_entry_path(relative_path: str, item: dict[str, Any]) -> str:
    item_path = _normalize_browse_entry_path(item.get("Path") or item.get("Name"))
    if not item_path:
        return relative_path
    if not relative_path:
        return item_path
    if item_path == relative_path or item_path.startswith(f"{relative_path}/"):
        return item_path
    return f"{relative_path}/{item_path}"


def _serialize_browse_entry_size(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        size = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(size) or size < 0:
        return None
    return int(size)


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


def _replace_managed_remote_config(
    config_path: Path,
    *,
    old_remote_name: str,
    remote_name: str,
    provider: str,
    redacted_config: dict[str, Any] | None,
) -> None:
    parser = _load_config(config_path)
    if old_remote_name != remote_name:
        parser.remove_section(old_remote_name)
    else:
        parser.remove_section(remote_name)
    parser.add_section(remote_name)
    for key, value in _managed_config_values(provider, redacted_config).items():
        parser.set(remote_name, key, value)
    _write_config_file(config_path, parser)


def _restore_managed_config(
    config_path: Path, parser: configparser.ConfigParser
) -> None:
    if parser.sections():
        _write_config_file(config_path, parser)
    else:
        config_path.unlink(missing_ok=True)


def _managed_config_path_for_remote(remote: RcloneRemote) -> Path:
    if remote.config_path:
        return Path(remote.config_path)
    return _managed_config_path(Path(settings.rclone_config_root))


def _remote_usage_count(db: Session, remote_id: int) -> int:
    return (
        db.query(RepositoryStorage)
        .filter(
            RepositoryStorage.backend == "rclone",
            RepositoryStorage.rclone_remote_id == remote_id,
        )
        .count()
    )


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
        "redacted_config": _redact_config_values(remote.redacted_config),
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


@router.get("/providers")
async def list_providers(current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    return {"providers": RCLONE_PROVIDER_CATALOG}


@router.post("/oauth/sessions", status_code=status.HTTP_201_CREATED)
async def start_oauth_session(
    payload: RcloneOAuthStart,
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    provider = _normalize_provider(payload.provider)
    _require_oauth_provider(provider)

    session_id = secrets.token_urlsafe(18)
    ready_event = asyncio.Event()
    session = {
        "provider": provider,
        "status": "starting",
        "authorization_url": None,
        "config": None,
        "error": None,
        "output": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "ready_event": ready_event,
        "process": None,
        "task": None,
    }
    RCLONE_OAUTH_SESSIONS[session_id] = session

    try:
        process = await _start_oauth_process(
            provider,
            client_id=payload.client_id,
            client_secret=payload.client_secret,
        )
    except RcloneUnavailable as exc:
        RCLONE_OAUTH_SESSIONS.pop(session_id, None)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"key": "backend.errors.rclone.unavailable", "message": str(exc)},
        ) from exc

    session["process"] = process
    session["task"] = asyncio.create_task(_consume_oauth_process(session_id, process))
    try:
        await asyncio.wait_for(
            ready_event.wait(), timeout=RCLONE_OAUTH_START_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        pass
    await asyncio.sleep(0)
    return _oauth_session_response(session_id)


@router.get("/oauth/sessions/{session_id}")
async def get_oauth_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    if session_id not in RCLONE_OAUTH_SESSIONS:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.rclone.oauthNotFound"}
        )
    await asyncio.sleep(0)
    return _oauth_session_response(session_id)


@router.delete("/oauth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_oauth_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    session = RCLONE_OAUTH_SESSIONS.pop(session_id, None)
    if session is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    task = session.get("task")
    if task is not None and not task.done():
        task.cancel()
    process = session.get("process")
    if process is not None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    raw_config = payload.redacted_config
    remote = RcloneRemote(
        name=remote_name,
        provider=provider,
        config_source=payload.config_source,
        config_path=payload.config_path,
        redacted_config=_redact_config_values(raw_config),
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
                redacted_config=raw_config,
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


@router.put("/remotes/{remote_id}")
async def update_remote(
    remote_id: int,
    payload: RcloneRemoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    remote = db.query(RcloneRemote).filter(RcloneRemote.id == remote_id).first()
    if not remote:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.rclone.remoteNotFound"}
        )
    if (
        payload.config_source is not None
        and payload.config_source != remote.config_source
    ):
        raise HTTPException(
            status_code=400, detail={"key": "backend.errors.rclone.updateUnsupported"}
        )

    remote_name = (
        _normalize_remote_name(payload.name)
        if payload.name is not None
        else remote.name
    )
    if remote_name != remote.name:
        existing = (
            db.query(RcloneRemote)
            .filter(RcloneRemote.name == remote_name, RcloneRemote.id != remote.id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409, detail={"key": "backend.errors.rclone.remoteExists"}
            )
    provider = (
        _normalize_provider(payload.provider)
        if payload.provider is not None
        else remote.provider
    )
    redacted_config = remote.redacted_config

    config_file: Path | None = None
    original_parser: configparser.ConfigParser | None = None
    wrote_config = False
    old_remote_name = remote.name
    try:
        if remote.config_source == "managed":
            config_file = _managed_config_path_for_remote(remote)
            original_parser = _load_config(config_file)
            existing_config = _config_section_values(original_parser, old_remote_name)
            config_for_write = (
                _preserve_redacted_config_values(
                    payload.redacted_config, existing_config
                )
                if payload.redacted_config is not None
                else existing_config or remote.redacted_config
            )
            _replace_managed_remote_config(
                config_file,
                old_remote_name=old_remote_name,
                remote_name=remote_name,
                provider=provider,
                redacted_config=config_for_write,
            )
            wrote_config = True
            remote.config_path = str(config_file)
            redacted_config = _redact_config_values(config_for_write)
        elif payload.redacted_config is not None:
            redacted_config = _redact_config_values(payload.redacted_config)

        remote.name = remote_name
        remote.provider = provider
        remote.redacted_config = redacted_config
        db.commit()
    except Exception as exc:
        db.rollback()
        if config_file is not None and original_parser is not None and wrote_config:
            _restore_managed_config(config_file, original_parser)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.rclone.failedToUpdateRemote"},
        ) from exc

    db.refresh(remote)
    return _serialize_remote(remote)


@router.delete("/remotes/{remote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_remote(
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
    if _remote_usage_count(db, remote.id):
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.rclone.remoteInUse"}
        )

    config_file: Path | None = None
    original_parser: configparser.ConfigParser | None = None
    wrote_config = False
    try:
        if remote.config_source == "managed":
            config_file = _managed_config_path_for_remote(remote)
            original_parser = _load_config(config_file)
            _remove_managed_remote_config(config_file, remote.name)
            wrote_config = True
        db.delete(remote)
        db.commit()
    except Exception as exc:
        db.rollback()
        if config_file is not None and original_parser is not None and wrote_config:
            _restore_managed_config(config_file, original_parser)
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.rclone.failedToDeleteRemote"},
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
                "path": _compose_browse_entry_path(relative_path, item),
                "is_dir": bool(item.get("IsDir")),
                "size": _serialize_browse_entry_size(item.get("Size")),
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
