"""Borg 2 prune service for shared scheduled/manual maintenance flows."""

from datetime import datetime, timezone
from pathlib import Path
import structlog

from app.config import settings
from app.core.borg2 import borg2
from app.database.database import SessionLocal
from app.database.models import PruneJob, Repository

logger = structlog.get_logger()


class PruneV2Service:
    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

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

            result = await self.run_prune(
                repo=repo,
                keep_hourly=keep_hourly,
                keep_daily=keep_daily,
                keep_weekly=keep_weekly,
                keep_monthly=keep_monthly,
                keep_quarterly=keep_quarterly,
                keep_yearly=keep_yearly,
                dry_run=dry_run,
            )

            stdout = result.get("stdout", "") or ""
            stderr = result.get("stderr", "") or ""
            combined_output = "\n".join(part for part in [stdout, stderr] if part).strip()

            if combined_output:
                log_file = self.log_dir / f"prune_job_{job_id}.log"
                log_file.write_text(combined_output)
                job.log_file_path = str(log_file)
                job.has_logs = True

            if result.get("success"):
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
            db.close()


prune_v2_service = PruneV2Service()
