from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.features import FEATURES, Plan, get_current_plan, plan_includes

if TYPE_CHECKING:
    from app.database.models import BackupPlan


BACKUP_PLAN_ADVANCED_FEATURE = "backup_plan_multi_repository"


@dataclass(frozen=True)
class BackupPlanFeatureDecision:
    allowed: bool
    current: Plan
    required: Plan
    feature: str
    reason: Optional[str]


def evaluate_backup_plan_feature_access(
    db: Session, *, enabled_repository_count: int, repository_run_mode: str
) -> BackupPlanFeatureDecision:
    current_plan = get_current_plan(db)
    required = FEATURES[BACKUP_PLAN_ADVANCED_FEATURE]
    reason = None
    if enabled_repository_count > 1:
        reason = "multi_repository"
    elif repository_run_mode == "parallel":
        reason = "parallel"

    allowed = reason is None or plan_includes(current_plan, required)
    return BackupPlanFeatureDecision(
        allowed=allowed,
        current=current_plan,
        required=required,
        feature=BACKUP_PLAN_ADVANCED_FEATURE,
        reason=reason,
    )


def evaluate_backup_plan_access(
    db: Session, plan: BackupPlan
) -> BackupPlanFeatureDecision:
    return evaluate_backup_plan_feature_access(
        db,
        enabled_repository_count=sum(1 for link in plan.repositories if link.enabled),
        repository_run_mode=plan.repository_run_mode,
    )


def raise_backup_plan_feature_error(
    decision: BackupPlanFeatureDecision,
    *,
    status_code: int = status.HTTP_403_FORBIDDEN,
) -> None:
    if decision.allowed:
        return
    raise HTTPException(
        status_code=status_code,
        detail={
            "key": "backend.errors.plan.featureNotAvailable",
            "feature": decision.feature,
            "required": decision.required.value,
            "current": decision.current.value,
        },
    )


def require_backup_plan_feature_access(
    db: Session, *, enabled_repository_count: int, repository_run_mode: str
) -> None:
    decision = evaluate_backup_plan_feature_access(
        db,
        enabled_repository_count=enabled_repository_count,
        repository_run_mode=repository_run_mode,
    )
    raise_backup_plan_feature_error(decision)
