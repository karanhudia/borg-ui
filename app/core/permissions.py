from __future__ import annotations

from typing import Dict, List, Optional


GLOBAL_ROLES: List[dict[str, object]] = [
    {"id": "viewer", "rank": 1, "scope": "global"},
    {"id": "operator", "rank": 2, "scope": "global"},
    {"id": "admin", "rank": 3, "scope": "global"},
]

REPOSITORY_ROLES: List[dict[str, object]] = [
    {"id": "viewer", "rank": 1, "scope": "repository"},
    {"id": "operator", "rank": 2, "scope": "repository"},
]

GLOBAL_ROLE_RANK: Dict[str, int] = {role["id"]: int(role["rank"]) for role in GLOBAL_ROLES}
REPOSITORY_ROLE_RANK: Dict[str, int] = {role["id"]: int(role["rank"]) for role in REPOSITORY_ROLES}

# Minimum global role required to use a system-wide capability.
GLOBAL_PERMISSION_RULES: Dict[str, str] = {
    "repositories.manage_all": "admin",
    "repositories.create": "admin",
    "repositories.import": "admin",
    "settings.users.manage": "admin",
    "settings.system.manage": "admin",
    "settings.mqtt.manage": "admin",
    "settings.beta.manage": "admin",
    "settings.cache.manage": "admin",
    "settings.logs.manage": "admin",
    "settings.packages.manage": "admin",
    "settings.ssh.manage": "admin",
    "settings.scripts.manage": "admin",
    "settings.export_import.manage": "admin",
    "settings.mounts.manage": "operator",
    "activity.view_all": "admin",
}

# Minimum repository role required to perform a repository-scoped action.
REPOSITORY_ACTION_RULES: Dict[str, str] = {
    "view": "viewer",
    "restore": "viewer",
    "backup": "operator",
    "maintenance": "operator",
    "delete_archive": "operator",
}

ASSIGNABLE_REPOSITORY_ROLES_BY_GLOBAL_ROLE: Dict[str, List[str]] = {
    "viewer": ["viewer"],
    "operator": ["viewer", "operator"],
    "admin": ["viewer", "operator"],
}


def default_repository_role_for_global_role(role: str) -> Optional[str]:
    if role == "admin":
        return None
    if role in ASSIGNABLE_REPOSITORY_ROLES_BY_GLOBAL_ROLE:
        return role
    return None


def normalize_repository_role_for_global_role(
    global_role: str,
    repository_role: Optional[str],
) -> Optional[str]:
    if repository_role is None:
        return None
    allowed_roles = ASSIGNABLE_REPOSITORY_ROLES_BY_GLOBAL_ROLE.get(global_role, [])
    if repository_role in allowed_roles:
        return repository_role
    return default_repository_role_for_global_role(global_role)


def is_repository_role_assignable_to_global_role(
    global_role: str,
    repository_role: Optional[str],
) -> bool:
    if repository_role is None:
        return True
    allowed_roles = ASSIGNABLE_REPOSITORY_ROLES_BY_GLOBAL_ROLE.get(global_role, [])
    return repository_role in allowed_roles


def has_global_permission(role: str, permission: str) -> bool:
    required_role = GLOBAL_PERMISSION_RULES.get(permission)
    if not required_role:
        return False
    return GLOBAL_ROLE_RANK.get(role, 0) >= GLOBAL_ROLE_RANK.get(required_role, 0)


def get_global_permissions_for_role(role: str) -> List[str]:
    return sorted(
        permission
        for permission in GLOBAL_PERMISSION_RULES
        if has_global_permission(role, permission)
    )


def can_repository_role_perform(role: str, action: str) -> bool:
    required_role = REPOSITORY_ACTION_RULES.get(action)
    if not required_role:
        return False
    return REPOSITORY_ROLE_RANK.get(role, 0) >= REPOSITORY_ROLE_RANK.get(required_role, 0)


def serialize_authorization_model() -> dict:
    return {
        "global_roles": GLOBAL_ROLES,
        "repository_roles": REPOSITORY_ROLES,
        "global_permission_rules": GLOBAL_PERMISSION_RULES,
        "repository_action_rules": REPOSITORY_ACTION_RULES,
        "assignable_repository_roles_by_global_role": ASSIGNABLE_REPOSITORY_ROLES_BY_GLOBAL_ROLE,
    }
