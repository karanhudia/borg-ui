from __future__ import annotations

from enum import Enum
from typing import Optional
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.services.licensing_service import get_effective_plan_value


class Plan(str, Enum):
    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"


_RANK = {Plan.COMMUNITY: 0, Plan.PRO: 1, Plan.ENTERPRISE: 2}

# Single source of truth: feature name → minimum plan required
FEATURES: dict[str, Plan] = {
    "borg_v2": Plan.PRO,
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


def require_feature(feature: str):
    """FastAPI dependency factory. Usage: dependencies=[require_feature("borg_v2")]"""

    def _check(db: Session = Depends(get_db)):
        current = get_current_plan(db)
        required = FEATURES.get(feature)
        if required is None:
            raise ValueError(
                f"Unknown feature: {feature!r}. Valid features: {list(FEATURES)}"
            )
        if not plan_includes(current, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "key": "backend.errors.plan.featureNotAvailable",
                    "feature": feature,
                    "required": required.value,
                    "current": current.value,
                },
            )

    return Depends(_check)
