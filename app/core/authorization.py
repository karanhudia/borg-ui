import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Pattern, Tuple

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


def _strip_root_path(path: str, root_path: str) -> str:
    """Drop the mount prefix so matching is done on the app-relative path.

    Under a non-empty ``BASE_PATH`` (``FastAPI(root_path=...)``), the ASGI
    server can leave ``request.url.path`` carrying the mount prefix while
    ``scope["root_path"]`` holds it separately. Stripping it on a path-segment
    boundary keeps the policy lookup working — otherwise the prefixed path
    misses every template and the guard is skipped. A no-op when no prefix is
    present.
    """
    root_path = root_path.rstrip("/")
    if not root_path:
        return path
    if path == root_path:
        return "/"
    if path.startswith(root_path + "/"):
        return path[len(root_path) :]
    return path


def _template_to_regex(path: str) -> Pattern[str]:
    """Compile a policy path template into an anchored regex.

    ``/api/repositories/{repo_id}/wipe-jobs/{job_id}`` becomes
    ``^/api/repositories/[^/]+/wipe-jobs/[^/]+$``. Splitting on ``{...}`` also
    absorbs converter forms such as ``{repo_id:int}``.
    """
    parts = re.split(r"\{[^/]+\}", path)
    return re.compile("^" + "[^/]+".join(re.escape(part) for part in parts) + "$")


ENDPOINT_POLICIES: Dict[Tuple[str, str], EndpointPolicy] = {
    ("PUT", "/api/settings/system"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/settings/refresh-stats"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("GET", "/api/settings/users"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/settings/users"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("PUT", "/api/settings/users/{user_id}"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("DELETE", "/api/settings/users/{user_id}"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/settings/users/{user_id}/reset-password"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/settings/system/cleanup"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/settings/system/logs/cleanup"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/settings/cache/clear"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("PUT", "/api/settings/cache/settings"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("GET", "/api/packages"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/packages"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/packages/{package_id}/install"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("PUT", "/api/packages/{package_id}"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("DELETE", "/api/packages/{package_id}"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/packages/{package_id}/reinstall"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("GET", "/api/packages/jobs/{job_id}"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("GET", "/api/packages/jobs"): EndpointPolicy(
        ("admin",), "backend.errors.settings.adminAccessRequired"
    ),
    ("POST", "/api/repositories"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("POST", "/api/repositories/import"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("POST", "/api/repositories/{repo_id}/keyfile"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("GET", "/api/repositories/{repo_id}/keyfile"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("PUT", "/api/repositories/{repo_id}"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("DELETE", "/api/repositories/{repo_id}"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("POST", "/api/repositories/{repo_id}/compact"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("POST", "/api/repositories/{repo_id}/prune"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("POST", "/api/repositories/{repo_id}/wipe-preview"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("POST", "/api/repositories/{repo_id}/wipe"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    ("GET", "/api/repositories/{repo_id}/wipe-jobs/{job_id}"): EndpointPolicy(
        ("admin",), "backend.errors.repo.adminAccessRequired"
    ),
    (
        "POST",
        "/api/repositories/{repo_id}/wipe-jobs/{job_id}/cancel",
    ): EndpointPolicy(("admin",), "backend.errors.repo.adminAccessRequired"),
    ("POST", "/api/ssh-keys"): EndpointPolicy(
        ("admin",), "backend.errors.ssh.adminAccessRequired"
    ),
    ("POST", "/api/ssh-keys/generate"): EndpointPolicy(
        ("admin",), "backend.errors.ssh.adminAccessRequired"
    ),
    ("POST", "/api/ssh-keys/import"): EndpointPolicy(
        ("admin",), "backend.errors.ssh.adminAccessRequired"
    ),
    ("POST", "/api/ssh-keys/quick-setup"): EndpointPolicy(
        ("admin",), "backend.errors.ssh.adminAccessRequired"
    ),
    ("POST", "/api/ssh-keys/{key_id}/deploy"): EndpointPolicy(
        ("admin",), "backend.errors.ssh.adminAccessRequired"
    ),
    ("PUT", "/api/ssh-keys/{key_id}"): EndpointPolicy(
        ("admin",), "backend.errors.ssh.adminAccessRequired"
    ),
    ("DELETE", "/api/ssh-keys/{key_id}"): EndpointPolicy(
        ("admin",), "backend.errors.ssh.adminAccessRequired"
    ),
    (
        "PATCH",
        "/api/ssh-keys/connections/{connection_id}/backup-source",
    ): EndpointPolicy(("admin",), "backend.errors.ssh.adminAccessRequired"),
    ("POST", "/api/ssh-keys/connections/{connection_id}/verify-borg"): EndpointPolicy(
        ("admin",), "backend.errors.ssh.adminAccessRequired"
    ),
    ("POST", "/api/mounts/borg"): EndpointPolicy(
        ("admin", "operator"), "backend.errors.mounts.operatorAccessRequired"
    ),
    ("POST", "/api/mounts/borg/unmount/{mount_id}"): EndpointPolicy(
        ("admin", "operator"), "backend.errors.mounts.operatorAccessRequired"
    ),
    ("POST", "/api/schedule"): EndpointPolicy(
        ("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"
    ),
    ("PUT", "/api/schedule/{job_id}"): EndpointPolicy(
        ("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"
    ),
    ("DELETE", "/api/schedule/{job_id}"): EndpointPolicy(
        ("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"
    ),
    ("POST", "/api/schedule/{job_id}/toggle"): EndpointPolicy(
        ("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"
    ),
    ("POST", "/api/schedule/{job_id}/duplicate"): EndpointPolicy(
        ("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"
    ),
    ("POST", "/api/schedule/{job_id}/run-now"): EndpointPolicy(
        ("admin", "operator"), "backend.errors.schedule.operatorAccessRequired"
    ),
}


def _is_param_segment(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _templates_overlap(a: str, b: str) -> bool:
    """True when some concrete path would match both templates.

    They overlap iff they have the same number of segments and, at every
    position, the segments are equal or at least one is a ``{param}``.
    """
    seg_a = a.strip("/").split("/")
    seg_b = b.strip("/").split("/")
    if len(seg_a) != len(seg_b):
        return False
    return all(
        _is_param_segment(x) or _is_param_segment(y) or x == y
        for x, y in zip(seg_a, seg_b)
    )


def _assert_unambiguous_policies() -> None:
    """No two same-method templates may match the same concrete path.

    FastAPI does not reject overlapping routes — it resolves them by declaration
    order — so the guard must not rely on that. Enforcing uniqueness here keeps a
    single match per request: a future overlap fails loudly at import instead of
    silently resolving to the wrong policy.
    """
    by_method: Dict[str, List[str]] = {}
    for method, path in ENDPOINT_POLICIES:
        by_method.setdefault(method, []).append(path)
    for method, paths in by_method.items():
        for index, first in enumerate(paths):
            for second in paths[index + 1 :]:
                if _templates_overlap(first, second):
                    raise ValueError(
                        f"Ambiguous authorization policies for {method}: "
                        f"{first!r} overlaps {second!r}"
                    )


_assert_unambiguous_policies()

# Policies compiled once at import, matched against the concrete request path.
# Uniqueness is enforced above, so the first regex match is the only match.
_COMPILED_POLICIES: List[Tuple[str, Pattern[str], EndpointPolicy]] = [
    (method, _template_to_regex(path), policy)
    for (method, path), policy in ENDPOINT_POLICIES.items()
]


def _match_policy(method: str, path: str) -> Optional[EndpointPolicy]:
    """Resolve the policy for a request from its concrete path.

    Matching the concrete ``request.url.path`` against our own templates keeps
    authorization independent of how FastAPI names the matched route: since
    0.141 a router-level dependency sees the router-relative ``route.path``
    (``/{job_id}``) rather than the full path, which silently defeated a lookup
    keyed on the full template.
    """
    path = _normalize_path(path)
    for policy_method, pattern, policy in _COMPILED_POLICIES:
        if policy_method == method and pattern.match(path):
            return policy
    return None


async def authorize_request(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    method = request.method.upper()
    # Match the path as received first; only if that misses retry with the
    # BASE_PATH/root_path prefix stripped. As-is-first never breaks a path that
    # already matches, so a mount prefix that happens to prefix a real route
    # cannot cause a wrongful strip.
    policy = _match_policy(method, request.url.path)
    if policy is None:
        stripped = _strip_root_path(
            request.url.path, request.scope.get("root_path") or ""
        )
        if stripped != request.url.path:
            policy = _match_policy(method, stripped)
    if policy is None:
        return

    current_user = await get_current_user(request, db)
    require_any_role(current_user, *policy.roles, detail_key=policy.detail_key)
