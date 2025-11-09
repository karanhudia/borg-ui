"""
Utility functions for process management and orphan detection
"""
import os
import subprocess
import structlog
from datetime import datetime
from sqlalchemy.orm import Session
from app.database.models import CheckJob, CompactJob, Repository

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
        with open(f'/proc/{pid}/stat', 'r') as f:
            stat_data = f.read()

        # Extract current start_time
        # Format: pid (comm) state ppid ... starttime (22nd field)
        fields = stat_data.split(')')[1].split()
        current_start_time = int(fields[19])

        # Compare with stored start_time
        if current_start_time == stored_start_time:
            # Same process! It's still alive
            return True
        else:
            # PID was reused by a different process
            logger.info("PID reused by different process",
                       pid=pid,
                       stored_start_time=stored_start_time,
                       current_start_time=current_start_time)
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
        # Build borg break-lock command
        cmd = ["borg", "break-lock", repository.path]

        # Set environment variables
        env = os.environ.copy()
        if repository.passphrase:
            env['BORG_PASSPHRASE'] = repository.passphrase

        # For remote repos, add SSH options
        if repository.repository_type != "local":
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR"
            ]
            env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            if repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])

        # Execute break-lock command
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info("Successfully broke repository lock",
                       repository_id=repository.id,
                       repository_path=repository.path)
            return True
        else:
            logger.error("Failed to break repository lock",
                        repository_id=repository.id,
                        returncode=result.returncode,
                        stderr=result.stderr)
            return False

    except Exception as e:
        logger.error("Error breaking repository lock",
                    repository_id=repository.id,
                    error=str(e))
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

    # Find all running check jobs
    running_check_jobs = db.query(CheckJob).filter(
        CheckJob.status == "running"
    ).all()

    # Find all running compact jobs
    running_compact_jobs = db.query(CompactJob).filter(
        CompactJob.status == "running"
    ).all()

    total_jobs = len(running_check_jobs) + len(running_compact_jobs)
    logger.info("Found running jobs",
               check_jobs=len(running_check_jobs),
               compact_jobs=len(running_compact_jobs))

    if total_jobs == 0:
        logger.info("No orphaned jobs found")
        return

    # Process check jobs
    for job in running_check_jobs:
        if not is_process_alive(job.process_pid, job.process_start_time):
            # Process is dead! Mark job as failed
            job.status = "failed"
            job.error_message = "Container restarted during operation"
            job.completed_at = datetime.utcnow()

            logger.info("Orphaned check job detected",
                       job_id=job.id,
                       repository_id=job.repository_id,
                       pid=job.process_pid)

            # Get repository to determine if we should auto-break lock
            repository = db.query(Repository).filter(
                Repository.id == job.repository_id
            ).first()

            if repository:
                if repository.repository_type == "local":
                    # For local repos, we can safely break the lock
                    logger.info("Attempting to break lock for local repository",
                               repository_id=repository.id)
                    if break_repository_lock(repository):
                        logger.info("Successfully broke lock for local repository",
                                   repository_id=repository.id)
                    else:
                        logger.warning("Failed to break lock for local repository",
                                      repository_id=repository.id)
                        job.error_message += " (Warning: Failed to automatically break lock)"
                else:
                    # For remote repos, don't auto-break lock (remote process may still be running)
                    logger.warning("Orphaned check job for remote repository - manual lock break may be needed",
                                  repository_id=repository.id,
                                  repository_type=repository.repository_type)
                    job.error_message += " (Warning: Remote process may still be running, manual verification recommended)"
        else:
            # Process is still alive! This is unexpected
            logger.warning("Check job marked as running and process is still alive",
                          job_id=job.id,
                          pid=job.process_pid)

    # Process compact jobs
    for job in running_compact_jobs:
        if not is_process_alive(job.process_pid, job.process_start_time):
            # Process is dead! Mark job as failed
            job.status = "failed"
            job.error_message = "Container restarted during operation"
            job.completed_at = datetime.utcnow()

            logger.info("Orphaned compact job detected",
                       job_id=job.id,
                       repository_id=job.repository_id,
                       pid=job.process_pid)

            # Get repository to determine if we should auto-break lock
            repository = db.query(Repository).filter(
                Repository.id == job.repository_id
            ).first()

            if repository:
                if repository.repository_type == "local":
                    # For local repos, we can safely break the lock
                    logger.info("Attempting to break lock for local repository",
                               repository_id=repository.id)
                    if break_repository_lock(repository):
                        logger.info("Successfully broke lock for local repository",
                                   repository_id=repository.id)
                    else:
                        logger.warning("Failed to break lock for local repository",
                                      repository_id=repository.id)
                        job.error_message += " (Warning: Failed to automatically break lock)"
                else:
                    # For remote repos, don't auto-break lock
                    logger.warning("Orphaned compact job for remote repository - manual lock break may be needed",
                                  repository_id=repository.id,
                                  repository_type=repository.repository_type)
                    job.error_message += " (Warning: Remote process may still be running, manual verification recommended)"
        else:
            # Process is still alive! This is unexpected
            logger.warning("Compact job marked as running and process is still alive",
                          job_id=job.id,
                          pid=job.process_pid)

    # Commit all changes
    db.commit()

    logger.info("Orphaned job cleanup completed")
