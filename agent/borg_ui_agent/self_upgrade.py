"""Whether this endpoint can reinstall itself when the server asks.

One predicate answers this, and both the capability report and the
`agent.upgrade` handler call it. A partial or half-removed install can leave
any one piece behind without the others, and each missing piece would otherwise
fail at a different point, after the operator has already been told the
endpoint can upgrade itself.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

UPGRADE_UNIT_NAME = "borg-ui-agent-upgrade.service"
UPGRADE_PATH_UNIT_NAME = "borg-ui-agent-upgrade.path"
DEFAULT_TRIGGER_PATH = Path("/etc/borg-ui-agent/upgrade-requested")
# Outside /etc/borg-ui-agent on purpose: that directory belongs to the service
# user, and root sources this file.
DEFAULT_CONF_PATH = Path("/etc/borg-ui-agent-upgrade.conf")
DEFAULT_UNIT_PATH = Path("/etc/systemd/system") / UPGRADE_UNIT_NAME
DEFAULT_PATH_UNIT_PATH = Path("/etc/systemd/system") / UPGRADE_PATH_UNIT_NAME
REQUIRED_CONF_KEYS = (
    "SERVER",
    "AGENT_ID",
    "BORG_INSTALL_MODE",
    "SERVICE_USER",
    "AGENT_ROOT",
)

_CONF_LINE = re.compile(r'^\s*([A-Z_]+)\s*=\s*"(.*)"\s*$')


@dataclass(frozen=True)
class UpgradeReadiness:
    supported: bool
    reason: str = ""
    trigger: Optional[Path] = None


def _parse_conf(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _CONF_LINE.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _exec_start(unit_path: Path) -> Optional[Path]:
    for line in unit_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ExecStart="):
            command = line.split("=", 1)[1].strip()
            return Path(command.split()[0]) if command else None
    return None


def check_self_upgrade(
    *,
    conf_path: Path = DEFAULT_CONF_PATH,
    unit_path: Path = DEFAULT_UNIT_PATH,
    path_unit_path: Path = DEFAULT_PATH_UNIT_PATH,
    trigger_path: Path = DEFAULT_TRIGGER_PATH,
) -> UpgradeReadiness:
    if not unit_path.is_file():
        return UpgradeReadiness(supported=False, reason="unit_missing")

    helper = _exec_start(unit_path)
    if helper is None or not helper.is_file() or not os.access(helper, os.X_OK):
        return UpgradeReadiness(supported=False, reason="helper_missing")

    if not conf_path.is_file():
        return UpgradeReadiness(supported=False, reason="conf_missing")

    conf = _parse_conf(conf_path)
    if any(not conf.get(key) for key in REQUIRED_CONF_KEYS):
        return UpgradeReadiness(supported=False, reason="conf_missing")

    # The helper refuses a non-https server, so an endpoint enrolled over http
    # would be told it can upgrade and then abort as soon as it was asked to.
    if not conf["SERVER"].startswith("https://"):
        return UpgradeReadiness(supported=False, reason="server_not_https")

    # Nothing starts the helper without the path unit watching for the trigger.
    if not path_unit_path.is_file():
        return UpgradeReadiness(supported=False, reason="path_unit_missing")

    # And an agent that cannot create the trigger cannot ask. This is the whole
    # escalation, so it is also the whole check: no sudo, which the agent unit's
    # NoNewPrivileges=true would refuse anyway.
    if not os.access(trigger_path.parent, os.W_OK | os.X_OK):
        return UpgradeReadiness(supported=False, reason="trigger_not_writable")

    return UpgradeReadiness(supported=True, trigger=trigger_path)


def can_self_upgrade() -> bool:
    try:
        return check_self_upgrade().supported
    except OSError:
        # An unreadable /etc or a vanished file means the endpoint cannot
        # upgrade itself. It must not mean the agent stops reporting at all.
        return False
