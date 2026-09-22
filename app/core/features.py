from __future__ import annotations

from enum import Enum
from typing import Optional
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.services.licensing_service import get_effective_plan_value, get_feature_access


class Plan(str, Enum):
    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"


_RANK = {Plan.COMMUNITY: 0, Plan.PRO: 1, Plan.ENTERPRISE: 2}

# Single source of truth: feature name → minimum plan required
FEATURES: dict[str, Plan] = {
    "borg_v2": Plan.PRO,
    "backup_plan_multi_repository": Plan.PRO,
    "backup_plan_mixed_sources": Plan.PRO,
    "rclone": Plan.PRO,
    "managed_agents": Plan.PRO,
    "remote_clients": Plan.PRO,
    "database_discovery": Plan.PRO,
    "container_backups": Plan.PRO,
    "backup_reports": Plan.PRO,
    "alerting_monitoring": Plan.PRO,
    "archive_history": Plan.PRO,  # change deltas, file history, search, outlier flags
    "multi_user": Plan.COMMUNITY,  # up to 5 users
    "extra_users": Plan.PRO,  # >5 users (up to 10 on Pro)
    "rbac": Plan.ENTERPRISE,  # role-based access control
}

# User limits per plan (None = unlimited)
USER_LIMITS: dict[Plan, Optional[int]] = {
    Plan.COMMUNITY: 5,
    Plan.PRO: 10,
    Plan.ENTERPRISE: None,
}


def plan_includes(current: Plan, required: Plan) -> bool:
    return _RANK[current] >= _RANK[required]


def get_current_plan(db: Session) -> Plan:
    return Plan(get_effective_plan_value(db))


def has_feature(db: Session, feature: str) -> bool:
    """Whether this install may use one feature right now.

    The plan rank is the usual answer, but not the only one: an entitlement
    can carry an override that grants a single feature on a plan that does
    not include it, which is what a feature trial is. Asking the rank alone
    left the trial granted in the summary the UI reads and refused by every
    gate behind it (spec 2026-09-21, section 3).
    """
    if feature not in FEATURES:
        raise ValueError(
            f"Unknown feature: {feature!r}. Valid features: {list(FEATURES)}"
        )
    return get_feature_access(db).get(feature, False)


def require_feature_access(
    db: Session, feature: str, *, status_code: int = status.HTTP_403_FORBIDDEN
) -> None:
    current = get_current_plan(db)
    required = FEATURES.get(feature)
    if required is None:
        raise ValueError(
            f"Unknown feature: {feature!r}. Valid features: {list(FEATURES)}"
        )
    if not has_feature(db, feature):
        raise HTTPException(
            status_code=status_code,
            detail={
                "key": "backend.errors.plan.featureNotAvailable",
                "feature": feature,
                "required": required.value,
                "current": current.value,
            },
        )


def require_feature(feature: str):
    """FastAPI dependency factory. Usage: dependencies=[require_feature("borg_v2")]"""

    def _check(db: Session = Depends(get_db)):
        require_feature_access(db, feature)

    return Depends(_check)
