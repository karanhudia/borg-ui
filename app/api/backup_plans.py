from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.core.security import (
    check_repo_access,
    encrypt_secret,
    get_current_user,
    require_any_role,
)
from app.database.database import get_db
from app.database.models import (
    BackupJob,
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    BackupPlanRunRepository,
    BackupPlanScript,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
    Script,
    ScriptExecution,
    User,
)
from app.services.backup_plan_policy import (
    evaluate_backup_plan_access,
    raise_backup_plan_feature_error,
    require_backup_plan_feature_access,
)
from app.services.backup_plan_execution_service import backup_plan_execution_service
from app.services.backup_route_planner import plan_repository_route
from app.services.upload_ratelimit_policies import parse_upload_policy_time
from app.services.check_flag_validation import (
    CheckFlagConflictError,
    validate_check_flags_for_max_duration,
)
from app.services.backup_progress_contract import serialize_backup_progress_details
from app.services.log_policy import (
    DEFAULT_LOG_SAVE_POLICY,
    get_log_save_policy,
    job_has_logs_by_policy,
)
from app.services.repository_executor import repository_executor_type
from app.utils.datetime_utils import serialize_datetime
from app.utils.schedule_time import (
    InvalidScheduleTimezone,
    calculate_next_cron_run,
    normalize_schedule_timezone,
)
from app.utils.source_locations import (
    decode_source_locations,
    legacy_source_fields,
    normalize_source_locations,
)
from app.utils.script_params import (
    filter_system_variables_from_params,
    mask_password_values,
    validate_parameter_value,
)

logger = structlog.get_logger()
router = APIRouter(tags=["backup-plans"])

PLAN_SCRIPT_HOOK_TYPES = {"pre-backup", "post-backup"}
PLAN_SCRIPT_RUN_ON_VALUES = {"success", "failure", "warning", "always"}


def _raise_check_flag_conflict(exc: CheckFlagConflictError) -> None:
    raise HTTPException(
        status_code=422,
        detail={
            "key": "backend.errors.repo.checkFlagsRequireUnlimitedDuration",
            "params": {"flags": ", ".join(exc.conflicting_flags)},
        },
    ) from exc


class BackupPlanRepositoryPayload(BaseModel):
    repository_id: int
    enabled: bool = True
    execution_order: int
    compression_source: str = "plan"
    compression_override: Optional[str] = None
    custom_flags_override: Optional[str] = None
    upload_ratelimit_kib_override: Optional[int] = None
    failure_behavior_override: Optional[str] = None


class UploadRatelimitSchedulePolicyPayload(BaseModel):
    label: str
    start_time: str
    end_time: str
    upload_ratelimit_kib: Optional[int] = None


class BackupPlanScriptPayload(BaseModel):
    # A hook references EITHER a server-side library script (script_id) OR a
    # script the agent publishes (agent_script_name). Exactly one must be set.
    script_id: Optional[int] = None
    agent_script_name: Optional[str] = None
    hook_type: str
    execution_order: float = 1
    enabled: bool = True
    custom_timeout: Optional[int] = None
    custom_run_on: Optional[str] = None
    continue_on_error: Optional[bool] = False
    skip_on_failure: Optional[bool] = False
    parameter_values: Optional[dict[str, Any]] = None


class BackupPlanPayload(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    source_type: str = "local"
    source_ssh_connection_id: Optional[int] = None
    source_directories: list[str]
    source_locations: Optional[list[dict[str, Any]]] = None
    exclude_patterns: Optional[list[str]] = None
    # Set when the plan source came from the database scan / template flow.
    # Keeps the wizard from forgetting that this is a DB-backed plan.
    database_template_id: Optional[str] = None
    archive_name_template: str = "{plan_name}-{now}"
    compression: str = "lz4"
    custom_flags: Optional[str] = None
    upload_ratelimit_kib: Optional[int] = None
    upload_ratelimit_schedule_policies: list[UploadRatelimitSchedulePolicyPayload] = (
        Field(default_factory=list)
    )
    repository_run_mode: str = "series"
    max_parallel_repositories: int = 1
    failure_behavior: str = "continue"
    schedule_enabled: bool = False
    cron_expression: Optional[str] = None
    timezone: str = "UTC"
    pre_backup_script_id: Optional[int] = None
    post_backup_script_id: Optional[int] = None
    pre_backup_script_parameters: Optional[dict[str, Any]] = None
    post_backup_script_parameters: Optional[dict[str, Any]] = None
    script_hooks: Optional[list[BackupPlanScriptPayload]] = None
    run_repository_scripts: bool = True
    run_prune_after: bool = False
    run_compact_after: bool = False
    run_check_after: bool = False
    check_max_duration: int = 3600
    check_extra_flags: Optional[str] = None
    prune_keep_hourly: int = 0
    prune_keep_daily: int = 7
    prune_keep_weekly: int = 4
    prune_keep_monthly: int = 6
    prune_keep_quarterly: int = 0
    prune_keep_yearly: int = 1
    prune_keep_within: Optional[str] = None
    repositories: list[BackupPlanRepositoryPayload]
    clear_legacy_source_repository_ids: list[int] = Field(default_factory=list)


class BackupPlanFromRepositoryPayload(BaseModel):
    name: Optional[str] = None
    copy_schedule: bool = True
    disable_repository_schedule: bool = False
    move_source_settings: bool = True


def _decode_json_list(value: Optional[str]) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def _normalize_prune_keep_within(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _unique_backup_plan_name(db: Session, base_name: str) -> str:
    candidate = base_name.strip() or "Backup Plan"
    existing_names = {
        name
        for (name,) in db.query(BackupPlan.name)
        .filter(BackupPlan.name.like(f"{candidate}%"))
        .all()
    }
    if candidate not in existing_names:
        return candidate

    suffix = 2
    while f"{candidate} ({suffix})" in existing_names:
        suffix += 1
    return f"{candidate} ({suffix})"


def _repository_schedule_candidates(
    db: Session, repository: Repository
) -> list[ScheduledJob]:
    linked_schedule_ids = [
        row.scheduled_job_id
        for row in db.query(ScheduledJobRepository.scheduled_job_id)
        .filter(ScheduledJobRepository.repository_id == repository.id)
        .all()
    ]

    candidates: dict[int, ScheduledJob] = {}
    direct_jobs = (
        db.query(ScheduledJob)
        .filter(
            (ScheduledJob.repository_id == repository.id)
            | (ScheduledJob.repository == repository.path)
        )
        .all()
    )
    for job in direct_jobs:
        candidates[job.id] = job

    if linked_schedule_ids:
        linked_jobs = (
            db.query(ScheduledJob)
            .filter(ScheduledJob.id.in_(linked_schedule_ids))
            .all()
        )
        for job in linked_jobs:
            candidates[job.id] = job

    return sorted(
        candidates.values(),
        key=lambda job: (
            not bool(job.enabled),
            job.next_run is None,
            job.id,
        ),
    )


def _preferred_repository_schedule(
    db: Session, repository: Repository
) -> Optional[ScheduledJob]:
    candidates = _repository_schedule_candidates(db, repository)
    return candidates[0] if candidates else None


def _disable_exclusive_repository_schedule(
    db: Session, schedule: ScheduledJob, repository: Repository
) -> tuple[bool, Optional[str]]:
    links = (
        db.query(ScheduledJobRepository)
        .filter(ScheduledJobRepository.scheduled_job_id == schedule.id)
        .all()
    )
    linked_repository_ids = {link.repository_id for link in links}
    direct_match = schedule.repository_id == repository.id or (
        bool(schedule.repository) and schedule.repository == repository.path
    )
    linked_match = linked_repository_ids == {repository.id}

    if repository.id in linked_repository_ids and linked_repository_ids != {
        repository.id
    }:
        return False, "shared_schedule"
    if not direct_match and not linked_match:
        return False, "not_repository_schedule"
    if linked_repository_ids and linked_repository_ids != {repository.id}:
        return False, "shared_schedule"

    schedule.enabled = False
    schedule.next_run = None
    schedule.updated_at = datetime.utcnow()
    return True, None


def _payload_from_repository(
    repository: Repository,
    schedule: Optional[ScheduledJob],
    *,
    name: str,
    copy_schedule: bool,
) -> BackupPlanPayload:
    schedule_enabled = bool(copy_schedule and schedule and schedule.enabled)
    timezone = schedule.timezone if schedule else "UTC"
    archive_name_template = (
        schedule.archive_name_template
        if schedule and schedule.archive_name_template
        else "{plan_name}-{repo_name}-{now}"
    )

    return BackupPlanPayload(
        name=name,
        description=f'Created from repository "{repository.name}".',
        enabled=True,
        source_type="remote" if repository.source_ssh_connection_id else "local",
        source_ssh_connection_id=repository.source_ssh_connection_id,
        source_directories=_decode_json_list(repository.source_directories),
        source_locations=decode_source_locations(
            repository.source_locations,
            source_type="remote" if repository.source_ssh_connection_id else "local",
            source_ssh_connection_id=repository.source_ssh_connection_id,
            source_directories=_decode_json_list(repository.source_directories),
        ),
        exclude_patterns=_decode_json_list(repository.exclude_patterns),
        archive_name_template=archive_name_template,
        compression=repository.compression or "lz4",
        custom_flags=repository.custom_flags,
        upload_ratelimit_kib=None,
        repository_run_mode="series",
        max_parallel_repositories=1,
        failure_behavior="continue",
        schedule_enabled=schedule_enabled,
        cron_expression=schedule.cron_expression
        if schedule_enabled and schedule
        else None,
        timezone=timezone,
        pre_backup_script_id=schedule.pre_backup_script_id if schedule else None,
        post_backup_script_id=schedule.post_backup_script_id if schedule else None,
        pre_backup_script_parameters=(
            schedule.pre_backup_script_parameters if schedule else None
        ),
        post_backup_script_parameters=(
            schedule.post_backup_script_parameters if schedule else None
        ),
        run_repository_scripts=True,
        run_prune_after=bool(schedule and schedule.run_prune_after),
        run_compact_after=bool(schedule and schedule.run_compact_after),
        run_check_after=False,
        check_max_duration=3600,
        check_extra_flags=None,
        prune_keep_hourly=schedule.prune_keep_hourly if schedule else 0,
        prune_keep_daily=schedule.prune_keep_daily if schedule else 7,
        prune_keep_weekly=schedule.prune_keep_weekly if schedule else 4,
        prune_keep_monthly=schedule.prune_keep_monthly if schedule else 6,
        prune_keep_quarterly=schedule.prune_keep_quarterly if schedule else 0,
        prune_keep_yearly=schedule.prune_keep_yearly if schedule else 1,
        prune_keep_within=schedule.prune_keep_within if schedule else None,
        repositories=[
            BackupPlanRepositoryPayload(
                repository_id=repository.id,
                enabled=True,
                execution_order=1,
            )
        ],
    )


def _serialize_repository_link(link: BackupPlanRepository) -> dict[str, Any]:
    repo = link.repository
    return {
        "id": link.id,
        "repository_id": link.repository_id,
        "enabled": bool(link.enabled),
        "execution_order": link.execution_order,
        "compression_source": link.compression_source,
        "compression_override": link.compression_override,
        "custom_flags_override": link.custom_flags_override,
        "upload_ratelimit_kib_override": link.upload_ratelimit_kib_override,
        "failure_behavior_override": link.failure_behavior_override,
        "repository": {
            "id": repo.id,
            "name": repo.name,
            "path": repo.path,
            "borg_version": repo.borg_version,
            "mode": repo.mode,
            "repository_type": repo.repository_type,
            "connection_id": repo.connection_id,
            "execution_target": repo.execution_target,
            "executor_type": repository_executor_type(repo),
            "agent_machine_id": repo.agent_machine_id,
        }
        if repo
        else None,
    }


def _script_parameter_defs(script: Optional[Script]) -> list[dict[str, Any]]:
    if not script or not script.parameters:
        return []
    try:
        decoded = json.loads(script.parameters)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    return filter_system_variables_from_params(decoded)


def _decode_hook_parameter_values(value: Optional[str]) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _serialize_script_hook_assignment(hook: BackupPlanScript) -> dict[str, Any]:
    if hook.agent_script_name:
        # Agent-published script: no server-side Script row, no parameters.
        return {
            "id": hook.id,
            "script_id": None,
            "agent_script_name": hook.agent_script_name,
            "is_agent_script": True,
            "script_name": hook.agent_script_name,
            "script_description": None,
            "hook_type": hook.hook_type,
            "execution_order": hook.execution_order,
            "enabled": bool(hook.enabled),
            "custom_timeout": hook.custom_timeout,
            "custom_run_on": hook.custom_run_on,
            "continue_on_error": bool(hook.continue_on_error),
            "skip_on_failure": bool(hook.skip_on_failure),
            "default_timeout": None,
            "default_run_on": "always",
            "parameters": [],
            "parameter_values": None,
        }
    script = hook.script
    parameters = _script_parameter_defs(script)
    parameter_values = _decode_hook_parameter_values(hook.parameter_values)
    return {
        "id": hook.id,
        "script_id": hook.script_id,
        "agent_script_name": None,
        "is_agent_script": False,
        "script_name": script.name if script else f"Script #{hook.script_id}",
        "script_description": script.description if script else None,
        "hook_type": hook.hook_type,
        "execution_order": hook.execution_order,
        "enabled": bool(hook.enabled),
        "custom_timeout": hook.custom_timeout,
        "custom_run_on": hook.custom_run_on,
        "continue_on_error": bool(hook.continue_on_error),
        "skip_on_failure": bool(hook.skip_on_failure),
        "default_timeout": script.timeout if script else None,
        "default_run_on": script.run_on if script else "always",
        "parameters": parameters,
        "parameter_values": mask_password_values(parameters, parameter_values)
        if parameter_values
        else None,
    }


def _serialize_legacy_script_hook(
    plan: BackupPlan,
    script: Script,
    *,
    hook_type: str,
    parameter_values: Optional[dict[str, Any]],
) -> dict[str, Any]:
    parameters = _script_parameter_defs(script)
    return {
        "id": None,
        "script_id": script.id,
        "script_name": script.name,
        "script_description": script.description,
        "hook_type": hook_type,
        "execution_order": 1,
        "enabled": True,
        "custom_timeout": None,
        "custom_run_on": None,
        "continue_on_error": False,
        "skip_on_failure": False,
        "default_timeout": script.timeout,
        "default_run_on": script.run_on,
        "parameters": parameters,
        "parameter_values": mask_password_values(parameters, parameter_values or {})
        if parameter_values
        else None,
    }


def _serialize_plan_script_hooks(plan: BackupPlan) -> list[dict[str, Any]]:
    explicit_hooks = [
        hook
        for hook in plan.script_hooks
        if hook.script is not None or hook.agent_script_name
    ]
    if explicit_hooks:
        hook_order = {"pre-backup": 0, "post-backup": 1}
        return [
            _serialize_script_hook_assignment(hook)
            for hook in sorted(
                explicit_hooks,
                key=lambda item: (
                    hook_order.get(item.hook_type, 99),
                    item.execution_order,
                    item.id,
                ),
            )
        ]

    hooks: list[dict[str, Any]] = []
    if plan.pre_backup_script_id:
        pre_script = plan.pre_backup_script or None
        if pre_script:
            hooks.append(
                _serialize_legacy_script_hook(
                    plan,
                    pre_script,
                    hook_type="pre-backup",
                    parameter_values=plan.pre_backup_script_parameters,
                )
            )
    if plan.post_backup_script_id:
        post_script = plan.post_backup_script or None
        if post_script:
            hooks.append(
                _serialize_legacy_script_hook(
                    plan,
                    post_script,
                    hook_type="post-backup",
                    parameter_values=plan.post_backup_script_parameters,
                )
            )
    return hooks


def _decode_upload_ratelimit_schedule_policies(
    value: Optional[str],
) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    policies: list[dict[str, Any]] = []
    for item in decoded:
        if isinstance(item, dict):
            policies.append(
                {
                    "label": str(item.get("label", "")).strip(),
                    "start_time": item.get("start_time"),
                    "end_time": item.get("end_time"),
                    "upload_ratelimit_kib": item.get("upload_ratelimit_kib"),
                }
            )
    return policies


def _normalize_upload_ratelimit_schedule_policies(
    policies: list[UploadRatelimitSchedulePolicyPayload],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for policy in policies:
        label = policy.label.strip()
        try:
            start = parse_upload_policy_time(policy.start_time)
            end = parse_upload_policy_time(policy.end_time)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.invalidUploadLimitPolicy"},
            ) from exc
        if not label or start == end:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.invalidUploadLimitPolicy"},
            )
        if policy.upload_ratelimit_kib is not None and policy.upload_ratelimit_kib <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.invalidUploadLimitPolicy"},
            )
        normalized.append(
            {
                "label": label,
                "start_time": policy.start_time,
                "end_time": policy.end_time,
                "upload_ratelimit_kib": policy.upload_ratelimit_kib,
            }
        )
    return normalized


def _serialize_plan(plan: BackupPlan, *, detail: bool = False) -> dict[str, Any]:
    enabled_links = [link for link in plan.repositories if link.enabled]
    source_directories = _decode_json_list(plan.source_directories)
    source_locations = decode_source_locations(
        plan.source_locations,
        source_type=plan.source_type,
        source_ssh_connection_id=plan.source_ssh_connection_id,
        source_directories=source_directories,
    )
    payload: dict[str, Any] = {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "enabled": bool(plan.enabled),
        "source_type": plan.source_type,
        "source_ssh_connection_id": plan.source_ssh_connection_id,
        "source_directories": source_directories,
        "source_locations": source_locations,
        "exclude_patterns": _decode_json_list(plan.exclude_patterns),
        "database_template_id": plan.database_template_id,
        "archive_name_template": plan.archive_name_template,
        "compression": plan.compression,
        "custom_flags": plan.custom_flags,
        "check_extra_flags": plan.check_extra_flags,
        "upload_ratelimit_kib": plan.upload_ratelimit_kib,
        "upload_ratelimit_schedule_policies": _decode_upload_ratelimit_schedule_policies(
            plan.upload_ratelimit_schedule_policies
        ),
        "repository_run_mode": plan.repository_run_mode,
        "max_parallel_repositories": plan.max_parallel_repositories,
        "failure_behavior": plan.failure_behavior,
        "schedule_enabled": bool(plan.schedule_enabled),
        "cron_expression": plan.cron_expression,
        "timezone": plan.timezone,
        "last_run": serialize_datetime(plan.last_run),
        "next_run": serialize_datetime(plan.next_run),
        "repository_count": len(enabled_links),
        "created_at": serialize_datetime(plan.created_at),
        "updated_at": serialize_datetime(plan.updated_at),
    }
    if detail:
        payload.update(
            {
                "pre_backup_script_id": plan.pre_backup_script_id,
                "post_backup_script_id": plan.post_backup_script_id,
                "pre_backup_script_parameters": plan.pre_backup_script_parameters,
                "post_backup_script_parameters": plan.post_backup_script_parameters,
                "script_hooks": _serialize_plan_script_hooks(plan),
                "run_repository_scripts": bool(plan.run_repository_scripts),
                "run_prune_after": bool(plan.run_prune_after),
                "run_compact_after": bool(plan.run_compact_after),
                "run_check_after": bool(plan.run_check_after),
                "check_max_duration": plan.check_max_duration,
                "prune_keep_hourly": plan.prune_keep_hourly,
                "prune_keep_daily": plan.prune_keep_daily,
                "prune_keep_weekly": plan.prune_keep_weekly,
                "prune_keep_monthly": plan.prune_keep_monthly,
                "prune_keep_quarterly": plan.prune_keep_quarterly,
                "prune_keep_yearly": plan.prune_keep_yearly,
                "prune_keep_within": plan.prune_keep_within,
                "repositories": [
                    _serialize_repository_link(link) for link in plan.repositories
                ],
            }
        )
    return payload


def _serialize_backup_job(
    job: Optional[BackupJob],
    repo: Optional[Repository],
    *,
    log_save_policy: str = DEFAULT_LOG_SAVE_POLICY,
) -> Optional[dict[str, Any]]:
    if not job:
        return None
    return {
        "id": job.id,
        "repository": job.repository,
        "repository_id": job.repository_id,
        "status": job.status,
        "started_at": serialize_datetime(job.started_at),
        "completed_at": serialize_datetime(job.completed_at),
        "progress": job.progress,
        "error_message": job.error_message,
        "has_logs": job_has_logs_by_policy(
            job,
            log_save_policy,
            output_text=[job.logs, job.error_message],
            file_path=job.log_file_path,
        ),
        "maintenance_status": job.maintenance_status,
        "archive_name": job.archive_name,
        "execution_mode": job.execution_mode or "local",
        "route_strategy": job.route_strategy,
        "retry_attempt": job.retry_attempt or 1,
        "retry_original_job_id": job.retry_original_job_id,
        "retry_source_job_id": job.retry_source_job_id,
        "retry_requested_by_user_id": job.retry_requested_by_user_id,
        "retry_requested_at": serialize_datetime(job.retry_requested_at),
        "progress_details": serialize_backup_progress_details(job, repo),
    }


def _serialize_plan_run_repository(
    link: BackupPlanRunRepository, *, log_save_policy: str = DEFAULT_LOG_SAVE_POLICY
) -> dict[str, Any]:
    repo = link.repository
    return {
        "id": link.id,
        "repository_id": link.repository_id,
        "status": link.status,
        "started_at": serialize_datetime(link.started_at),
        "completed_at": serialize_datetime(link.completed_at),
        "error_message": link.error_message,
        "repository": {
            "id": repo.id,
            "name": repo.name,
            "path": repo.path,
            "borg_version": repo.borg_version,
            "mode": repo.mode,
            "repository_type": repo.repository_type,
            "connection_id": repo.connection_id,
            "execution_target": repo.execution_target,
            "executor_type": repository_executor_type(repo),
            "agent_machine_id": repo.agent_machine_id,
        }
        if repo
        else None,
        "backup_job": _serialize_backup_job(
            link.backup_job,
            repo,
            log_save_policy=log_save_policy,
        ),
    }


def _serialize_script_execution(
    execution: ScriptExecution, *, log_save_policy: str = DEFAULT_LOG_SAVE_POLICY
) -> dict[str, Any]:
    return {
        "id": execution.id,
        "script_id": execution.script_id,
        "agent_script_name": execution.agent_script_name,
        "script_name": execution.script.name
        if execution.script
        else (execution.agent_script_name or f"Script #{execution.script_id}"),
        "hook_type": execution.hook_type,
        "status": execution.status,
        "started_at": serialize_datetime(execution.started_at),
        "completed_at": serialize_datetime(execution.completed_at),
        "execution_time": execution.execution_time,
        "exit_code": execution.exit_code,
        "error_message": execution.error_message,
        "has_logs": job_has_logs_by_policy(
            execution,
            log_save_policy,
            output_text=[
                execution.stdout,
                execution.stderr,
                execution.error_message,
            ],
            exit_code=execution.exit_code,
        ),
    }


def _serialize_plan_run(
    run: BackupPlanRun,
    *,
    detail: bool = True,
    log_save_policy: str = DEFAULT_LOG_SAVE_POLICY,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": run.id,
        "backup_plan_id": run.backup_plan_id,
        "trigger": run.trigger,
        "status": run.status,
        "started_at": serialize_datetime(run.started_at),
        "completed_at": serialize_datetime(run.completed_at),
        "error_message": run.error_message,
        "created_at": serialize_datetime(run.created_at),
        "retry_attempt": run.retry_attempt or 1,
        "retry_original_run_id": run.retry_original_run_id,
        "retry_source_run_id": run.retry_source_run_id,
        "retry_requested_by_user_id": run.retry_requested_by_user_id,
        "retry_requested_at": serialize_datetime(run.retry_requested_at),
    }
    if detail:
        payload["repositories"] = [
            _serialize_plan_run_repository(link, log_save_policy=log_save_policy)
            for link in sorted(run.repositories, key=lambda item: item.id)
        ]
        payload["script_executions"] = [
            _serialize_script_execution(
                execution,
                log_save_policy=log_save_policy,
            )
            for execution in sorted(
                run.script_executions,
                key=lambda item: (item.started_at or datetime.min, item.id),
            )
        ]
    return payload


def _can_view_plan(db: Session, user: User, plan: BackupPlan) -> bool:
    if user.role == "admin":
        return True
    if not plan.repositories:
        return False
    for link in plan.repositories:
        if not link.repository:
            continue
        try:
            check_repo_access(db, user, link.repository, "viewer")
        except HTTPException:
            return False
    return True


def _require_plan_operator_access(db: Session, user: User, plan: BackupPlan) -> None:
    if user.role == "admin":
        return
    if not plan.repositories:
        require_any_role(user, "admin", "operator")
        return
    for link in plan.repositories:
        if link.repository:
            check_repo_access(db, user, link.repository, "operator")


def _require_run_operator_access(db: Session, user: User, run: BackupPlanRun) -> None:
    if user.role == "admin":
        return
    if not run.repositories:
        require_any_role(user, "admin", "operator")
        return
    for link in run.repositories:
        if link.repository:
            check_repo_access(db, user, link.repository, "operator")


def _load_plan_or_404(db: Session, plan_id: int) -> BackupPlan:
    plan = (
        db.query(BackupPlan)
        .options(
            joinedload(BackupPlan.repositories).joinedload(
                BackupPlanRepository.repository
            ),
            joinedload(BackupPlan.script_hooks).joinedload(BackupPlanScript.script),
            joinedload(BackupPlan.pre_backup_script),
            joinedload(BackupPlan.post_backup_script),
        )
        .filter(BackupPlan.id == plan_id)
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.backupPlans.notFound"},
        )
    return plan


def _load_run_or_404(db: Session, run_id: int) -> BackupPlanRun:
    run = (
        db.query(BackupPlanRun)
        .options(
            joinedload(BackupPlanRun.repositories).joinedload(
                BackupPlanRunRepository.repository
            ),
            joinedload(BackupPlanRun.repositories).joinedload(
                BackupPlanRunRepository.backup_job
            ),
            joinedload(BackupPlanRun.script_executions).joinedload(
                ScriptExecution.script
            ),
        )
        .filter(BackupPlanRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.backupPlans.runNotFound"},
        )
    return run


def _process_hook_parameter_values(
    script: Script, parameter_values: Optional[dict[str, Any]]
) -> Optional[str]:
    parameter_values = parameter_values or {}
    parameters = _script_parameter_defs(script)
    processed_values: dict[str, Any] = {}
    for param_def in parameters:
        param_name = param_def["name"]
        if param_name not in parameter_values:
            if param_def.get("required"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required script parameter: {param_name}",
                )
            continue
        value = parameter_values[param_name]
        is_valid, error_msg = validate_parameter_value(param_def, value)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        if param_def.get("type", "text") == "password" and value:
            processed_values[param_name] = encrypt_secret(str(value))
        else:
            processed_values[param_name] = value

    return json.dumps(processed_values) if processed_values else None


def _validate_script_hooks(db: Session, payload: BackupPlanPayload) -> None:
    if payload.script_hooks is None:
        return

    seen: set[tuple[Any, str]] = set()
    for hook in payload.script_hooks:
        if hook.hook_type not in PLAN_SCRIPT_HOOK_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.scripts.hookTypeMustBe"},
            )
        # Exactly one of script_id / agent_script_name identifies the script.
        agent_script_name = (hook.agent_script_name or "").strip()
        has_library = hook.script_id is not None
        has_agent = bool(agent_script_name)
        if has_library == has_agent:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.scripts.hookScriptRequired"},
            )
        # Defense-in-depth: the agent is the real allow-list boundary, but reject
        # obviously malformed names here too (length matches the DB column; no path
        # separators / traversal) for a clear 422 instead of an agent-side failure.
        if has_agent and (
            len(agent_script_name) > 255
            or "/" in agent_script_name
            or "\\" in agent_script_name
            or ".." in agent_script_name
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.scripts.invalidAgentScriptName"},
            )
        if hook.custom_run_on and hook.custom_run_on not in PLAN_SCRIPT_RUN_ON_VALUES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.scripts.invalidRunCondition"},
            )
        if hook.custom_timeout is not None and hook.custom_timeout <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.scripts.invalidTimeout"},
            )
        if hook.execution_order <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.scripts.invalidExecutionOrder"},
            )
        key = (
            ("agent", agent_script_name) if has_agent else ("library", hook.script_id),
            hook.hook_type,
        )
        if key in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.scripts.scriptAlreadyAssigned"},
            )
        seen.add(key)
        # Agent scripts live on the node and are validated by the agent at run
        # time; only library scripts are checked against the server-side table.
        if has_library and not (
            db.query(Script.id).filter(Script.id == hook.script_id).first()
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.scripts.scriptNotFound"},
            )


def _mirror_legacy_script_fields(payload: BackupPlanPayload) -> None:
    if payload.script_hooks is None:
        return

    # Legacy single-FK columns are library-only; agent hooks never mirror here.
    enabled_hooks = [
        hook
        for hook in payload.script_hooks
        if hook.enabled and hook.script_id is not None
    ]
    pre_hooks = sorted(
        (hook for hook in enabled_hooks if hook.hook_type == "pre-backup"),
        key=lambda item: item.execution_order,
    )
    post_hooks = sorted(
        (hook for hook in enabled_hooks if hook.hook_type == "post-backup"),
        key=lambda item: item.execution_order,
    )
    first_pre = pre_hooks[0] if pre_hooks else None
    first_post = post_hooks[0] if post_hooks else None
    payload.pre_backup_script_id = first_pre.script_id if first_pre else None
    payload.pre_backup_script_parameters = None
    payload.post_backup_script_id = first_post.script_id if first_post else None
    payload.post_backup_script_parameters = None


def _replace_script_hooks(
    db: Session, plan: BackupPlan, payload: BackupPlanPayload
) -> None:
    if payload.script_hooks is None:
        return

    db.query(BackupPlanScript).filter(
        BackupPlanScript.backup_plan_id == plan.id
    ).delete()
    for hook in payload.script_hooks:
        is_agent_hook = hook.script_id is None
        if is_agent_hook:
            script = None
            parameter_values = None
        else:
            script = db.query(Script).filter(Script.id == hook.script_id).one()
            parameter_values = _process_hook_parameter_values(
                script, hook.parameter_values
            )
        db.add(
            BackupPlanScript(
                backup_plan_id=plan.id,
                script_id=hook.script_id,
                agent_script_name=(
                    (hook.agent_script_name or "").strip() or None
                    if is_agent_hook
                    else None
                ),
                hook_type=hook.hook_type,
                execution_order=hook.execution_order,
                enabled=hook.enabled,
                custom_timeout=hook.custom_timeout,
                custom_run_on=hook.custom_run_on,
                continue_on_error=bool(hook.continue_on_error),
                skip_on_failure=bool(hook.skip_on_failure),
                parameter_values=parameter_values,
                created_at=datetime.utcnow(),
            )
        )


def _validate_payload(
    db: Session, user: User, payload: BackupPlanPayload
) -> list[Repository]:
    if not payload.name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.nameRequired"},
        )
    if payload.source_type not in {"local", "remote", "agent", "mixed"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.invalidSourceType"},
        )
    try:
        source_locations = normalize_source_locations(
            payload.source_locations,
            source_type=payload.source_type,
            source_ssh_connection_id=payload.source_ssh_connection_id,
            source_directories=payload.source_directories,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.sourceConnectionRequired"},
        ) from exc

    payload.source_locations = source_locations
    (
        payload.source_type,
        payload.source_ssh_connection_id,
        payload.source_directories,
    ) = legacy_source_fields(source_locations)

    if not payload.source_directories:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.sourceRequired"},
        )
    if not payload.repositories:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.repositoriesRequired"},
        )
    if payload.repository_run_mode not in {"series", "parallel"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.invalidRunMode"},
        )
    if payload.failure_behavior not in {"continue", "stop"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.invalidFailureBehavior"},
        )
    if payload.upload_ratelimit_kib is not None and payload.upload_ratelimit_kib <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.invalidUploadLimit"},
        )
    _normalize_upload_ratelimit_schedule_policies(
        payload.upload_ratelimit_schedule_policies
    )
    if payload.run_check_after:
        try:
            validate_check_flags_for_max_duration(
                payload.check_extra_flags, payload.check_max_duration
            )
        except CheckFlagConflictError as exc:
            _raise_check_flag_conflict(exc)
    if (
        payload.repository_run_mode == "series"
        and payload.max_parallel_repositories != 1
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.invalidParallelLimit"},
        )
    if (
        payload.repository_run_mode == "parallel"
        and payload.max_parallel_repositories < 2
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.invalidParallelLimit"},
        )

    normalized_tz = normalize_schedule_timezone(payload.timezone)
    payload.timezone = normalized_tz
    if payload.schedule_enabled:
        if not payload.cron_expression:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.cronRequired"},
            )
        try:
            calculate_next_cron_run(
                payload.cron_expression, schedule_timezone=normalized_tz
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.schedule.invalidCronExpression"},
            ) from exc

    for script_id in (
        payload.pre_backup_script_id,
        payload.post_backup_script_id,
    ):
        if script_id and not db.query(Script.id).filter(Script.id == script_id).first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.scripts.scriptNotFound"},
            )

    _validate_script_hooks(db, payload)
    _mirror_legacy_script_fields(payload)

    seen_ids: set[int] = set()
    repos: list[Repository] = []
    for link in payload.repositories:
        if link.repository_id in seen_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.duplicateRepository"},
            )
        seen_ids.add(link.repository_id)
        if (
            link.upload_ratelimit_kib_override is not None
            and link.upload_ratelimit_kib_override <= 0
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.invalidUploadLimit"},
            )
        if link.failure_behavior_override not in {None, "continue", "stop"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.invalidFailureBehavior"},
            )
        if link.compression_source not in {"plan", "repository", "custom"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.invalidCompressionSource"},
            )
        if link.compression_source == "custom" and not link.compression_override:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.invalidCompressionOverride"},
            )
        repo = db.query(Repository).filter(Repository.id == link.repository_id).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backupPlans.repositoryNotFound"},
            )
        if repo.mode == "observe" and link.enabled:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.observeRepositorySelected"},
            )
        check_repo_access(db, user, repo, "operator")
        repos.append(repo)

        if link.enabled:
            route = plan_repository_route(repo, source_locations)
            if not route.supported:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "key": route.reason_key,
                        "params": route.display_params,
                    },
                )

    clear_ids = set(payload.clear_legacy_source_repository_ids)
    if clear_ids - seen_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "key": "backend.errors.backupPlans.clearLegacyRepositoryNotSelected"
            },
        )

    require_backup_plan_feature_access(
        db,
        enabled_repository_count=sum(
            1 for link in payload.repositories if link.enabled
        ),
        repository_run_mode=payload.repository_run_mode,
        source_locations=source_locations,
    )
    return repos


def _clear_legacy_source_settings(
    payload: BackupPlanPayload, repositories: list[Repository]
) -> None:
    clear_ids = set(payload.clear_legacy_source_repository_ids)
    if not clear_ids:
        return

    for repository in repositories:
        if repository.id not in clear_ids:
            continue
        repository.source_directories = None
        repository.source_locations = None
        repository.exclude_patterns = None
        repository.source_ssh_connection_id = None
        repository.updated_at = datetime.utcnow()


def _apply_payload(plan: BackupPlan, payload: BackupPlanPayload) -> None:
    plan.name = payload.name.strip()
    plan.description = payload.description.strip() if payload.description else None
    plan.enabled = payload.enabled
    plan.source_type = payload.source_type
    plan.source_ssh_connection_id = payload.source_ssh_connection_id
    plan.source_directories = json.dumps(payload.source_directories)
    plan.source_locations = json.dumps(payload.source_locations or [])
    plan.exclude_patterns = json.dumps(payload.exclude_patterns or [])
    plan.database_template_id = payload.database_template_id
    plan.archive_name_template = (
        payload.archive_name_template.strip() or "{plan_name}-{now}"
    )
    plan.compression = payload.compression
    plan.custom_flags = payload.custom_flags.strip() if payload.custom_flags else None
    plan.upload_ratelimit_kib = payload.upload_ratelimit_kib
    plan.upload_ratelimit_schedule_policies = json.dumps(
        _normalize_upload_ratelimit_schedule_policies(
            payload.upload_ratelimit_schedule_policies
        )
    )
    plan.repository_run_mode = payload.repository_run_mode
    plan.max_parallel_repositories = payload.max_parallel_repositories
    plan.failure_behavior = payload.failure_behavior
    plan.schedule_enabled = payload.schedule_enabled
    plan.cron_expression = payload.cron_expression if payload.schedule_enabled else None
    plan.timezone = payload.timezone
    plan.next_run = (
        calculate_next_cron_run(
            payload.cron_expression, schedule_timezone=payload.timezone
        )
        if payload.schedule_enabled and payload.cron_expression
        else None
    )
    plan.pre_backup_script_id = payload.pre_backup_script_id
    plan.post_backup_script_id = payload.post_backup_script_id
    plan.pre_backup_script_parameters = payload.pre_backup_script_parameters
    plan.post_backup_script_parameters = payload.post_backup_script_parameters
    plan.run_repository_scripts = payload.run_repository_scripts
    plan.run_prune_after = payload.run_prune_after
    plan.run_compact_after = payload.run_compact_after
    plan.run_check_after = payload.run_check_after
    plan.check_max_duration = payload.check_max_duration
    plan.check_extra_flags = (
        payload.check_extra_flags.strip() if payload.check_extra_flags else None
    )
    plan.prune_keep_hourly = payload.prune_keep_hourly
    plan.prune_keep_daily = payload.prune_keep_daily
    plan.prune_keep_weekly = payload.prune_keep_weekly
    plan.prune_keep_monthly = payload.prune_keep_monthly
    plan.prune_keep_quarterly = payload.prune_keep_quarterly
    plan.prune_keep_yearly = payload.prune_keep_yearly
    plan.prune_keep_within = _normalize_prune_keep_within(payload.prune_keep_within)
    plan.updated_at = datetime.utcnow()


def _replace_repository_links(
    db: Session, plan: BackupPlan, payload: BackupPlanPayload
) -> None:
    db.query(BackupPlanRepository).filter(
        BackupPlanRepository.backup_plan_id == plan.id
    ).delete()
    for index, link in enumerate(payload.repositories):
        db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=link.repository_id,
                enabled=link.enabled,
                execution_order=link.execution_order or index + 1,
                compression_source=link.compression_source,
                compression_override=(
                    link.compression_override
                    if link.compression_source == "custom"
                    else None
                ),
                custom_flags_override=link.custom_flags_override,
                upload_ratelimit_kib_override=link.upload_ratelimit_kib_override,
                failure_behavior_override=link.failure_behavior_override,
            )
        )


@router.get("/")
async def list_backup_plans(
    repository_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BackupPlan).options(
        joinedload(BackupPlan.repositories).joinedload(BackupPlanRepository.repository)
    )
    if repository_id is not None:
        query = query.join(BackupPlanRepository).filter(
            BackupPlanRepository.repository_id == repository_id,
            BackupPlanRepository.enabled.is_(True),
        )
    plans = query.order_by(BackupPlan.name.asc()).all()
    visible = [plan for plan in plans if _can_view_plan(db, current_user, plan)]
    return {
        "backup_plans": [
            _serialize_plan(plan, detail=repository_id is not None) for plan in visible
        ]
    }


@router.get("/runs")
async def list_backup_plan_runs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    plans = (
        db.query(BackupPlan)
        .options(
            joinedload(BackupPlan.repositories).joinedload(
                BackupPlanRepository.repository
            )
        )
        .all()
    )
    visible_plan_ids = [
        plan.id for plan in plans if _can_view_plan(db, current_user, plan)
    ]
    if not visible_plan_ids:
        return {"runs": []}

    runs = (
        db.query(BackupPlanRun)
        .options(
            joinedload(BackupPlanRun.repositories).joinedload(
                BackupPlanRunRepository.repository
            ),
            joinedload(BackupPlanRun.repositories).joinedload(
                BackupPlanRunRepository.backup_job
            ),
            joinedload(BackupPlanRun.script_executions).joinedload(
                ScriptExecution.script
            ),
        )
        .filter(BackupPlanRun.backup_plan_id.in_(visible_plan_ids))
        .order_by(BackupPlanRun.id.desc())
        .limit(limit)
        .all()
    )
    log_save_policy = get_log_save_policy(db)
    return {
        "runs": [
            _serialize_plan_run(run, log_save_policy=log_save_policy) for run in runs
        ]
    }


@router.get("/runs/{run_id}")
async def get_backup_plan_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _load_run_or_404(db, run_id)
    if run.backup_plan_id:
        plan = _load_plan_or_404(db, run.backup_plan_id)
        if not _can_view_plan(db, current_user, plan):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"key": "backend.errors.auth.notEnoughPermissions"},
            )
    return _serialize_plan_run(run, log_save_policy=get_log_save_policy(db))


@router.post("/runs/{run_id}/cancel")
async def cancel_backup_plan_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _load_run_or_404(db, run_id)
    _require_run_operator_access(db, current_user, run)
    result = await backup_plan_execution_service.cancel_run(db, run.id)
    run = _load_run_or_404(db, run.id)
    logger.info(
        "Backup plan run cancelled",
        backup_plan_run_id=run.id,
        user=current_user.username,
        result=result,
    )
    return {
        "message": "backend.success.backupPlans.runCancelled",
        "run": _serialize_plan_run(run, log_save_policy=get_log_save_policy(db)),
        **result,
    }


@router.post("/runs/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_backup_plan_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _load_run_or_404(db, run_id)
    _require_run_operator_access(db, current_user, run)
    try:
        retry_run_id = backup_plan_execution_service.retry_failed_run(
            db,
            run,
            requested_by_user_id=current_user.id,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.backupPlans.retryUnsupported"},
        ) from exc

    retry_run = _load_run_or_404(db, retry_run_id)
    logger.info(
        "Backup plan run retry started",
        source_backup_plan_run_id=run.id,
        retry_backup_plan_run_id=retry_run.id,
        user=current_user.username,
    )
    return _serialize_plan_run(retry_run, log_save_policy=get_log_save_policy(db))


@router.post("/from-repository/{repo_id}", status_code=status.HTTP_201_CREATED)
async def create_backup_plan_from_repository(
    repo_id: int,
    payload: BackupPlanFromRepositoryPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.backupPlans.repositoryNotFound"},
        )
    check_repo_access(db, current_user, repository, "operator")

    if repository.mode == "observe":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.observeRepositorySelected"},
        )

    source_directories = _decode_json_list(repository.source_directories)
    if not source_directories:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.sourceRequired"},
        )

    schedule = (
        _preferred_repository_schedule(db, repository)
        if payload.copy_schedule
        else None
    )
    explicit_name = payload.name.strip() if payload.name else None
    if explicit_name:
        existing = db.query(BackupPlan).filter(BackupPlan.name == explicit_name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"key": "backend.errors.backupPlans.nameExists"},
            )
        plan_name = explicit_name
    else:
        plan_name = _unique_backup_plan_name(db, f"{repository.name} Backup Plan")

    plan_payload = _payload_from_repository(
        repository,
        schedule,
        name=plan_name,
        copy_schedule=payload.copy_schedule,
    )
    try:
        _validate_payload(db, current_user, plan_payload)
    except InvalidScheduleTimezone as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.schedule.invalidTimezone"},
        ) from exc

    plan = BackupPlan(created_at=datetime.utcnow())
    _apply_payload(plan, plan_payload)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    _replace_repository_links(db, plan, plan_payload)

    schedule_disabled = False
    schedule_disable_reason = None
    if schedule and payload.disable_repository_schedule:
        schedule_disabled, schedule_disable_reason = (
            _disable_exclusive_repository_schedule(db, schedule, repository)
        )

    source_settings_moved = False
    if payload.move_source_settings:
        repository.source_directories = None
        repository.source_locations = None
        repository.exclude_patterns = None
        repository.source_ssh_connection_id = None
        repository.updated_at = datetime.utcnow()
        source_settings_moved = True

    db.commit()
    plan = _load_plan_or_404(db, plan.id)
    logger.info(
        "Backup plan created from repository",
        backup_plan_id=plan.id,
        repository_id=repository.id,
        copied_schedule_id=schedule.id if schedule else None,
        repository_schedule_disabled=schedule_disabled,
        source_settings_moved=source_settings_moved,
        user=current_user.username,
    )
    return {
        "backup_plan": _serialize_plan(plan, detail=True),
        "source_repository_id": repository.id,
        "copied_schedule_id": schedule.id if schedule else None,
        "repository_schedule_disabled": schedule_disabled,
        "repository_schedule_disable_reason": schedule_disable_reason,
        "source_settings_moved": source_settings_moved,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_backup_plan(
    payload: BackupPlanPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        repositories = _validate_payload(db, current_user, payload)
    except InvalidScheduleTimezone as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.schedule.invalidTimezone"},
        ) from exc

    existing = (
        db.query(BackupPlan).filter(BackupPlan.name == payload.name.strip()).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.backupPlans.nameExists"},
        )

    plan = BackupPlan(created_at=datetime.utcnow())
    _apply_payload(plan, payload)
    db.add(plan)
    db.flush()
    _replace_repository_links(db, plan, payload)
    _replace_script_hooks(db, plan, payload)
    _clear_legacy_source_settings(payload, repositories)
    db.commit()
    db.refresh(plan)

    plan = _load_plan_or_404(db, plan.id)
    logger.info(
        "Backup plan created", backup_plan_id=plan.id, user=current_user.username
    )
    return _serialize_plan(plan, detail=True)


@router.post("/{plan_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_backup_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _load_plan_or_404(db, plan_id)
    _require_plan_operator_access(db, current_user, plan)
    if not plan.enabled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.disabled"},
        )
    if not any(link.enabled for link in plan.repositories):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.backupPlans.repositoriesRequired"},
        )
    raise_backup_plan_feature_error(evaluate_backup_plan_access(db, plan))
    if backup_plan_execution_service.has_active_run(db, plan.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.backupPlans.runAlreadyActive"},
        )

    run_id = backup_plan_execution_service.start_run(db, plan, trigger="manual")
    run = _load_run_or_404(db, run_id)
    logger.info(
        "Backup plan run started",
        backup_plan_id=plan.id,
        backup_plan_run_id=run.id,
        user=current_user.username,
    )
    return _serialize_plan_run(run, log_save_policy=get_log_save_policy(db))


@router.get("/{plan_id}/runs")
async def list_backup_plan_runs_for_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 20,
):
    plan = _load_plan_or_404(db, plan_id)
    if not _can_view_plan(db, current_user, plan):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.auth.notEnoughPermissions"},
        )
    runs = (
        db.query(BackupPlanRun)
        .options(
            joinedload(BackupPlanRun.repositories).joinedload(
                BackupPlanRunRepository.repository
            ),
            joinedload(BackupPlanRun.repositories).joinedload(
                BackupPlanRunRepository.backup_job
            ),
            joinedload(BackupPlanRun.script_executions).joinedload(
                ScriptExecution.script
            ),
        )
        .filter(BackupPlanRun.backup_plan_id == plan_id)
        .order_by(BackupPlanRun.id.desc())
        .limit(limit)
        .all()
    )
    log_save_policy = get_log_save_policy(db)
    return {
        "runs": [
            _serialize_plan_run(run, log_save_policy=log_save_policy) for run in runs
        ]
    }


@router.post("/{plan_id}/toggle")
async def toggle_backup_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _load_plan_or_404(db, plan_id)
    _require_plan_operator_access(db, current_user, plan)

    enable_plan = not plan.enabled
    next_run = None
    if enable_plan:
        if not any(link.enabled for link in plan.repositories):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.backupPlans.repositoriesRequired"},
            )
        raise_backup_plan_feature_error(evaluate_backup_plan_access(db, plan))
        if plan.schedule_enabled and plan.cron_expression:
            try:
                next_run = calculate_next_cron_run(
                    plan.cron_expression,
                    schedule_timezone=plan.timezone,
                )
            except InvalidScheduleTimezone as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"key": "backend.errors.schedule.invalidTimezone"},
                ) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"key": "backend.errors.schedule.invalidCronExpression"},
                ) from exc

    plan.enabled = enable_plan
    plan.next_run = next_run
    plan.updated_at = datetime.utcnow()
    db.commit()
    plan = _load_plan_or_404(db, plan_id)
    logger.info(
        "Backup plan toggled",
        backup_plan_id=plan.id,
        enabled=plan.enabled,
        user=current_user.username,
    )
    return _serialize_plan(plan, detail=True)


@router.get("/{plan_id}")
async def get_backup_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _load_plan_or_404(db, plan_id)
    if not _can_view_plan(db, current_user, plan):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.auth.notEnoughPermissions"},
        )
    return _serialize_plan(plan, detail=True)


@router.put("/{plan_id}")
async def update_backup_plan(
    plan_id: int,
    payload: BackupPlanPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _load_plan_or_404(db, plan_id)
    _require_plan_operator_access(db, current_user, plan)
    try:
        repositories = _validate_payload(db, current_user, payload)
    except InvalidScheduleTimezone as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.schedule.invalidTimezone"},
        ) from exc

    existing = (
        db.query(BackupPlan)
        .filter(BackupPlan.name == payload.name.strip(), BackupPlan.id != plan_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.backupPlans.nameExists"},
        )

    _apply_payload(plan, payload)
    _replace_repository_links(db, plan, payload)
    _replace_script_hooks(db, plan, payload)
    _clear_legacy_source_settings(payload, repositories)
    db.commit()
    plan = _load_plan_or_404(db, plan_id)
    logger.info(
        "Backup plan updated", backup_plan_id=plan.id, user=current_user.username
    )
    return _serialize_plan(plan, detail=True)


@router.delete("/{plan_id}")
async def delete_backup_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _load_plan_or_404(db, plan_id)
    _require_plan_operator_access(db, current_user, plan)
    db.delete(plan)
    db.commit()
    logger.info(
        "Backup plan deleted", backup_plan_id=plan_id, user=current_user.username
    )
    return {"message": "backend.success.backupPlans.deleted"}
