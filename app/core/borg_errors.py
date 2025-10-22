"""
Borg error code and message ID mappings

This module provides user-friendly error messages for Borg's error codes
and message IDs from the JSON API output.

Reference: https://borgbackup.readthedocs.io/en/stable/usage/general.html#return-codes
"""

# Exit code mappings (modern exit codes)
BORG_EXIT_CODES = {
    0: "Success",
    1: "Warning (legacy)",
    2: "Error (legacy)",
    # Modern exit codes (3-99 are errors)
    13: "Repository does not exist",
    14: "Repository already exists",
    15: "Repository is locked",
    17: "Repository incompatible with this version",
    # 100-127 are warnings in modern mode
    100: "Warning: Some files changed during backup",
    101: "Warning: Minor issues encountered",
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
