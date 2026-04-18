"""
Utility functions for process management and orphan detection
"""

import json
import os
import subprocess
from pathlib import Path
import structlog
from datetime import datetime
from sqlalchemy.orm import Session
from app.config import settings
from app.core.borg_router import BorgRouter
from app.database.models import (
    CheckJob,
    CompactJob,
    BackupJob,
    PruneJob,
    RestoreJob,
    Repository,
)

logger = structlog.get_logger()


def is_process_alive(pid: int, stored_start_time: int) -> bool:
    """
    Check if a process with given PID and start_time is still running

    Args:
        pid: Process ID to check
        stored_start_time: Start time in jiffies when process was created

    Returns:
        True if process is alive and matches stored start_time
        False if process is dead OR PID was reused by different process
    """
    if not pid or not stored_start_time:
        return False

    try:
        # Try to read /proc/[pid]/stat
        with open(f"/proc/{pid}/stat", "r") as f:
            stat_data = f.read()

        # Extract current start_time
        # Format: pid (comm) state ppid ... starttime (22nd field)
        fields = stat_data.split(")")[1].split()
        current_start_time = int(fields[19])

        # Compare with stored start_time
        if current_start_time == stored_start_time:
            # Same process! It's still alive
            return True
        else:
            # PID was reused by a different process
            logger.info(
                "PID reused by different process",
                pid=pid,
                stored_start_time=stored_start_time,
                current_start_time=current_start_time,
            )
            return False

    except FileNotFoundError:
        # /proc/[pid] doesn't exist - process is dead
        logger.info("Process not found in /proc", pid=pid)
        return False
    except Exception as e:
        logger.error("Error checking process", pid=pid, error=str(e))
        return False


def break_repository_lock(repository: Repository) -> bool:
    """
    Break the lock on a repository

    Args:
        repository: Repository model instance

    Returns:
        True if lock was successfully broken, False otherwise
    """
    try:
        cmd = BorgRouter(repository).build_break_lock_command(
            repository_path=repository.path,
            remote_path=repository.remote_path,
        )

        # Set environment variables
        env = os.environ.copy()
        if repository.passphrase:
            env["BORG_PASSPHRASE"] = repository.passphrase

        # For remote repos, add SSH options
        if repository.connection_id:
            ssh_opts = [
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "LogLevel=ERROR",
            ]
            env["BORG_RSH"] = f"ssh {' '.join(ssh_opts)}"

        # Execute break-lock command
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            logger.info(
                "Successfully broke repository lock",
                repository_id=repository.id,
                repository_path=repository.path,
            )
            return True
        else:
            logger.error(
                "Failed to break repository lock",
                repository_id=repository.id,
                returncode=result.returncode,
                stderr=result.stderr,
            )
            return False

    except Exception as e:
        logger.error(
            "Error breaking repository lock", repository_id=repository.id, error=str(e)
        )
        return False


def cleanup_orphaned_jobs(db: Session):
    """
    Find and cleanup jobs that were running when container stopped

    This function is called on container startup to detect and cleanup
    orphaned jobs from container restarts or crashes.

    Args:
        db: Database session
    """
    logger.info("Checking for orphaned jobs...")

    # Find all running backup jobs
    running_backup_jobs = (
        db.query(BackupJob).filter(BackupJob.status == "running").all()
    )

    # Find all running restore jobs
    running_restore_jobs = (
        db.query(RestoreJob).filter(RestoreJob.status == "running").all()
    )

    # Find all running check jobs
    running_check_jobs = db.query(CheckJob).filter(CheckJob.status == "running").all()

    # Find all running prune jobs
    running_prune_jobs = db.query(PruneJob).filter(PruneJob.status == "running").all()

    # Find all running compact jobs
    running_compact_jobs = (
        db.query(CompactJob).filter(CompactJob.status == "running").all()
    )

    total_jobs = (
        len(running_backup_jobs)
        + len(running_restore_jobs)
        + len(running_check_jobs)
        + len(running_prune_jobs)
        + len(running_compact_jobs)
    )
    logger.info(
        "Found running jobs",
        backup_jobs=len(running_backup_jobs),
        restore_jobs=len(running_restore_jobs),
        check_jobs=len(running_check_jobs),
        prune_jobs=len(running_prune_jobs),
        compact_jobs=len(running_compact_jobs),
    )

    if total_jobs == 0:
        logger.info("No orphaned jobs found")
        return

    # Process backup jobs
    for job in running_backup_jobs:
        # Backup jobs don't have process_pid tracking, so we mark them all as failed on restart
        job.status = "failed"
        job.error_message = json.dumps(
            {"key": "backend.errors.service.containerRestartedDuringBackup"}
        )
        job.completed_at = datetime.utcnow()

        logger.info(
            "Orphaned backup job detected", job_id=job.id, repository=job.repository
        )

    # Process restore jobs
    for job in running_restore_jobs:
        # Restore jobs don't have process_pid tracking, so we mark them all as failed on restart
        job.status = "failed"
        job.error_message = json.dumps(
            {"key": "backend.errors.service.containerRestartedDuringRestore"}
        )
        job.completed_at = datetime.utcnow()

        logger.info(
            "Orphaned restore job detected", job_id=job.id, repository=job.repository
        )

    # Process check jobs
    for job in running_check_jobs:
        if not is_process_alive(job.process_pid, job.process_start_time):
            # Process is dead! Mark job as failed
            job.status = "failed"
            job.error_message = json.dumps(
                {"key": "backend.errors.service.containerRestartedDuringOperation"}
            )
            job.completed_at = datetime.utcnow()

            logger.info(
                "Orphaned check job detected",
                job_id=job.id,
                repository_id=job.repository_id,
                pid=job.process_pid,
            )

            # Get repository to determine if we should auto-break lock
            repository = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )

            if repository:
                if not repository.connection_id:
                    # For local repos, we can safely break the lock
                    logger.info(
                        "Attempting to break lock for local repository",
                        repository_id=repository.id,
                    )
                    if break_repository_lock(repository):
                        logger.info(
                            "Successfully broke lock for local repository",
                            repository_id=repository.id,
                        )
                    else:
                        logger.warning(
                            "Failed to break lock for local repository",
                            repository_id=repository.id,
                        )
                        job.error_message += "\n" + json.dumps(
                            {"key": "backend.errors.service.warningFailedBreakLock"}
                        )
                else:
                    # For remote repos, don't auto-break lock (remote process may still be running)
                    logger.warning(
                        "Orphaned check job for remote repository - manual lock break may be needed",
                        repository_id=repository.id,
                    )
                    job.error_message += "\n" + json.dumps(
                        {
                            "key": "backend.errors.service.warningRemoteProcessMayBeRunning"
                        }
                    )
        else:
            # Process is still alive! This is unexpected
            logger.warning(
                "Check job marked as running and process is still alive",
                job_id=job.id,
                pid=job.process_pid,
            )

    # Process prune jobs
    for job in running_prune_jobs:
        job.status = "failed"
        job.error_message = json.dumps(
            {"key": "backend.errors.service.containerRestartedDuringOperation"}
        )
        job.completed_at = datetime.utcnow()

        logger.info(
            "Orphaned prune job detected",
            job_id=job.id,
            repository_id=job.repository_id,
        )

        affected_backup_jobs = (
            db.query(BackupJob)
            .filter(
                BackupJob.repository == job.repository_path,
                BackupJob.maintenance_status == "running_prune",
            )
            .all()
        )

        for backup_job in affected_backup_jobs:
            backup_job.maintenance_status = "prune_failed"
            logger.info(
                "Marked backup maintenance state as failed after orphaned prune",
                backup_job_id=backup_job.id,
                prune_job_id=job.id,
                repository=backup_job.repository,
            )

    # Process compact jobs
    for job in running_compact_jobs:
        if not is_process_alive(job.process_pid, job.process_start_time):
            # Process is dead! Mark job as failed
            job.status = "failed"
            job.error_message = json.dumps(
                {"key": "backend.errors.service.containerRestartedDuringOperation"}
            )
            job.completed_at = datetime.utcnow()

            logger.info(
                "Orphaned compact job detected",
                job_id=job.id,
                repository_id=job.repository_id,
                pid=job.process_pid,
            )

            # Get repository to determine if we should auto-break lock
            repository = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )

            if repository:
                if not repository.connection_id:
                    # For local repos, we can safely break the lock
                    logger.info(
                        "Attempting to break lock for local repository",
                        repository_id=repository.id,
                    )
                    if break_repository_lock(repository):
                        logger.info(
                            "Successfully broke lock for local repository",
                            repository_id=repository.id,
                        )
                    else:
                        logger.warning(
                            "Failed to break lock for local repository",
                            repository_id=repository.id,
                        )
                        job.error_message += "\n" + json.dumps(
                            {"key": "backend.errors.service.warningFailedBreakLock"}
                        )
                else:
                    # For remote repos, don't auto-break lock
                    logger.warning(
                        "Orphaned compact job for remote repository - manual lock break may be needed",
                        repository_id=repository.id,
                    )
                    job.error_message += "\n" + json.dumps(
                        {
                            "key": "backend.errors.service.warningRemoteProcessMayBeRunning"
                        }
                    )

            affected_backup_jobs = (
                db.query(BackupJob)
                .filter(
                    BackupJob.repository == job.repository_path,
                    BackupJob.maintenance_status == "running_compact",
                )
                .all()
            )

            for backup_job in affected_backup_jobs:
                backup_job.maintenance_status = "compact_failed"
                logger.info(
                    "Marked backup maintenance state as failed after orphaned compact",
                    backup_job_id=backup_job.id,
                    compact_job_id=job.id,
                    repository=backup_job.repository,
                )
        else:
            # Process is still alive! This is unexpected
            logger.warning(
                "Compact job marked as running and process is still alive",
                job_id=job.id,
                pid=job.process_pid,
            )

    # Commit all changes
    db.commit()

    logger.info("Orphaned job cleanup completed")


def cleanup_orphaned_mounts():
    """
    Cleanup stale FUSE mounts on container startup

    This function detects and cleans up orphaned SSHFS and Borg mounts
    that may have been left behind from container restarts or crashes.

    Should be called during application startup.
    """
    logger.info("Checking for orphaned mounts...")

    try:
        managed_mount_base = Path(settings.data_dir) / "mounts"

        result = subprocess.run(["mount"], capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            logger.warning("Failed to list mounts", returncode=result.returncode)
            return

        orphaned_count = 0

        for line in result.stdout.split("\n"):
            parts = line.split()
            if len(parts) < 3 or "on" not in parts:
                continue

            try:
                on_index = parts.index("on")
                if on_index + 1 >= len(parts):
                    continue
                mount_point = parts[on_index + 1]
            except (ValueError, IndexError):
                continue

            is_temp_mount = (
                "sshfs_mount_" in mount_point or "borg_backup_root_" in mount_point
            )
            is_managed_mount = False
            try:
                is_managed_mount = (
                    Path(mount_point)
                    .resolve()
                    .is_relative_to(managed_mount_base.resolve())
                )
            except Exception:
                pass

            if not is_temp_mount and not is_managed_mount:
                continue

            logger.info("Found orphaned mount", mount_point=mount_point)
            orphaned_count += 1

            try:
                cleanup_result = subprocess.run(
                    ["fusermount", "-uz", mount_point],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if cleanup_result.returncode == 0:
                    logger.info(
                        "Successfully unmounted orphaned mount",
                        mount_point=mount_point,
                    )
                else:
                    logger.warning(
                        "Failed to unmount orphaned mount",
                        mount_point=mount_point,
                        stderr=cleanup_result.stderr,
                    )
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Timeout unmounting orphaned mount",
                    mount_point=mount_point,
                )
            except FileNotFoundError:
                try:
                    cleanup_result = subprocess.run(
                        ["umount", "-f", mount_point],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if cleanup_result.returncode == 0:
                        logger.info(
                            "Successfully unmounted orphaned mount (umount)",
                            mount_point=mount_point,
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to unmount with umount",
                        mount_point=mount_point,
                        error=str(e),
                    )
            except Exception as e:
                logger.error(
                    "Error unmounting orphaned mount",
                    mount_point=mount_point,
                    error=str(e),
                )

        if managed_mount_base.exists():
            for child in managed_mount_base.iterdir():
                if not child.is_dir():
                    continue
                try:
                    if any(child.iterdir()):
                        continue
                    child.rmdir()
                    logger.debug(
                        "Removed orphaned managed mount directory",
                        mount_point=str(child),
                    )
                except Exception as e:
                    logger.debug(
                        "Could not remove managed mount directory",
                        mount_point=str(child),
                        error=str(e),
                    )

        if orphaned_count > 0:
            logger.info(
                "Orphaned mount cleanup completed", cleaned_up_count=orphaned_count
            )
        else:
            logger.info("No orphaned mounts found")

    except subprocess.TimeoutExpired:
        logger.error("Timeout while listing mounts")
    except Exception as e:
        logger.error("Failed orphan mount cleanup", error=str(e))
