"""Borg 2 prune service for shared scheduled/manual maintenance flows."""

import asyncio
import contextlib
from datetime import datetime, timezone
from pathlib import Path
import structlog

from app.config import settings
from app.core.borg2 import _get_borg2_binary, borg2
from app.database.database import SessionLocal
from app.database.models import PruneJob, Repository
from app.utils.borg_env import build_repository_borg_env, cleanup_temp_key_file

logger = structlog.get_logger()


class PruneV2Service:
    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes: dict = {}

    async def cancel_prune(self, job_id: int) -> bool:
        """Cancel a running borg2 prune job by terminating its tracked process."""
        if job_id not in self.running_processes:
            logger.warning(
                "No running borg2 prune process found for job", job_id=job_id
            )
            return False

        process = self.running_processes[job_id]
        try:
            process.terminate()
            logger.info(
                "Sent SIGTERM to borg2 prune process", job_id=job_id, pid=process.pid
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            return True
        except Exception as e:
            logger.error(
                "Failed to cancel borg2 prune process", job_id=job_id, error=str(e)
            )
            return False

    async def run_prune(
        self,
        repo: Repository,
        keep_hourly: int,
        keep_daily: int,
        keep_weekly: int,
        keep_monthly: int,
        keep_quarterly: int,
        keep_yearly: int,
        dry_run: bool = False,
    ) -> dict:
        """Execute a Borg 2 prune command and return the raw result."""
        return await borg2.prune_archives(
            repository=repo.path,
            keep_hourly=keep_hourly,
            keep_daily=keep_daily,
            keep_weekly=keep_weekly,
            keep_monthly=keep_monthly,
            keep_quarterly=keep_quarterly,
            keep_yearly=keep_yearly,
            dry_run=dry_run,
            passphrase=repo.passphrase,
            remote_path=repo.remote_path,
        )

    async def execute_prune(
        self,
        job_id: int,
        repository_id: int,
        keep_hourly: int,
        keep_daily: int,
        keep_weekly: int,
        keep_monthly: int,
        keep_quarterly: int,
        keep_yearly: int,
        dry_run: bool = False,
        _db=None,
    ):
        """Execute borg2 prune and persist results to the shared PruneJob model."""
        db = SessionLocal()
        temp_key_file = None
        try:
            job = db.query(PruneJob).filter(PruneJob.id == job_id).first()
            if not job:
                logger.error("Borg2 prune job not found", job_id=job_id)
                return

            repo = db.query(Repository).filter(Repository.id == repository_id).first()
            if not repo:
                job.status = "failed"
                job.error_message = f"Repository not found (ID: {repository_id})"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.progress = 10
            job.progress_message = "Pruning archives"
            db.commit()

            env, temp_key_file = build_repository_borg_env(repo, db, keepalive=True)
            borg_cmd = _get_borg2_binary()
            cmd = [borg_cmd, "-r", repo.path, "prune", "--list"]
            if repo.remote_path:
                cmd.extend(["--remote-path", repo.remote_path])
            if keep_hourly > 0:
                cmd.extend(["--keep-hourly", str(keep_hourly)])
            if keep_daily > 0:
                cmd.extend(["--keep-daily", str(keep_daily)])
            if keep_weekly > 0:
                cmd.extend(["--keep-weekly", str(keep_weekly)])
            if keep_monthly > 0:
                cmd.extend(["--keep-monthly", str(keep_monthly)])
            if keep_quarterly > 0:
                cmd.extend(["--keep-3monthly", str(keep_quarterly)])
            if keep_yearly > 0:
                cmd.extend(["--keep-yearly", str(keep_yearly)])
            if dry_run:
                cmd.append("--dry-run")

            logger.info(
                "Starting borg2 prune",
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
            self.running_processes[job_id] = process

            async def check_cancellation():
                while process.returncode is None:
                    await asyncio.sleep(1)
                    db.refresh(job)
                    if job.status == "cancelled":
                        logger.info("Borg2 prune cancelled, terminating", job_id=job_id)
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()
                        break

            check_task = asyncio.create_task(check_cancellation())
            try:
                stdout_bytes, stderr_bytes = await process.communicate()
            finally:
                check_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await check_task

            stdout = stdout_bytes.decode() if stdout_bytes else ""
            stderr = stderr_bytes.decode() if stderr_bytes else ""
            combined_output = "\n".join(
                part for part in [stdout, stderr] if part
            ).strip()

            if combined_output:
                log_file = self.log_dir / f"prune_job_{job_id}.log"
                log_file.write_text(combined_output)
                job.log_file_path = str(log_file)
                job.has_logs = True

            if job.status == "cancelled":
                job.progress_message = "Prune cancelled"
            elif process.returncode == 0:
                job.status = "completed"
                job.progress = 100
                job.progress_message = "Prune completed successfully"
            else:
                job.status = "failed"
                job.progress_message = "Prune failed"
                job.error_message = stderr or stdout or "Prune failed"

            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as e:
            logger.error("Borg2 prune service error", job_id=job_id, error=str(e))
            try:
                job = db.query(PruneJob).filter(PruneJob.id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error_message = str(e)
                    job.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                pass
        finally:
            self.running_processes.pop(job_id, None)
            cleanup_temp_key_file(temp_key_file)
            db.close()


prune_v2_service = PruneV2Service()
