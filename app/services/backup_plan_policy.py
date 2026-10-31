from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.borg_major import is_borg2
from app.core.features import FEATURES, Plan, get_current_plan, has_feature
from app.utils.source_locations import decode_source_locations

if TYPE_CHECKING:
    from app.database.models import BackupPlan


BACKUP_PLAN_ADVANCED_FEATURE = "backup_plan_multi_repository"
BACKUP_PLAN_MIXED_SOURCES_FEATURE = "backup_plan_mixed_sources"
CONTAINER_BACKUPS_FEATURE = "container_backups"
DATABASE_DISCOVERY_FEATURE = "database_discovery"
BORG2_FEATURE = "borg_v2"

# A scheduled run skipped because the plan no longer includes what it needs.
PLAN_REQUIRED_SKIP_REASON = "plan_required"


def plan_required_message(feature: str, required: Plan) -> str:
    what = (
        "Borg 2 repositories need"
        if feature == BORG2_FEATURE
        else "This schedule needs"
    )
    return (
        f"Scheduled backups are paused: {what} the {required.value.title()} plan, "
        "which this install no longer has. Existing archives are untouched and "
        "can still be browsed and downloaded. Backups resume once the plan is active."
    )


@dataclass(frozen=True)
class BackupPlanFeatureDecision:
    allowed: bool
    current: Plan
    required: Plan
    feature: str
    reason: Optional[str]


def _source_type_feature_requirement(
    source_locations: Optional[list[dict[str, Any]]],
) -> tuple[Optional[str], Optional[str]]:
    source_types = {
        str(location.get("source_type") or "").strip().lower()
        for location in source_locations or []
        if str(location.get("source_type") or "").strip()
    }
    if any(location.get("database") for location in source_locations or []):
        return DATABASE_DISCOVERY_FEATURE, "database_source"
    if any(location.get("container") for location in source_locations or []):
        return CONTAINER_BACKUPS_FEATURE, "container_source"
    if len(source_types) > 1:
        return BACKUP_PLAN_MIXED_SOURCES_FEATURE, "mixed_source_types"
    return None, None


def _decode_plan_source_directories(plan: BackupPlan) -> list[str]:
    if not plan.source_directories:
        return []
    try:
        decoded = json.loads(plan.source_directories)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded if str(item).strip()]


def evaluate_backup_plan_feature_access(
    db: Session,
    *,
    enabled_repository_count: int,
    repository_run_mode: str,
    source_locations: Optional[list[dict[str, Any]]] = None,
) -> BackupPlanFeatureDecision:
    current_plan = get_current_plan(db)
    feature = BACKUP_PLAN_ADVANCED_FEATURE
    reason: Optional[str] = None
    if enabled_repository_count > 1:
        reason = "multi_repository"
    elif repository_run_mode == "parallel":
        reason = "parallel"
    else:
        feature_requirement, source_reason = _source_type_feature_requirement(
            source_locations
        )
        if feature_requirement is not None:
            feature = feature_requirement
            reason = source_reason

    required = FEATURES[feature]
    allowed = reason is None or has_feature(db, feature)
    return BackupPlanFeatureDecision(
        allowed=allowed,
        current=current_plan,
        required=required,
        feature=feature,
        reason=reason,
    )


def evaluate_backup_plan_access(
    db: Session, plan: BackupPlan
) -> BackupPlanFeatureDecision:
    decision = evaluate_backup_plan_feature_access(
        db,
        enabled_repository_count=sum(1 for link in plan.repositories if link.enabled),
        repository_run_mode=plan.repository_run_mode,
        source_locations=decode_source_locations(
            plan.source_locations,
            source_type=plan.source_type,
            source_ssh_connection_id=plan.source_ssh_connection_id,
            source_directories=_decode_plan_source_directories(plan),
        ),
    )
    if decision.reason is None and any(
        link.enabled and link.repository is not None and is_borg2(link.repository)
        for link in plan.repositories
    ):
        return BackupPlanFeatureDecision(
            allowed=has_feature(db, BORG2_FEATURE),
            current=decision.current,
            required=FEATURES[BORG2_FEATURE],
            feature=BORG2_FEATURE,
            reason="borg2_repository",
        )
    return decision


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
    db: Session,
    *,
    enabled_repository_count: int,
    repository_run_mode: str,
    source_locations: Optional[list[dict[str, Any]]] = None,
) -> None:
    decision = evaluate_backup_plan_feature_access(
        db,
        enabled_repository_count=enabled_repository_count,
        repository_run_mode=repository_run_mode,
        source_locations=source_locations,
    )
    raise_backup_plan_feature_error(decision)
