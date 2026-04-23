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
from app.utils.db_retries import commit_with_retry
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

                def persist_missing_repo_state():
                    job.status = "failed"
                    job.error_message = "Repository not found"

                await commit_with_retry(
                    db,
                    prepare=persist_missing_repo_state,
                    logger=logger,
                    action="borg2_delete_missing_repo",
                    job_id=job_id,
                    repository_id=repository_id,
                )
                return

            started_at = datetime.now(timezone.utc)

            def persist_start_state():
                job.status = "running"
                job.started_at = started_at
                job.progress = 10
                job.progress_message = "Deleting archive..."

            await commit_with_retry(
                db,
                prepare=persist_start_state,
                logger=logger,
                action="borg2_delete_start",
                job_id=job_id,
                repository_id=repository_id,
            )

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
                completed_at = datetime.now(timezone.utc)

                def persist_delete_failure():
                    job.status = "failed"
                    job.error_message = delete_result["stderr"]
                    job.completed_at = completed_at

                await commit_with_retry(
                    db,
                    prepare=persist_delete_failure,
                    logger=logger,
                    action="borg2_delete_delete_fail",
                    job_id=job_id,
                    repository_id=repository_id,
                )
                logger.error(
                    "Borg2 delete archive failed",
                    job_id=job_id,
                    stderr=delete_result["stderr"],
                )
                return

            # Step 2: compact (mandatory in borg2 to reclaim space)
            def persist_compact_transition():
                job.progress = 60
                job.progress_message = "Compacting repository to free space..."

            await commit_with_retry(
                db,
                prepare=persist_compact_transition,
                logger=logger,
                action="borg2_delete_compact_transition",
                job_id=job_id,
                repository_id=repository_id,
            )

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

            completed_at = datetime.now(timezone.utc)

            def persist_final_state():
                job.status = "completed"
                job.progress = 100
                job.progress_message = "Archive deleted and repository compacted"
                job.completed_at = completed_at

            await commit_with_retry(
                db,
                prepare=persist_final_state,
                logger=logger,
                action="borg2_delete_finalize",
                job_id=job_id,
                repository_id=repository_id,
            )

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
                    completed_at = datetime.now(timezone.utc)

                    def persist_failure_state():
                        job.status = "failed"
                        job.error_message = str(e)
                        job.completed_at = completed_at

                    await commit_with_retry(
                        db,
                        prepare=persist_failure_state,
                        logger=logger,
                        action="borg2_delete_fail",
                        job_id=job_id,
                        repository_id=repository_id,
                    )
            except Exception:
                pass
        finally:
            cleanup_temp_key_file(temp_key_file)
            db.close()


delete_archive_v2_service = DeleteArchiveV2Service()
