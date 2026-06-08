from __future__ import annotations

import asyncio
import configparser
import json
import logging
import math
import re
import secrets
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.authorization import authorize_request
from app.core.features import require_feature
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    get_current_download_user,
    get_current_user,
)
from app.database.database import get_db
from app.database.models import (
    RepositoryStorage,
    RcloneOAuthProviderCredential,
    RcloneRemote,
    SystemSettings,
    User,
)
from app.services.rclone_repository_service import normalize_rclone_relative_path
from app.services.rclone_service import RcloneUnavailable, rclone_service

logger = logging.getLogger(__name__)

RCLONE_FEATURE_DEPENDENCY = require_feature("rclone")

router = APIRouter(
    tags=["rclone"],
    dependencies=[Depends(authorize_request)],
)
public_router = APIRouter(tags=["rclone"])

RCLONE_REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
RCLONE_ABOUT_STORAGE_LINE_RE = re.compile(
    r"^\s*(total|used|free|available)\s*:\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)?\s*$",
    re.IGNORECASE,
)
RCLONE_OAUTH_URL_RE = re.compile(r"https?://[^\s<>]+")
RCLONE_SHAREFILE_HOST_PART_RE = re.compile(r"^[A-Za-z0-9.-]+$")
RCLONE_OAUTH_START_TIMEOUT_SECONDS = 15
RCLONE_OAUTH_SESSION_TTL_SECONDS = 15 * 60
RCLONE_OAUTH_MAX_SESSIONS = 32
RCLONE_OAUTH_OUTPUT_LIMIT_CHARS = 20_000
RCLONE_OAUTH_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
BORG_UI_OAUTH_MARKER_KEY = "_borg_ui_oauth_provider"
BORG_UI_OAUTH_SESSION_KEY = "_borg_ui_oauth_session_id"
GOOGLE_DRIVE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_DRIVE_TOKEN_URL = "https://oauth2.googleapis.com/token"
MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_GRAPH_ME_DRIVE_URL = "https://graph.microsoft.com/v1.0/me/drive"
DROPBOX_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
BOX_AUTH_URL = "https://app.box.com/api/oauth2/authorize"
BOX_TOKEN_URL = "https://app.box.com/api/oauth2/token"
PCLOUD_AUTH_URL = "https://my.pcloud.com/oauth2/authorize"
PCLOUD_TOKEN_URL = "https://api.pcloud.com/oauth2_token"
GCS_SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"
GOOGLE_PHOTOS_APPEND_ONLY_SCOPE = (
    "https://www.googleapis.com/auth/photoslibrary.appendonly"
)
GOOGLE_PHOTOS_READ_ONLY_SCOPE = (
    "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata"
)
GOOGLE_PHOTOS_READ_WRITE_SCOPE = (
    "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata"
)
HIDRIVE_AUTH_URL = "https://my.hidrive.com/client/authorize"
HIDRIVE_TOKEN_URL = "https://my.hidrive.com/oauth2/token"
HUAWEI_DRIVE_AUTH_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/authorize"
HUAWEI_DRIVE_TOKEN_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
PREMIUMIZE_AUTH_URL = "https://www.premiumize.me/authorize"
PREMIUMIZE_TOKEN_URL = "https://www.premiumize.me/token"
PUTIO_AUTH_URL = "https://api.put.io/v2/oauth2/authenticate"
PUTIO_TOKEN_URL = "https://api.put.io/v2/oauth2/access_token"
SHAREFILE_AUTH_URL = "https://secure.sharefile.com/oauth/authorize"
SHAREFILE_TOKEN_PATH = "/oauth/token"
YANDEX_AUTH_URL = "https://oauth.yandex.com/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.com/token"
ZOHO_OAUTH_SCOPES = (
    "aaaserver.profile.read WorkDrive.team.READ WorkDrive.workspace.READ "
    "WorkDrive.files.ALL ZohoFiles.files.ALL"
)
ZOHO_REGIONS = {"com", "eu", "in", "jp", "com.cn", "com.au"}
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
    "authorization_code",
    "client_id",
    "client_secret",
    "code",
    "code_verifier",
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
    "authorization_code",
    "client_id",
    "client_secret",
    "code_verifier",
    "password",
    "refresh_token",
    "secret",
    "token",
)


@dataclass(frozen=True)
class RcloneOAuthAdapter:
    auth_url: str
    token_url: str
    scope: str | None = None
    extra_auth_params: dict[str, str] = field(default_factory=dict)
    state_optional: bool = False
    token_type: str | None = None


BORG_UI_OAUTH_ADAPTERS: dict[str, RcloneOAuthAdapter] = {
    "drive": RcloneOAuthAdapter(
        auth_url=GOOGLE_DRIVE_AUTH_URL,
        token_url=GOOGLE_DRIVE_TOKEN_URL,
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    ),
    "onedrive": RcloneOAuthAdapter(
        auth_url=MICROSOFT_AUTH_URL,
        token_url=MICROSOFT_TOKEN_URL,
        extra_auth_params={"response_mode": "query"},
    ),
    "dropbox": RcloneOAuthAdapter(
        auth_url=DROPBOX_AUTH_URL,
        token_url=DROPBOX_TOKEN_URL,
        scope=(
            "files.metadata.write files.content.write files.content.read "
            "sharing.write account_info.read"
        ),
        extra_auth_params={"token_access_type": "offline"},
    ),
    "box": RcloneOAuthAdapter(auth_url=BOX_AUTH_URL, token_url=BOX_TOKEN_URL),
    "gcs": RcloneOAuthAdapter(
        auth_url=GOOGLE_DRIVE_AUTH_URL,
        token_url=GOOGLE_DRIVE_TOKEN_URL,
        scope=GCS_SCOPE,
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    ),
    "gphotos": RcloneOAuthAdapter(
        auth_url=GOOGLE_DRIVE_AUTH_URL,
        token_url=GOOGLE_DRIVE_TOKEN_URL,
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    ),
    "hidrive": RcloneOAuthAdapter(
        auth_url=HIDRIVE_AUTH_URL,
        token_url=HIDRIVE_TOKEN_URL,
    ),
    "huaweidrive": RcloneOAuthAdapter(
        auth_url=HUAWEI_DRIVE_AUTH_URL,
        token_url=HUAWEI_DRIVE_TOKEN_URL,
        scope=(
            "openid profile https://www.huawei.com/auth/drive "
            "https://www.huawei.com/auth/drive.file"
        ),
        extra_auth_params={"access_type": "offline"},
    ),
    "pcloud": RcloneOAuthAdapter(
        auth_url=PCLOUD_AUTH_URL,
        token_url=PCLOUD_TOKEN_URL,
        state_optional=True,
    ),
    "premiumizeme": RcloneOAuthAdapter(
        auth_url=PREMIUMIZE_AUTH_URL,
        token_url=PREMIUMIZE_TOKEN_URL,
    ),
    "putio": RcloneOAuthAdapter(
        auth_url=PUTIO_AUTH_URL,
        token_url=PUTIO_TOKEN_URL,
    ),
    "sharefile": RcloneOAuthAdapter(
        auth_url=SHAREFILE_AUTH_URL,
        token_url="",
    ),
    "yandex": RcloneOAuthAdapter(
        auth_url=YANDEX_AUTH_URL,
        token_url=YANDEX_TOKEN_URL,
        token_type="OAuth",
    ),
    "zoho": RcloneOAuthAdapter(
        auth_url="",
        token_url="",
        scope=ZOHO_OAUTH_SCOPES,
        extra_auth_params={"approval_prompt": "force"},
        token_type="Zoho-oauthtoken",
    ),
}

RCLONE_OAUTH_PROVIDER_TYPES = {
    "box",
    "drive",
    "dropbox",
    "gcs",
    "gphotos",
    "hidrive",
    "huaweidrive",
    "jottacloud",
    "mailru",
    "onedrive",
    "pcloud",
    "premiumizeme",
    "putio",
    "sharefile",
    "yandex",
    "zoho",
}

RCLONE_NON_BROWSER_OAUTH_PROVIDER_TYPES = {"jottacloud", "mailru"}

RCLONE_PROVIDER_DOC_OVERRIDES = {
    "gphotos": "https://rclone.org/googlephotos/",
    "premiumizeme": "https://rclone.org/premiumize/",
}

RCLONE_GENERATED_FIELD_EXCLUSIONS = {
    "auth_url",
    "client_id",
    "client_secret",
    "config_refresh_token",
    "description",
    "encoding",
    "token_url",
}

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
                "helper": "Start browser authorization from Borg UI, then return to the dialog.",
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
                "helper": "Start browser authorization from Borg UI, then return to the dialog.",
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
                "helper": "Start browser authorization from Borg UI, then return to the dialog.",
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
                "helper": "Start browser authorization from Borg UI, then return to the dialog.",
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

RCLONE_OAUTH_SESSIONS: OrderedDict[str, dict[str, Any]] = OrderedDict()


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
    mode: str = "auto"


class RcloneOAuthCredentialUpdate(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    clear_client_secret: bool = False

    @model_validator(mode="after")
    def validate_paired_credentials(self) -> "RcloneOAuthCredentialUpdate":
        if self.clear_client_secret:
            return self

        credential_fields = {"client_id", "client_secret"}
        provided_credentials = set(self.model_fields_set) & credential_fields
        if provided_credentials and provided_credentials != credential_fields:
            raise ValueError(
                "client_id and client_secret must both be provided or both be empty"
            )

        if provided_credentials == credential_fields:
            client_id_set = bool((self.client_id or "").strip())
            client_secret_set = bool((self.client_secret or "").strip())
            if client_id_set != client_secret_set:
                raise ValueError(
                    "client_id and client_secret must both be provided or both be empty"
                )
        return self


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


def _option_name(option: dict[str, Any]) -> str:
    return str(option.get("Name") or "").strip()


def _option_is_sensitive(option: dict[str, Any]) -> bool:
    name = _option_name(option).lower()
    return bool(
        option.get("Sensitive")
        or option.get("IsPassword")
        or name in SENSITIVE_CONFIG_KEYS
        or any(fragment in name for fragment in SENSITIVE_CONFIG_FRAGMENTS)
    )


def _option_help(option: dict[str, Any]) -> str:
    raw_help = str(option.get("Help") or "").strip()
    if not raw_help:
        return "rclone provider option."
    first_paragraph = raw_help.split("\n\n", 1)[0].replace("\n", " ").strip()
    return first_paragraph[:220]


def _option_label(name: str) -> str:
    label = name.replace("_", " ").strip().title()
    return label.replace(" Id", " ID").replace(" Url", " URL")


def _generated_field_from_option(option: dict[str, Any]) -> dict[str, Any]:
    name = _option_name(option)
    kind = "text"
    if name == "token" or str(option.get("Type") or "").lower() == "json":
        kind = "json"
    elif _option_is_sensitive(option):
        kind = "password"
    return {
        "name": name,
        "label": _option_label(name),
        "kind": kind,
        "required": bool(option.get("Required")),
        "secret": _option_is_sensitive(option),
        "helper": _option_help(option),
    }


def _generated_provider_auth_type(provider: str, options: list[dict[str, Any]]) -> str:
    option_names = {_option_name(option) for option in options}
    if provider not in RCLONE_NON_BROWSER_OAUTH_PROVIDER_TYPES and (
        provider in RCLONE_OAUTH_PROVIDER_TYPES
        or {"client_id", "client_secret", "token"}.issubset(option_names)
    ):
        return "oauth_token"
    if provider in {"local", "memory"}:
        return "none"
    if (
        {"access_key_id", "secret_access_key"} <= option_names
        or "api_key" in option_names
        or "api_token" in option_names
        or ({"account", "key"} <= option_names)
    ):
        return "access_key"
    if option_names & {"pass", "password"} and option_names & {"user", "username"}:
        return "basic"
    if any(
        bool(option.get("Required")) and _option_is_sensitive(option)
        for option in options
    ):
        return "access_key"
    return "manual"


def _generated_provider_catalog_entry(
    raw_provider: dict[str, Any],
) -> dict[str, Any] | None:
    provider = str(raw_provider.get("Prefix") or raw_provider.get("Name") or "").strip()
    if not provider:
        return None
    raw_options = raw_provider.get("Options")
    options = raw_options if isinstance(raw_options, list) else []
    option_dicts = [
        option
        for option in options
        if isinstance(option, dict) and _option_name(option)
    ]
    auth_type = _generated_provider_auth_type(provider, option_dicts)
    if auth_type == "oauth_token":
        fields = [
            {
                "name": "token",
                "label": "OAuth token JSON",
                "kind": "json",
                "required": True,
                "secret": True,
                "helper": "Start browser authorization from Borg UI when configured, or use rclone's local authorization flow.",
            }
        ]
        config_template: dict[str, Any] = {"type": provider, "token": ""}
    else:
        fields = [
            _generated_field_from_option(option)
            for option in option_dicts
            if _option_name(option) not in RCLONE_GENERATED_FIELD_EXCLUSIONS
            and (
                bool(option.get("Required"))
                or (not option.get("Advanced") and _option_is_sensitive(option))
            )
        ][:8]
        config_template = {"type": provider}
        for field_info in fields:
            config_template[field_info["name"]] = ""

    description = str(
        raw_provider.get("Description") or raw_provider.get("Name") or provider
    ).strip()
    return {
        "type": provider,
        "label": description or provider,
        "description": description or f"rclone {provider} backend.",
        "auth_type": auth_type,
        "type_editable": False,
        "docs_url": RCLONE_PROVIDER_DOC_OVERRIDES.get(
            provider, f"https://rclone.org/{provider}/"
        ),
        "config_template": config_template,
        "fields": fields,
    }


def _minimal_oauth_provider_catalog_entry(provider: str) -> dict[str, Any]:
    return {
        "type": provider,
        "label": _option_label(provider),
        "description": f"rclone {provider} OAuth backend.",
        "auth_type": "oauth_token",
        "type_editable": False,
        "docs_url": RCLONE_PROVIDER_DOC_OVERRIDES.get(
            provider, f"https://rclone.org/{provider}/"
        ),
        "config_template": {"type": provider, "token": ""},
        "fields": [
            {
                "name": "token",
                "label": "OAuth token JSON",
                "kind": "json",
                "required": True,
                "secret": True,
                "helper": "Start browser authorization from Borg UI when configured, or use rclone's local authorization flow.",
            }
        ],
    }


async def _rclone_generated_provider_catalog() -> list[dict[str, Any]]:
    try:
        result = await rclone_service.execute(
            rclone_service.providers_command(), timeout=30
        )
    except (RcloneUnavailable, TimeoutError, OSError) as exc:
        logger.info("Unable to load rclone provider catalog: %s", exc, exc_info=True)
        return []
    if not result.success:
        logger.info(
            "rclone provider catalog command failed",
            extra={"return_code": result.return_code, "stderr": result.stderr},
        )
        return []
    try:
        parsed = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        logger.warning("rclone provider catalog returned invalid JSON")
        return []
    if not isinstance(parsed, list):
        return []
    entries = [
        _generated_provider_catalog_entry(raw_provider)
        for raw_provider in parsed
        if isinstance(raw_provider, dict)
    ]
    return [entry for entry in entries if entry is not None]


async def _provider_catalog() -> list[dict[str, Any]]:
    generated_entries = await _rclone_generated_provider_catalog()
    generated_by_type = {
        str(entry["type"]): entry
        for entry in generated_entries
        if str(entry.get("type") or "")
    }
    curated_by_type = {entry["type"]: entry for entry in RCLONE_PROVIDER_CATALOG}
    catalog: list[dict[str, Any]] = [
        curated_by_type[entry["type"]]
        for entry in RCLONE_PROVIDER_CATALOG
        if entry["type"] != "custom"
    ]
    catalog.extend(
        generated_by_type[provider]
        for provider in sorted(generated_by_type)
        if provider not in curated_by_type and provider != "custom"
    )
    custom_entry = curated_by_type.get("custom")
    if custom_entry:
        catalog.append(custom_entry)
    return catalog


def _provider_catalog_entry(provider: str) -> dict[str, Any] | None:
    for entry in RCLONE_PROVIDER_CATALOG:
        if entry["type"] == provider:
            return entry
    if (
        provider in RCLONE_OAUTH_PROVIDER_TYPES
        and provider not in RCLONE_NON_BROWSER_OAUTH_PROVIDER_TYPES
    ):
        return _minimal_oauth_provider_catalog_entry(provider)
    return None


def _require_oauth_provider(provider: str) -> dict[str, Any]:
    entry = _provider_catalog_entry(provider)
    if not entry or entry.get("auth_type") != "oauth_token":
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.oauthUnsupported"},
        )
    return entry


def _strip_optional(value: str | None) -> str | None:
    stripped = (value or "").strip()
    return stripped or None


def _get_or_create_system_settings(db: Session) -> SystemSettings:
    settings_query = (
        db.query(SystemSettings).order_by(SystemSettings.id.asc()).with_for_update()
    )
    settings_row = settings_query.first()
    if settings_row is None:
        settings_row = SystemSettings(id=1)
        db.add(settings_row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            settings_row = settings_query.first()
            if settings_row is None:
                raise
    return settings_row


def _provider_oauth_db_field_names(provider: str) -> tuple[str, str]:
    if provider == "drive":
        return (
            "google_drive_oauth_client_id",
            "google_drive_oauth_client_secret_encrypted",
        )
    if provider == "onedrive":
        return ("onedrive_oauth_client_id", "onedrive_oauth_client_secret_encrypted")
    raise HTTPException(
        status_code=400,
        detail={"key": "backend.errors.rclone.oauthUnsupported"},
    )


def _provider_oauth_label(provider: str) -> str:
    entry = _provider_catalog_entry(provider)
    return str(entry.get("label") or provider) if entry else provider


def _provider_supports_borg_ui_oauth(provider: str) -> bool:
    return provider in BORG_UI_OAUTH_ADAPTERS


def _require_borg_ui_oauth_provider(provider: str) -> None:
    if not _provider_supports_borg_ui_oauth(provider):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.oauthUnsupported"},
        )


def _decrypt_optional_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _strip_optional(decrypt_secret(value))
    except Exception:
        logger.warning("Failed to decrypt stored rclone OAuth provider secret")
        return None


def _provider_oauth_credential_record(
    provider: str, db: Session
) -> RcloneOAuthProviderCredential | None:
    return (
        db.query(RcloneOAuthProviderCredential)
        .filter(RcloneOAuthProviderCredential.provider == provider)
        .first()
    )


def _provider_stored_oauth_credentials(
    provider: str, db: Session | None
) -> tuple[str | None, str | None, bool]:
    if db is None or not _provider_supports_borg_ui_oauth(provider):
        return None, None, False
    credential_row = _provider_oauth_credential_record(provider, db)
    if credential_row is not None:
        stored_client_id = _strip_optional(credential_row.client_id)
        stored_secret = _decrypt_optional_secret(credential_row.client_secret_encrypted)
        has_stored_credentials = bool(
            stored_client_id or credential_row.client_secret_encrypted
        )
        if has_stored_credentials:
            return stored_client_id, stored_secret, True

    if provider not in {"drive", "onedrive"}:
        return None, None, False
    settings_row = db.query(SystemSettings).first()
    if settings_row is None:
        return None, None, False
    client_id_field, client_secret_field = _provider_oauth_db_field_names(provider)
    stored_client_id = _strip_optional(getattr(settings_row, client_id_field, None))
    stored_secret_encrypted = getattr(settings_row, client_secret_field, None)
    has_stored_credentials = bool(stored_client_id or stored_secret_encrypted)
    return (
        stored_client_id,
        _decrypt_optional_secret(stored_secret_encrypted),
        has_stored_credentials,
    )


def _provider_oauth_credential_state(
    provider: str, db: Session | None = None
) -> dict[str, Any]:
    if not _provider_supports_borg_ui_oauth(provider):
        return {
            "client_id": None,
            "client_secret": None,
            "client_id_set": False,
            "client_secret_set": False,
            "configured": False,
            "source": "unsupported",
        }

    stored_client_id, stored_secret, has_stored_credentials = (
        _provider_stored_oauth_credentials(provider, db)
    )
    if has_stored_credentials:
        return {
            "client_id": stored_client_id,
            "client_secret": stored_secret,
            "client_id_set": bool(stored_client_id),
            "client_secret_set": bool(stored_secret),
            "configured": bool(stored_client_id and stored_secret),
            "source": "database",
        }

    return {
        "client_id": None,
        "client_secret": None,
        "client_id_set": False,
        "client_secret_set": False,
        "configured": False,
        "source": "unset",
    }


def _provider_oauth_credentials(
    provider: str, *, db: Session | None = None, required: bool = False
) -> tuple[str | None, str | None]:
    credential_state = _provider_oauth_credential_state(provider, db)
    client_id = credential_state["client_id"]
    client_secret = credential_state["client_secret"]

    if required and (not client_id or not client_secret):
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.rclone.oauthProviderCredentialsRequired"},
        )
    return client_id, client_secret


def _validate_public_base_url() -> str:
    raw_base_url = _strip_optional(settings.public_base_url)
    if not raw_base_url:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.rclone.oauthPublicBaseUrlRequired"},
        )

    base_url = raw_base_url.rstrip("/")
    parsed = urlparse(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.rclone.oauthPublicBaseUrlInvalid"},
        )
    if parsed.scheme != "https" and parsed.hostname not in RCLONE_OAUTH_LOCAL_HOSTS:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.rclone.oauthPublicBaseUrlHttpsRequired"},
        )
    return base_url


def _borg_ui_oauth_callback_url(provider: str) -> str:
    return f"{_validate_public_base_url()}/api/rclone/oauth/callback/{provider}"


def _borg_ui_oauth_setup_status(
    provider: str, db: Session | None = None
) -> dict[str, Any]:
    if not _provider_supports_borg_ui_oauth(provider):
        return {
            "oauth_mode": "rclone_loopback",
            "oauth_configured": False,
            "oauth_callback_url": None,
            "oauth_setup_key": None,
            "oauth_credentials_source": "unsupported",
            "oauth_client_id_set": False,
            "oauth_client_secret_set": False,
        }

    credential_state = _provider_oauth_credential_state(provider, db)
    if not credential_state["configured"]:
        return {
            "oauth_mode": "borg_ui",
            "oauth_configured": False,
            "oauth_callback_url": None,
            "oauth_setup_key": "backend.errors.rclone.oauthProviderCredentialsRequired",
            "oauth_credentials_source": credential_state["source"],
            "oauth_client_id_set": credential_state["client_id_set"],
            "oauth_client_secret_set": credential_state["client_secret_set"],
        }
    try:
        callback_url = _borg_ui_oauth_callback_url(provider)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return {
            "oauth_mode": "borg_ui",
            "oauth_configured": False,
            "oauth_callback_url": None,
            "oauth_setup_key": detail.get(
                "key", "backend.errors.rclone.oauthPublicBaseUrlInvalid"
            ),
            "oauth_credentials_source": credential_state["source"],
            "oauth_client_id_set": credential_state["client_id_set"],
            "oauth_client_secret_set": credential_state["client_secret_set"],
        }
    return {
        "oauth_mode": "borg_ui",
        "oauth_configured": True,
        "oauth_callback_url": callback_url,
        "oauth_setup_key": None,
        "oauth_credentials_source": credential_state["source"],
        "oauth_client_id_set": credential_state["client_id_set"],
        "oauth_client_secret_set": credential_state["client_secret_set"],
    }


def _serialize_provider_catalog_entry(
    entry: dict[str, Any], db: Session | None = None
) -> dict[str, Any]:
    serialized = dict(entry)
    if entry.get("auth_type") == "oauth_token":
        serialized.update(_borg_ui_oauth_setup_status(str(entry["type"]), db))
    else:
        serialized.update(
            {
                "oauth_mode": "manual",
                "oauth_configured": False,
                "oauth_callback_url": None,
                "oauth_setup_key": None,
                "oauth_credentials_source": "unsupported",
                "oauth_client_id_set": False,
                "oauth_client_secret_set": False,
            }
        )
    return serialized


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


def _oauth_authorization_path(session_id: str) -> str:
    return f"/rclone/oauth/sessions/{session_id}/authorize"


def _validate_local_oauth_url(url: str | None) -> str:
    parsed = urlparse(url or "")
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in RCLONE_OAUTH_LOCAL_HOSTS
    ):
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.rclone.oauthLinkUnavailable"},
        )
    return url or ""


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _google_drive_scope(config: dict[str, Any] | None) -> str:
    configured_scope = str((config or {}).get("scope") or "drive").strip()
    if configured_scope == "drive.readonly":
        return "https://www.googleapis.com/auth/drive.readonly"
    return "https://www.googleapis.com/auth/drive"


def _onedrive_scope(config: dict[str, Any] | None) -> str:
    configured_scope = str((config or {}).get("access_scopes") or "").strip()
    if configured_scope:
        return configured_scope
    return (
        "offline_access Files.Read Files.ReadWrite Files.Read.All Files.ReadWrite.All"
    )


def _google_photos_scope(config: dict[str, Any] | None) -> str:
    if bool((config or {}).get("read_only")):
        return f"openid profile {GOOGLE_PHOTOS_READ_ONLY_SCOPE}"
    return (
        "openid profile "
        f"{GOOGLE_PHOTOS_APPEND_ONLY_SCOPE} "
        f"{GOOGLE_PHOTOS_READ_ONLY_SCOPE} "
        f"{GOOGLE_PHOTOS_READ_WRITE_SCOPE}"
    )


def _hidrive_scope(config: dict[str, Any] | None) -> str:
    scope_access = str((config or {}).get("scope_access") or "rw").strip()
    scope_role = str((config or {}).get("scope_role") or "user").strip()
    if scope_access and scope_role:
        return f"{scope_access},{scope_role}"
    return scope_role or scope_access


def _zoho_region(config: dict[str, Any] | None) -> str:
    region = str((config or {}).get("region") or "com").strip().lower()
    if region not in ZOHO_REGIONS:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidProvider"},
        )
    return region


def _zoho_oauth_url(config: dict[str, Any] | None, path: str) -> str:
    region = _zoho_region(config)
    return f"https://accounts.zoho.{region}/oauth/v2/{path}"


def _sharefile_endpoint_from_callback(callback_params: dict[str, Any] | None) -> str:
    params = callback_params or {}
    subdomain = _strip_optional(str(params.get("subdomain") or ""))
    apicp = _strip_optional(str(params.get("apicp") or ""))
    if (
        not subdomain
        or not apicp
        or not RCLONE_SHAREFILE_HOST_PART_RE.fullmatch(subdomain)
        or not RCLONE_SHAREFILE_HOST_PART_RE.fullmatch(apicp)
    ):
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        )
    return f"https://{subdomain}.{apicp}"


def _provider_oauth_scope(
    provider: str, adapter: RcloneOAuthAdapter, config: dict[str, Any] | None
) -> str | None:
    if provider == "drive":
        return _google_drive_scope(config)
    if provider == "onedrive":
        return _onedrive_scope(config)
    if provider == "gphotos":
        return _google_photos_scope(config)
    if provider == "hidrive":
        return _hidrive_scope(config)
    return adapter.scope


def _provider_oauth_auth_url(
    provider: str, adapter: RcloneOAuthAdapter, config: dict[str, Any] | None
) -> str:
    if provider == "zoho":
        return _zoho_oauth_url(config, "auth")
    return adapter.auth_url


def _provider_oauth_token_url(
    provider: str,
    adapter: RcloneOAuthAdapter,
    config: dict[str, Any] | None,
    callback_params: dict[str, Any] | None = None,
) -> str:
    if provider == "sharefile":
        return f"{_sharefile_endpoint_from_callback(callback_params)}{SHAREFILE_TOKEN_PATH}"
    if provider == "zoho":
        return _zoho_oauth_url(config, "token")
    return adapter.token_url


def _provider_oauth_config_updates(
    provider: str,
    config: dict[str, Any],
    token_response: dict[str, Any],
    callback_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if (
        provider == "pcloud"
        and token_response.get("hostname")
        and not config.get("hostname")
    ):
        updates["hostname"] = str(token_response["hostname"])
    if provider == "sharefile" and not config.get("endpoint"):
        updates["endpoint"] = _sharefile_endpoint_from_callback(callback_params)
    if provider == "zoho" and not config.get("region"):
        updates["region"] = _zoho_region(config)
    return updates


def _provider_authorization_url(
    provider: str,
    *,
    config: dict[str, Any] | None,
    redirect_uri: str,
    state: str,
    db: Session | None = None,
) -> str:
    client_id, _client_secret = _provider_oauth_credentials(
        provider, db=db, required=True
    )
    adapter = BORG_UI_OAUTH_ADAPTERS.get(provider)
    if adapter is None:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.oauthUnsupported"},
        )

    scope = _provider_oauth_scope(provider, adapter, config)
    auth_url = _provider_oauth_auth_url(provider, adapter, config)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        **adapter.extra_auth_params,
    }
    if scope:
        params["scope"] = scope
    return f"{auth_url}?{urlencode(params)}"


def _rclone_token_from_oauth_response(
    payload: dict[str, Any], provider: str | None = None
) -> str:
    token: dict[str, Any] = {}
    adapter = BORG_UI_OAUTH_ADAPTERS.get(provider or "")
    token_type = adapter.token_type if adapter else None
    if payload.get("access_token"):
        token["access_token"] = payload["access_token"]
    if token_type:
        token["token_type"] = token_type
    elif payload.get("token_type"):
        token["token_type"] = payload["token_type"]
    for key in ("refresh_token", "id_token"):
        if payload.get(key):
            token[key] = payload[key]
    expires_in = payload.get("expires_in")
    if expires_in is not None:
        try:
            seconds = int(expires_in)
        except (TypeError, ValueError):
            seconds = 0
        if seconds > 0:
            token["expiry"] = (
                (_utc_now() + timedelta(seconds=seconds))
                .isoformat()
                .replace("+00:00", "Z")
            )
    return json.dumps(token, separators=(",", ":"))


def _serialize_utc_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_token_expiry(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw_value = value.strip()
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_oauth_token_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _oauth_token_status_from_value(value: Any) -> dict[str, Any]:
    token = _parse_oauth_token_value(value)
    if not token:
        return {"status": "missing", "expires_at": None, "refresh_available": False}

    refresh_available = bool(token.get("refresh_token"))
    expires_at = _parse_token_expiry(token.get("expiry"))
    if expires_at is None:
        return {
            "status": "unknown",
            "expires_at": None,
            "refresh_available": refresh_available,
        }

    status_value = "valid"
    if expires_at <= _utc_now():
        status_value = "refreshable" if refresh_available else "expired"
    return {
        "status": status_value,
        "expires_at": _serialize_utc_z(expires_at),
        "refresh_available": refresh_available,
    }


def _oauth_token_status_from_config_values(
    provider: str, values: dict[str, Any] | None
) -> dict[str, Any] | None:
    if provider not in RCLONE_OAUTH_PROVIDER_TYPES:
        return None
    return _oauth_token_status_from_value((values or {}).get("token"))


async def _exchange_borg_ui_oauth_code(
    provider: str,
    code: str,
    redirect_uri: str,
    db: Session | None = None,
    *,
    config: dict[str, Any] | None = None,
    callback_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client_id, client_secret = _provider_oauth_credentials(
        provider, db=db, required=True
    )
    adapter = BORG_UI_OAUTH_ADAPTERS.get(provider)
    if adapter is None:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.oauthUnsupported"},
        )
    token_url = _provider_oauth_token_url(
        provider, adapter, config, callback_params=callback_params
    )
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(token_url, data=data)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        )
    try:
        parsed = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        ) from exc
    if not isinstance(parsed, dict) or not parsed.get("access_token"):
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        )
    return parsed


async def _fetch_onedrive_default_drive(access_token: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                MICROSOFT_GRAPH_ME_DRIVE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        )
    try:
        parsed = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        ) from exc
    if not isinstance(parsed, dict) or not parsed.get("id"):
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthCodeExchangeFailed"},
        )
    return parsed


def _terminate_oauth_session(session: dict[str, Any]) -> None:
    task = session.get("task")
    if task is not None and not task.done():
        task.cancel()
    process = session.get("process")
    if process is not None:
        try:
            process.kill()
        except ProcessLookupError:
            pass


async def _terminate_oauth_session_async(session: dict[str, Any]) -> None:
    task = session.get("task")
    if task is not None and not task.done():
        task.cancel()
    process = session.get("process")
    if process is None:
        return
    try:
        process.kill()
    except ProcessLookupError:
        pass
    wait = getattr(process, "wait", None)
    if wait is None:
        return
    try:
        await asyncio.wait_for(wait(), timeout=2)
    except (asyncio.TimeoutError, ProcessLookupError):
        pass


def _drop_oauth_session(session_id: str) -> dict[str, Any] | None:
    session = RCLONE_OAUTH_SESSIONS.pop(session_id, None)
    if session is not None:
        _terminate_oauth_session(session)
    return session


async def _drop_oauth_session_async(session_id: str) -> dict[str, Any] | None:
    session = RCLONE_OAUTH_SESSIONS.pop(session_id, None)
    if session is not None:
        await _terminate_oauth_session_async(session)
    return session


async def _drop_active_oauth_sessions() -> None:
    for session_id, session in list(RCLONE_OAUTH_SESSIONS.items()):
        if session.get("status") not in {"authorized", "failed"}:
            await _drop_oauth_session_async(session_id)


def _cleanup_rclone_oauth_sessions(now: datetime | None = None) -> None:
    now = now or _utc_now()
    for session_id, session in list(RCLONE_OAUTH_SESSIONS.items()):
        updated_at = session.get("updated_at") or session.get("created_at")
        if not isinstance(updated_at, datetime):
            updated_at = now
        if (now - updated_at).total_seconds() > RCLONE_OAUTH_SESSION_TTL_SECONDS:
            _drop_oauth_session(session_id)

    while len(RCLONE_OAUTH_SESSIONS) > RCLONE_OAUTH_MAX_SESSIONS:
        oldest_session_id = next(iter(RCLONE_OAUTH_SESSIONS))
        _drop_oauth_session(oldest_session_id)


def _store_oauth_session(session_id: str, session: dict[str, Any]) -> None:
    _cleanup_rclone_oauth_sessions()
    RCLONE_OAUTH_SESSIONS[session_id] = session
    RCLONE_OAUTH_SESSIONS.move_to_end(session_id)
    _cleanup_rclone_oauth_sessions()


def _get_oauth_session(session_id: str) -> dict[str, Any] | None:
    _cleanup_rclone_oauth_sessions()
    session = RCLONE_OAUTH_SESSIONS.get(session_id)
    if session is None:
        return None
    session["updated_at"] = _utc_now()
    RCLONE_OAUTH_SESSIONS.move_to_end(session_id)
    return session


def _append_oauth_output(session: dict[str, Any], line: str) -> None:
    output: list[str] = session["output"]
    output.append(line[-RCLONE_OAUTH_OUTPUT_LIMIT_CHARS:])
    total_chars = sum(len(chunk) for chunk in output)
    while len(output) > 1 and total_chars > RCLONE_OAUTH_OUTPUT_LIMIT_CHARS:
        total_chars -= len(output.pop(0))
    if output and total_chars > RCLONE_OAUTH_OUTPUT_LIMIT_CHARS:
        output[0] = output[0][-RCLONE_OAUTH_OUTPUT_LIMIT_CHARS:]
    session["updated_at"] = _utc_now()


def _borg_ui_oauth_safe_session_config(
    session_id: str, session: dict[str, Any]
) -> dict[str, Any] | None:
    if session.get("status") != "authorized" or not session.get("config"):
        return None
    config = dict(session.get("config") or {})
    config.pop("token", None)
    config.pop(BORG_UI_OAUTH_MARKER_KEY, None)
    config.pop(BORG_UI_OAUTH_SESSION_KEY, None)
    config["type"] = session["provider"]
    config[BORG_UI_OAUTH_MARKER_KEY] = session["provider"]
    config[BORG_UI_OAUTH_SESSION_KEY] = session_id
    return config


def _session_token_status(session: dict[str, Any]) -> dict[str, Any] | None:
    config = session.get("config")
    if not isinstance(config, dict):
        return None
    return _oauth_token_status_from_config_values(session["provider"], config)


def _oauth_session_response(session_id: str) -> dict[str, Any]:
    session = RCLONE_OAUTH_SESSIONS[session_id]
    RCLONE_OAUTH_SESSIONS.move_to_end(session_id)
    if session.get("flow") == "borg_ui":
        config = _borg_ui_oauth_safe_session_config(session_id, session)
    else:
        config = session.get("config")
    return {
        "session_id": session_id,
        "provider": session["provider"],
        "status": session["status"],
        "authorization_url": session.get("authorization_url"),
        "local_authorization_url": session.get("local_authorization_url"),
        "oauth_mode": session.get("flow", "rclone_loopback"),
        "config": config,
        "token_status": _session_token_status(session),
        "error": session.get("error"),
    }


async def _fetch_oauth_authorization_redirect(url: str) -> str:
    local_url = _validate_local_oauth_url(url)
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
            response = await client.get(local_url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "key": "backend.errors.rclone.oauthLinkUnavailable",
                "message": str(exc),
            },
        ) from exc

    redirect_url = response.headers.get("location")
    if not redirect_url:
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.rclone.oauthLinkUnavailable"},
        )
    return redirect_url


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


async def _start_borg_ui_oauth_session(
    session_id: str,
    provider: str,
    config: dict[str, Any] | None,
    db: Session | None = None,
) -> dict[str, Any]:
    redirect_uri = _borg_ui_oauth_callback_url(provider)
    state = secrets.token_urlsafe(32)
    authorization_url = _provider_authorization_url(
        provider, config=config, redirect_uri=redirect_uri, state=state, db=db
    )
    now = _utc_now()
    base_config = dict(config or {})
    base_config.pop("token", None)
    base_config.pop(BORG_UI_OAUTH_MARKER_KEY, None)
    session = {
        "provider": provider,
        "flow": "borg_ui",
        "status": "awaiting_callback",
        "authorization_url": _oauth_authorization_path(session_id),
        "local_authorization_url": None,
        "provider_authorization_url": authorization_url,
        "redirect_uri": redirect_uri,
        "state": state,
        "base_config": base_config,
        "config": None,
        "error": None,
        "output": [],
        "created_at": now,
        "updated_at": now,
        "ready_event": None,
        "process": None,
        "task": None,
    }
    _store_oauth_session(session_id, session)
    return _oauth_session_response(session_id)


async def _consume_oauth_process(session_id: str, process) -> None:
    session = RCLONE_OAUTH_SESSIONS.get(session_id)
    if session is None:
        return
    ready_event: asyncio.Event = session["ready_event"]
    try:
        while True:
            raw_line = await process.stdout.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace")
            _append_oauth_output(session, line)
            authorization_url = _extract_oauth_authorization_url(line)
            if authorization_url and not session.get("local_authorization_url"):
                session["local_authorization_url"] = authorization_url
                session["authorization_url"] = _oauth_authorization_path(session_id)
                session["status"] = "awaiting_callback"
                ready_event.set()
            token = _extract_oauth_token("".join(session["output"][-20:]))
            if token:
                session["status"] = "authorized"
                session["config"] = {"type": session["provider"], "token": token}
                session["error"] = None
                ready_event.set()
        return_code = await process.wait()
        if session["status"] != "authorized":
            session["status"] = "failed"
            tail = "".join(session["output"][-12:]).strip()
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
        session["updated_at"] = _utc_now()


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
        key_text = str(key)
        if key_text.startswith("_borg_ui_oauth"):
            continue
        if _is_sensitive_config_key(key_text) and value not in (None, ""):
            redacted[key_text] = REDACTED_CONFIG_VALUE
        elif isinstance(value, dict):
            redacted[key_text] = _redact_config_values(value)
        elif isinstance(value, list):
            redacted[key_text] = [
                _redact_config_values(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key_text] = value
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
        if _is_redacted_config_value(value):
            if key_text in existing:
                resolved[key_text] = existing[key_text]
            continue
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


def _resolve_borg_ui_oauth_session_config(
    provider: str,
    values: dict[str, Any],
    *,
    session_id: str,
) -> dict[str, Any]:
    session = RCLONE_OAUTH_SESSIONS.get(session_id)
    if (
        session is None
        or session.get("flow") != "borg_ui"
        or session.get("provider") != provider
        or session.get("status") != "authorized"
        or not isinstance(session.get("config"), dict)
    ):
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.rclone.oauthNotFound"},
        )

    session_config = dict(session["config"])
    token = session_config.get("token")
    if not token:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.rclone.oauthTokenMissing"},
        )

    resolved = dict(session_config)
    resolved.update(values)
    resolved["type"] = provider
    resolved["token"] = token
    resolved[BORG_UI_OAUTH_MARKER_KEY] = provider
    return resolved


def _managed_config_values(
    provider: str, redacted_config: dict[str, Any] | None, db: Session | None = None
) -> dict[str, str]:
    values = dict(redacted_config or {})
    borg_ui_oauth_provider = values.pop(BORG_UI_OAUTH_MARKER_KEY, None)
    borg_ui_oauth_session_id = values.pop(BORG_UI_OAUTH_SESSION_KEY, None)
    if borg_ui_oauth_session_id:
        if borg_ui_oauth_provider != provider:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.rclone.oauthProviderMismatch"},
            )
        values = _resolve_borg_ui_oauth_session_config(
            provider, values, session_id=str(borg_ui_oauth_session_id)
        )
        borg_ui_oauth_provider = provider
    values = {
        str(key): value
        for key, value in values.items()
        if not str(key).startswith("_borg_ui_oauth")
    }
    values["type"] = str(values.get("type") or provider).strip()
    if borg_ui_oauth_provider == provider and _provider_supports_borg_ui_oauth(
        provider
    ):
        client_id, client_secret = _provider_oauth_credentials(
            provider, db=db, required=True
        )
        values["client_id"] = client_id
        values["client_secret"] = client_secret
    return {
        str(key): _stringify_config_value(value)
        for key, value in values.items()
        if value is not None
        and str(key).strip()
        and not _is_redacted_config_value(value)
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
    db: Session | None = None,
) -> None:
    parser = _load_config(config_path)
    if not parser.has_section(remote_name):
        parser.add_section(remote_name)
    for key, value in _managed_config_values(provider, redacted_config, db).items():
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
    db: Session | None = None,
) -> None:
    parser = _load_config(config_path)
    if old_remote_name != remote_name:
        parser.remove_section(old_remote_name)
    else:
        parser.remove_section(remote_name)
    parser.add_section(remote_name)
    for key, value in _managed_config_values(provider, redacted_config, db).items():
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


def _remote_oauth_token_status(remote: RcloneRemote) -> dict[str, Any] | None:
    if (
        not _provider_catalog_entry(remote.provider)
        or (_provider_catalog_entry(remote.provider) or {}).get("auth_type")
        != "oauth_token"
    ):
        return None
    values: dict[str, Any] = {}
    if remote.config_path:
        try:
            values = _config_section_values(
                _load_config(Path(remote.config_path)), remote.name
            )
        except OSError:
            values = {}
    used_redacted_fallback = False
    if not values:
        values = dict(remote.redacted_config or {})
        used_redacted_fallback = True
    if used_redacted_fallback and _is_redacted_config_value(values.get("token")):
        return {"status": "unknown", "expires_at": None, "refresh_available": False}
    return _oauth_token_status_from_config_values(remote.provider, values)


def _format_bytes(bytes_size: int) -> str:
    value = float(bytes_size)
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if value < 1024.0:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} EB"


def _parse_about_size_value(value: str, unit: str | None) -> int | None:
    try:
        parsed = float(value)
    except ValueError:
        return None

    normalized_unit = (unit or "B").strip().lower()
    multipliers = {
        "b": 1,
        "byte": 1,
        "bytes": 1,
        "kb": 1024,
        "kib": 1024,
        "mb": 1024**2,
        "mib": 1024**2,
        "gb": 1024**3,
        "gib": 1024**3,
        "tb": 1024**4,
        "tib": 1024**4,
        "pb": 1024**5,
        "pib": 1024**5,
        "eb": 1024**6,
        "eib": 1024**6,
    }
    multiplier = multipliers.get(normalized_unit)
    if multiplier is None:
        return None
    return int(parsed * multiplier)


def _parse_rclone_about_storage(stdout: str | None) -> dict[str, Any] | None:
    if not stdout:
        return None

    values: dict[str, int] = {}
    for line in stdout.splitlines():
        match = RCLONE_ABOUT_STORAGE_LINE_RE.match(line)
        if not match:
            continue
        key = match.group(1).lower()
        if key == "free":
            key = "available"
        parsed = _parse_about_size_value(match.group(2), match.group(3))
        if parsed is not None:
            values[key] = parsed

    total = values.get("total")
    used = values.get("used")
    available = values.get("available")

    if total is None and used is not None and available is not None:
        total = used + available
    if used is None and total is not None and available is not None:
        used = max(total - available, 0)
    if available is None and total is not None and used is not None:
        available = max(total - used, 0)

    if total is None or used is None or available is None:
        return None

    percent_used = 0.0 if total <= 0 else round((used / total) * 100, 1)
    return {
        "total": total,
        "used": used,
        "available": available,
        "percent_used": percent_used,
    }


def _serialize_remote_storage(remote: RcloneRemote) -> dict[str, Any] | None:
    if (
        remote.storage_total is None
        or remote.storage_used is None
        or remote.storage_available is None
        or remote.storage_percent_used is None
    ):
        return None

    return {
        "total": remote.storage_total,
        "total_formatted": _format_bytes(remote.storage_total),
        "used": remote.storage_used,
        "used_formatted": _format_bytes(remote.storage_used),
        "available": remote.storage_available,
        "available_formatted": _format_bytes(remote.storage_available),
        "percent_used": remote.storage_percent_used,
        "last_check": _iso(remote.last_storage_check),
    }


def _apply_remote_storage_snapshot(
    remote: RcloneRemote, storage: dict[str, Any] | None
) -> None:
    if storage is None:
        remote.storage_total = None
        remote.storage_used = None
        remote.storage_available = None
        remote.storage_percent_used = None
        remote.last_storage_check = None
        return

    remote.storage_total = storage["total"]
    remote.storage_used = storage["used"]
    remote.storage_available = storage["available"]
    remote.storage_percent_used = storage["percent_used"]
    remote.last_storage_check = datetime.now(timezone.utc)


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
        "oauth_token": _remote_oauth_token_status(remote),
        "storage": _serialize_remote_storage(remote),
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
async def list_providers(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_admin(current_user)
    catalog = await _provider_catalog()
    return {
        "providers": [
            _serialize_provider_catalog_entry(provider, db) for provider in catalog
        ]
    }


def _serialize_oauth_credential_status(provider: str, db: Session) -> dict[str, Any]:
    _require_borg_ui_oauth_provider(provider)
    credential_state = _provider_oauth_credential_state(provider, db)
    try:
        callback_url = _borg_ui_oauth_callback_url(provider)
        setup_key = None
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        callback_url = None
        setup_key = detail.get("key", "backend.errors.rclone.oauthPublicBaseUrlInvalid")

    return {
        "provider": provider,
        "label": _provider_oauth_label(provider),
        "configured": bool(credential_state["configured"] and callback_url),
        "credential_source": credential_state["source"],
        "client_id": credential_state["client_id"],
        "client_id_set": credential_state["client_id_set"],
        "client_secret_set": credential_state["client_secret_set"],
        "callback_url": callback_url,
        "setup_key": setup_key
        if setup_key
        else (
            None
            if credential_state["configured"]
            else "backend.errors.rclone.oauthProviderCredentialsRequired"
        ),
    }


@router.get("/oauth/credentials", dependencies=[RCLONE_FEATURE_DEPENDENCY])
async def list_oauth_credentials(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_admin(current_user)
    return {
        "providers": [
            _serialize_oauth_credential_status(provider, db)
            for provider in sorted(BORG_UI_OAUTH_ADAPTERS)
        ]
    }


@router.put("/oauth/credentials/{provider}", dependencies=[RCLONE_FEATURE_DEPENDENCY])
async def update_oauth_credentials(
    provider: str,
    payload: RcloneOAuthCredentialUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    provider = _normalize_provider(provider)
    _require_borg_ui_oauth_provider(provider)
    credential_row = _provider_oauth_credential_record(provider, db)
    if credential_row is None:
        credential_row = RcloneOAuthProviderCredential(provider=provider)
        db.add(credential_row)

    legacy_settings_row: SystemSettings | None = None
    legacy_client_id_field: str | None = None
    legacy_client_secret_field: str | None = None
    if provider in {"drive", "onedrive"}:
        legacy_settings_row = _get_or_create_system_settings(db)
        legacy_client_id_field, legacy_client_secret_field = (
            _provider_oauth_db_field_names(provider)
        )
    payload_fields = getattr(payload, "model_fields_set", None)
    if payload_fields is None:
        payload_fields = getattr(payload, "__fields_set__", set())

    if "client_id" in payload_fields:
        stripped_client_id = _strip_optional(payload.client_id)
        credential_row.client_id = stripped_client_id
        if legacy_settings_row is not None and legacy_client_id_field is not None:
            setattr(legacy_settings_row, legacy_client_id_field, stripped_client_id)
    if payload.clear_client_secret or "client_secret" in payload_fields:
        stripped_secret = _strip_optional(payload.client_secret)
        credential_row.client_secret_encrypted = None
        if legacy_settings_row is not None and legacy_client_secret_field is not None:
            setattr(legacy_settings_row, legacy_client_secret_field, None)
        if stripped_secret and not payload.clear_client_secret:
            encrypted_secret = encrypt_secret(stripped_secret)
            credential_row.client_secret_encrypted = encrypted_secret
            if (
                legacy_settings_row is not None
                and legacy_client_secret_field is not None
            ):
                setattr(
                    legacy_settings_row, legacy_client_secret_field, encrypted_secret
                )

    db.commit()
    db.refresh(credential_row)
    return _serialize_oauth_credential_status(provider, db)


@router.post(
    "/oauth/sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[RCLONE_FEATURE_DEPENDENCY],
)
async def start_oauth_session(
    payload: RcloneOAuthStart,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    provider = _normalize_provider(payload.provider)
    _require_oauth_provider(provider)
    await _drop_active_oauth_sessions()

    session_id = secrets.token_urlsafe(18)
    mode = (payload.mode or "auto").strip()
    if mode not in {"auto", "borg_ui", "rclone_loopback"}:
        raise HTTPException(
            status_code=400, detail={"key": "backend.errors.rclone.oauthModeInvalid"}
        )
    if mode == "borg_ui" or (
        mode == "auto"
        and _provider_supports_borg_ui_oauth(provider)
        and _borg_ui_oauth_setup_status(provider, db)["oauth_configured"]
    ):
        return await _start_borg_ui_oauth_session(
            session_id, provider, payload.config, db
        )
    if mode == "borg_ui":
        raise HTTPException(
            status_code=409,
            detail={
                "key": _borg_ui_oauth_setup_status(provider, db).get(
                    "oauth_setup_key",
                    "backend.errors.rclone.oauthProviderCredentialsRequired",
                )
            },
        )

    ready_event = asyncio.Event()
    now = _utc_now()
    session = {
        "provider": provider,
        "flow": "rclone_loopback",
        "status": "starting",
        "authorization_url": None,
        "local_authorization_url": None,
        "config": None,
        "error": None,
        "output": [],
        "created_at": now,
        "updated_at": now,
        "ready_event": ready_event,
        "process": None,
        "task": None,
    }
    _store_oauth_session(session_id, session)

    try:
        process = await _start_oauth_process(
            provider,
            client_id=payload.client_id,
            client_secret=payload.client_secret,
        )
    except RcloneUnavailable as exc:
        _drop_oauth_session(session_id)
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


@router.get("/oauth/sessions/{session_id}", dependencies=[RCLONE_FEATURE_DEPENDENCY])
async def get_oauth_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    if _get_oauth_session(session_id) is None:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.rclone.oauthNotFound"}
        )
    await asyncio.sleep(0)
    return _oauth_session_response(session_id)


@router.get(
    "/oauth/sessions/{session_id}/authorize",
    dependencies=[RCLONE_FEATURE_DEPENDENCY],
)
async def open_oauth_authorization(
    session_id: str,
    current_user: User = Depends(get_current_download_user),
):
    _require_admin(current_user)
    session = _get_oauth_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.rclone.oauthNotFound"}
        )
    if session.get("flow") == "borg_ui":
        provider_url = session.get("provider_authorization_url")
        if not provider_url:
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.rclone.oauthLinkUnavailable"},
            )
        return RedirectResponse(provider_url)
    redirect_url = await _fetch_oauth_authorization_redirect(
        session.get("local_authorization_url")
    )
    return RedirectResponse(redirect_url)


@public_router.get("/oauth/callback/{provider}")
async def complete_borg_ui_oauth_callback(
    request: Request,
    provider: str,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    provider = _normalize_provider(provider)
    _require_borg_ui_oauth_provider(provider)
    adapter = BORG_UI_OAUTH_ADAPTERS[provider]
    session_id = None
    session = None
    for candidate_id, candidate in RCLONE_OAUTH_SESSIONS.items():
        state_matches = candidate.get("state") == state
        if not state_matches and adapter.state_optional and not state:
            state_matches = candidate.get("status") == "awaiting_callback"
        if (
            candidate.get("flow") == "borg_ui"
            and candidate.get("provider") == provider
            and state_matches
        ):
            session_id = candidate_id
            session = candidate
            break
    if session_id is None or session is None:
        raise HTTPException(
            status_code=400, detail={"key": "backend.errors.rclone.oauthStateInvalid"}
        )

    if error:
        session["status"] = "failed"
        session["error"] = error_description or error
        session["updated_at"] = _utc_now()
        raise HTTPException(
            status_code=400, detail={"key": "backend.errors.rclone.oauthProviderDenied"}
        )
    if not code:
        session["status"] = "failed"
        session["error"] = (
            "OAuth provider callback did not include an authorization code."
        )
        session["updated_at"] = _utc_now()
        raise HTTPException(
            status_code=400, detail={"key": "backend.errors.rclone.oauthCodeMissing"}
        )

    callback_params = dict(request.query_params)
    base_config = dict(session.get("base_config") or {})
    exchange_kwargs: dict[str, Any] = {}
    if provider == "sharefile":
        exchange_kwargs["callback_params"] = callback_params
    if provider == "zoho":
        exchange_kwargs["config"] = base_config
    token_response = await _exchange_borg_ui_oauth_code(
        provider, code, session["redirect_uri"], db, **exchange_kwargs
    )
    config = dict(base_config)
    if (
        provider == "onedrive"
        and not config.get("drive_id")
        and token_response.get("access_token")
    ):
        default_drive = await _fetch_onedrive_default_drive(
            str(token_response["access_token"])
        )
        config["drive_id"] = str(default_drive["id"])
        if default_drive.get("driveType") and not config.get("drive_type"):
            config["drive_type"] = str(default_drive["driveType"])
    config.update(
        _provider_oauth_config_updates(
            provider, config, token_response, callback_params=callback_params
        )
    )
    config.update(
        {
            "type": provider,
            "token": _rclone_token_from_oauth_response(token_response, provider),
            BORG_UI_OAUTH_MARKER_KEY: provider,
        }
    )
    session["status"] = "authorized"
    session["config"] = config
    session["error"] = None
    session["updated_at"] = _utc_now()
    RCLONE_OAUTH_SESSIONS.move_to_end(session_id)
    return HTMLResponse(
        "<!doctype html><title>Borg UI OAuth</title>"
        '<main style="font-family: system-ui, sans-serif; max-width: 42rem; '
        'margin: 4rem auto; padding: 0 1rem; line-height: 1.5;">'
        "<h1>Authorization complete</h1>"
        "<p>Borg UI received the provider callback and stored the token result "
        "server-side for this setup session.</p>"
        "<p><strong>Return to Borg UI</strong>. The Cloud Storage dialog will "
        "check authorization automatically; save the remote when the token is "
        "ready.</p>"
        "</main>"
    )


@router.delete(
    "/oauth/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[RCLONE_FEATURE_DEPENDENCY],
)
async def cancel_oauth_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    session = await _drop_oauth_session_async(session_id)
    if session is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/remotes")
async def list_remotes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    remotes = db.query(RcloneRemote).order_by(RcloneRemote.name).all()
    return {"remotes": [_serialize_remote(remote) for remote in remotes]}


@router.post(
    "/remotes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[RCLONE_FEATURE_DEPENDENCY],
)
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
            resolved_config_for_db = _managed_config_values(provider, raw_config, db)
            remote.config_path = str(config_file)
            remote.redacted_config = _redact_config_values(resolved_config_for_db)
            _write_managed_remote_config(
                config_file,
                remote_name=remote_name,
                provider=provider,
                redacted_config=raw_config,
                db=db,
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


@router.put("/remotes/{remote_id}", dependencies=[RCLONE_FEATURE_DEPENDENCY])
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
            if (
                payload.provider is not None
                and provider != remote.provider
                and payload.redacted_config is None
            ):
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.rclone.updateUnsupported"},
                )
            config_file = _managed_config_path_for_remote(remote)
            original_parser = _load_config(config_file)
            existing_config = _config_section_values(original_parser, old_remote_name)
            if payload.redacted_config is not None:
                config_for_write = _preserve_redacted_config_values(
                    payload.redacted_config, existing_config
                )
            elif existing_config:
                config_for_write = existing_config
            else:
                config_for_write = _preserve_redacted_config_values(
                    remote.redacted_config or {}, existing_config
                )
            resolved_config_for_db = _managed_config_values(
                provider, config_for_write, db
            )
            _replace_managed_remote_config(
                config_file,
                old_remote_name=old_remote_name,
                remote_name=remote_name,
                provider=provider,
                redacted_config=config_for_write,
                db=db,
            )
            wrote_config = True
            remote.config_path = str(config_file)
            redacted_config = _redact_config_values(resolved_config_for_db)
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


@router.delete(
    "/remotes/{remote_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[RCLONE_FEATURE_DEPENDENCY],
)
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


@router.post("/remotes/{remote_id}/test", dependencies=[RCLONE_FEATURE_DEPENDENCY])
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
        _apply_remote_storage_snapshot(
            remote, _parse_rclone_about_storage(result.get("stdout"))
        )
    else:
        remote.last_test_status = "failed"
        remote.last_error = result.get("stderr") or "rclone remote test failed"
    db.commit()
    db.refresh(remote)
    return {"status": remote.last_test_status, "remote": _serialize_remote(remote)}


@router.get("/remotes/{remote_id}/browse", dependencies=[RCLONE_FEATURE_DEPENDENCY])
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
