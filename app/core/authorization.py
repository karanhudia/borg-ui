from dataclasses import dataclass
from typing import Dict, Tuple

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_any_role
from app.database.database import get_db


@dataclass(frozen=True)
class EndpointPolicy:
    roles: Tuple[str, ...]
    detail_key: str


def _normalize_path(path: str) -> str:
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


ENDPOINT_POLICIES: Dict[Tuple[str, str], EndpointPolicy] = {
    ("PUT", "/api/settings/system"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/settings/refresh-stats"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("GET", "/api/settings/users"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/settings/users"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("PUT", "/api/settings/users/{user_id}"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("DELETE", "/api/settings/users/{user_id}"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/settings/users/{user_id}/reset-password"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/settings/system/cleanup"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/settings/system/logs/cleanup"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/settings/cache/clear"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("PUT", "/api/settings/cache/settings"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("GET", "/api/packages"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/packages"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/packages/{package_id}/install"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("PUT", "/api/packages/{package_id}"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("DELETE", "/api/packages/{package_id}"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/packages/{package_id}/reinstall"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("GET", "/api/packages/jobs/{job_id}"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("GET", "/api/packages/jobs"): EndpointPolicy(("admin",), "backend.errors.settings.adminAccessRequired"),
    ("POST", "/api/repositories"): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("POST", "/api/repositories/import"): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("POST", "/api/repositories/{repo_id}/keyfile"): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("GET", "/api/repositories/{repo_id}/keyfile"): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("PUT", "/api/repositories/{repo_id}"): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("DELETE", "/api/repositories/{repo_id}"): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("POST", "/api/repositories/{repo_id}/compact"): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("POST", "/api/repositories/{repo_id}/prune"): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("POST", "/api/ssh-keys"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("POST", "/api/ssh-keys/generate"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("POST", "/api/ssh-keys/import"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("POST", "/api/ssh-keys/quick-setup"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("POST", "/api/ssh-keys/{key_id}/deploy"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("PUT", "/api/ssh-keys/{key_id}"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("DELETE", "/api/ssh-keys/{key_id}"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("PATCH", "/api/ssh-keys/connections/{connection_id}/backup-source"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("POST", "/api/ssh-keys/connections/{connection_id}/verify-borg"): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("POST", "/api/mounts/borg"): EndpointPolicy(("admin", "operator"), "backend.errors.mounts.operatorAccessRequired"),
    ("DELETE", "/api/mounts/borg/{mount_id}"): EndpointPolicy(("admin", "operator"), "backend.errors.mounts.operatorAccessRequired"),
    ("POST", "/api/schedule"): EndpointPolicy(("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"),
    ("PUT", "/api/schedule/{job_id}"): EndpointPolicy(("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"),
    ("DELETE", "/api/schedule/{job_id}"): EndpointPolicy(("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"),
    ("POST", "/api/schedule/{job_id}/toggle"): EndpointPolicy(("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"),
    ("POST", "/api/schedule/{job_id}/duplicate"): EndpointPolicy(("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"),
    ("POST", "/api/schedule/{job_id}/run-now"): EndpointPolicy(("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"),
}


async def authorize_request(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    route = request.scope.get("route")
    route_path = _normalize_path(getattr(route, "path", request.url.path))
    policy = ENDPOINT_POLICIES.get((request.method.upper(), route_path))
    if policy is None:
        return

    current_user = await get_current_user(request, db)
    require_any_role(current_user, *policy.roles, detail_key=policy.detail_key)
