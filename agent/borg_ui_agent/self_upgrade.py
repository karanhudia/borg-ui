"""Whether this endpoint can reinstall itself when the server asks.

One predicate answers this, and both the capability report and the
`agent.upgrade` handler call it. A partial or half-removed install can leave
any one piece behind without the others, and each missing piece would otherwise
fail at a different point, after the operator has already been told the
endpoint can upgrade itself.

On Linux the pieces are a root-owned conf, a oneshot unit naming the helper
and a path unit watching the trigger. On macOS they are the per-user conf and
one launchd job that both names the helper and watches the trigger.

The conf also has to name the server this endpoint is enrolled against. The
helper refuses when the two differ, which is what `set-server` leaves behind
when it runs without the rights to rewrite the conf.
"""

from __future__ import annotations

import os
import plistlib
import re
import stat
import tempfile
from xml.parsers.expat import ExpatError
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.borg_ui_agent.paths import default_agent_root, is_darwin

UPGRADE_UNIT_NAME = "borg-ui-agent-upgrade.service"
UPGRADE_PATH_UNIT_NAME = "borg-ui-agent-upgrade.path"
UPGRADE_JOB_LABEL = "com.borg-ui.agent-upgrade"
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
# The helper's own expression for the config's server, so that the two cannot
# disagree about a line one of them reads and the other does not.
_SERVER_URL_LINE = re.compile(r'^server_url\s*=\s*"(.*)"\s*$', re.ASCII)
# The installer's own test for a server it writes into the record, and the
# line it writes it on.
_PLAIN_SERVER = re.compile(r"https?://[A-Za-z0-9._:/-]+", re.ASCII)
_RECORD_SERVER_LINE = re.compile(r'^SERVER=".*"$', re.MULTILINE)


@dataclass(frozen=True)
class UpgradeReadiness:
    supported: bool
    reason: str = ""
    trigger: Optional[Path] = None


@dataclass(frozen=True)
class UpgradePaths:
    conf_path: Path
    unit_path: Path
    path_unit_path: Path
    trigger_path: Path


def default_upgrade_paths() -> UpgradePaths:
    if is_darwin():
        root = default_agent_root()
        job = Path.home() / "Library" / "LaunchAgents" / f"{UPGRADE_JOB_LABEL}.plist"
        # The one job carries both the helper and the watch condition.
        return UpgradePaths(
            conf_path=root / "upgrade.conf",
            unit_path=job,
            path_unit_path=job,
            trigger_path=root / "upgrade-requested",
        )
    return UpgradePaths(
        conf_path=DEFAULT_CONF_PATH,
        unit_path=DEFAULT_UNIT_PATH,
        path_unit_path=DEFAULT_PATH_UNIT_PATH,
        trigger_path=DEFAULT_TRIGGER_PATH,
    )


def _parse_conf(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _CONF_LINE.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def recorded_server(conf_path: Optional[Path] = None) -> str:
    """The server the upgrade record names, or nothing without a record."""
    conf_path = conf_path or default_upgrade_paths().conf_path
    if not conf_path.is_file():
        return ""
    return _parse_conf(conf_path).get("SERVER", "")


def move_recorded_server(server_url: str, conf_path: Optional[Path] = None) -> bool:
    """Point the upgrade record at `server_url`, if this process may write it.

    Root sources the record, so it takes only an address the installer would
    write itself, and the rewritten file keeps the owner and mode it had. False
    leaves the record as it was: no record, no SERVER line, another address,
    or no rights to replace it (the agent's own user on Linux).
    """
    conf_path = conf_path or default_upgrade_paths().conf_path
    if not _PLAIN_SERVER.fullmatch(server_url):
        return False
    tmp_path: Optional[Path] = None
    try:
        original = conf_path.stat()
        text, count = _RECORD_SERVER_LINE.subn(
            lambda _: f'SERVER="{server_url}"', conf_path.read_text(encoding="utf-8")
        )
        if not count:
            return False
        fd, name = tempfile.mkstemp(dir=conf_path.parent, prefix=f".{conf_path.name}.")
        tmp_path = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chown(tmp_path, original.st_uid, original.st_gid)
        os.chmod(tmp_path, stat.S_IMODE(original.st_mode))
        os.replace(tmp_path, conf_path)
    except (OSError, ValueError):
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        return False
    return True


def _enrolled_server(config_path: Path) -> str:
    """The server in the agent's config, as the helper reads it.

    The helper takes the first line of that form and reads a config without
    one, or one it cannot open, as no server at all. It then refuses, so none
    of that is an error here either.
    """
    try:
        lines = config_path.read_text(encoding="utf-8").split("\n")
    except (OSError, ValueError):
        return ""
    for line in lines:
        match = _SERVER_URL_LINE.match(line)
        if match:
            return match.group(1)
    return ""


def _read_plist(path: Path) -> dict:
    """The job's definition, or nothing for a file launchd could not load either."""
    try:
        with path.open("rb") as handle:
            loaded = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException, ExpatError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _exec_start(unit_path: Path) -> Optional[Path]:
    if unit_path.suffix == ".plist":
        arguments = _read_plist(unit_path).get("ProgramArguments")
        if isinstance(arguments, list) and arguments and arguments[0]:
            return Path(str(arguments[0]))
        return None
    for line in unit_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ExecStart="):
            command = line.split("=", 1)[1].strip()
            return Path(command.split()[0]) if command else None
    return None


def _watches_trigger(path_unit_path: Path, trigger_path: Path) -> bool:
    """Whether the watcher exists and is armed on this trigger.

    A systemd path unit's presence is the whole check, as the installer writes
    it for exactly this trigger. A launchd job watches through its own
    KeepAlive condition, so the plist has to name the trigger.
    """
    if not path_unit_path.is_file():
        return False
    if path_unit_path.suffix != ".plist":
        return True
    keep_alive = _read_plist(path_unit_path).get("KeepAlive")
    if not isinstance(keep_alive, dict):
        return False
    states = keep_alive.get("PathState")
    return isinstance(states, dict) and states.get(str(trigger_path)) is True


def check_self_upgrade(
    *,
    conf_path: Optional[Path] = None,
    unit_path: Optional[Path] = None,
    path_unit_path: Optional[Path] = None,
    trigger_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
) -> UpgradeReadiness:
    defaults = default_upgrade_paths()
    conf_path = conf_path or defaults.conf_path
    unit_path = unit_path or defaults.unit_path
    path_unit_path = path_unit_path or defaults.path_unit_path
    trigger_path = trigger_path or defaults.trigger_path
    # The helper reads the config that sits beside the trigger.
    config_path = config_path or trigger_path.parent / "config.toml"

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

    # The helper also refuses a conf that names another server than the one
    # this endpoint is enrolled against. `set-server` without the rights to
    # write the conf moves only the config, so that endpoint needs one
    # reinstall before it can upgrade itself.
    enrolled = _enrolled_server(config_path)
    if enrolled.removesuffix("/") != conf["SERVER"].removesuffix("/"):
        return UpgradeReadiness(supported=False, reason="server_mismatch")

    # Nothing starts the helper without the watcher armed on the trigger.
    if not _watches_trigger(path_unit_path, trigger_path):
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
    except (OSError, ValueError):
        # An unreadable /etc, a vanished file or one that is not text means
        # the endpoint cannot upgrade itself. It must not mean the agent stops
        # reporting at all.
        return False
