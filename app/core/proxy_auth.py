from __future__ import annotations

from typing import Any

from app.config import settings


def inspect_proxy_auth_config() -> dict[str, Any]:
    if not settings.disable_authentication:
        return {"enabled": False, "warnings": []}

    warnings: list[dict[str, str]] = []

    if settings.host not in {"127.0.0.1", "localhost", "::1"}:
        warnings.append(
            {
                "code": "broad_bind",
                "message": "Borg UI is bound broadly while proxy authentication is enabled. Ensure only your authenticated reverse proxy can reach it.",
            }
        )

    proxy_auth_header = settings.proxy_auth_header.strip()
    proxy_auth_header_normalized = proxy_auth_header.lower()
    conflicting_headers = {"authorization", "x-borg-authorization"}
    if proxy_auth_header_normalized in conflicting_headers:
        warnings.append(
            {
                "code": "username_header_conflict",
                "message": f'The proxy authentication username header "{proxy_auth_header}" conflicts with API authentication headers.',
            }
        )

    role_header = (settings.proxy_auth_role_header or "").strip()
    role_header_normalized = role_header.lower()
    if role_header and role_header_normalized == proxy_auth_header_normalized:
        warnings.append(
            {
                "code": "role_header_matches_username",
                "message": "The proxy role header matches the proxy username header. Use distinct trusted headers.",
            }
        )

    all_repositories_role_header = (
        settings.proxy_auth_all_repositories_role_header or ""
    ).strip()
    all_repositories_role_header_normalized = all_repositories_role_header.lower()
    if (
        all_repositories_role_header
        and all_repositories_role_header_normalized == proxy_auth_header_normalized
    ):
        warnings.append(
            {
                "code": "all_repo_header_matches_username",
                "message": "The proxy all-repositories role header matches the proxy username header. Use distinct trusted headers.",
            }
        )

    if (
        role_header
        and all_repositories_role_header
        and role_header_normalized == all_repositories_role_header_normalized
    ):
        warnings.append(
            {
                "code": "role_headers_conflict",
                "message": "The proxy role header and all-repositories role header should be distinct.",
            }
        )

    email_header = (settings.proxy_auth_email_header or "").strip()
    email_header_normalized = email_header.lower()
    if email_header and email_header_normalized == proxy_auth_header_normalized:
        warnings.append(
            {
                "code": "email_header_matches_username",
                "message": "The proxy email header matches the proxy username header. Use distinct trusted headers.",
            }
        )

    full_name_header = (settings.proxy_auth_full_name_header or "").strip()
    full_name_header_normalized = full_name_header.lower()
    if full_name_header and full_name_header_normalized == proxy_auth_header_normalized:
        warnings.append(
            {
                "code": "full_name_header_matches_username",
                "message": "The proxy full-name header matches the proxy username header. Use distinct trusted headers.",
            }
        )

    if (
        email_header
        and role_header
        and email_header_normalized == role_header_normalized
    ):
        warnings.append(
            {
                "code": "email_header_matches_role",
                "message": "The proxy email header matches the proxy role header. Use distinct trusted headers.",
            }
        )

    if (
        full_name_header
        and role_header
        and full_name_header_normalized == role_header_normalized
    ):
        warnings.append(
            {
                "code": "full_name_header_matches_role",
                "message": "The proxy full-name header matches the proxy role header. Use distinct trusted headers.",
            }
        )

    return {"enabled": True, "warnings": warnings}
