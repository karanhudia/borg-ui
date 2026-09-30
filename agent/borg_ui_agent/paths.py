"""Where the agent keeps its files, per platform.

Linux keeps the installer-managed root and the configuration apart, because
they belong to different owners there. macOS runs the agent as the user whose
data it backs up, so both live in that user's Application Support directory.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

LINUX_AGENT_ROOT = Path("/opt/borg-ui-agent")


def system() -> str:
    return platform.system().lower()


def is_darwin() -> bool:
    return system() == "darwin"


def default_agent_root() -> Path:
    """The root the installer manages: binaries, the virtualenv, forwarders."""
    if is_darwin():
        return Path.home() / "Library" / "Application Support" / "borg-ui-agent"
    return LINUX_AGENT_ROOT


def default_config_dir() -> Path:
    """The directory of config.toml and of what sits beside it."""
    name = system()
    if name == "darwin":
        return default_agent_root()
    if name == "windows":
        root = os.environ.get("ProgramData", r"C:\ProgramData")
        return Path(root) / "borg-ui-agent"
    return Path.home() / ".config" / "borg-ui-agent"
