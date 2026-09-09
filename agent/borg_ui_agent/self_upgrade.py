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
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

UPGRADE_UNIT_NAME = "borg-ui-agent-upgrade.service"
DEFAULT_ETC_DIR = Path("/etc/borg-ui-agent")
DEFAULT_UNIT_PATH = Path("/etc/systemd/system") / UPGRADE_UNIT_NAME
REQUIRED_CONF_KEYS = ("SERVER", "AGENT_ID", "SYSTEMCTL")

_CONF_LINE = re.compile(r'^\s*([A-Z_]+)\s*=\s*"(.*)"\s*$')


@dataclass(frozen=True)
class UpgradeReadiness:
    supported: bool
    reason: str = ""
    systemctl: str = ""
    needs_sudo: bool = True


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


def _sudo_lists_upgrade_command(systemctl: str) -> bool:
    """Whether sudo would let this user start the upgrade unit without a password.

    `sudo -l` on the exact command, so the answer covers the whole argv the
    handler will run rather than only the binary.
    """
    sudo = shutil.which("sudo")
    if sudo is None:
        return False
    result = subprocess.run(
        [sudo, "-n", "-l", systemctl, "start", "--no-block", UPGRADE_UNIT_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def check_self_upgrade(
    *,
    etc_dir: Path = DEFAULT_ETC_DIR,
    unit_path: Path = DEFAULT_UNIT_PATH,
    is_root: Callable[[], bool] = lambda: os.geteuid() == 0,
    sudo_lists: Callable[[str], bool] = _sudo_lists_upgrade_command,
) -> UpgradeReadiness:
    if not unit_path.is_file():
        return UpgradeReadiness(supported=False, reason="unit_missing")

    helper = _exec_start(unit_path)
    if helper is None or not helper.is_file() or not os.access(helper, os.X_OK):
        return UpgradeReadiness(supported=False, reason="helper_missing")

    conf_path = etc_dir / "upgrade.conf"
    if not conf_path.is_file():
        return UpgradeReadiness(supported=False, reason="conf_missing")

    conf = _parse_conf(conf_path)
    if any(not conf.get(key) for key in REQUIRED_CONF_KEYS):
        return UpgradeReadiness(supported=False, reason="conf_missing")

    # The helper refuses a non-https server, so an endpoint enrolled over http
    # would be told it can upgrade and then abort as soon as it was asked to.
    if not conf["SERVER"].startswith("https://"):
        return UpgradeReadiness(supported=False, reason="server_not_https")

    systemctl = conf["SYSTEMCTL"]

    # A root agent starts the unit itself. The installer writes no sudoers file
    # for it and does not install sudo, so asking sudo here would report no
    # capability on exactly the endpoints that need no escalation.
    if is_root():
        return UpgradeReadiness(supported=True, systemctl=systemctl, needs_sudo=False)

    if not sudo_lists(systemctl):
        return UpgradeReadiness(supported=False, reason="sudo_not_permitted")

    return UpgradeReadiness(supported=True, systemctl=systemctl, needs_sudo=True)


def can_self_upgrade() -> bool:
    try:
        return check_self_upgrade().supported
    except OSError:
        # An unreadable /etc or a vanished file means the endpoint cannot
        # upgrade itself. It must not mean the agent stops reporting at all.
        return False
