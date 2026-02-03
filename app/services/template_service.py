"""
Script template rendering service.

Renders script templates by replacing {{PARAM}} placeholders with actual values.
Handles parameter decryption for password-type parameters.
"""

import re
import shlex
from typing import Dict, List, Any, Optional
import structlog

from app.core.security import decrypt_secret
from app.utils.script_params import validate_parameter_value

logger = structlog.get_logger()


class TemplateRenderingError(Exception):
    """Raised when template rendering fails"""
    pass


def render_script_template(
    script_content: str,
    parameters: List[Dict[str, Any]],
    parameter_values: Dict[str, str],
    decrypt_passwords: bool = True,
    system_vars: Optional[Dict[str, str]] = None
) -> str:
    """
    Render a script template by replacing {{PARAM}} placeholders with values.
    
    Args:
        script_content: The script template content
        parameters: List of parameter definitions from Script.parameters
        parameter_values: Dict of parameter values from RepositoryScript.parameter_values
        decrypt_passwords: Whether to decrypt password-type parameters
        system_vars: Optional dict of system-provided variables (BORG_REPO, etc.)
        
    Returns:
        Rendered script content
        
    Raises:
        TemplateRenderingError: If required parameters are missing or rendering fails
    """
    if not script_content:
        return ""
    
    # Build parameter lookup dict
    param_lookup = {}
    for param_def in parameters:
        param_name = param_def['name']
        param_type = param_def.get('type', 'text')
        required = param_def.get('required', False)
        default_value = param_def.get('default', '')
        
        # Get value: from parameter_values, or use default
        value = parameter_values.get(param_name, default_value) if parameter_values else default_value
        
        # Validate required parameters
        is_valid, error_msg = validate_parameter_value(param_def, value)
        if not is_valid:
            logger.error(
                "Missing required parameter",
                param_name=param_name,
                error=error_msg
            )
            raise TemplateRenderingError(error_msg)
        
        # Decrypt password-type parameters if needed
        if param_type == 'password' and value and decrypt_passwords:
            try:
                value = decrypt_secret(value)
                logger.debug(
                    "Decrypted password parameter",
                    param_name=param_name
                )
            except Exception as e:
                logger.error(
                    "Failed to decrypt password parameter",
                    param_name=param_name,
                    error=str(e)
                )
                raise TemplateRenderingError(
                    f"Failed to decrypt parameter '{param_name}': {str(e)}"
                )
        
        param_lookup[param_name] = value or ''
    
    # Add system variables
    if system_vars:
        param_lookup.update(system_vars)
    
    # Render template by replacing ${PARAM} and ${PARAM:-default}
    def replace_placeholder(match):
        param_name = match.group(1)
        default_in_template = match.group(2) if match.lastindex >= 2 else None
        
        # Get value from lookup or use inline default
        value = param_lookup.get(param_name, default_in_template or '')
        
        # Sanitize value to prevent shell injection
        # Note: We don't shell-escape here because the script might use these
        # in non-shell contexts (e.g., in heredocs, config files, etc.)
        # The caller should handle shell escaping if needed
        return value
    
    # Pattern matches: ${WORD} or ${WORD:-anything}
    pattern = r'\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}'
    rendered_content = re.sub(pattern, replace_placeholder, script_content)
    
    logger.info(
        "Rendered script template",
        param_count=len(param_lookup),
        password_params=[
            p['name'] for p in parameters 
            if p.get('type') == 'password' and p['name'] in param_lookup
        ]
    )
    
    return rendered_content


def sanitize_for_shell(value: str) -> str:
    """
    Sanitize a value for safe use in shell commands.
    Uses shlex.quote() to properly escape shell metacharacters.
    
    Args:
        value: The value to sanitize
        
    Returns:
        Shell-safe quoted string
    """
    return shlex.quote(value)


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


def preview_rendered_script(
    script_content: str,
    parameters: List[Dict[str, Any]],
    parameter_values: Dict[str, str],
    system_vars: Optional[Dict[str, str]] = None
) -> str:
    """
    Preview a rendered script with password values masked.
    Used for showing users what the script will look like without exposing secrets.
    
    Args:
        script_content: The script template content
        parameters: List of parameter definitions
        parameter_values: Dict of parameter values (encrypted passwords)
        system_vars: Optional dict of system variables
        
    Returns:
        Rendered script with passwords shown as '***'
    """
    # Create masked parameter values
    masked_values = {}
    for param_def in parameters:
        param_name = param_def['name']
        param_type = param_def.get('type', 'text')
        value = parameter_values.get(param_name, param_def.get('default', ''))
        
        if param_type == 'password' and value:
            masked_values[param_name] = '***'
        else:
            masked_values[param_name] = value
    
    # Render without decryption
    return render_script_template(
        script_content,
        parameters,
        masked_values,
        decrypt_passwords=False,
        system_vars=system_vars
    )
