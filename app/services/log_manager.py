"""
Log Manager Service

Handles log storage calculations, cleanup operations, and log file management.
Supports all job types: backup, restore, check, compact, prune, package
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Optional
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import (
    BackupJob, RestoreJob, CheckJob, CompactJob, PruneJob, PackageInstallJob
)

logger = structlog.get_logger()


class LogManager:
    """Manages log files for all job types"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Log file patterns for different job types
        self.log_patterns = [
            "backup_job_",
            "restore_job_",
            "check_job_",
            "compact_job_",
            "prune_job_",
            "package_job_"
        ]

    def calculate_log_storage(self) -> Dict:
        """
        Calculate total log storage usage and statistics.

        Returns:
            dict with:
                - total_size_bytes: Total size in bytes
                - total_size_mb: Total size in MB (float)
                - file_count: Number of log files
                - oldest_log_date: Datetime of oldest log (or None)
                - newest_log_date: Datetime of newest log (or None)
                - files_by_type: Breakdown by job type
        """
        try:
            total_size = 0
            file_count = 0
            oldest_mtime = None
            newest_mtime = None
            files_by_type = {
                "backup": 0,
                "restore": 0,
                "check": 0,
                "compact": 0,
                "prune": 0,
                "package": 0
            }

            # Use os.scandir() for performance (faster than glob)
            if not self.log_dir.exists():
                return {
                    "total_size_bytes": 0,
                    "total_size_mb": 0.0,
                    "file_count": 0,
                    "oldest_log_date": None,
                    "newest_log_date": None,
                    "files_by_type": files_by_type
                }

            with os.scandir(self.log_dir) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.endswith('.log'):
                        try:
                            stat = entry.stat()
                            total_size += stat.st_size
                            file_count += 1

                            # Track oldest and newest
                            if oldest_mtime is None or stat.st_mtime < oldest_mtime:
                                oldest_mtime = stat.st_mtime
                            if newest_mtime is None or stat.st_mtime > newest_mtime:
                                newest_mtime = stat.st_mtime

                            # Count by job type
                            for job_type in files_by_type.keys():
                                if entry.name.startswith(f"{job_type}_job_"):
                                    files_by_type[job_type] += 1
                                    break

                        except OSError as e:
                            logger.warning("Failed to stat log file", file=entry.name, error=str(e))
                            continue

            return {
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
                "oldest_log_date": datetime.fromtimestamp(oldest_mtime) if oldest_mtime else None,
                "newest_log_date": datetime.fromtimestamp(newest_mtime) if newest_mtime else None,
                "files_by_type": files_by_type
            }

        except Exception as e:
            logger.error("Failed to calculate log storage", error=str(e))
            raise

    def get_running_job_log_paths(self, db: Session) -> Set[str]:
        """
        Query all job tables for running jobs and return their log file paths.

        This protects running job logs from deletion during cleanup.

        Returns:
            Set of absolute log file paths for running jobs
        """
        try:
            protected_paths = set()

            # Query all job types for running status
            job_models = [BackupJob, RestoreJob, CheckJob, CompactJob, PruneJob, PackageInstallJob]

            for model in job_models:
                running_jobs = db.query(model).filter(model.status == 'running').all()
                for job in running_jobs:
                    if hasattr(job, 'log_file_path') and job.log_file_path:
                        protected_paths.add(str(job.log_file_path))

            logger.info("Found running job logs to protect",
                       count=len(protected_paths),
                       paths=list(protected_paths))

            return protected_paths

        except Exception as e:
            logger.error("Failed to get running job log paths", error=str(e))
            # Return empty set on error (safer to not delete anything)
            return set()

    def cleanup_logs_by_age(
        self,
        max_age_days: int,
        protected_paths: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict:
        """
        Delete log files older than max_age_days.

        Args:
            max_age_days: Maximum age in days
            protected_paths: Set of file paths to never delete (running jobs)
            dry_run: If True, don't actually delete files

        Returns:
            dict with:
                - deleted_count: Number of files deleted
                - deleted_size_mb: Size freed in MB
                - skipped_count: Number of files skipped (protected)
                - errors: List of error messages
        """
        try:
            if protected_paths is None:
                protected_paths = set()

            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            cutoff_timestamp = cutoff_date.timestamp()

            deleted_count = 0
            deleted_size = 0
            skipped_count = 0
            errors = []

            if not self.log_dir.exists():
                return {
                    "deleted_count": 0,
                    "deleted_size_mb": 0.0,
                    "skipped_count": 0,
                    "errors": []
                }

            with os.scandir(self.log_dir) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.endswith('.log'):
                        try:
                            # Skip protected files (running jobs)
                            if entry.path in protected_paths:
                                skipped_count += 1
                                logger.debug("Skipping protected log", file=entry.name)
                                continue

                            stat = entry.stat()

                            # Check if file is older than cutoff
                            if stat.st_mtime < cutoff_timestamp:
                                if not dry_run:
                                    os.remove(entry.path)
                                    logger.info("Deleted old log file",
                                              file=entry.name,
                                              age_days=(datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days,
                                              size_kb=round(stat.st_size / 1024, 2))

                                deleted_count += 1
                                deleted_size += stat.st_size

                        except OSError as e:
                            error_msg = f"Failed to delete {entry.name}: {str(e)}"
                            errors.append(error_msg)
                            logger.warning("Failed to delete log file", file=entry.name, error=str(e))
                            continue

            return {
                "deleted_count": deleted_count,
                "deleted_size_mb": round(deleted_size / (1024 * 1024), 2),
                "skipped_count": skipped_count,
                "errors": errors
            }

        except Exception as e:
            logger.error("Failed to cleanup logs by age", error=str(e))
            raise

    def cleanup_logs_by_size(
        self,
        max_total_size_mb: int,
        protected_paths: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict:
        """
        Delete oldest log files until total size is under max_total_size_mb.

        Args:
            max_total_size_mb: Maximum total size in MB
            protected_paths: Set of file paths to never delete (running jobs)
            dry_run: If True, don't actually delete files

        Returns:
            dict with:
                - deleted_count: Number of files deleted
                - deleted_size_mb: Size freed in MB
                - skipped_count: Number of files skipped (protected)
                - final_size_mb: Final total size after cleanup
                - errors: List of error messages
        """
        try:
            if protected_paths is None:
                protected_paths = set()

            max_size_bytes = max_total_size_mb * 1024 * 1024
            deleted_count = 0
            deleted_size = 0
            skipped_count = 0
            errors = []

            # Get all log files with their stats
            log_files = []
            current_total_size = 0

            if not self.log_dir.exists():
                return {
                    "deleted_count": 0,
                    "deleted_size_mb": 0.0,
                    "skipped_count": 0,
                    "final_size_mb": 0.0,
                    "errors": []
                }

            with os.scandir(self.log_dir) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.endswith('.log'):
                        try:
                            stat = entry.stat()
                            log_files.append({
                                "path": entry.path,
                                "name": entry.name,
                                "size": stat.st_size,
                                "mtime": stat.st_mtime,
                                "protected": entry.path in protected_paths
                            })
                            current_total_size += stat.st_size
                        except OSError as e:
                            logger.warning("Failed to stat log file", file=entry.name, error=str(e))
                            continue

            # If current size is under limit, nothing to do
            if current_total_size <= max_size_bytes:
                logger.info("Log storage within limits",
                          current_mb=round(current_total_size / (1024 * 1024), 2),
                          limit_mb=max_total_size_mb)
                return {
                    "deleted_count": 0,
                    "deleted_size_mb": 0.0,
                    "skipped_count": 0,
                    "final_size_mb": round(current_total_size / (1024 * 1024), 2),
                    "errors": []
                }

            # Sort by mtime (oldest first)
            log_files.sort(key=lambda x: x["mtime"])

            # Delete oldest files until we're under the limit
            remaining_size = current_total_size

            for log_file in log_files:
                # Stop if we're under the limit
                if remaining_size <= max_size_bytes:
                    break

                # Skip protected files
                if log_file["protected"]:
                    skipped_count += 1
                    logger.debug("Skipping protected log", file=log_file["name"])
                    continue

                # Delete the file
                try:
                    if not dry_run:
                        os.remove(log_file["path"])
                        logger.info("Deleted log file to free space",
                                  file=log_file["name"],
                                  size_kb=round(log_file["size"] / 1024, 2))

                    deleted_count += 1
                    deleted_size += log_file["size"]
                    remaining_size -= log_file["size"]

                except OSError as e:
                    error_msg = f"Failed to delete {log_file['name']}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning("Failed to delete log file", file=log_file["name"], error=str(e))
                    continue

            return {
                "deleted_count": deleted_count,
                "deleted_size_mb": round(deleted_size / (1024 * 1024), 2),
                "skipped_count": skipped_count,
                "final_size_mb": round(remaining_size / (1024 * 1024), 2),
                "errors": errors
            }

        except Exception as e:
            logger.error("Failed to cleanup logs by size", error=str(e))
            raise

    def cleanup_logs_combined(
        self,
        db: Session,
        max_age_days: int,
        max_total_size_mb: int,
        dry_run: bool = False
    ) -> Dict:
        """
        Combined cleanup: First delete by age, then by size if needed.

        This is the recommended cleanup method as it:
        1. Removes old logs regardless of size
        2. Then ensures total size is within limits
        3. Protects running job logs

        Args:
            db: Database session (to query running jobs)
            max_age_days: Maximum age in days
            max_total_size_mb: Maximum total size in MB
            dry_run: If True, don't actually delete files

        Returns:
            dict with:
                - age_cleanup: Results from age-based cleanup
                - size_cleanup: Results from size-based cleanup
                - total_deleted_count: Total files deleted
                - total_deleted_size_mb: Total size freed
                - total_errors: Combined list of errors
        """
        try:
            # Get protected paths (running jobs)
            protected_paths = self.get_running_job_log_paths(db)

            logger.info("Starting combined log cleanup",
                       max_age_days=max_age_days,
                       max_total_size_mb=max_total_size_mb,
                       protected_count=len(protected_paths),
                       dry_run=dry_run)

            # Step 1: Cleanup by age
            age_result = self.cleanup_logs_by_age(
                max_age_days=max_age_days,
                protected_paths=protected_paths,
                dry_run=dry_run
            )

            logger.info("Age-based cleanup completed",
                       deleted=age_result["deleted_count"],
                       size_mb=age_result["deleted_size_mb"],
                       skipped=age_result["skipped_count"])

            # Step 2: Cleanup by size (if needed)
            size_result = self.cleanup_logs_by_size(
                max_total_size_mb=max_total_size_mb,
                protected_paths=protected_paths,
                dry_run=dry_run
            )

            logger.info("Size-based cleanup completed",
                       deleted=size_result["deleted_count"],
                       size_mb=size_result["deleted_size_mb"],
                       skipped=size_result["skipped_count"],
                       final_size_mb=size_result["final_size_mb"])

            # Combine results
            total_deleted = age_result["deleted_count"] + size_result["deleted_count"]
            total_size_freed = age_result["deleted_size_mb"] + size_result["deleted_size_mb"]
            total_errors = age_result["errors"] + size_result["errors"]

            return {
                "age_cleanup": age_result,
                "size_cleanup": size_result,
                "total_deleted_count": total_deleted,
                "total_deleted_size_mb": round(total_size_freed, 2),
                "total_errors": total_errors,
                "success": len(total_errors) == 0
            }

        except Exception as e:
            logger.error("Failed to run combined log cleanup", error=str(e))
            raise


# Global instance
log_manager = LogManager()
