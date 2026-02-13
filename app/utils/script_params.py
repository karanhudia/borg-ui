"""
Script parameter parsing and validation utilities.

Parses script content for ${PARAM} and ${PARAM:-default} syntax.
Detects parameter types based on naming conventions.
"""

import re
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger()

# Parameter naming patterns that indicate password/secret type
PASSWORD_SUFFIXES = [
    '_PASSWORD',
    '_TOKEN',
    '_SECRET',
    '_KEY',
    '_API_KEY',
    '_PASSPHRASE',
    '_APIKEY',
    '_AUTH',
    '_CREDENTIAL',
    '_CREDENTIALS'
]

# System-provided variables that should NOT be treated as user parameters
# These are automatically injected at runtime and don't need user input
# All Borg UI variables use BORG_UI_ prefix
SYSTEM_VARIABLES = {
    'BORG_UI_BACKUP_STATUS',
    'BORG_UI_REPOSITORY_NAME',
    'BORG_UI_REPOSITORY_PATH',
    'BORG_UI_REPOSITORY_ID',
    'BORG_UI_HOOK_TYPE',
    'BORG_UI_JOB_ID',
}


def parse_script_parameters(script_content: str) -> List[Dict[str, Any]]:
    """
    Parse script content for parameter placeholders in ${PARAM} or ${PARAM:-default} syntax.
    
    Args:
        script_content: The script content to parse
        
    Returns:
        List of parameter definitions with schema:
        [
            {
                'name': 'PARAM_NAME',
                'type': 'text' | 'password',
                'default': 'default_value' or '',
                'description': 'Auto-generated description' or '',
                'required': bool
            }
        ]
    """
    if not script_content:
        return []
    
    # Find all ${PARAM} and ${PARAM:-default} patterns
    # Pattern matches: ${WORD} or ${WORD:-anything}
    pattern = r'\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}'
    matches = re.findall(pattern, script_content)
    
    logger.debug(
        "Searching for parameters in script",
        content_length=len(script_content),
        pattern=pattern,
        raw_matches=matches
    )
    
    # Use dict to deduplicate and merge defaults
    params_dict = {}
    
    for param_name, default_value in matches:
        # Validate parameter name (UPPER_SNAKE_CASE)
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', param_name):
            logger.warning(
                "Invalid parameter name - should be UPPER_SNAKE_CASE",
                param_name=param_name
            )
            continue

        # Skip system-provided variables (automatically injected at runtime)
        if param_name in SYSTEM_VARIABLES:
            logger.debug(
                "Skipping system variable (auto-provided)",
                param_name=param_name
            )
            continue

        # Detect parameter type from naming convention
        param_type = detect_parameter_type(param_name)
        
        # Create or update parameter definition
        if param_name not in params_dict:
            params_dict[param_name] = {
                'name': param_name,
                'type': param_type,
                'default': default_value.strip() if default_value else '',
                'description': generate_description(param_name, param_type),
                'required': not bool(default_value)  # Required if no default provided
            }
        else:
            # If we find the same param with a default, update it
            if default_value and not params_dict[param_name]['default']:
                params_dict[param_name]['default'] = default_value.strip()
                params_dict[param_name]['required'] = False
    
    # Convert to sorted list (by name)
    parameters = sorted(params_dict.values(), key=lambda x: x['name'])
    
    logger.info(
        "Parsed script parameters (system variables excluded)",
        param_count=len(parameters),
        password_params=[p['name'] for p in parameters if p['type'] == 'password'],
        system_vars_skipped=len([name for name, _ in matches if name in SYSTEM_VARIABLES])
    )
    
    return parameters


def detect_parameter_type(param_name: str) -> str:
    """
    Detect if a parameter is a password/secret type based on naming convention.
    
    Args:
        param_name: The parameter name (e.g., 'DB_PASSWORD', 'API_KEY')
        
    Returns:
        'password' if name matches secret patterns, otherwise 'text'
    """
    param_upper = param_name.upper()
    
    for suffix in PASSWORD_SUFFIXES:
        if param_upper.endswith(suffix):
            return 'password'
    
    return 'text'


def generate_description(param_name: str, param_type: str) -> str:
    """
    Generate a human-friendly description for a parameter based on its name.

    Args:
        param_name: The parameter name (e.g., 'DB_HOST', 'API_KEY')
        param_type: The parameter type ('text' or 'password')

    Returns:
        A descriptive string (empty for auto-detected params as user should provide their own)
    """
    # Don't generate redundant descriptions - let users provide meaningful ones
    # Auto-generated descriptions like "Db Host" or "Api Key" are not helpful
    return ""


def validate_parameter_name(param_name: str) -> bool:
    """
    Validate that a parameter name follows UPPER_SNAKE_CASE convention.
    
    Args:
        param_name: The parameter name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not param_name:
        return False
    
    # Must be UPPER_SNAKE_CASE: starts with letter or underscore,
    # contains only uppercase letters, numbers, and underscores
    pattern = r'^[A-Z_][A-Z0-9_]*$'
    return bool(re.match(pattern, param_name))


def validate_parameter_value(
    param_def: Dict[str, Any],
    value: Optional[str]
) -> tuple[bool, Optional[str]]:
    """
    Validate a parameter value against its definition.

    Args:
        param_def: Parameter definition dict with 'name', 'type', 'required' fields
        value: The value to validate (can be None or empty string)

    Returns:
        Tuple of (is_valid, error_message)
    """
    param_name = param_def.get('name')
    required = param_def.get('required', False)

    # Check required fields
    if required and not value:
        return False, f"Parameter '{param_name}' is required but no value provided"

    # Basic length validation to prevent extremely large values
    if value and len(value) > 10000:
        return False, f"Parameter '{param_name}' value exceeds maximum length of 10000 characters"

    # Note: We don't validate for shell metacharacters here because:
    # 1. Bash properly handles ${VAR} expansion from environment variables
    # 2. Environment variables are not directly interpolated into shell commands
    # 3. Users may legitimately need special characters in their values
    # The script execution uses subprocess with env parameter, not shell string interpolation

    # Value is valid
    return True, None


def filter_system_variables_from_params(
    parameters: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Filter out system variables from a parameter list.

    This is used when returning parameters to the frontend to ensure
    that scripts created before the SYSTEM_VARIABLES filter was added
    don't show system variables as required parameters.

    Args:
        parameters: List of parameter definitions

    Returns:
        List of parameters with system variables removed
    """
    if not parameters:
        return []

    return [
        param for param in parameters
        if param.get('name') not in SYSTEM_VARIABLES
    ]


def mask_password_values(
    parameters: List[Dict[str, Any]],
    parameter_values: Dict[str, str]
) -> Dict[str, str]:
    """
    Mask password-type parameter values for API responses.

    Args:
        parameters: List of parameter definitions
        parameter_values: Dict of parameter values

    Returns:
        Dict with password values masked as '***'
    """
    if not parameter_values:
        return {}

    masked_values = parameter_values.copy()

    # Create lookup of password-type parameters
    password_params = {p['name'] for p in parameters if p.get('type') == 'password'}

    # Mask password values
    for param_name in password_params:
        if param_name in masked_values and masked_values[param_name]:
            masked_values[param_name] = '***'

    return masked_values
