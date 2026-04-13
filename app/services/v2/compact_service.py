"""Borg 2 compact service.

Mirrors compact_service.py but uses the borg2 binary.

Borg 2 compact has two phases (verified against live borg2 2.0.0b21):
  operation=1  compact.analyze_archives  "Computing used chunks X%"   → 0-50%
  operation=2  compact.report_and_delete "Deleting unused objects X%"  → 50-100%

Both phases emit progress_percent on stderr with --progress --log-json.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
import structlog

from app.database.models import CompactJob, Repository
from app.database.database import SessionLocal
from app.core.borg2 import _get_borg2_binary
from app.config import settings
from app.utils.borg_env import build_repository_borg_env, cleanup_temp_key_file

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


class CompactV2Service:
    """Run borg2 compact with real-time two-phase progress tracking."""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes: dict = {}

    async def execute_compact(self, job_id: int, repository_id: int, _db=None):
        """Execute borg2 compact with progress streaming into a CompactJob record."""
        db = SessionLocal()
        temp_key_file = None

        try:
            job = db.query(CompactJob).filter(CompactJob.id == job_id).first()
            if not job:
                logger.error("Borg2 compact job not found", job_id=job_id)
                return

            repo = db.query(Repository).filter(Repository.id == repository_id).first()
            if not repo:
                job.status = "failed"
                job.error_message = f"Repository not found (ID: {repository_id})"
                job.completed_at = datetime.utcnow()
                db.commit()
                return

            # Job is pre-set to running by the endpoint; refresh to ensure we have latest state.
            # If the job was somehow already completed/cancelled (race), bail out.
            db.refresh(job)
            if job.status not in ("running", "pending"):
                logger.warning(
                    "Compact job already in terminal state, skipping",
                    job_id=job_id,
                    status=job.status,
                )
                return

            env, temp_key_file = build_repository_borg_env(
                repo,
                db,
                keepalive=True,
                show_progress=True,
            )

            borg_cmd = _get_borg2_binary()
            cmd = [borg_cmd, "-r", repo.path, "compact", "--progress", "--log-json"]
            if repo.remote_path:
                cmd.extend(["--remote-path", repo.remote_path])

            logger.info(
                "Starting borg2 compact",
                job_id=job_id,
                repository=repo.path,
                command=" ".join(cmd),
            )

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            job.process_pid = process.pid
            job.process_start_time = _get_process_start_time(process.pid)
            db.commit()

            self.running_processes[job_id] = process
            cancelled = False
            last_commit_time = asyncio.get_event_loop().time()
            COMMIT_INTERVAL = 1.0
            first_progress_committed = False
            last_progress_update: dict = {}
            PROGRESS_THROTTLE = 2.0
            log_buffer: list = []
            MAX_BUFFER = 1000

            async def check_cancellation():
                nonlocal cancelled
                while not cancelled and process.returncode is None:
                    await asyncio.sleep(3)
                    db.refresh(job)
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
                        if len(log_buffer) > MAX_BUFFER:
                            log_buffer.pop(0)

                        if line_str:
                            logger.info(
                                "Borg2 compact output",
                                job_id=job_id,
                                line=line_str[:200],
                            )

                        try:
                            if line_str and line_str[0] == "{":
                                msg = json.loads(line_str)
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
                                        # operation=2 (compact.report_and_delete) → 50-100%
                                        if operation == 1:
                                            job.progress = int(pct / 2)
                                        else:
                                            job.progress = int(50 + pct / 2)

                                        should_commit = (
                                            not first_progress_committed
                                            or now - last_commit_time >= COMMIT_INTERVAL
                                        )
                                        if should_commit:
                                            db.commit()
                                            last_commit_time = now
                                            first_progress_committed = True
                        except (json.JSONDecodeError, KeyError, ValueError):
                            pass
                except asyncio.CancelledError:
                    raise
                finally:
                    db.commit()

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

            if job.status == "cancelled":
                job.completed_at = datetime.utcnow()
            elif process.returncode == 0:
                job.status = "completed"
                job.progress = 100
                job.progress_message = "Compact completed successfully"
                job.completed_at = datetime.utcnow()
                logger.info("Borg2 compact completed", job_id=job_id)
            elif process.returncode == 1 or (100 <= process.returncode <= 127):
                job.status = "completed_with_warnings"
                job.progress = 100
                job.progress_message = (
                    f"Compact completed with warnings (exit code {process.returncode})"
                )
                job.error_message = job.progress_message
                job.completed_at = datetime.utcnow()
                logger.warning(
                    "Borg2 compact warnings",
                    job_id=job_id,
                    exit_code=process.returncode,
                )
            else:
                job.status = "failed"
                job.error_message = (
                    f"Compact failed with exit code {process.returncode}"
                )
                job.completed_at = datetime.utcnow()
                logger.error(
                    "Borg2 compact failed", job_id=job_id, exit_code=process.returncode
                )

            if log_buffer:
                log_file = (
                    self.log_dir
                    / f"compact_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
                try:
                    log_file.write_text("\n".join(log_buffer))
                    job.log_file_path = str(log_file)
                    job.has_logs = True
                    job.logs = f"Logs saved to: {log_file.name}"
                except Exception as e:
                    job.has_logs = False
                    job.logs = f"Failed to save logs: {e}"
                    logger.error(
                        "Failed to save borg2 compact logs", job_id=job_id, error=str(e)
                    )

            db.commit()

        except Exception as e:
            logger.error("Borg2 compact execution failed", job_id=job_id, error=str(e))
            try:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db.commit()
            except Exception:
                db.rollback()
        finally:
            self.running_processes.pop(job_id, None)
            cleanup_temp_key_file(temp_key_file)
            db.close()


compact_v2_service = CompactV2Service()
