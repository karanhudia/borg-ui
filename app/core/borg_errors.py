"""
Borg error code and message ID mappings

This module provides user-friendly error messages for Borg's error codes
and message IDs from the JSON API output.

Reference: https://borgbackup.readthedocs.io/en/stable/usage/general.html#return-codes
"""

import re as _re
from typing import Any

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

# "Repository already exists", the one repo-create failure that is not a
# failure for us: the caller is adding a repository that is already there.
# Only the modern code counts. Under the legacy codes every error is 2, so
# matching that would swallow every failed repo-create, and the old `== 2`
# check did exactly that while never matching a real already-exists, since
# Borg 2 has always answered 10.
REPOSITORY_EXISTS_EXIT_CODE = 10

# Both shipped versions raise Repository.AlreadyExists with the same text,
# verified against borg 1.4.5 and 2.0.0b25: "A repository already exists at
# {}." Matched whole, one line at a time: borg prints other diagnostics
# around it, and a bare "repository already exists" substring would also
# accept an unrelated failure. Getting this wrong in the permissive
# direction records a repository that was never created, so a reworded
# future borg failing this match (a visible error on an existing
# repository) is the better way to be wrong.
_REPOSITORY_EXISTS_LINE = _re.compile(r"a repository already exists at .+\.", _re.I)


class RestoreRefused(Exception):
    """A restore the repository's Borg will not run as asked. `detail` is
    the translatable reason, shaped like an HTTP error detail."""

    def __init__(self, detail: dict):
        super().__init__(detail.get("key", "restore refused"))
        self.detail = detail


_CRASH_WRAPPERS = ("Local Exception", "Remote Exception")
_TRACEBACK_HEADER = "Traceback (most recent call last):"


def lead_with_cause(diagnostic: str, *, lock_contention: bool = False) -> str:
    """Put a Borg crash's cause on the first line.

    A crash is Borg's wrapper ("Local Exception") and a traceback, sometimes
    after interpreter noise ("Exception ignored in: <function
    Repository.__del__ ...>" and a traceback of its own), so a message cut to
    its first lines named no cause, or the wrong one. The cause is read from
    Borg's own traceback; the full diagnostic still follows it.
    """
    lines = [line.strip() for line in diagnostic.splitlines()]
    start = next((i for i, line in enumerate(lines) if line in _CRASH_WRAPPERS), None)
    if start is None:
        if not lines or lines[0] != _TRACEBACK_HEADER:
            return diagnostic
        start = 0
    from app.services.repository_executor import _tail_reason_line

    cause = _tail_reason_line(
        "\n".join(diagnostic.splitlines()[start:]), lock_contention=lock_contention
    )
    return f"{cause}\n{diagnostic}" if cause else diagnostic


def bounded_operation_diagnostic(reason: str) -> str:
    """Redact before bounding so a truncated secret cannot escape masking."""
    from app.utils.redaction import redact_secrets

    diagnostic = lead_with_cause(redact_secrets(str(reason)).strip())
    if len(diagnostic) > 2000:
        marker = "\n... [truncated] ...\n"
        diagnostic = diagnostic[:400] + marker + diagnostic[-(1600 - len(marker)) :]
    return diagnostic


# Borg missing on the remote end of an SSH repository: "sh: borg: command not
# found" (bash), "sh: 1: borg: not found" (dash), or a configured remote path.
_REMOTE_BORG_MISSING = _re.compile(r"\bborg[\w./-]*: (?:command )?not found")


def repository_failure_status(result: dict) -> int:
    """Classify evidenced refusals only; unknown Borg failures remain 500."""
    reason = "\n".join(
        str(result.get(key) or "") for key in ("error", "stderr")
    ).lower()
    # 422, not 403: the frontend reads 403 as a role refusal and toasts so.
    if (
        result.get("return_code") in (21, 42, 44)
        # A keyfile repository whose key is not where Borg looks, or a
        # directory where Borg expects key files (dashboard a4b2fad0603467e8,
        # ed36651bb055713a).
        or "no key file for repository" in reason
        or ("isadirectoryerror" in reason and "/keys/" in reason)
        # The SSH host has no Borg (dashboard 859daa3dfb3863ec).
        or _REMOTE_BORG_MISSING.search(reason)
        or "permission denied" in reason
        # A read-only mount is the host's configuration, not a Borg UI fault.
        or "[errno 30] read-only file system" in reason
        # Borg crashed decoding the repository's `config`: the path holds a
        # file of that name that is not a Borg config, so it is not a
        # repository (dashboard f60df0963ec9494f).
        or ("unicodedecodeerror" in reason and "borg/repository.py" in reason)
    ):
        return 422
    if (
        result.get("return_code") in (19, REPOSITORY_EXISTS_EXIT_CODE)
        # Init where a repository already is, e.g. a repository whose path
        # was edited (dashboard 2bf3c31b30712233).
        or any(
            _REPOSITORY_EXISTS_LINE.fullmatch(line.strip())
            for line in reason.splitlines()
        )
        or "fileexistserror: [errno 17]" in reason
        # Borg 1's legacy exit code 2 cannot distinguish an occupied target.
        # This exact message is emitted by PathAlreadyExists (borg 1.4.3).
        or any(
            _re.fullmatch(r"there is already something at .+\.", line.strip())
            for line in reason.splitlines()
        )
    ):
        return 409
    return 500


class ArchiveListingError(Exception):
    """An expected Borg listing failure with bounded, secret-free diagnostics."""

    def __init__(self, result: dict | None):
        from app.utils.redaction import redact_secrets

        result = result or {}
        message = "listing archives failed"
        if result.get("return_code") is not None:
            message += f" (exit code {result['return_code']})"
        reason = result.get("stderr") or result.get("error")
        # Classify before bounding the diagnostic: Borg 2 can use 73 when
        # another process killed our own lock, which must remain terminal.
        self.is_lock_contention = is_lock_contention_exit_code(
            result.get("return_code")
        ) and "Our lock was killed by another borg" not in str(reason or "")
        if reason:
            # Redact before truncation: cutting a quoted secret first could
            # leave part of its value outside the redactor's match.
            diagnostic = redact_secrets(str(reason)).strip()
            diagnostic = lead_with_cause(
                diagnostic, lock_contention=self.is_lock_contention
            )
            if len(diagnostic) > 2000:
                # The last exception follows the frames; keeping only the
                # start can turn a useful error into an unexplained traceback.
                marker = "\n... [truncated] ...\n"
                diagnostic = (
                    diagnostic[:400] + marker + diagnostic[-(1600 - len(marker)) :]
                )
            message += f": {diagnostic}"
        super().__init__(message)


def is_repository_exists_failure(result: dict) -> bool:
    """Whether a failed repository create failed only because the repository
    was already there, the one outcome a caller may treat as success.

    The modern codes say so outright. Under the legacy codes, which an
    operator can still pin with BORG_EXIT_CODES, every error collapses into
    2, so the code cannot separate this from a generic failure and borg's
    own wording has to.
    """
    return_code = result.get("return_code")
    if return_code == REPOSITORY_EXISTS_EXIT_CODE:
        return True
    if return_code != 2:
        return False
    return any(
        _REPOSITORY_EXISTS_LINE.fullmatch(line.strip())
        for line in (result.get("stderr") or "").splitlines()
    )


# Message ID to user-friendly error messages
# These come from Borg's JSON log output
BORG_MESSAGE_IDS = {
    # Repository errors
    "Repository.DoesNotExist": {
        "message": "Repository does not exist at the specified path",
        "suggestion": "Please check the repository path and ensure it has been initialized with 'borg init'",
        "severity": "error",
    },
    "Repository.AlreadyExists": {
        "message": "Repository already exists at this location",
        "suggestion": "Use a different path or delete the existing repository first",
        "severity": "error",
    },
    "Repository.InvalidRepository": {
        "message": "Not a valid BorgBackup repository",
        "suggestion": "Check that the path points to a valid Borg repository",
        "severity": "error",
    },
    "Repository.CheckNeeded": {
        "message": "Repository check needed before operations can continue",
        "suggestion": "Run 'borg check' to verify and repair the repository",
        "severity": "warning",
    },
    "Repository.ObjectNotFound": {
        "message": "Repository object not found",
        "suggestion": "The repository may be corrupted. Run 'borg check'",
        "severity": "error",
    },
    # Lock errors
    "LockTimeout": {
        "message": "Could not acquire repository lock - the repository is locked by another process or has a stale lock",
        "suggestion": "If no backup is currently running, this is likely a stale lock from a crashed backup. Use the 'Break Lock' button to remove it safely.",
        "severity": "error",
        "is_lock_error": True,
    },
    "LockError": {
        "message": "Repository locking error",
        "suggestion": "Check if another process is using the repository. If not, use the 'Break Lock' button to remove the stale lock.",
        "severity": "error",
        "is_lock_error": True,
    },
    # Authentication/Passphrase errors
    "PassphraseWrong": {
        "message": "Incorrect repository passphrase",
        "suggestion": "Check your passphrase and try again",
        "severity": "error",
    },
    "PasscommandFailed": {
        "message": "Passphrase command failed",
        "suggestion": "Check your passphrase command configuration",
        "severity": "error",
    },
    # Archive errors
    "Archive.DoesNotExist": {
        "message": "Archive does not exist",
        "suggestion": "Check the archive name and try again",
        "severity": "error",
    },
    "Archive.AlreadyExists": {
        "message": "Archive with this name already exists",
        "suggestion": "Use a different archive name or delete the existing archive",
        "severity": "error",
    },
    # Storage/Quota errors
    "NotEnoughSpace": {
        "message": "Not enough disk space",
        "suggestion": "Free up disk space on the repository storage device",
        "severity": "error",
    },
    "QuotaExceeded": {
        "message": "Storage quota exceeded",
        "suggestion": "Delete old archives or increase storage quota",
        "severity": "error",
    },
    # SSH/Remote errors
    "Connection.FailedToConnect": {
        "message": "Failed to connect to remote repository",
        "suggestion": "Check your SSH configuration, hostname, and credentials",
        "severity": "error",
    },
    "Connection.ConnectionClosed": {
        "message": "Connection to remote repository was closed",
        "suggestion": "Check network connection and SSH server status",
        "severity": "error",
    },
    # File access errors
    "FileNotFound": {
        "message": "Source file or directory not found",
        "suggestion": "Check that the source path exists and is accessible",
        "severity": "warning",
    },
    "PermissionDenied": {
        "message": "Permission denied accessing file",
        "suggestion": "Check file permissions or run with appropriate privileges",
        "severity": "warning",
    },
    # Integrity errors
    "IntegrityError": {
        "message": "Repository integrity error detected",
        "suggestion": "Run 'borg check' to verify and repair the repository",
        "severity": "error",
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
        "severity": "error",
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


def is_borg_warning_exit_code(exit_code) -> bool:
    """Borg's warning exit codes: legacy rc 1, modern range 100-127.

    Warnings mean the operation ran to completion but something was worth
    telling the operator (a file changed mid-read, a path was missing).
    They are not failures; jobs record them as completed_with_warnings.
    """
    return (
        isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and (exit_code == 1 or 100 <= exit_code <= 127)
    )


# Borg's modern exit codes for a lock another process holds: LockTimeout
# (73), and LockError / LockErrorT (70, 71) for a lock that could not be
# taken. Not LockFailed (72), the lock file could not be created (a
# read-only or foreign-owned repository), nor NotLocked / NotMyLock (74,
# 75), about a lock that is not there: waiting changes neither.
LOCK_CONTENTION_EXIT_CODES = (70, 71, 73)

# The key a waiter's failure detail carries when the agent's Borg run ended
# on such a lock, for the operations runner: the repository is taken for
# now, and the operation is deferred like one the admission refused.
LOCK_CONTENTION_DETAIL_KEY = "lock_contention"


def is_lock_contention_exit_code(exit_code: Any) -> bool:
    return (
        isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and exit_code in LOCK_CONTENTION_EXIT_CODES
    )


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
    if msgid in [
        "LockError",
        "LockErrorT",
        "LockFailed",
        "LockTimeout",
        "NotLocked",
        "NotMyLock",
    ]:
        return True

    return False


import json as _json

# Maps Borg message IDs to backend.errors.borg locale keys
_MSGID_TO_LOCALE_KEY = {
    "Repository.DoesNotExist": "repositoryDoesNotExist",
    "Repository.AlreadyExists": "repositoryAlreadyExists",
    "Repository.InvalidRepository": "notValidBorgRepository",
    "Repository.CheckNeeded": "repositoryCheckNeeded",
    "LockTimeout": "lockTimeout",
    "LockErrorT": "lockTimeout",
    "LockFailed": "lockTimeout",
    "LockError": "lockError",
    "NotLocked": "lockError",
    "NotMyLock": "lockError",
    "PassphraseWrong": "passphraseWrong",
    "PasscommandFailed": "passphraseWrong",
    "Archive.DoesNotExist": "archiveDoesNotExist",
    "Archive.AlreadyExists": "archiveAlreadyExists",
}

# The same locale keys, reached by exit code, for the failures that arrive
# without a message id (no --log-json, or a wrapper that swallowed it). Only
# the modern codes carry this much: the legacy set collapses every error into
# 2, which is why this map is worth having only now that every borg we run is
# asked for the modern codes. Codes with no key of their own fall through to
# the generic "exit code N" below rather than inventing an untranslated
# string.
_EXIT_CODE_TO_LOCALE_KEY = {
    10: "repositoryAlreadyExists",
    12: "repositoryCheckNeeded",
    13: "repositoryDoesNotExist",
    15: "notValidBorgRepository",
    16: "notValidBorgRepository",
    30: "archiveAlreadyExists",
    31: "archiveDoesNotExist",
    70: "lockError",
    71: "lockError",
    72: "lockError",
    73: "lockTimeout",
    74: "lockError",
    75: "lockError",
}


def format_error_message(
    msgid: str = None, original_message: str = None, exit_code: int = None
) -> str:
    """
    Format a JSON-encoded locale key string for a Borg error.

    Returns a json.dumps({"key": "backend.errors.borg.X", ...}) string
    that can be stored in error_message and rendered by translateBackendKey.

    Args:
        msgid: Borg message ID
        original_message: Original error message from Borg (unused — borg output is out of scope)
        exit_code: Process exit code

    Returns:
        JSON-encoded locale key string
    """
    if msgid and msgid in _MSGID_TO_LOCALE_KEY:
        return _json.dumps(
            {"key": f"backend.errors.borg.{_MSGID_TO_LOCALE_KEY[msgid]}"}
        )

    if exit_code in _EXIT_CODE_TO_LOCALE_KEY:
        return _json.dumps(
            {"key": f"backend.errors.borg.{_EXIT_CODE_TO_LOCALE_KEY[exit_code]}"}
        )

    if exit_code is not None:
        return _json.dumps(
            {
                "key": "backend.errors.borg.exitCodeError",
                "params": {"exitCode": exit_code},
            }
        )

    return _json.dumps({"key": "backend.errors.borg.unknownError"})
