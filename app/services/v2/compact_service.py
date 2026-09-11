"""Borg 2 compact service.

Mirrors compact_service.py but uses the borg2 binary.

Borg 2 compact has two phases (verified against live borg2 2.0.0b22):
  operation=1  compact.analyze_archives  "Computing used chunks X%"   → 0-50%
  operation=2  compact.compact_packs     "Compacting packs X%"        → 50-100%

The second phase was compact.report_and_delete until 2.0.0b22 renamed it; the
progress split keys on `operation`, not on the msgid, so it did not move.

Both phases emit progress_percent on stderr with --progress --log-json.
"""

import asyncio
import json
from collections import deque
from datetime import datetime
from pathlib import Path
import structlog

from app.database.models import Repository
from app.database.database import SessionLocal
from app.core.borg2 import _get_borg2_binary, compact_stats_supported
from app.config import settings
from app.services.borg2_compact_stats import is_stats_line, parse_compact_stats
from app.services.maintenance_state import apply_compact_completion
from app.services.operations.job_facade import (
    claim_running,
    refresh_job,
    resolve_maintenance_job,
)
from app.utils.db_retries import commit_with_retry
from app.utils.borg_env import (
    build_repository_borg_env,
    cleanup_temp_key_file,
    effective_repository_remote_path,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,  # noqa: F401
)  # Backward-compatible patch target for tests

logger = structlog.get_logger()


def _get_process_start_time(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            stat_data = f.read()
        fields = stat_data.split(")")[1].split()
        return int(fields[19])
    except Exception as e:
        logger.error("Failed to read process start time", pid=pid, error=str(e))
        return 0


class _LogWindow:
    """The lines a compact's saved log keeps: the first `head` lines and
    the last `tail` lines, with a marker for what fell out between them.
    `--info` prints a line per analysed archive and `--progress` a frame
    per step, so a large repository outgrows any flat cap; the start and
    the end (the statistics, the verdict) are what a reader needs."""

    HEAD = 1000
    TAIL = 4000

    def __init__(self) -> None:
        self.head: list[str] = []
        self.tail: deque[str] = deque(maxlen=self.TAIL)
        self.dropped = 0

    def append(self, line: str) -> None:
        if len(self.head) < self.HEAD:
            self.head.append(line)
            return
        if len(self.tail) == self.tail.maxlen:
            self.dropped += 1
        self.tail.append(line)

    def __len__(self) -> int:
        return len(self.head) + len(self.tail)

    def lines(self) -> list[str]:
        marker = [f"... {self.dropped} lines omitted ..."] if self.dropped else []
        return [*self.head, *marker, *self.tail]

    def last(self, count: int) -> list[str]:
        """The newest `count` lines, wherever they sit."""
        if count <= 0:
            return []
        return [*self.head, *self.tail][-count:]


class CompactV2Service:
    """Run borg2 compact with real-time two-phase progress tracking."""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes: dict = {}

    async def cancel_compact(self, job_id: int) -> bool:
        """Cancel a running borg2 compact job by terminating its tracked process."""
        if job_id not in self.running_processes:
            logger.warning(
                "No running borg2 compact process found for job", job_id=job_id
            )
            return False

        process = self.running_processes[job_id]
        try:
            process.terminate()
            logger.info(
                "Sent SIGTERM to borg2 compact process",
                job_id=job_id,
                pid=process.pid,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            return True
        except Exception as e:
            logger.error(
                "Failed to cancel borg2 compact process",
                job_id=job_id,
                error=str(e),
            )
            return False

    async def execute_compact(self, job_id: int, repository_id: int, _db=None):
        """Execute borg2 compact with progress streaming into the operation."""
        db = SessionLocal()
        temp_key_file = None

        try:
            job = resolve_maintenance_job(db, job_id, "compact")
            if not job:
                logger.error("Borg2 compact job not found", job_id=job_id)
                return

            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not repository:
                completed_at = datetime.utcnow()

                def persist_missing_repo_state():
                    job.status = "failed"
                    job.error_message = f"Repository not found (ID: {repository_id})"
                    job.completed_at = completed_at

                await commit_with_retry(
                    db,
                    prepare=persist_missing_repo_state,
                    logger=logger,
                    action="borg2_compact_missing_repo",
                    job_id=job_id,
                    repository_id=repository_id,
                )
                return

            # Refresh to ensure we have the latest state. If the job was
            # somehow already completed/cancelled (race), bail out.
            refresh_job(db, job)
            if job.status not in ("running", "pending"):
                logger.warning(
                    "Compact job already in terminal state, skipping",
                    job_id=job_id,
                    status=job.status,
                )
                return

            # The manual endpoint pre-sets the job to running, but scheduler
            # jobs arrive as pending. Record the actual execution start either
            # way so started_at is never left NULL (job history and the
            # dashboard activity feed both filter on it). The status predicate
            # keeps a concurrent cancellation from being overwritten.
            started_at = datetime.utcnow()
            claimed = 0

            def persist_start_state():
                nonlocal claimed
                claimed = claim_running(db, job_id, "compact", started_at)

            await commit_with_retry(
                db,
                prepare=persist_start_state,
                logger=logger,
                action="borg2_compact_start",
                job_id=job_id,
                repository_id=repository_id,
            )
            if not claimed:
                logger.warning(
                    "Compact job reached a terminal state before start, skipping",
                    job_id=job_id,
                )
                return
            refresh_job(db, job)

            env, temp_key_file = build_repository_borg_env(
                repository,
                db,
                keepalive=True,
                show_progress=True,
            )

            borg_cmd = _get_borg2_binary()
            # --stats --info: Borg 2 reports the repository statistics only
            # here, on INFO level (see borg2_compact_stats), from 2.0.0b15 on.
            # a subprocess probe, off the event loop
            with_stats = await asyncio.to_thread(compact_stats_supported, borg_cmd)
            if with_stats:
                # Exact byte counts in the statistics lines instead of the
                # rounded, BORG_UNITS-dependent human form.
                env["BORG_UNITS"] = "raw"
            cmd = [borg_cmd, "-r", repository.path, "compact"]
            if with_stats:
                cmd.extend(["--stats", "--info"])
            cmd.extend(["--progress", "--log-json"])
            if remote_path := effective_repository_remote_path(repository):
                cmd.extend(["--remote-path", remote_path])

            logger.info(
                "Starting borg2 compact",
                job_id=job_id,
                repository=repository.path,
                command=" ".join(cmd),
            )

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            process_start_time = _get_process_start_time(process.pid)

            def persist_pid_tracking():
                job.process_pid = process.pid
                job.process_start_time = process_start_time

            await commit_with_retry(
                db,
                prepare=persist_pid_tracking,
                logger=logger,
                action="borg2_compact_store_pid",
                job_id=job_id,
                repository_id=repository_id,
            )

            self.running_processes[job_id] = process
            cancelled = False
            last_commit_time = asyncio.get_event_loop().time()
            COMMIT_INTERVAL = 1.0
            first_progress_committed = False
            last_progress_update: dict = {}
            PROGRESS_THROTTLE = 2.0
            log_buffer = _LogWindow()

            async def check_cancellation():
                nonlocal cancelled
                while not cancelled and process.returncode is None:
                    await asyncio.sleep(3)
                    refresh_job(db, job)
                    if job.status == "cancelled":
                        logger.info(
                            "Borg2 compact cancelled, terminating", job_id=job_id
                        )
                        cancelled = True
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()
                        break

            async def stream_logs():
                nonlocal cancelled, last_commit_time, first_progress_committed
                try:
                    async for line in process.stderr:
                        if cancelled:
                            break
                        line_str = line.decode("utf-8", errors="replace").strip()
                        log_buffer.append(line_str)

                        framed = None
                        if line_str and line_str[0] == "{":
                            try:
                                framed = json.loads(line_str)
                            except (ValueError, RecursionError):
                                # not a frame: an integer literal past the
                                # interpreter's digit limit is a ValueError
                                # that is not a JSONDecodeError
                                framed = None
                        if line_str:
                            # --info makes this stream long (a line per
                            # analysed archive); framed INFO and progress
                            # entries go to debug, everything else (borg's
                            # warnings, errors, criticals, unframed text)
                            # stays visible, as do the statistics lines
                            # themselves, so a compact that printed none
                            # can be told from one whose lines did not
                            # parse.
                            quiet = isinstance(framed, dict) and (
                                framed.get("type") != "log_message"
                                or (
                                    framed.get("levelname") in ("DEBUG", "INFO")
                                    and not is_stats_line(
                                        str(framed.get("message", ""))
                                    )
                                )
                            )
                            emit = logger.debug if quiet else logger.info
                            emit(
                                "Borg2 compact output",
                                job_id=job_id,
                                line=line_str[:200],
                            )

                        try:
                            if isinstance(framed, dict):
                                msg = framed
                                msg_type = msg.get("type")

                                if msg_type == "progress_percent":
                                    message = msg.get("message", "")
                                    finished = msg.get("finished", False)
                                    operation = msg.get("operation", 1)
                                    current = msg.get("current", 0)
                                    total = msg.get("total", 1)
                                    now = asyncio.get_event_loop().time()

                                    if message:
                                        progress_msg = f"{message} ({current}/{total})"
                                        if (
                                            now
                                            - last_progress_update.get(progress_msg, 0)
                                            >= PROGRESS_THROTTLE
                                        ):
                                            job.progress_message = progress_msg
                                            last_progress_update[progress_msg] = now

                                    if not finished and total > 0:
                                        pct = (current / total) * 100
                                        # Two phases:
                                        # operation=1 (compact.analyze_archives) → 0-50%
                                        # operation=2 (compact.compact_packs) → 50-100%
                                        if operation == 1:
                                            job.progress = int(pct / 2)
                                        else:
                                            job.progress = int(50 + pct / 2)

                                        should_commit = (
                                            not first_progress_committed
                                            or now - last_commit_time >= COMMIT_INTERVAL
                                        )
                                        if should_commit:
                                            progress = job.progress
                                            progress_message = job.progress_message

                                            def persist_progress():
                                                job.progress = progress
                                                job.progress_message = progress_message

                                            await commit_with_retry(
                                                db,
                                                prepare=persist_progress,
                                                logger=logger,
                                                action="borg2_compact_progress",
                                                job_id=job_id,
                                                repository_id=repository_id,
                                            )
                                            last_commit_time = now
                                            first_progress_committed = True
                        except (json.JSONDecodeError, KeyError, ValueError):
                            pass
                except asyncio.CancelledError:
                    raise
                finally:
                    final_progress = job.progress
                    final_progress_message = job.progress_message

                    def persist_stream_state():
                        job.progress = final_progress
                        job.progress_message = final_progress_message

                    await commit_with_retry(
                        db,
                        prepare=persist_stream_state,
                        logger=logger,
                        action="borg2_compact_stream_finalize",
                        job_id=job_id,
                        repository_id=repository_id,
                    )

            try:
                await asyncio.gather(
                    check_cancellation(), stream_logs(), return_exceptions=True
                )
            except asyncio.CancelledError:
                cancelled = True
                process.terminate()
                await process.wait()
                raise

            if process.returncode is None:
                await process.wait()

            size_written = False
            if job.status == "cancelled":
                job.completed_at = datetime.utcnow()
            else:
                # the whole window: the parser is line-anchored and cheap,
                # and the statistics must not depend on how many lines
                # Borg prints after them
                stats = parse_compact_stats(log_buffer.lines()) if with_stats else None
                size_written = apply_compact_completion(
                    job,
                    repository,
                    process.returncode,
                    stats=stats,
                )
                if (
                    with_stats
                    and stats is None
                    and job.status
                    in (
                        "completed",
                        "completed_with_warnings",
                    )
                ):
                    # The size this compact was asked for is missing: a
                    # Borg release that no longer prints these lines shows
                    # up here, not as a silently unchanged total_size.
                    logger.warning(
                        "Borg2 compact reported no statistics",
                        job_id=job_id,
                        repository_id=repository_id,
                    )
                if job.status == "completed":
                    logger.info("Borg2 compact completed", job_id=job_id)
                elif job.status == "completed_with_warnings":
                    logger.warning(
                        "Borg2 compact warnings",
                        job_id=job_id,
                        exit_code=process.returncode,
                    )
                else:
                    logger.error(
                        "Borg2 compact failed",
                        job_id=job_id,
                        exit_code=process.returncode,
                    )

            if log_buffer:
                log_file = (
                    self.log_dir
                    / f"compact_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
                try:
                    log_file.write_text("\n".join(log_buffer.lines()))
                    job.log_file_path = str(log_file)
                    job.has_logs = True
                    job.logs = f"Logs saved to: {log_file.name}"
                except Exception as e:
                    job.has_logs = False
                    job.logs = f"Failed to save logs: {e}"
                    logger.error(
                        "Failed to save borg2 compact logs", job_id=job_id, error=str(e)
                    )

            final_status = job.status
            final_progress = job.progress
            final_progress_message = job.progress_message
            final_completed_at = job.completed_at
            final_error_message = job.error_message
            final_log_file_path = job.log_file_path
            final_has_logs = job.has_logs
            final_logs = job.logs
            # A pre-phase-5 legacy row has no statistics attribute at all.
            final_stats = getattr(job, "stats", None)
            repository_last_compact = repository.last_compact
            # the four size columns move together (`set_repository_size`)
            repository_size_columns = (
                repository.total_size,
                repository.total_size_bytes,
                repository.total_size_source,
                repository.total_size_measured_at,
            )

            def persist_final_state():
                job.status = final_status
                job.progress = final_progress
                job.progress_message = final_progress_message
                job.completed_at = final_completed_at
                job.error_message = final_error_message
                job.log_file_path = final_log_file_path
                job.has_logs = final_has_logs
                job.logs = final_logs
                repository.last_compact = repository_last_compact
                if final_stats is not None:
                    job.stats = final_stats
                if size_written:
                    # Only a size this compact wrote is restored after a
                    # rolled-back attempt; one it left alone may have been
                    # measured by a follow-up in the meantime.
                    (
                        repository.total_size,
                        repository.total_size_bytes,
                        repository.total_size_source,
                        repository.total_size_measured_at,
                    ) = repository_size_columns

            await commit_with_retry(
                db,
                prepare=persist_final_state,
                logger=logger,
                action="borg2_compact_finalize",
                job_id=job_id,
                repository_id=repository_id,
            )

        except Exception as e:
            logger.error("Borg2 compact execution failed", job_id=job_id, error=str(e))
            try:
                completed_at = datetime.utcnow()

                error_message = str(e)

                def persist_failure_state():
                    job.status = "failed"
                    job.error_message = error_message
                    job.completed_at = completed_at

                await commit_with_retry(
                    db,
                    prepare=persist_failure_state,
                    logger=logger,
                    action="borg2_compact_fail",
                    job_id=job_id,
                    repository_id=repository_id,
                )
            except Exception:
                db.rollback()
        finally:
            self.running_processes.pop(job_id, None)
            cleanup_temp_key_file(temp_key_file)
            db.close()


compact_v2_service = CompactV2Service()
