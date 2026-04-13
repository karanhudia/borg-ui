"""
System variables service for script execution.

Provides system-level variables to scripts during execution.
Scripts use ${PARAM} syntax which bash interprets natively from environment variables.
"""

from typing import Dict, Optional


def get_system_variables(
    repository_id: Optional[int] = None,
    repository_name: Optional[str] = None,
    repository_path: Optional[str] = None,
    backup_status: Optional[str] = None,
    hook_type: Optional[str] = None,
    job_id: Optional[int] = None,
    source_host: Optional[str] = None,
    source_port: Optional[int] = None,
    source_username: Optional[str] = None,
) -> Dict[str, str]:
    """
    Build dict of system-provided variables for script rendering.

    All variables use BORG_UI_ prefix as they are Borg UI specific job-related variables.

    Args:
        repository_id: Repository ID
        repository_name: Repository name
        repository_path: Repository path
        backup_status: Backup job status (for post-backup hooks)
        hook_type: Hook type ('pre-backup' or 'post-backup')
        job_id: Backup job ID
        source_host: Hostname/IP of the SSH source connection (remote host being backed up)
        source_port: SSH port of the source connection
        source_username: SSH username of the source connection

    Returns:
        Dict of BORG_UI_ prefixed system variables
    """
    system_vars = {}

    if repository_id is not None:
        system_vars["BORG_UI_REPOSITORY_ID"] = str(repository_id)

    if repository_name:
        system_vars["BORG_UI_REPOSITORY_NAME"] = repository_name

    if repository_path:
        system_vars["BORG_UI_REPOSITORY_PATH"] = repository_path

    if backup_status:
        system_vars["BORG_UI_BACKUP_STATUS"] = backup_status

    if hook_type:
        system_vars["BORG_UI_HOOK_TYPE"] = hook_type

    if job_id is not None:
        system_vars["BORG_UI_JOB_ID"] = str(job_id)

    if source_host:
        system_vars["BORG_UI_REMOTE_HOST"] = source_host

    if source_port is not None:
        system_vars["BORG_UI_REMOTE_PORT"] = str(source_port)

    if source_username:
        system_vars["BORG_UI_REMOTE_USERNAME"] = source_username

    return system_vars
