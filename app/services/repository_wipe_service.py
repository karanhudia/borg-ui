import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.borg_major import borg_major
from app.config import settings
from app.core.borg_router import BorgRouter
from app.database.database import SessionLocal
from app.database.models import (
    AgentJob,
    Operation,
    Repository,
    RepositoryWipeJob,
    User,
    utc_now,
)
from app.services.operations.details import wipe_details
from app.services.operations.enqueue import enqueue, wake_runner
from app.services.operations.wipe_facade import (
    WipeJobFacade,
    active_wipe_operation,
    resolve_wipe_job,
)
from app.services.agent_job_dispatcher import (
    dispatch_agent_cancel_if_connected,
    dispatch_agent_job_best_effort,
)
from app.services.log_policy import DEFAULT_LOG_SAVE_POLICY, job_has_logs_by_policy
from app.services.repository_command_lock import run_serialized_repository_command
from app.services.repository_executor import (
    AGENT_DELETE_ARCHIVES_JOB_KIND,
    abandon_agent_repository_operation_job,
    agent_supports_job,
    agent_timezone_for_repository,
    is_agent_executor,
    queue_agent_repository_operation_job,
    wait_for_agent_repository_operation_job,
)
from app.utils.borg_env import build_repository_borg_env, cleanup_temp_key_file
from app.utils.datetime_utils import serialize_borg_archive_time, serialize_datetime

logger = structlog.get_logger()

# Kinds whose queued or running operation blocks a wipe. `rclone_sync` is
# not here, because it takes the rclone lock scope, not the repository lane
# (spec 7.2), and mirrors a repository nobody is writing to.
CONFLICTING_KINDS = (
    "backup",
    "check",
    "prune",
    "compact",
    "delete_archive",
    "restore",
    "restore_check",
)
TERMINAL_EXECUTION_STATUSES = {
    "completed",
    "completed_compaction_failed",
    "completed_with_warnings",
    "failed",
    "failed_partial",
    "cancelled",
}


class WipeArchiveSetChanged(Exception):
    """Raised when execution no longer matches the previewed archive set."""


class _AgentDeleteFailed(Exception):
    """The delete phase of an agent wipe ended on a failure; `partial` when
    archives may have been deleted before it."""

    def __init__(self, reason: str, *, partial: bool):
        self.reason = reason
        self.partial = partial
        super().__init__(reason)


class WipeValidationError(Exception):
    """Raised when an execution request fails confirmation validation."""

    def __init__(self, detail_key: str, *, status_code: int = 400):
        self.detail_key = detail_key
        self.status_code = status_code
        super().__init__(detail_key)


def _archive_display_name(archive: dict[str, Any]) -> str:
    value = archive.get("name") or archive.get("archive") or archive.get("id")
    return str(value) if value is not None else ""


def normalize_archive_manifest(
    *, borg_version: int, archives: list[Any], timezone_name: str | None = "UTC"
) -> list[dict[str, Any]]:
    """Return a stable, secret-free archive manifest for fingerprinting/UI."""
    manifest: list[dict[str, Any]] = []
    for archive in archives:
        if not isinstance(archive, dict):
            archive = {"name": str(archive)}

        identity_value = (
            archive.get("id")
            if borg_version == 2
            else archive.get("name") or archive.get("archive")
        )
        if identity_value is None:
            identity_value = archive.get("name") or archive.get("archive")
        if identity_value is None:
            raise ValueError("Archive identity is missing")

        tags = archive.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]

        # Select on None, not truthiness - the epoch 0 is a valid time.
        time_value = archive.get("time")
        if time_value is None:
            time_value = archive.get("start")

        manifest.append(
            {
                "identity": str(identity_value),
                "name": _archive_display_name(archive),
                # A server-side listing runs under TZ=UTC (the wrapper pins
                # it), an agent's in the agent's zone.
                "time": serialize_borg_archive_time(
                    time_value,
                    timezone_name=timezone_name,
                ),
                "id": archive.get("id"),
                "protected": "@PROT" in tags,
            }
        )
    return manifest


def compute_archive_fingerprint(
    manifest: list[dict[str, Any]], *, agent_machine_id: int | None = None
) -> str:
    """Compute a stable fingerprint over the archive identity set only.

    An agent repository's fingerprint names its agent too: the archives were
    listed by that agent, and a confirmation must not carry over to another
    one that holds a repository at the same path."""
    canonical: Any = [
        {"identity": str(item["identity"])}
        for item in sorted(manifest, key=lambda value: str(value["identity"]))
    ]
    if agent_machine_id is not None:
        canonical = {"agent": agent_machine_id, "archives": canonical}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decode_json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _command_output(result: dict[str, Any]) -> str:
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    return "\n".join(part for part in [stdout, stderr] if part)


def _preview_already_consumed(db: Session, preview_id: int) -> bool:
    """True once a wipe operation names this preview. Replaces the legacy
    `status != "previewed"` gate: the preview row keeps its own status and the
    operation is the record of the confirmed run. Scanned in Python because a
    JSON column is not portably queryable across SQLite and PostgreSQL, the
    same shape phase 5 used for `active_delete_for_archive`."""
    for operation in db.query(Operation).filter(Operation.kind == "wipe").all():
        if (operation.params or {}).get("preview_id") == preview_id:
            return True
    return False


def _partial_delete_signal(output: str) -> bool:
    lowered = output.lower()
    return any(
        marker in lowered
        for marker in (
            "deleting archive",
            "deleted data",
            "would delete",
            "archive deleted",
        )
    )


def _failure_text(error: BaseException) -> str:
    from app.utils.http_detail import detail_text

    if isinstance(error, HTTPException):
        return detail_text(error.detail)
    return str(error) or type(error).__name__


def _archive_selector(borg_version: int, item: dict[str, Any]) -> str:
    """The archive a manifest entry names, exactly: its id for Borg 2 (a
    series shares one name), its unique name for Borg 1."""
    identity = str(item["identity"])
    return f"aid:{identity}" if borg_version == 2 else identity


def _agent_dry_run_output(manifest: list[dict[str, Any]]) -> str:
    """What the wipe will delete, in the shape of Borg's own dry run: an
    agent repository's wipe deletes exactly the listed archives."""
    count = len(manifest)
    return "\n".join(
        f"Would delete: {item['name'] or item['identity']} ({index}/{count})"
        for index, item in enumerate(manifest, 1)
    )


async def _agent_job_result(
    db: Session,
    repository: Repository,
    job_kind: str,
    *,
    timeout_seconds: int,
    operation: dict[str, Any] | None = None,
    wipe_operation_id: int | None = None,
    agent_machine_id: int | None = None,
    queued: list[AgentJob] | None = None,
) -> dict[str, Any]:
    """Run one job on the repository's agent and wait for its result.

    A job of the running wipe names the wipe as its maintenance job:
    admission then leaves the wipe out of the work its own jobs are checked
    against, and the operations queued behind the wipe's lane too, as for
    a maintenance operation the runner drives (`_require_repository_lane`).
    The completion handlers complete no wipe; the wipe reads each result
    itself.

    A wait that ends without the job's verdict (a timeout, a cancelled
    caller) takes the job back: one the agent has not claimed is cancelled,
    a claimed one is asked to stop. Left queued, a delete would still run
    when the agent comes back, after the wipe was reported failed.

    `agent_machine_id` is the agent the caller read or confirmed the
    archives on. The job goes to the repository's agent as it is when the
    job is queued; another one gets nothing.

    `queued` receives the job once it is queued, for a caller that reads
    the failed job's report."""
    agent_job = queue_agent_repository_operation_job(
        db,
        repository,
        job_kind=job_kind,
        operation=operation,
        maintenance_job_kind="wipe" if wipe_operation_id is not None else None,
        maintenance_job_id=wipe_operation_id,
        ignore_queued_operations=wipe_operation_id is not None,
    )
    if queued is not None:
        queued.append(agent_job)
    try:
        if (
            agent_machine_id is not None
            and agent_job.agent_machine_id != agent_machine_id
        ):
            raise RuntimeError(
                "The repository's agent changed since its archives were "
                "listed; nothing was run on the new one."
            )
        await dispatch_agent_job_best_effort(db, agent_job, repository_id=repository.id)
        return await wait_for_agent_repository_operation_job(
            db, agent_job.id, timeout_seconds=timeout_seconds
        )
    except BaseException as exc:
        # 502: the job failed and is over; anything else left it live
        if not (isinstance(exc, HTTPException) and exc.status_code == 502):
            abandoned = abandon_agent_repository_operation_job(db, agent_job.id)
            if abandoned is not None and abandoned.status == "cancel_requested":
                await dispatch_agent_cancel_if_connected(abandoned)
        raise


def _agent_warning(result: dict[str, Any]) -> bool:
    """A completed agent job whose Borg ended with a warning (exit 1)."""
    return result.get("return_code") not in (None, 0)


def _deleted_before_failure(db: Session, agent_job: AgentJob | None) -> int | None:
    """How many archives a failed `repository.delete_archives` job deleted:
    the count its failure report gave, 0 for a job no agent ever claimed,
    None when unknown (the job was reaped, or taken back while it ran)."""
    if agent_job is None:
        return 0
    db.refresh(agent_job)
    result = agent_job.result if isinstance(agent_job.result, dict) else {}
    deleted = result.get("deleted_archives")
    if isinstance(deleted, int) and not isinstance(deleted, bool):
        return deleted
    if agent_job.claimed_at is None:
        return 0
    return None


def _listing_agent(repository: Repository) -> int | None:
    """The agent that lists and wipes an agent repository; None for the
    server's own."""
    return repository.agent_machine_id if is_agent_executor(repository) else None


def _wipe_target(repository: Repository) -> tuple:
    """Where an agent repository's wipe deletes: its agent and location."""
    return (
        repository.agent_machine_id,
        repository.path,
        repository.remote_path,
        borg_major(repository),
        is_agent_executor(repository),
    )


async def _agent_archives(
    db: Session, repository: Repository, *, with_tags: bool, agent_machine_id: int
) -> list[Any]:
    """The repository's archives, listed on its agent.

    Borg 2's listing on the agent asks for name, id and time only, so it
    has no tags; its `info` has them. The preview reads the tags
    (`with_tags`), since `borg2 delete` skips a protected archive without a
    word, and the wipe has to be refused for one as on the server."""
    from app.api.repositories import get_operation_timeouts

    timeouts = get_operation_timeouts(db)
    use_info = with_tags and borg_major(repository) == 2
    result = await _agent_job_result(
        db,
        repository,
        "repository.info" if use_info else "repository.list_archives",
        timeout_seconds=timeouts["info_timeout" if use_info else "list_timeout"],
        agent_machine_id=agent_machine_id,
    )
    if result.get("return_code", 0) != 0 or result.get("success", True) is False:
        raise RuntimeError(
            result.get("stderr") or "the agent could not list the archives"
        )
    payload = json.loads(result.get("stdout") or "{}")
    archives = payload.get("archives") if isinstance(payload, dict) else None
    return archives if isinstance(archives, list) else []


class RepositoryWipeService:
    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_no_conflicting_operations(
        self, db: Session, repository: Repository
    ) -> None:
        """Refuse to preview or wipe while other work holds the repository.

        A queued row counts, because the runner will start it.
        """
        repo_id = repository.id

        if (
            db.query(Operation.id)
            .filter(
                Operation.repository_id == repo_id,
                Operation.kind.in_(CONFLICTING_KINDS),
                Operation.status.in_(("queued", "running")),
            )
            .first()
        ):
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.operationAlreadyRunning"},
            )

        if active_wipe_operation(db, repo_id) is not None:
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.wipeAlreadyRunning"},
            )

    async def create_preview(
        self,
        db: Session,
        repository: Repository,
        current_user: User,
        *,
        run_compact: bool = True,
    ) -> dict[str, Any]:
        async def operation() -> dict[str, Any]:
            self._ensure_no_conflicting_operations(db, repository)
            agent = is_agent_executor(repository)
            # read before the listing: its commit reloads the repository,
            # which may name another agent or location by then
            listing_agent = _listing_agent(repository)
            listed_target = _wipe_target(repository)
            listed_path = repository.path
            temp_key_file = None
            try:
                if agent:
                    archives = await _agent_archives(
                        db, repository, with_tags=True, agent_machine_id=listing_agent
                    )
                    db.refresh(repository)
                    if _wipe_target(repository) != listed_target:
                        # the listing is of the repository as it was
                        raise HTTPException(
                            status_code=409,
                            detail={"key": "backend.errors.repo.wipePreviewNotFresh"},
                        )
                    timezone_name = agent_timezone_for_repository(db, repository)
                else:
                    env, temp_key_file = build_repository_borg_env(
                        repository, db, keepalive=True
                    )
                    router = BorgRouter(repository)
                    archives = await router.list_archives(env=env)
                    timezone_name = "UTC"
                manifest = normalize_archive_manifest(
                    borg_version=borg_major(repository),
                    archives=archives,
                    timezone_name=timezone_name,
                )
                fingerprint = compute_archive_fingerprint(
                    manifest, agent_machine_id=listing_agent
                )
                protected_archives = [
                    item["name"] or item["identity"]
                    for item in manifest
                    if item.get("protected")
                ]
                blocking_reason = "protected_archives" if protected_archives else None
                dry_run_output = ""
                if manifest and not blocking_reason and agent:
                    dry_run_output = _agent_dry_run_output(manifest)
                elif manifest and not blocking_reason:
                    dry_run_result = await router.run_wipe_delete(dry_run=True, env=env)
                    dry_run_output = _command_output(dry_run_result)
                    if not dry_run_result.get("success"):
                        blocking_reason = "dry_run_failed"

                job = RepositoryWipeJob(
                    repository_id=repository.id,
                    repository_path=listed_path,
                    repository_name=repository.name,
                    borg_version=borg_major(repository),
                    status="previewed",
                    phase="preview",
                    archive_count=len(manifest),
                    archive_fingerprint=fingerprint,
                    archive_manifest_json=json.dumps(manifest, sort_keys=True),
                    dry_run_output=dry_run_output,
                    blocking_reason=blocking_reason,
                    protected_archives_json=json.dumps(protected_archives),
                    run_compact=bool(run_compact),
                    requested_by_user_id=current_user.id,
                    progress=0,
                    progress_message="Wipe preview generated",
                )
                db.add(job)
                db.commit()
                db.refresh(job)
                logger.info(
                    "Repository wipe preview generated",
                    repository_id=repository.id,
                    job_id=job.id,
                    archive_count=len(manifest),
                    blocked=bool(blocking_reason),
                    actor=current_user.username,
                )
                return self.serialize_job(job, include_preview=True)
            finally:
                cleanup_temp_key_file(temp_key_file)

        return await run_serialized_repository_command(
            repository.id, operation, scope="wipe"
        )

    async def start_execution(
        self,
        db: Session,
        repository: Repository,
        current_user: User,
        *,
        preview_id: int,
        preview_fingerprint: str,
        confirmation_phrase: str,
        understood: bool,
        run_compact: bool,
    ) -> Any:
        preview = (
            db.query(RepositoryWipeJob)
            .filter(
                RepositoryWipeJob.id == preview_id,
                RepositoryWipeJob.repository_id == repository.id,
            )
            .first()
        )
        if not preview:
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewNotFound", status_code=404
            )
        if _preview_already_consumed(db, preview.id):
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewNotFresh", status_code=409
            )
        if preview.blocking_reason:
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewBlocked", status_code=409
            )
        if not understood:
            raise WipeValidationError("backend.errors.repo.wipeUnderstandingRequired")
        expected_phrase = f"WIPE {repository.name}"
        if confirmation_phrase != expected_phrase:
            raise WipeValidationError("backend.errors.repo.wipeConfirmationMismatch")
        if preview.archive_fingerprint != preview_fingerprint:
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewNotFresh", status_code=409
            )

        async def operation() -> Any:
            self._ensure_no_conflicting_operations(db, repository)
            listing_agent = _listing_agent(repository)
            temp_key_file = None
            try:
                if listing_agent is not None:
                    # the fingerprint covers the identities only: the
                    # listing has them, no tags needed
                    current_archives = await _agent_archives(
                        db,
                        repository,
                        with_tags=False,
                        agent_machine_id=listing_agent,
                    )
                else:
                    env, temp_key_file = build_repository_borg_env(
                        repository, db, keepalive=True
                    )
                    current_archives = await BorgRouter(repository).list_archives(
                        env=env
                    )
                current_manifest = normalize_archive_manifest(
                    borg_version=borg_major(repository),
                    archives=current_archives,
                )
                current_fingerprint = compute_archive_fingerprint(
                    current_manifest, agent_machine_id=listing_agent
                )
            finally:
                cleanup_temp_key_file(temp_key_file)

            if current_fingerprint != preview_fingerprint:
                preview.phase = "stale"
                db.commit()
                raise WipeArchiveSetChanged()

            # The preview stays where it is: it is not a unit of work and has
            # no spec 6.3 status. The confirmed run is the operation, and it
            # carries the preview snapshot in its details row (spec 6.2).
            op = enqueue(
                db,
                "wipe",
                repository_id=repository.id,
                trigger="manual",
                params={
                    "preview_id": preview.id,
                    "run_compact": bool(run_compact),
                    # the agent the archives were confirmed on
                    "agent_machine_id": listing_agent,
                },
                triggered_by_user_id=current_user.id,
                commit=False,
            )
            details = wipe_details(db, op)
            details.phase = "queued"
            details.archive_count = preview.archive_count
            details.archive_fingerprint = preview.archive_fingerprint
            details.archive_manifest_json = preview.archive_manifest_json
            details.dry_run_output = preview.dry_run_output
            details.blocking_reason = preview.blocking_reason
            details.protected_archives_json = preview.protected_archives_json
            details.run_compact = bool(run_compact)
            details.requested_by_user_id = preview.requested_by_user_id
            details.confirmed_by_user_id = current_user.id
            details.confirmed_at = utc_now()
            op.progress_percent = 0
            op.progress_message = "Repository wipe queued"
            db.commit()
            db.refresh(op)
            wake_runner()
            logger.warning(
                "Repository wipe execution queued",
                repository_id=repository.id,
                operation_id=op.id,
                archive_count=preview.archive_count,
                run_compact=bool(run_compact),
                actor=current_user.username,
            )
            return WipeJobFacade(db, op)

        return await run_serialized_repository_command(
            repository.id, operation, scope="wipe"
        )

    async def execute_wipe(self, job_id: int, repository_id: int) -> None:
        db = SessionLocal()
        close_db = getattr(SessionLocal, "return_value", None) is not db
        temp_key_file = None
        log_lines: list[str] = []
        job: Any = None
        try:
            job = resolve_wipe_job(db, job_id)
            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not job or not repository:
                return

            async def operation() -> None:
                nonlocal temp_key_file, log_lines
                if is_agent_executor(repository):
                    await self._execute_agent_wipe(db, job, repository, log_lines)
                    return
                if (job.operation.params or {}).get("agent_machine_id") is not None:
                    raise RuntimeError(
                        "The repository was moved off its agent after the wipe "
                        "was confirmed; no archives were deleted."
                    )
                env, temp_key_file = build_repository_borg_env(
                    repository, db, keepalive=True, show_progress=True
                )
                router = BorgRouter(repository)

                job.status = "running"
                job.phase = "delete"
                job.started_at = datetime.utcnow()
                job.progress = 10
                job.progress_message = "Deleting repository archives"
                db.commit()

                delete_result = await router.run_wipe_delete(dry_run=False, env=env)
                delete_output = _command_output(delete_result)
                if delete_output:
                    log_lines.append(delete_output)

                if not delete_result.get("success"):
                    partial = _partial_delete_signal(delete_output)
                    job.status = "failed_partial" if partial else "failed"
                    # The facade writes `delete_failed_partial` itself from the
                    # status above; this is the non-partial half, kept beside it
                    # so both phases read together.
                    job.phase = "delete_failed_partial" if partial else "delete_failed"
                    job.error_message = delete_output or "Repository wipe delete failed"
                    job.progress_message = "Repository wipe delete failed"
                    job.progress = 100
                    await self._best_effort_post_wipe_refresh(db, repository)
                    return

                if job.run_compact:
                    job.phase = "compact"
                    job.progress = 75
                    job.progress_message = "Compacting repository after wipe"
                    db.commit()
                    compact_result = await router.run_wipe_compact(env=env)
                    compact_output = _command_output(compact_result)
                    if compact_output:
                        log_lines.append(compact_output)
                    if not compact_result.get("success"):
                        job.status = "completed_compaction_failed"
                        job.phase = "compact_failed"
                        job.error_message = (
                            compact_output
                            or "Archives were deleted, but compact failed."
                        )
                    else:
                        job.status = "completed"
                        job.phase = "completed"
                else:
                    job.status = "completed_with_warnings"
                    job.phase = "compact_skipped"
                    job.error_message = (
                        "Archives were deleted, but compact was skipped. "
                        "Repository disk usage may not shrink yet."
                    )

                job.progress = 100
                job.progress_message = "Repository contents wipe completed"
                await self._best_effort_post_wipe_refresh(db, repository)

            await run_serialized_repository_command(
                repository_id, operation, scope="wipe"
            )
        except Exception as exc:
            logger.error(
                "Repository wipe execution failed", job_id=job_id, error=str(exc)
            )
            if job is not None:
                job.status = "failed"
                job.phase = "error"
                job.error_message = str(exc)
                job.progress_message = "Repository wipe failed"
        finally:
            if job is not None:
                if log_lines:
                    log_file_path = self.log_dir / f"repository_wipe_{job.id}.log"
                    log_file_path.write_text("\n".join(log_lines))
                    job.log_file_path = str(log_file_path)
                    job.has_logs = True
                    job.logs = "\n".join(log_lines[-50:])
                if job.status in TERMINAL_EXECUTION_STATUSES:
                    job.completed_at = datetime.utcnow()
                db.commit()
            cleanup_temp_key_file(temp_key_file)
            if close_db:
                db.close()

    async def _execute_agent_wipe(
        self, db: Session, job: Any, repository: Repository, log_lines: list[str]
    ) -> None:
        """Wipe an agent repository on its agent: delete the archives of the
        confirmed preview, then compact (`repository.compact`). An agent
        that has `repository.delete_archives` deletes them in that one job;
        an older one gets a `repository.delete_archive` job per archive.
        Only the archives the preview listed and the start confirmed are
        named; an archive added since stays. The job's states and phases
        are the server-side wipe's."""
        from app.api.repositories import get_operation_timeouts

        borg_version = borg_major(repository)
        manifest = _decode_json_list(job.archive_manifest_json)
        timeout_seconds = get_operation_timeouts(db)["backup_timeout"]
        # Each job names the repository as it is when it is queued. The
        # archives were confirmed at one location on one agent: should the
        # repository move meanwhile, the wipe stops rather than delete
        # same-named archives elsewhere.
        target = _wipe_target(repository)
        params = job.operation.params or {}
        preview_id = params.get("preview_id")
        preview = db.get(RepositoryWipeJob, preview_id) if preview_id else None
        moved_since_confirmation = (
            preview is not None and preview.repository_path != repository.path
        ) or params.get("agent_machine_id") != repository.agent_machine_id

        def ensure_target_unchanged() -> None:
            db.refresh(repository)
            if moved_since_confirmation or _wipe_target(repository) != target:
                raise RuntimeError(
                    "The repository's location or agent changed since the "
                    "wipe was confirmed; no further archives were deleted."
                )

        job.status = "running"
        job.phase = "delete"
        job.started_at = datetime.utcnow()
        job.progress = 10
        job.progress_message = "Deleting repository archives"
        db.commit()

        delete = (
            self._delete_agent_archives_in_one_job
            if manifest
            and agent_supports_job(db, repository, AGENT_DELETE_ARCHIVES_JOB_KIND)
            else self._delete_agent_archives_one_by_one
        )
        try:
            warnings = await delete(
                db,
                job,
                repository,
                manifest,
                borg_version=borg_version,
                timeout_seconds=timeout_seconds,
                agent_machine_id=params.get("agent_machine_id"),
                ensure_target_unchanged=ensure_target_unchanged,
                log_lines=log_lines,
            )
        except _AgentDeleteFailed as failure:
            job.status = "failed_partial" if failure.partial else "failed"
            job.phase = "delete_failed_partial" if failure.partial else "delete_failed"
            job.error_message = failure.reason
            job.progress_message = "Repository wipe delete failed"
            job.progress = 100
            await self._best_effort_post_wipe_refresh(db, repository)
            return

        if job.run_compact:
            job.phase = "compact"
            job.progress = 75
            job.progress_message = "Compacting repository after wipe"
            db.commit()
            try:
                ensure_target_unchanged()
                result = await _agent_job_result(
                    db,
                    repository,
                    "repository.compact",
                    timeout_seconds=timeout_seconds,
                    wipe_operation_id=job.id,
                    agent_machine_id=params.get("agent_machine_id"),
                )
            except Exception as exc:
                reason = _failure_text(exc)
                log_lines.append(f"Compact failed: {reason}")
                job.status = "completed_compaction_failed"
                job.phase = "compact_failed"
                job.error_message = reason
            else:
                if _agent_warning(result):
                    warnings.append(
                        "Compact ended with a warning "
                        f"(exit {result.get('return_code')}): "
                        f"{result.get('stderr') or 'see the agent job log'}"
                    )
                    log_lines.append(warnings[-1])
                job.phase = "completed"
                if warnings:
                    job.status = "completed_with_warnings"
                    job.error_message = "\n".join(warnings)
                else:
                    job.status = "completed"
        else:
            job.status = "completed_with_warnings"
            job.phase = "compact_skipped"
            job.error_message = "\n".join(
                [
                    *warnings,
                    "Archives were deleted, but compact was skipped. "
                    "Repository disk usage may not shrink yet.",
                ]
            )

        job.progress = 100
        job.progress_message = "Repository contents wipe completed"
        await self._best_effort_post_wipe_refresh(db, repository)

    async def _delete_agent_archives_one_by_one(
        self,
        db: Session,
        job: Any,
        repository: Repository,
        manifest: list[dict[str, Any]],
        *,
        borg_version: int,
        timeout_seconds: int,
        agent_machine_id: int | None,
        ensure_target_unchanged: Any,
        log_lines: list[str],
    ) -> list[str]:
        """A `repository.delete_archive` job per archive, for an agent from
        before `repository.delete_archives`. Returns the warnings."""
        count = len(manifest)
        warnings: list[str] = []
        for index, item in enumerate(manifest, 1):
            name = item.get("name") or item["identity"]
            try:
                ensure_target_unchanged()
                result = await _agent_job_result(
                    db,
                    repository,
                    "repository.delete_archive",
                    operation={"archive": _archive_selector(borg_version, item)},
                    timeout_seconds=timeout_seconds,
                    wipe_operation_id=job.id,
                    agent_machine_id=agent_machine_id,
                )
            except Exception as exc:
                reason = _failure_text(exc)
                log_lines.append(f"Deleting archive {name} failed: {reason}")
                raise _AgentDeleteFailed(reason, partial=index > 1) from exc
            if _agent_warning(result):
                warnings.append(
                    f"Deleting archive {name} ended with a warning "
                    f"(exit {result.get('return_code')}): "
                    f"{result.get('stderr') or 'see the agent job log'}"
                )
                log_lines.append(warnings[-1])
            else:
                log_lines.append(f"Deleted archive: {name} ({index}/{count})")
            job.progress = 10 + (65 * index) // max(count, 1)
            db.commit()
        return warnings

    async def _delete_agent_archives_in_one_job(
        self,
        db: Session,
        job: Any,
        repository: Repository,
        manifest: list[dict[str, Any]],
        *,
        borg_version: int,
        timeout_seconds: int,
        agent_machine_id: int | None,
        ensure_target_unchanged: Any,
        log_lines: list[str],
    ) -> list[str]:
        """One `repository.delete_archives` job naming every confirmed
        archive; the agent deletes them in that order and stops at the
        first failure, whose report says how many it deleted before.
        Returns the warnings.

        A Borg 2 archive protected after the confirmation is not skipped
        silently: tagging gives it a new id, and the `aid:` the job names
        then matches nothing, which fails the job."""
        count = len(manifest)
        names = {
            _archive_selector(borg_version, item): item.get("name") or item["identity"]
            for item in manifest
        }
        job.progress_message = f"Deleting {count} archives on the agent"
        db.commit()
        queued: list[AgentJob] = []
        try:
            ensure_target_unchanged()
            result = await _agent_job_result(
                db,
                repository,
                AGENT_DELETE_ARCHIVES_JOB_KIND,
                operation={"archives": list(names)},
                # the budget a job per archive had, in all
                timeout_seconds=timeout_seconds * count,
                wipe_operation_id=job.id,
                agent_machine_id=agent_machine_id,
                queued=queued,
            )
        except Exception as exc:
            reason = _failure_text(exc)
            log_lines.append(f"Deleting the archives failed: {reason}")
            deleted = _deleted_before_failure(db, queued[0] if queued else None)
            # an unknown count may include deleted archives
            raise _AgentDeleteFailed(reason, partial=deleted != 0) from exc
        warned: dict[str, str] = {}
        for warning in result.get("warnings") or []:
            if not isinstance(warning, dict):
                continue
            archive = str(warning.get("archive"))
            warned[archive] = (
                f"Deleting archive {names.get(archive, archive)} ended with a "
                f"warning (exit {warning.get('return_code')}): "
                f"{warning.get('stderr') or 'see the agent job log'}"
            )
        for index, (selector, name) in enumerate(names.items(), 1):
            log_lines.append(
                warned.get(selector) or f"Deleted archive: {name} ({index}/{count})"
            )
        job.progress = 75
        db.commit()
        return list(warned.values())

    async def _best_effort_post_wipe_refresh(
        self, db: Session, repository: Repository
    ) -> None:
        # No stats refresh here: spec 7.4 gives wipe the follow-up chain
        # archive_sync, stats, which the runner enqueues when
        # the operation reaches a success state.
        try:
            from app.services.cache_service import archive_cache

            await archive_cache.clear_repository(repository.id)
        except Exception as exc:
            logger.warning(
                "Failed to clear archive cache after wipe",
                repository_id=repository.id,
                error=str(exc),
            )
        try:
            from app.services.mqtt_service import mqtt_service

            mqtt_service.sync_state_with_db(db, reason="repository wipe")
        except Exception as exc:
            logger.warning(
                "Failed to sync MQTT after repository wipe",
                repository_id=repository.id,
                error=str(exc),
            )

    def resolve_job_or_preview(
        self, db: Session, repository: Repository, job_id: int
    ) -> Any:
        """The wipe execution operation with this id, or the preview row that
        has it.

        Previews are the only rows left in `repository_wipe_jobs`, and they
        keep their own id sequence, so a caller holding a preview id (the
        status and cancel routes take whichever id the client was given)
        cannot be answered by the operations facade alone. The operation wins
        the ambiguity, but only for this repository: an operation of another
        repository with the same id would otherwise win and be rejected by
        the caller's repository check, leaving a valid preview unreachable."""
        job = resolve_wipe_job(db, job_id)
        if job is not None and job.repository_id == repository.id:
            return job
        return (
            db.query(RepositoryWipeJob)
            .filter(
                RepositoryWipeJob.id == job_id,
                RepositoryWipeJob.repository_id == repository.id,
            )
            .first()
        )

    def cancel_preview(
        self,
        db: Session,
        repository: Repository,
        current_user: User,
        *,
        job_id: int,
    ) -> dict[str, Any]:
        job = self.resolve_job_or_preview(db, repository, job_id)
        if not job or job.repository_id != repository.id:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.wipeJobNotFound"},
            )
        if job.status not in ("previewed", "pending"):
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.wipeCannotCancelRunning"},
            )
        # The facade maps "pending" back to "queued", so a queued operation is
        # cancelled in place. The runner never dispatches a row that is no
        # longer queued (spec 7.1). No db.refresh(): a facade is not a mapped
        # instance, its mapped object is `.operation`.
        job.status = "cancelled"
        job.phase = "cancelled"
        job.completed_at = utc_now()
        job.progress_message = "Wipe preview cancelled"
        db.commit()
        logger.info(
            "Repository wipe cancelled",
            repository_id=repository.id,
            job_id=job_id,
            actor=current_user.username,
        )
        return self.serialize_job(job, include_preview=True)

    def serialize_job(
        self,
        job: RepositoryWipeJob,
        *,
        include_preview: bool = False,
        include_logs: bool = False,
        log_save_policy: str = DEFAULT_LOG_SAVE_POLICY,
    ) -> dict[str, Any]:
        has_logs = job_has_logs_by_policy(
            job,
            log_save_policy,
            output_text=[job.logs, job.error_message],
            file_path=job.log_file_path,
        )
        payload = {
            "id": job.id,
            "repository_id": job.repository_id,
            "status": job.status,
            "phase": job.phase,
            "started_at": serialize_datetime(job.started_at),
            "confirmed_at": serialize_datetime(job.confirmed_at),
            "completed_at": serialize_datetime(job.completed_at),
            "error_message": job.error_message,
            "progress": job.progress,
            "progress_message": job.progress_message,
            "archive_count": job.archive_count,
            "archive_fingerprint": job.archive_fingerprint,
            "run_compact": bool(job.run_compact),
            "has_logs": has_logs,
        }
        if include_preview:
            manifest = _decode_json_list(job.archive_manifest_json)
            protected_archives = _decode_json_list(job.protected_archives_json)
            payload.update(
                {
                    "archives": manifest,
                    "dry_run_output": job.dry_run_output or "",
                    "blocked": bool(job.blocking_reason),
                    "blocking_reason": job.blocking_reason,
                    "protected_archives": protected_archives,
                }
            )
        if include_logs:
            payload["logs"] = self._read_logs(job) if has_logs else ""
        return payload

    def _read_logs(self, job: RepositoryWipeJob) -> str:
        if job.log_file_path:
            path = Path(job.log_file_path)
            if path.exists():
                try:
                    return path.read_text()
                except Exception as exc:
                    return f"Failed to read log file: {exc}"
        return job.logs or job.error_message or ""


repository_wipe_service = RepositoryWipeService()
