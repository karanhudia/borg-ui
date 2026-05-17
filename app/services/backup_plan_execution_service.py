from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog
from sqlalchemy.orm import Session, joinedload

from app.api.maintenance_jobs import create_started_maintenance_job
from app.config import settings
from app.core.borg_router import BorgRouter
from app.core.security import decrypt_secret
from app.database.database import SessionLocal
from app.database.models import (
    BackupJob,
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    BackupPlanRunRepository,
    CheckJob,
    CompactJob,
    PruneJob,
    Repository,
    Script,
    ScriptExecution,
    SSHConnection,
)
from app.services.backup_service import backup_service
from app.services.backup_plan_policy import evaluate_backup_plan_access
from app.services.script_executor import execute_script
from app.services.template_service import get_system_variables
from app.utils.archive_names import build_archive_name
from app.utils.script_params import SYSTEM_VARIABLE_PREFIX
from app.utils.source_locations import decode_source_locations
from app.utils.schedule_time import calculate_next_cron_run, to_utc_naive

logger = structlog.get_logger()

ACTIVE_PLAN_RUN_STATUSES = {"pending", "running"}
TERMINAL_PLAN_RUN_STATUSES = {
    "completed",
    "completed_with_warnings",
    "partial",
    "failed",
    "cancelled",
}
SUCCESS_BACKUP_STATUSES = {"completed", "completed_with_warnings"}
WARNING_BACKUP_STATUSES = {"completed_with_warnings", "skipped"}
CANCELLED_MESSAGE = '{"key": "backend.errors.backup.cancelledByUser"}'


@dataclass(frozen=True)
class PlanRunContext:
    plan_id: int
    plan_name: str
    source_type: str
    source_ssh_connection_id: Optional[int]
    source_directories: list[str]
    source_locations: list[dict[str, Any]]
    exclude_patterns: list[str]
    archive_name_template: str
    compression: str
    custom_flags: Optional[str]
    upload_ratelimit_kib: Optional[int]
    repository_run_mode: str
    max_parallel_repositories: int
    failure_behavior: str
    pre_backup_script_id: Optional[int]
    post_backup_script_id: Optional[int]
    pre_backup_script_parameters: dict[str, Any]
    post_backup_script_parameters: dict[str, Any]
    run_repository_scripts: bool
    run_prune_after: bool
    run_compact_after: bool
    run_check_after: bool
    check_max_duration: int
    check_extra_flags: Optional[str]
    prune_keep_hourly: int
    prune_keep_daily: int
    prune_keep_weekly: int
    prune_keep_monthly: int
    prune_keep_quarterly: int
    prune_keep_yearly: int
    repository_count: int
    timestamp: str
    date: str
    time_str: str
    unix_timestamp: str


@dataclass(frozen=True)
class RepositoryRunContext:
    repository_id: int
    repository_name: str
    execution_order: int
    compression: str
    custom_flags: Optional[str]
    upload_ratelimit_kib: Optional[int]
    failure_behavior: str


def _json_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def _is_failure(status: Optional[str]) -> bool:
    return (
        status not in SUCCESS_BACKUP_STATUSES and status not in WARNING_BACKUP_STATUSES
    )


def _is_success(status: Optional[str]) -> bool:
    return status in SUCCESS_BACKUP_STATUSES


class BackupPlanExecutionService:
    def dispatch_due_runs(self, db: Session, now: datetime) -> int:
        now = to_utc_naive(now)
        due_plans = (
            db.query(BackupPlan)
            .options(
                joinedload(BackupPlan.repositories).joinedload(
                    BackupPlanRepository.repository
                )
            )
            .filter(
                BackupPlan.enabled == True,
                BackupPlan.schedule_enabled == True,
                BackupPlan.next_run <= now,
            )
            .order_by(BackupPlan.next_run.asc(), BackupPlan.id.asc())
            .all()
        )

        dispatched = 0
        for plan in due_plans:
            if self.has_active_run(db, plan.id):
                continue
            access_decision = evaluate_backup_plan_access(db, plan)
            if not access_decision.allowed:
                logger.warning(
                    "Skipping scheduled backup plan due to feature access",
                    backup_plan_id=plan.id,
                    feature=access_decision.feature,
                    required=access_decision.required.value,
                    current=access_decision.current.value,
                    reason=access_decision.reason,
                )
                plan.next_run = (
                    calculate_next_cron_run(
                        plan.cron_expression,
                        base_time=now,
                        schedule_timezone=plan.timezone,
                    )
                    if plan.cron_expression
                    else None
                )
                db.commit()
                continue
            try:
                self.start_run(db, plan, trigger="schedule")
                plan.last_run = now
                plan.next_run = (
                    calculate_next_cron_run(
                        plan.cron_expression,
                        base_time=now,
                        schedule_timezone=plan.timezone,
                    )
                    if plan.cron_expression
                    else None
                )
                db.commit()
                dispatched += 1
            except Exception as exc:
                logger.error(
                    "Failed to dispatch scheduled backup plan",
                    backup_plan_id=plan.id,
                    error=str(exc),
                )
                db.rollback()
        return dispatched

    def has_active_run(self, db: Session, plan_id: int) -> bool:
        return (
            db.query(BackupPlanRun)
            .filter(
                BackupPlanRun.backup_plan_id == plan_id,
                BackupPlanRun.status.in_(ACTIVE_PLAN_RUN_STATUSES),
            )
            .first()
            is not None
        )

    async def cancel_run(self, db: Session, run_id: int) -> dict[str, int | bool]:
        run = (
            db.query(BackupPlanRun)
            .options(
                joinedload(BackupPlanRun.repositories).joinedload(
                    BackupPlanRunRepository.backup_job
                )
            )
            .filter(BackupPlanRun.id == run_id)
            .first()
        )
        if not run:
            raise ValueError("Backup plan run not found")
        if run.status in TERMINAL_PLAN_RUN_STATUSES:
            return {
                "cancelled_repositories": 0,
                "cancelled_backup_jobs": 0,
                "processes_terminated": 0,
                "already_terminal": True,
            }

        now = datetime.utcnow()
        cancelled_repositories = 0
        cancelled_backup_jobs = 0
        processes_terminated = 0

        run.status = "cancelled"
        run.completed_at = now
        run.error_message = CANCELLED_MESSAGE

        for child in run.repositories:
            if child.status in {
                "completed",
                "completed_with_warnings",
                "failed",
                "cancelled",
            }:
                continue

            job = child.backup_job
            if job and job.status == "running":
                process_killed = await backup_service.cancel_backup(job.id)
                if process_killed:
                    processes_terminated += 1
                job.status = "cancelled"
                job.completed_at = now
                job.error_message = CANCELLED_MESSAGE
                cancelled_backup_jobs += 1
            elif job and job.maintenance_status in {"running_prune", "running_compact"}:
                if await self._cancel_running_maintenance(db, job):
                    processes_terminated += 1
            elif job and job.status in {"pending"}:
                job.status = "cancelled"
                job.completed_at = now
                job.error_message = CANCELLED_MESSAGE
                cancelled_backup_jobs += 1

            child.status = "cancelled"
            child.completed_at = now
            child.error_message = CANCELLED_MESSAGE
            cancelled_repositories += 1

        db.commit()
        return {
            "cancelled_repositories": cancelled_repositories,
            "cancelled_backup_jobs": cancelled_backup_jobs,
            "processes_terminated": processes_terminated,
            "already_terminal": False,
        }

    async def _cancel_running_maintenance(
        self, db: Session, backup_job: BackupJob
    ) -> bool:
        repo = (
            db.query(Repository)
            .filter(
                (Repository.id == backup_job.repository_id)
                | (Repository.path == backup_job.repository)
            )
            .first()
        )
        if not repo:
            return False

        if backup_job.maintenance_status == "running_prune":
            maintenance_job = (
                db.query(PruneJob)
                .filter(
                    PruneJob.repository_id == repo.id,
                    PruneJob.status == "running",
                )
                .order_by(PruneJob.id.desc())
                .first()
            )
            if not maintenance_job:
                return False
            if getattr(repo, "borg_version", 1) == 2:
                from app.services.v2.prune_service import prune_v2_service

                process_killed = await prune_v2_service.cancel_prune(maintenance_job.id)
            else:
                from app.services.prune_service import prune_service

                process_killed = await prune_service.cancel_prune(maintenance_job.id)
            maintenance_job.status = "cancelled"
            maintenance_job.completed_at = datetime.utcnow()
            backup_job.maintenance_status = "prune_failed"
            return process_killed

        if backup_job.maintenance_status == "running_compact":
            maintenance_job = (
                db.query(CompactJob)
                .filter(
                    CompactJob.repository_id == repo.id,
                    CompactJob.status == "running",
                )
                .order_by(CompactJob.id.desc())
                .first()
            )
            if not maintenance_job:
                return False
            if getattr(repo, "borg_version", 1) == 2:
                from app.services.v2.compact_service import compact_v2_service

                process_killed = await compact_v2_service.cancel_compact(
                    maintenance_job.id
                )
            else:
                from app.services.compact_service import compact_service

                process_killed = await compact_service.cancel_compact(
                    maintenance_job.id
                )
            maintenance_job.status = "cancelled"
            maintenance_job.completed_at = datetime.utcnow()
            backup_job.maintenance_status = "compact_failed"
            return process_killed

        return False

    def start_run(self, db: Session, plan: BackupPlan, *, trigger: str) -> int:
        enabled_links = [
            link
            for link in sorted(plan.repositories, key=lambda item: item.execution_order)
            if link.enabled
        ]
        if not enabled_links:
            raise ValueError("Backup plan has no enabled repositories")

        run = BackupPlanRun(
            backup_plan_id=plan.id,
            trigger=trigger,
            status="pending",
            created_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()

        for link in enabled_links:
            db.add(
                BackupPlanRunRepository(
                    backup_plan_run_id=run.id,
                    repository_id=link.repository_id,
                    status="pending",
                )
            )

        db.commit()
        asyncio.create_task(self.execute_run(run.id))
        return run.id

    async def execute_run(self, run_id: int) -> None:
        try:
            context, repositories = self._prepare_run(run_id)
            pre_script_ok, pre_script_error = await self._execute_plan_script(
                run_id,
                context,
                hook_type="pre-backup",
            )
            if not pre_script_ok:
                error_message = pre_script_error or "Plan pre-backup script failed"
                self._mark_pending_repositories_failed(run_id, error_message)
                raise ValueError(error_message)

            if context.repository_run_mode == "parallel":
                await self._execute_parallel(run_id, context, repositories)
            else:
                await self._execute_series(run_id, context, repositories)

            post_script_warning = None
            if not self._is_run_cancelled(run_id):
                backup_result = self._plan_backup_result(run_id)
                post_script_ok, post_script_error = await self._execute_plan_script(
                    run_id,
                    context,
                    hook_type="post-backup",
                    backup_result=backup_result,
                )
                if not post_script_ok:
                    post_script_warning = (
                        post_script_error or "Plan post-backup script failed"
                    )

            self._finalize_run(run_id, warning_message=post_script_warning)
        except Exception as exc:
            logger.error("Backup plan run failed", run_id=run_id, error=str(exc))
            self._mark_run_failed(run_id, str(exc))

    def _prepare_run(
        self, run_id: int
    ) -> tuple[PlanRunContext, list[RepositoryRunContext]]:
        db = SessionLocal()
        try:
            run = db.query(BackupPlanRun).filter(BackupPlanRun.id == run_id).first()
            if not run:
                raise ValueError(f"Backup plan run {run_id} not found")

            plan = (
                db.query(BackupPlan)
                .options(
                    joinedload(BackupPlan.repositories).joinedload(
                        BackupPlanRepository.repository
                    )
                )
                .filter(BackupPlan.id == run.backup_plan_id)
                .first()
            )
            if not plan:
                raise ValueError("Backup plan no longer exists")
            if not plan.enabled:
                raise ValueError("Backup plan is disabled")

            enabled_links = [
                link
                for link in sorted(
                    plan.repositories, key=lambda item: item.execution_order
                )
                if link.enabled and link.repository
            ]
            if not enabled_links:
                raise ValueError("Backup plan has no enabled repositories")

            now = datetime.now()
            context = PlanRunContext(
                plan_id=plan.id,
                plan_name=plan.name,
                source_type=plan.source_type,
                source_ssh_connection_id=plan.source_ssh_connection_id,
                source_directories=_json_list(plan.source_directories),
                source_locations=decode_source_locations(
                    plan.source_locations,
                    source_type=plan.source_type,
                    source_ssh_connection_id=plan.source_ssh_connection_id,
                    source_directories=_json_list(plan.source_directories),
                ),
                exclude_patterns=_json_list(plan.exclude_patterns),
                archive_name_template=plan.archive_name_template,
                compression=plan.compression,
                custom_flags=plan.custom_flags,
                upload_ratelimit_kib=plan.upload_ratelimit_kib,
                repository_run_mode=plan.repository_run_mode,
                max_parallel_repositories=max(1, plan.max_parallel_repositories or 1),
                failure_behavior=plan.failure_behavior,
                pre_backup_script_id=plan.pre_backup_script_id,
                post_backup_script_id=plan.post_backup_script_id,
                pre_backup_script_parameters=plan.pre_backup_script_parameters or {},
                post_backup_script_parameters=plan.post_backup_script_parameters or {},
                run_repository_scripts=bool(plan.run_repository_scripts),
                run_prune_after=bool(plan.run_prune_after),
                run_compact_after=bool(plan.run_compact_after),
                run_check_after=bool(plan.run_check_after),
                check_max_duration=plan.check_max_duration,
                check_extra_flags=plan.check_extra_flags,
                prune_keep_hourly=plan.prune_keep_hourly,
                prune_keep_daily=plan.prune_keep_daily,
                prune_keep_weekly=plan.prune_keep_weekly,
                prune_keep_monthly=plan.prune_keep_monthly,
                prune_keep_quarterly=plan.prune_keep_quarterly,
                prune_keep_yearly=plan.prune_keep_yearly,
                repository_count=len(enabled_links),
                timestamp=now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
                date=now.strftime("%Y-%m-%d"),
                time_str=now.strftime("%H:%M:%S"),
                unix_timestamp=str(int(now.timestamp() * 1000)),
            )
            repositories = [
                RepositoryRunContext(
                    repository_id=link.repository_id,
                    repository_name=link.repository.name,
                    execution_order=link.execution_order,
                    compression=(
                        link.repository.compression or context.compression
                        if link.compression_source == "repository"
                        else link.compression_override
                        if link.compression_source == "custom"
                        and link.compression_override
                        else context.compression
                    ),
                    custom_flags=(
                        link.custom_flags_override
                        if link.custom_flags_override is not None
                        else context.custom_flags
                    ),
                    upload_ratelimit_kib=(
                        link.upload_ratelimit_kib_override
                        if link.upload_ratelimit_kib_override is not None
                        else context.upload_ratelimit_kib
                    ),
                    failure_behavior=(
                        link.failure_behavior_override or context.failure_behavior
                    ),
                )
                for link in enabled_links
            ]

            run.status = "running"
            run.started_at = datetime.utcnow()
            plan.last_run = run.started_at
            db.commit()
            return context, repositories
        finally:
            db.close()

    async def _execute_series(
        self,
        run_id: int,
        context: PlanRunContext,
        repositories: list[RepositoryRunContext],
    ) -> None:
        for index, repository in enumerate(repositories):
            if self._is_run_cancelled(run_id):
                for skipped in repositories[index:]:
                    self._mark_repository_cancelled(run_id, skipped.repository_id)
                return
            status = await self._execute_repository(run_id, context, repository)
            if self._is_run_cancelled(run_id):
                for skipped in repositories[index + 1 :]:
                    self._mark_repository_cancelled(run_id, skipped.repository_id)
                return
            if repository.failure_behavior == "stop" and _is_failure(status):
                for skipped in repositories[index + 1 :]:
                    self._mark_repository_skipped(run_id, skipped.repository_id)
                return

    async def _execute_parallel(
        self,
        run_id: int,
        context: PlanRunContext,
        repositories: list[RepositoryRunContext],
    ) -> None:
        semaphore = asyncio.Semaphore(context.max_parallel_repositories)
        stop_event = asyncio.Event()

        async def worker(repository: RepositoryRunContext) -> None:
            if self._is_run_cancelled(run_id):
                self._mark_repository_cancelled(run_id, repository.repository_id)
                return
            if stop_event.is_set():
                self._mark_repository_skipped(run_id, repository.repository_id)
                return
            async with semaphore:
                if self._is_run_cancelled(run_id):
                    self._mark_repository_cancelled(run_id, repository.repository_id)
                    return
                if stop_event.is_set():
                    self._mark_repository_skipped(run_id, repository.repository_id)
                    return
                status = await self._execute_repository(run_id, context, repository)
                if repository.failure_behavior == "stop" and _is_failure(status):
                    stop_event.set()

        await asyncio.gather(*(worker(repository) for repository in repositories))

    async def _execute_plan_script(
        self,
        run_id: int,
        context: PlanRunContext,
        *,
        hook_type: str,
        backup_result: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        script_id = (
            context.pre_backup_script_id
            if hook_type == "pre-backup"
            else context.post_backup_script_id
        )
        if not script_id:
            return True, None

        script_parameters = (
            context.pre_backup_script_parameters
            if hook_type == "pre-backup"
            else context.post_backup_script_parameters
        )

        db = SessionLocal()
        execution: Optional[ScriptExecution] = None
        start_time = time.time()
        try:
            script = db.query(Script).filter(Script.id == script_id).first()
            if not script:
                return False, f"Plan {hook_type} script not found"

            execution = ScriptExecution(
                script_id=script.id,
                backup_plan_id=context.plan_id,
                backup_plan_run_id=run_id,
                hook_type=hook_type,
                status="running",
                started_at=datetime.utcnow(),
                triggered_by="backup_plan",
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)

            file_path = Path(settings.data_dir) / "scripts" / script.file_path
            if not file_path.exists():
                raise FileNotFoundError(f"Script file not found: {script.file_path}")

            source_connection = None
            if context.source_type == "remote" and context.source_ssh_connection_id:
                source_connection = (
                    db.query(SSHConnection)
                    .filter(SSHConnection.id == context.source_ssh_connection_id)
                    .first()
                )

            script_env = os.environ.copy()
            script_env.update(
                get_system_variables(
                    backup_status=backup_result,
                    hook_type=hook_type,
                    source_host=source_connection.host if source_connection else None,
                    source_port=source_connection.port if source_connection else None,
                    source_username=(
                        source_connection.username if source_connection else None
                    ),
                )
            )
            script_env.update(
                {
                    "BORG_UI_BACKUP_PLAN_ID": str(context.plan_id),
                    "BORG_UI_BACKUP_PLAN_NAME": context.plan_name,
                    "BORG_UI_BACKUP_PLAN_RUN_ID": str(run_id),
                    "BORG_UI_REPOSITORY_COUNT": str(context.repository_count),
                    "BORG_UI_SOURCE_TYPE": context.source_type,
                    "BORG_UI_SOURCE_DIRECTORIES": json.dumps(
                        context.source_directories
                    ),
                    "BORG_UI_SOURCE_LOCATIONS": json.dumps(context.source_locations),
                }
            )
            if source_connection:
                script_env.update(
                    {
                        "BORG_UI_SOURCE_HOST": source_connection.host or "",
                        "BORG_UI_SOURCE_PORT": str(source_connection.port or 22),
                        "BORG_UI_SOURCE_USERNAME": source_connection.username or "",
                    }
                )

            self._inject_script_parameters(script_env, script, script_parameters)

            result = await execute_script(
                script=file_path.read_text(),
                timeout=float(script.timeout),
                env=script_env,
                context=f"backup-plan:{context.plan_id}:{hook_type}:script:{script.id}",
            )

            execution.status = "completed" if result.get("success") else "failed"
            execution.completed_at = datetime.utcnow()
            execution.execution_time = time.time() - start_time
            execution.exit_code = result.get("exit_code")
            execution.stdout = result.get("stdout")
            execution.stderr = result.get("stderr")
            if not result.get("success"):
                stderr = result.get("stderr") or ""
                error = stderr.strip() or f"exit code {result.get('exit_code')}"
                execution.error_message = error

            script.last_used_at = datetime.utcnow()
            db.commit()

            if not result.get("success"):
                return False, f"Plan {hook_type} script '{script.name}' failed: {error}"

            logger.info(
                "Backup plan script completed",
                backup_plan_id=context.plan_id,
                backup_plan_run_id=run_id,
                script_id=script.id,
                hook_type=hook_type,
            )
            return True, None
        except Exception as exc:
            db.rollback()
            if execution is not None:
                execution.status = "failed"
                execution.completed_at = datetime.utcnow()
                execution.execution_time = time.time() - start_time
                execution.error_message = str(exc)
                execution.stderr = str(exc)
                db.commit()
            logger.error(
                "Backup plan script failed",
                backup_plan_id=context.plan_id,
                backup_plan_run_id=run_id,
                script_id=script_id,
                hook_type=hook_type,
                error=str(exc),
            )
            return False, str(exc)
        finally:
            db.close()

    def _inject_script_parameters(
        self,
        script_env: dict[str, str],
        script: Script,
        parameter_values: dict[str, Any],
    ) -> None:
        if not script.parameters:
            return

        parameters = json.loads(script.parameters)
        for param_def in parameters:
            param_name = param_def["name"]
            if param_name.startswith(SYSTEM_VARIABLE_PREFIX):
                continue

            default_value = param_def.get("default", "")
            value = parameter_values.get(param_name, default_value)
            if param_def.get("type", "text") == "password" and value:
                try:
                    value = decrypt_secret(value)
                except Exception:
                    logger.debug(
                        "Using stored plan script password parameter as provided",
                        script_id=script.id,
                        param_name=param_name,
                    )
            script_env[param_name] = "" if value is None else str(value)

    async def _execute_repository(
        self,
        run_id: int,
        context: PlanRunContext,
        repository_context: RepositoryRunContext,
    ) -> str:
        db = SessionLocal()
        try:
            child = (
                db.query(BackupPlanRunRepository)
                .filter(
                    BackupPlanRunRepository.backup_plan_run_id == run_id,
                    BackupPlanRunRepository.repository_id
                    == repository_context.repository_id,
                )
                .first()
            )
            repo = (
                db.query(Repository)
                .filter(Repository.id == repository_context.repository_id)
                .first()
            )
            if not child or not repo:
                return "failed"

            backup_job = BackupJob(
                repository=repo.path,
                repository_id=repo.id,
                backup_plan_id=context.plan_id,
                backup_plan_run_id=run_id,
                status="pending",
                source_ssh_connection_id=(
                    context.source_ssh_connection_id
                    if context.source_type == "remote"
                    else None
                ),
                created_at=datetime.utcnow(),
            )
            db.add(backup_job)
            db.flush()

            child.backup_job_id = backup_job.id
            child.status = "running"
            child.started_at = datetime.utcnow()
            db.commit()

            archive_name = build_archive_name(
                job_name=context.plan_name,
                repo_name=repository_context.repository_name,
                template=context.archive_name_template,
                timestamp=context.timestamp,
                date=context.date,
                time_str=context.time_str,
                unix_timestamp=context.unix_timestamp,
                stable_series=getattr(repo, "borg_version", 1) == 2,
            )

            await backup_service.execute_backup(
                backup_job.id,
                repo.path,
                db,
                archive_name=archive_name,
                skip_hooks=not context.run_repository_scripts,
                source_directories=context.source_directories,
                source_ssh_connection_id=(
                    context.source_ssh_connection_id
                    if context.source_type == "remote"
                    else None
                ),
                source_locations=context.source_locations,
                exclude_patterns_override=context.exclude_patterns,
                compression_override=repository_context.compression,
                custom_flags_override=repository_context.custom_flags,
                upload_ratelimit_kib=repository_context.upload_ratelimit_kib,
            )

            db.refresh(backup_job)
            final_status = backup_job.status or "failed"
            if final_status in SUCCESS_BACKUP_STATUSES:
                if self._is_run_cancelled(run_id):
                    child.status = "cancelled"
                    child.completed_at = datetime.utcnow()
                    child.error_message = CANCELLED_MESSAGE
                    db.commit()
                    return "cancelled"

                maintenance_status = await self._run_maintenance(
                    db, backup_job, repo, context, run_id
                )
                if maintenance_status == "cancelled":
                    child.status = "cancelled"
                    child.completed_at = datetime.utcnow()
                    child.error_message = CANCELLED_MESSAGE
                    db.commit()
                    return "cancelled"
                if maintenance_status == "completed_with_warnings":
                    final_status = "completed_with_warnings"

            child.status = final_status
            child.completed_at = backup_job.completed_at or datetime.utcnow()
            child.error_message = backup_job.error_message
            db.commit()
            return final_status
        except Exception as exc:
            logger.error(
                "Backup plan repository execution failed",
                run_id=run_id,
                repository_id=repository_context.repository_id,
                error=str(exc),
            )
            self._mark_repository_failed(
                run_id, repository_context.repository_id, str(exc)
            )
            return "failed"
        finally:
            db.close()

    async def _run_maintenance(
        self,
        db: Session,
        backup_job: BackupJob,
        repo: Repository,
        context: PlanRunContext,
        run_id: int,
    ) -> str:
        maintenance_ok = True

        if context.run_prune_after:
            if self._is_run_cancelled(run_id):
                return "cancelled"
            prune_job = create_started_maintenance_job(
                db,
                PruneJob,
                repo,
                extra_fields={"scheduled_prune": False},
            )
            backup_job.maintenance_status = "running_prune"
            db.commit()
            await BorgRouter(repo).prune(
                job_id=prune_job.id,
                keep_hourly=context.prune_keep_hourly,
                keep_daily=context.prune_keep_daily,
                keep_weekly=context.prune_keep_weekly,
                keep_monthly=context.prune_keep_monthly,
                keep_quarterly=context.prune_keep_quarterly,
                keep_yearly=context.prune_keep_yearly,
                dry_run=False,
            )
            db.refresh(prune_job)
            if self._is_run_cancelled(run_id):
                return "cancelled"
            if prune_job.status == "completed":
                backup_job.maintenance_status = "prune_completed"
            else:
                backup_job.maintenance_status = "prune_failed"
                maintenance_ok = False
            db.commit()

        if context.run_compact_after:
            if self._is_run_cancelled(run_id):
                return "cancelled"
            compact_job = create_started_maintenance_job(
                db,
                CompactJob,
                repo,
                extra_fields={"scheduled_compact": False},
            )
            backup_job.maintenance_status = "running_compact"
            db.commit()
            await BorgRouter(repo).compact(compact_job.id)
            db.refresh(compact_job)
            if self._is_run_cancelled(run_id):
                return "cancelled"
            if compact_job.status == "completed":
                backup_job.maintenance_status = "compact_completed"
            else:
                backup_job.maintenance_status = "compact_failed"
                maintenance_ok = False
            db.commit()

        if context.run_check_after:
            if self._is_run_cancelled(run_id):
                return "cancelled"
            check_job = create_started_maintenance_job(
                db,
                CheckJob,
                repo,
                extra_fields={
                    "scheduled_check": False,
                    "max_duration": context.check_max_duration,
                    "extra_flags": context.check_extra_flags,
                },
            )
            backup_job.maintenance_status = "running_check"
            db.commit()
            await BorgRouter(repo).check(check_job.id)
            db.refresh(check_job)
            if self._is_run_cancelled(run_id):
                return "cancelled"
            if check_job.status == "completed":
                backup_job.maintenance_status = "check_completed"
            else:
                backup_job.maintenance_status = "check_failed"
                maintenance_ok = False
            db.commit()

        if (
            backup_job.maintenance_status
            and "failed" not in backup_job.maintenance_status
        ):
            backup_job.maintenance_status = "maintenance_completed"
            db.commit()

        return "completed" if maintenance_ok else "completed_with_warnings"

    def _mark_repository_skipped(self, run_id: int, repository_id: int) -> None:
        db = SessionLocal()
        try:
            child = (
                db.query(BackupPlanRunRepository)
                .filter(
                    BackupPlanRunRepository.backup_plan_run_id == run_id,
                    BackupPlanRunRepository.repository_id == repository_id,
                    BackupPlanRunRepository.status == "pending",
                )
                .first()
            )
            if child:
                child.status = "skipped"
                child.completed_at = datetime.utcnow()
                child.error_message = "Skipped after an earlier repository failed"
                db.commit()
        finally:
            db.close()

    def _mark_repository_cancelled(self, run_id: int, repository_id: int) -> None:
        db = SessionLocal()
        try:
            child = (
                db.query(BackupPlanRunRepository)
                .filter(
                    BackupPlanRunRepository.backup_plan_run_id == run_id,
                    BackupPlanRunRepository.repository_id == repository_id,
                    BackupPlanRunRepository.status == "pending",
                )
                .first()
            )
            if child:
                child.status = "cancelled"
                child.completed_at = datetime.utcnow()
                child.error_message = CANCELLED_MESSAGE
                db.commit()
        finally:
            db.close()

    def _mark_repository_failed(
        self, run_id: int, repository_id: int, error_message: str
    ) -> None:
        db = SessionLocal()
        try:
            child = (
                db.query(BackupPlanRunRepository)
                .filter(
                    BackupPlanRunRepository.backup_plan_run_id == run_id,
                    BackupPlanRunRepository.repository_id == repository_id,
                )
                .first()
            )
            if child:
                child.status = "failed"
                child.completed_at = datetime.utcnow()
                child.error_message = error_message
                db.commit()
        finally:
            db.close()

    def _mark_pending_repositories_failed(
        self, run_id: int, error_message: str
    ) -> None:
        db = SessionLocal()
        try:
            children = (
                db.query(BackupPlanRunRepository)
                .filter(
                    BackupPlanRunRepository.backup_plan_run_id == run_id,
                    BackupPlanRunRepository.status == "pending",
                )
                .all()
            )
            now = datetime.utcnow()
            for child in children:
                child.status = "failed"
                child.completed_at = now
                child.error_message = error_message
            db.commit()
        finally:
            db.close()

    def _plan_backup_result(self, run_id: int) -> str:
        db = SessionLocal()
        try:
            statuses = [
                status
                for (status,) in db.query(BackupPlanRunRepository.status)
                .filter(BackupPlanRunRepository.backup_plan_run_id == run_id)
                .all()
            ]
            if not statuses:
                return "failure"
            if any(_is_failure(status) for status in statuses):
                return "failure"
            if any(status in WARNING_BACKUP_STATUSES for status in statuses):
                return "warning"
            return "success"
        finally:
            db.close()

    def _finalize_run(
        self, run_id: int, *, warning_message: Optional[str] = None
    ) -> None:
        db = SessionLocal()
        try:
            run = (
                db.query(BackupPlanRun)
                .options(joinedload(BackupPlanRun.repositories))
                .filter(BackupPlanRun.id == run_id)
                .first()
            )
            if not run:
                return
            if run.status == "cancelled":
                return
            statuses = [child.status for child in run.repositories]
            has_success = any(_is_success(status) for status in statuses)
            has_failure = any(_is_failure(status) for status in statuses)
            has_cancelled = any(status == "cancelled" for status in statuses)
            has_warning = warning_message or any(
                status in WARNING_BACKUP_STATUSES for status in statuses
            )
            if has_cancelled and not has_success:
                run.status = "cancelled"
                run.completed_at = run.completed_at or datetime.utcnow()
                db.commit()
                return
            if has_success and (has_failure or has_cancelled):
                run.status = "partial"
            elif has_failure:
                run.status = "failed"
            elif has_warning:
                run.status = "completed_with_warnings"
            else:
                run.status = "completed"
            if warning_message and run.status == "completed_with_warnings":
                run.error_message = warning_message
            run.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def _is_run_cancelled(self, run_id: int) -> bool:
        db = SessionLocal()
        try:
            return (
                db.query(BackupPlanRun.status)
                .filter(BackupPlanRun.id == run_id)
                .scalar()
                == "cancelled"
            )
        finally:
            db.close()

    def _mark_run_failed(self, run_id: int, error_message: str) -> None:
        db = SessionLocal()
        try:
            run = db.query(BackupPlanRun).filter(BackupPlanRun.id == run_id).first()
            if run:
                run.status = "failed"
                run.error_message = error_message
                run.completed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()


backup_plan_execution_service = BackupPlanExecutionService()
