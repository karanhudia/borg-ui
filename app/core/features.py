from enum import Enum
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.database.models import SystemSettings


class Plan(str, Enum):
    COMMUNITY  = "community"
    PRO        = "pro"
    ENTERPRISE = "enterprise"


_RANK = {Plan.COMMUNITY: 0, Plan.PRO: 1, Plan.ENTERPRISE: 2}

# Single source of truth: feature name → minimum plan required
FEATURES: dict[str, Plan] = {
    "borg_v2":    Plan.PRO,
    "multi_user": Plan.PRO,        # >1 user (up to 5)
    "extra_users": Plan.ENTERPRISE, # >5 users
}

# User limits per plan (None = unlimited)
USER_LIMITS: dict[Plan, int | None] = {
    Plan.COMMUNITY:  1,
    Plan.PRO:        5,
    Plan.ENTERPRISE: None,
}


def plan_includes(current: Plan, required: Plan) -> bool:
    return _RANK[current] >= _RANK[required]


def get_current_plan(db: Session) -> Plan:
    settings = db.query(SystemSettings).first()
    if not settings:
        return Plan.COMMUNITY
    return Plan(settings.plan or "pro")


def require_feature(feature: str):
    """FastAPI dependency factory. Usage: dependencies=[require_feature("borg_v2")]"""
    def _check(db: Session = Depends(get_db)):
        current = get_current_plan(db)
        required = FEATURES.get(feature)
        if required is None:
            raise ValueError(f"Unknown feature: {feature!r}. Valid features: {list(FEATURES)}")
        if not plan_includes(current, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "key": "backend.errors.plan.featureNotAvailable",
                    "feature": feature,
                    "required": required.value,
                    "current": current.value,
                }
            )
    return Depends(_check)
