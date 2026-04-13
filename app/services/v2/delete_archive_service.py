"""Borg 2 archive delete service.

Mirrors delete_archive_service.py but uses borg2 for the delete command and
automatically runs compact() afterwards — required in Borg 2 to free space.
"""

from datetime import datetime, timezone
from pathlib import Path
import structlog

from app.database.models import DeleteArchiveJob, Repository
from app.database.database import SessionLocal
from app.core.borg2 import borg2
from app.config import settings
from app.utils.borg_env import build_repository_borg_env, cleanup_temp_key_file

logger = structlog.get_logger()


class DeleteArchiveV2Service:
    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def execute_delete(
        self, job_id: int, repository_id: int, archive_name: str, _db=None
    ):
        """Delete a Borg 2 archive and compact the repository to free space."""
        db = SessionLocal()
        temp_key_file = None
        try:
            job = (
                db.query(DeleteArchiveJob).filter(DeleteArchiveJob.id == job_id).first()
            )
            if not job:
                logger.error("Borg2 delete job not found", job_id=job_id)
                return

            repo = db.query(Repository).filter(Repository.id == repository_id).first()
            if not repo:
                job.status = "failed"
                job.error_message = "Repository not found"
                db.commit()
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.progress = 10
            job.progress_message = "Deleting archive..."
            db.commit()

            env, temp_key_file = build_repository_borg_env(repo, db, keepalive=True)

            # Step 1: delete the archive
            delete_result = await borg2.delete_archive(
                repository=repo.path,
                archive=archive_name,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                env=env,
            )

            if not delete_result["success"]:
                job.status = "failed"
                job.error_message = delete_result["stderr"]
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                logger.error(
                    "Borg2 delete archive failed",
                    job_id=job_id,
                    stderr=delete_result["stderr"],
                )
                return

            # Step 2: compact (mandatory in borg2 to reclaim space)
            job.progress = 60
            job.progress_message = "Compacting repository to free space..."
            db.commit()

            compact_result = await borg2.compact(
                repository=repo.path,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                env=env,
            )

            if not compact_result["success"]:
                # Compact failure is non-fatal — archive was deleted successfully
                logger.warning(
                    "Borg2 post-delete compact failed",
                    job_id=job_id,
                    stderr=compact_result["stderr"],
                )

            job.status = "completed"
            job.progress = 100
            job.progress_message = "Archive deleted and repository compacted"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(
                "Borg2 archive deleted successfully",
                job_id=job_id,
                archive=archive_name,
            )

        except Exception as e:
            logger.error(
                "Borg2 delete archive service error", job_id=job_id, error=str(e)
            )
            try:
                job = (
                    db.query(DeleteArchiveJob)
                    .filter(DeleteArchiveJob.id == job_id)
                    .first()
                )
                if job:
                    job.status = "failed"
                    job.error_message = str(e)
                    job.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                pass
        finally:
            cleanup_temp_key_file(temp_key_file)
            db.close()


delete_archive_v2_service = DeleteArchiveV2Service()
