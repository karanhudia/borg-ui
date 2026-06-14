"""Shared OpenSSH option builders for noninteractive key-based commands."""

from __future__ import annotations


PUBLIC_KEY_ONLY_OPTIONS = (
    "BatchMode=yes",
    "PreferredAuthentications=publickey",
    "PasswordAuthentication=no",
    "NumberOfPasswordPrompts=0",
)


def ssh_option_args(options: list[str] | tuple[str, ...]) -> list[str]:
    """Return OpenSSH CLI arguments for a sequence of -o option values."""
    args: list[str] = []
    for option in options:
        args.extend(["-o", option])
    return args


def public_key_only_ssh_args(*, identities_only: bool = False) -> list[str]:
    """Return OpenSSH args that prevent password fallback in batch commands."""
    options: list[str] = []
    if identities_only:
        options.append("IdentitiesOnly=yes")
    options.extend(PUBLIC_KEY_ONLY_OPTIONS)
    return ssh_option_args(options)


def ssh_key_auth_args(key_file: str) -> list[str]:
    """Return OpenSSH args for a specific identity file with no password fallback."""
    return ["-i", key_file, *public_key_only_ssh_args(identities_only=True)]


def sshfs_key_auth_options(key_file: str) -> list[str]:
    """Return sshfs -o options for a specific identity with no password fallback."""
    return ssh_option_args(
        (
            f"IdentityFile={key_file}",
            "IdentitiesOnly=yes",
            *PUBLIC_KEY_ONLY_OPTIONS,
        )
    )
