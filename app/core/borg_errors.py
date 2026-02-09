"""
Borg error code and message ID mappings

This module provides user-friendly error messages for Borg's error codes
and message IDs from the JSON API output.

Reference: https://borgbackup.readthedocs.io/en/stable/usage/general.html#return-codes
"""

# Exit code mappings (modern exit codes)
# Source: https://borgbackup.readthedocs.io/en/stable/internals/frontends.html#message-ids
BORG_EXIT_CODES = {
    # Success
    0: "Success",

    # Legacy codes
    1: "Warning (legacy)",
    2: "Error (legacy)",

    # Runtime errors (3-6)
    3: "Cancelled by user",
    4: "Command error",
    5: "Formatting error",
    6: "Invalid placeholder",

    # Repository errors (10-21)
    10: "Repository already exists",
    11: "Attic repository detected",
    12: "Repository check needed",
    13: "Repository does not exist",
    14: "Insufficient free space",
    15: "Invalid repository",
    16: "Invalid repository config",
    17: "Object not found in repository",
    18: "Parent path does not exist",
    19: "Path already exists",
    20: "Storage quota exceeded",
    21: "Permission denied",

    # Feature/Manifest errors (25-27)
    25: "Unsupported repository feature",
    26: "Repository has no manifest",
    27: "Unsupported manifest envelope",

    # Archive errors (30-32)
    30: "Archive already exists",
    31: "Archive does not exist",
    32: "Filesystem encoding error",

    # Key errors (40-48)
    40: "Invalid key data",
    41: "Key file mismatch",
    42: "Key file not found",
    43: "Not a Borg key backup",
    44: "Repository key not found",
    45: "Repository ID mismatch",
    46: "Key management not available for unencrypted repos",
    47: "Unknown key type",
    48: "Unsupported payload type",

    # Passphrase errors (50-53)
    50: "Cannot acquire passphrase",
    51: "Passcommand failed",
    52: "Passphrase incorrect",
    53: "Password retries exceeded",

    # Cache errors (60-64)
    60: "Cache initialization aborted",
    61: "Encryption method mismatch",
    62: "Repository access aborted",
    63: "Repository ID not unique",
    64: "Cache replay attack detected",

    # Lock errors (70-75) ⚠️ IMPORTANT
    70: "Failed to acquire the lock",
    71: "Failed to acquire the lock (with traceback)",
    72: "Failed to create/acquire the lock",
    73: "Failed to create/acquire the lock (timeout)",
    74: "Failed to release the lock (was not locked)",
    75: "Failed to release the lock (not by me)",

    # Connection/RPC errors (80-87)
    80: "Connection closed by remote host",
    81: "Connection closed with hint",
    82: "Invalid RPC method",
    83: "Path not allowed",
    84: "Remote Borg server outdated",
    85: "Unexpected RPC data format from client",
    86: "Unexpected RPC data format from server",
    87: "Connection broken",

    # Integrity errors (90-99)
    90: "Data integrity error",
    91: "File integrity error",
    92: "Decompression error",
    95: "Archive TAM invalid",
    96: "Archive authentication required",
    97: "Manifest TAM invalid",
    98: "Manifest authentication required",
    99: "Unsupported authentication suite",

    # Warnings (100-107)
    100: "Warning: File changed during backup",
    101: "Warning: Include pattern never matched",
    102: "Warning: Backup error",
    103: "Warning: Backup race condition",
    104: "Warning: Backup OS error",
    105: "Warning: Backup permission error",
    106: "Warning: Backup IO error",
    107: "Warning: Backup file not found",
}

# Message ID to user-friendly error messages
# These come from Borg's JSON log output
BORG_MESSAGE_IDS = {
    # Repository errors
    "Repository.DoesNotExist": {
        "message": "Repository does not exist at the specified path",
        "suggestion": "Please check the repository path and ensure it has been initialized with 'borg init'",
        "severity": "error"
    },
    "Repository.AlreadyExists": {
        "message": "Repository already exists at this location",
        "suggestion": "Use a different path or delete the existing repository first",
        "severity": "error"
    },
    "Repository.InvalidRepository": {
        "message": "Not a valid BorgBackup repository",
        "suggestion": "Check that the path points to a valid Borg repository",
        "severity": "error"
    },
    "Repository.CheckNeeded": {
        "message": "Repository check needed before operations can continue",
        "suggestion": "Run 'borg check' to verify and repair the repository",
        "severity": "warning"
    },
    "Repository.ObjectNotFound": {
        "message": "Repository object not found",
        "suggestion": "The repository may be corrupted. Run 'borg check'",
        "severity": "error"
    },

    # Lock errors
    "LockTimeout": {
        "message": "Could not acquire repository lock - the repository is locked by another process or has a stale lock",
        "suggestion": "If no backup is currently running, this is likely a stale lock from a crashed backup. Use the 'Break Lock' button to remove it safely.",
        "severity": "error",
        "is_lock_error": True
    },
    "LockError": {
        "message": "Repository locking error",
        "suggestion": "Check if another process is using the repository. If not, use the 'Break Lock' button to remove the stale lock.",
        "severity": "error",
        "is_lock_error": True
    },

    # Authentication/Passphrase errors
    "PassphraseWrong": {
        "message": "Incorrect repository passphrase",
        "suggestion": "Check your passphrase and try again",
        "severity": "error"
    },
    "PasscommandFailed": {
        "message": "Passphrase command failed",
        "suggestion": "Check your passphrase command configuration",
        "severity": "error"
    },

    # Archive errors
    "Archive.DoesNotExist": {
        "message": "Archive does not exist",
        "suggestion": "Check the archive name and try again",
        "severity": "error"
    },
    "Archive.AlreadyExists": {
        "message": "Archive with this name already exists",
        "suggestion": "Use a different archive name or delete the existing archive",
        "severity": "error"
    },

    # Storage/Quota errors
    "NotEnoughSpace": {
        "message": "Not enough disk space",
        "suggestion": "Free up disk space on the repository storage device",
        "severity": "error"
    },
    "QuotaExceeded": {
        "message": "Storage quota exceeded",
        "suggestion": "Delete old archives or increase storage quota",
        "severity": "error"
    },

    # SSH/Remote errors
    "Connection.FailedToConnect": {
        "message": "Failed to connect to remote repository",
        "suggestion": "Check your SSH configuration, hostname, and credentials",
        "severity": "error"
    },
    "Connection.ConnectionClosed": {
        "message": "Connection to remote repository was closed",
        "suggestion": "Check network connection and SSH server status",
        "severity": "error"
    },

    # File access errors
    "FileNotFound": {
        "message": "Source file or directory not found",
        "suggestion": "Check that the source path exists and is accessible",
        "severity": "warning"
    },
    "PermissionDenied": {
        "message": "Permission denied accessing file",
        "suggestion": "Check file permissions or run with appropriate privileges",
        "severity": "warning"
    },

    # Integrity errors
    "IntegrityError": {
        "message": "Repository integrity error detected",
        "suggestion": "Run 'borg check' to verify and repair the repository",
        "severity": "error"
    },
}


def get_error_details(msgid: str, default_message: str = None):
    """
    Get detailed error information for a Borg message ID

    Args:
        msgid: The Borg message ID (e.g., "Repository.DoesNotExist")
        default_message: Fallback message if msgid is not recognized

    Returns:
        dict with message, suggestion, and severity
    """
    if msgid in BORG_MESSAGE_IDS:
        return BORG_MESSAGE_IDS[msgid]

    return {
        "message": default_message or f"Borg error: {msgid}",
        "suggestion": "Check the Borg documentation for more details",
        "severity": "error"
    }


def get_exit_code_message(exit_code: int) -> str:
    """
    Get a human-readable message for a Borg exit code

    Args:
        exit_code: The Borg process exit code

    Returns:
        Human-readable error message
    """
    if exit_code in BORG_EXIT_CODES:
        return BORG_EXIT_CODES[exit_code]
    elif 3 <= exit_code <= 99:
        return f"Error (exit code {exit_code})"
    elif 100 <= exit_code <= 127:
        return f"Warning (exit code {exit_code})"
    else:
        return f"Unknown error (exit code {exit_code})"


def is_lock_error(exit_code: int = None, msgid: str = None) -> bool:
    """
    Check if an error is a lock-related error

    Uses ONLY exit code and msgid - no fuzzy text matching to avoid false positives.

    Args:
        exit_code: Borg process exit code (70-75 are lock errors)
        msgid: Borg message ID (LockError, LockTimeout, etc.)

    Returns:
        True if this is a lock error, False otherwise
    """
    # Primary: Check exit code (70-75 are all lock-related)
    # This is the most reliable and definitive method
    if exit_code is not None and 70 <= exit_code <= 75:
        return True

    # Secondary: Check message ID (for operations using --log-json)
    if msgid in ['LockError', 'LockErrorT', 'LockFailed', 'LockTimeout', 'NotLocked', 'NotMyLock']:
        return True

    return False


def format_error_message(msgid: str = None, original_message: str = None, exit_code: int = None) -> str:
    """
    Format a comprehensive error message with msgid details and suggestions

    Args:
        msgid: Borg message ID
        original_message: Original error message from Borg
        exit_code: Process exit code

    Returns:
        Formatted error message with details and suggestions
    """
    parts = []

    if exit_code is not None:
        parts.append(f"[Exit Code {exit_code}] {get_exit_code_message(exit_code)}")

    if msgid:
        details = get_error_details(msgid, original_message)
        parts.append(f"\n{details['message']}")
        parts.append(f"\n💡 Suggestion: {details['suggestion']}")
    elif original_message:
        parts.append(f"\n{original_message}")

    return "\n".join(parts) if parts else "Unknown error occurred"
