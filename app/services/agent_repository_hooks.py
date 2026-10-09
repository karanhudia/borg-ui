"""A repository's own pre/post-backup hooks when an agent runs its backups.

The server cannot run a shell script for an agent repository: it would act
on the wrong machine. The hooks of such a repository are scripts its agent
publishes, assigned by name (`repository_scripts.agent_script_name`) and run
as `script.run` jobs before and after the agent backup, the way a plan's
agent hooks run, with the same contract: return code 0 = success, 1 =
warning (the backup proceeds), >1 = failure. What an assignment decides on
failure (skip the backup, continue, or count it as failed) is what it
decides for a server library script. Each run is a `script_executions` row
linked to the backup and to its agent job, which carries the output.

Inline shell scripts and server library assignments can never run for an
agent repository; `unrunnable_repository_scripts` names them so a backup can
say so instead of passing over them in silence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database.models import (
    AgentMachine,
    Repository,
    RepositoryScript,
    ScriptExecution,
)
from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
from app.services.operations.backup_facade import backup_job_link_columns
from app.services.repository_executor import (
    queue_agent_script_job,
    wait_for_agent_script_job,
)
from app.services.template_service import get_system_variables
from app.utils.http_detail import detail_text

logger = structlog.get_logger()

DEFAULT_HOOK_TIMEOUT_SECONDS = 300

# The post-backup status a skipped backup hands its hooks: only those that
# run "always" match it.
SKIPPED = "skipped"


@dataclass
class AgentHookResult:
    executed: int = 0
    failed: int = 0
    # the pre-backup hook whose failure asks to skip the backup
    skip_script: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0


def unrunnable_repository_scripts(db: Session, repository: Repository) -> list[str]:
    """The hooks of an agent repository its agent cannot run: the inline
    shell scripts and the enabled server library assignments."""
    names = []
    if (repository.pre_backup_script or "").strip():
        names.append("pre-backup inline script")
    if (repository.post_backup_script or "").strip():
        names.append("post-backup inline script")
    library = (
        db.query(RepositoryScript)
        .options(joinedload(RepositoryScript.script))
        .filter(
            RepositoryScript.repository_id == repository.id,
            RepositoryScript.enabled == True,  # noqa: E712
            RepositoryScript.script_id.isnot(None),
        )
        .order_by(RepositoryScript.hook_type.desc(), RepositoryScript.execution_order)
        .all()
    )
    names.extend(
        f"{rs.hook_type} library script '{rs.script.name if rs.script else rs.script_id}'"
        for rs in library
    )
    return names


def agent_hooks(
    db: Session,
    repository: Repository,
    hook_type: str,
    backup_result: Optional[str] = None,
) -> list[RepositoryScript]:
    """The enabled agent hooks of `hook_type` in order; post-backup ones only
    when their run_on condition matches `backup_result`."""
    hooks = (
        db.query(RepositoryScript)
        .filter(
            RepositoryScript.repository_id == repository.id,
            RepositoryScript.hook_type == hook_type,
            RepositoryScript.enabled == True,  # noqa: E712
            RepositoryScript.agent_script_name.isnot(None),
        )
        .order_by(RepositoryScript.execution_order, RepositoryScript.id)
        .all()
    )
    if hook_type == "post-backup":
        hooks = [
            rs
            for rs in hooks
            if (rs.custom_run_on or "always") in ("always", backup_result)
        ]
    return hooks


def _hook_env(
    repository: Repository,
    *,
    operation_id: int,
    hook_type: str,
    backup_result: Optional[str],
) -> dict[str, str]:
    env = get_system_variables(
        repository_id=repository.id,
        repository_name=repository.name,
        repository_path=repository.path,
        backup_status=backup_result,
        hook_type=hook_type,
        job_id=operation_id,
    )
    return {key: str(value) for key, value in env.items() if value is not None}


async def _run_one(
    db: Session,
    repository: Repository,
    agent: Optional[AgentMachine],
    rs: RepositoryScript,
    *,
    operation_id: int,
    hook_type: str,
    backup_result: Optional[str],
    is_cancelled: Optional[Callable[[], bool]],
) -> tuple[bool, Optional[str]]:
    """Run one agent hook and record it; (hook_ok, message)."""
    from app.services.backup_plan_execution_service import (
        _classify_agent_script_outcome,
    )

    name = rs.agent_script_name
    started = time.time()
    execution = ScriptExecution(
        script_id=None,
        agent_script_name=name,
        repository_id=repository.id,
        **backup_job_link_columns(db, operation_id),
        hook_type=hook_type,
        status="running",
        started_at=datetime.utcnow(),
        triggered_by="backup",
    )
    db.add(execution)
    db.commit()

    def _finish(status_value, message, rc=None, stdout=None, stderr=None):
        execution.status = status_value
        execution.completed_at = datetime.utcnow()
        execution.execution_time = time.time() - started
        execution.exit_code = rc
        execution.stdout = stdout
        execution.stderr = stderr
        execution.error_message = message
        db.commit()

    if agent is None:
        message = f"Repository {hook_type} agent script '{name}': agent not found"
        _finish("failed", message)
        return False, message
    try:
        try:
            agent_job = queue_agent_script_job(
                db,
                agent,
                script_name=name,
                env=_hook_env(
                    repository,
                    operation_id=operation_id,
                    hook_type=hook_type,
                    backup_result=backup_result,
                ),
            )
        except HTTPException as exc:
            reason = detail_text(exc.detail) or "agent cannot run scripts"
            message = f"Repository {hook_type} agent script '{name}': {reason}"
            _finish("failed", message)
            return False, message

        # The log endpoint streams the agent's output through this link.
        execution.agent_job_id = agent_job.id
        db.commit()
        await dispatch_agent_job_best_effort(db, agent_job)

        default_timeout = (
            repository.pre_hook_timeout
            if hook_type == "pre-backup"
            else repository.post_hook_timeout
        )
        outcome = await wait_for_agent_script_job(
            db,
            agent_job.id,
            is_cancelled=is_cancelled,
            timeout_seconds=float(
                rs.custom_timeout or default_timeout or DEFAULT_HOOK_TIMEOUT_SECONDS
            ),
        )
        result = outcome.get("result") or {}
        hook_ok, status_value, message = _classify_agent_script_outcome(
            outcome, hook_type=hook_type, script_name=name, scope="Repository"
        )
        logger.info(
            "Repository agent script finished",
            repository_id=repository.id,
            operation_id=operation_id,
            agent_script_name=name,
            hook_type=hook_type,
            status=status_value,
            return_code=result.get("return_code"),
        )
        _finish(
            status_value,
            message,
            result.get("return_code"),
            result.get("stdout"),
            result.get("stderr"),
        )
        return hook_ok, message
    except Exception as exc:
        # an unexpected error still closes the record, so the history does
        # not show the hook running forever; the caller sees the error
        db.rollback()
        _finish("failed", f"Repository {hook_type} agent script '{name}': {exc}")
        raise


async def run_agent_repository_hooks(
    db: Session,
    repository: Repository,
    *,
    operation_id: int,
    hook_type: str,
    backup_result: Optional[str] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> AgentHookResult:
    """Run the repository's agent hooks of `hook_type` (`agent_hooks`).

    Like the server's library hooks, a failed hook does not stop the hooks
    after it: a pre-backup hook marked skip_on_failure asks to skip the
    backup, one with continue_on_error (the default) becomes a warning, any
    other counts as failed and the caller decides.
    """
    result = AgentHookResult()
    hooks = agent_hooks(db, repository, hook_type, backup_result)
    if not hooks:
        return result

    agent = (
        db.get(AgentMachine, repository.agent_machine_id)
        if repository.agent_machine_id
        else None
    )
    for rs in hooks:
        if is_cancelled is not None and is_cancelled():
            break
        hook_ok, message = await _run_one(
            db,
            repository,
            agent,
            rs,
            operation_id=operation_id,
            hook_type=hook_type,
            backup_result=backup_result,
            is_cancelled=is_cancelled,
        )
        result.executed += 1
        if hook_ok:
            # return code 1: the hook passed with a warning
            if message:
                result.warnings.append(message)
            continue
        if hook_type == "pre-backup" and rs.skip_on_failure:
            result.skip_script = rs.agent_script_name
            return result
        if rs.continue_on_error is None or rs.continue_on_error:
            result.warnings.append(message)
            continue
        result.failed += 1
    return result
