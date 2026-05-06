from datetime import datetime


def apply_compact_completion(job, repository, returncode: int, *, now=None) -> None:
    """Apply the shared terminal compact state to a job and repository."""
    completed_at = now or datetime.utcnow()
    job.completed_at = completed_at

    if returncode == 0:
        job.status = "completed"
        job.progress = 100
        job.progress_message = "Compact completed successfully"
        repository.last_compact = completed_at
        return

    if returncode == 1 or (100 <= returncode <= 127):
        job.status = "completed_with_warnings"
        job.progress = 100
        job.progress_message = (
            f"Compact completed with warnings (exit code {returncode})"
        )
        job.error_message = job.progress_message
        repository.last_compact = completed_at
        return

    job.status = "failed"
    job.error_message = f"Compact failed with exit code {returncode}"
