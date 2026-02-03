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
    hook_type: Optional[str] = None
) -> Dict[str, str]:
    """
    Build dict of system-provided variables for script rendering.
    
    Args:
        repository_id: Repository ID
        repository_name: Repository name
        repository_path: Repository path
        backup_status: Backup job status (for post-backup hooks)
        hook_type: Hook type ('pre-backup' or 'post-backup')
        
    Returns:
        Dict of system variables
    """
    system_vars = {}
    
    if repository_id is not None:
        system_vars['REPOSITORY_ID'] = str(repository_id)
    
    if repository_name:
        system_vars['REPOSITORY_NAME'] = repository_name
    
    if repository_path:
        system_vars['BORG_REPO'] = repository_path
        system_vars['REPOSITORY_PATH'] = repository_path
    
    if backup_status:
        system_vars['BACKUP_STATUS'] = backup_status
    
    if hook_type:
        system_vars['HOOK_TYPE'] = hook_type
    
    return system_vars
