"""Process groups an agent process leaves running when it dies.

Borg and script hooks run in a session of their own (``start_new_session``).
systemd stops the whole control group and a container takes every process
with it, but launchd stops only the agent's own process group: after a crash
and a ``KeepAlive`` restart, or with an agent started by hand, a hook can keep
running while the server runs its job again.

The agent writes one small file per child it starts into ``children/`` beside
its config, and removes it once the child has ended. Before its first hello,
a new agent process ends the group of every file whose agent process is gone,
while that group is still the recorded one (see _is_recorded_group).
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from agent.borg_ui_agent.config import default_config_path

logger = logging.getLogger(__name__)

# How long a leftover group gets to end on SIGTERM before SIGKILL.
LEFTOVER_GRACE_SECONDS = 10.0


def default_children_dir(config_path: Optional[Path] = None) -> Path:
    """Beside config.toml: written by the agent's own user on every platform."""
    return (config_path or default_config_path()).parent / "children"


def process_start_token(pid: int) -> Optional[str]:
    """When `pid` started, as an opaque string, or None if it does not exist
    or cannot be read. Tells a process apart from a later one with its pid."""
    try:
        # The fields after the command name's closing parenthesis are fixed;
        # starttime is field 22.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return f"proc:{fields[19]}"
    except (OSError, IndexError):
        pass
    try:
        completed = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    started = completed.stdout.strip()
    return f"ps:{started}" if completed.returncode == 0 and started else None


def boot_identity() -> Optional[str]:
    """This boot of the machine, or None if it cannot be read. No process of
    an earlier boot can still run, and its ids now name other processes."""
    try:
        return "linux:" + Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        pass
    try:
        completed = subprocess.run(
            ["sysctl", "-n", "kern.boottime"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    booted = completed.stdout.strip()
    return f"bsd:{booted}" if completed.returncode == 0 and booted else None


def _is_process(pid: Any, start: Any) -> bool:
    """Whether `pid` is alive and still the process that started at `start`."""
    if not isinstance(pid, int) or pid <= 1 or not start:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        pass
    return process_start_token(pid) == start


def _is_recorded_group(entry: dict[str, Any]) -> bool:
    """Whether the recorded group still lives and is still that group. A
    group id is not handed out again while the group has members, so a live
    group whose leader has ended (a hook's shell gone, a background child
    left) is still the original one. Only a process with the leader's pid
    and another start time (or one that cannot be read) means the group
    emptied and its id was taken."""
    pgid = entry.get("pgid")
    if not isinstance(pgid, int) or pgid <= 1 or not _group_alive(pgid):
        return False
    try:
        os.kill(pgid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        pass
    return process_start_token(pgid) == entry.get("start")


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    return True


class ChildRegistry:
    """The children this agent process started, one file each."""

    def __init__(self, root: Optional[Path]):
        self.root = root if os.name == "posix" else None
        self._lock = threading.Lock()
        self._children: dict[int, subprocess.Popen] = {}
        self._boot: Optional[str] = None
        self._agent: Optional[dict[str, Any]] = None

    def _path(self, pid: int) -> Path:
        assert self.root is not None
        return self.root / f"{pid}.json"

    def track(self, process: subprocess.Popen) -> None:
        """Record a child a job handler started in a session of its own."""
        if self.root is None:
            return
        if self._agent is None:
            self._boot = boot_identity()
            self._agent = {
                "pid": os.getpid(),
                "start": process_start_token(os.getpid()),
            }
        entry = {
            "pid": process.pid,
            "pgid": process.pid,
            "start": process_start_token(process.pid),
            "boot": self._boot,
            "agent": self._agent,
        }
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = self._path(process.pid)
            temporary = path.with_name(f".{path.name}.tmp")
            temporary.write_text(json.dumps(entry), encoding="utf-8")
            os.replace(temporary, path)
        except OSError:
            logger.warning("Could not record child %s", process.pid, exc_info=True)
            return
        with self._lock:
            self._children[process.pid] = process

    def forget_ended(self) -> None:
        """Remove the files of children that have ended (a job ended)."""
        with self._lock:
            ended = [
                pid
                for pid, process in self._children.items()
                if process.returncode is not None
            ]
            for pid in ended:
                self._children.pop(pid, None)
        for pid in ended:
            self._path(pid).unlink(missing_ok=True)

    def end_leftovers(self, *, grace_seconds: float = LEFTOVER_GRACE_SECONDS) -> None:
        """Before the first hello: end the groups a dead agent process left.

        Only a group of this boot that is still the recorded one is
        signalled; a file of another live agent process (one started by hand
        next to the service) is left.
        """
        if self.root is None or not self.root.is_dir():
            return
        boot = boot_identity()
        # A signalled group's file stays until the group has ended: an
        # agent stopped during the grace leaves it for the next one.
        signalled: list[tuple[Path, dict[str, Any]]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                path.unlink(missing_ok=True)
                continue
            agent = entry.get("agent") if isinstance(entry, dict) else None
            if isinstance(agent, dict) and _is_process(
                agent.get("pid"), agent.get("start")
            ):
                continue
            pgid = entry.get("pgid")
            if entry.get("boot") == boot and _is_recorded_group(entry):
                try:
                    os.killpg(pgid, signal.SIGTERM)
                    signalled.append((path, entry))
                    logger.warning(
                        "Ending process group %s a previous agent process left running",
                        pgid,
                    )
                    continue
                except OSError:
                    pass
            path.unlink(missing_ok=True)
        deadline = time.monotonic() + grace_seconds
        while signalled and time.monotonic() < deadline:
            if not any(_group_alive(entry["pgid"]) for _, entry in signalled):
                break
            time.sleep(0.1)
        else:
            for _, entry in signalled:
                try:
                    if _is_recorded_group(entry):
                        os.killpg(entry["pgid"], signal.SIGKILL)
                except OSError:
                    pass
            # SIGKILL cannot be caught; give the members a moment to go.
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and any(
                _group_alive(entry["pgid"]) for _, entry in signalled
            ):
                time.sleep(0.05)
        for path, entry in signalled:
            if not _group_alive(entry["pgid"]):
                _remove_if_unchanged(path, entry)


def _remove_if_unchanged(path: Path, entry: dict[str, Any]) -> None:
    """Remove a child file unless it now describes another child: once the
    group has ended, its pid may go to a child of another agent process,
    whose file has the same name."""
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if current == entry:
        path.unlink(missing_ok=True)


_registry: Optional[ChildRegistry] = None


def install(registry: Optional[ChildRegistry]) -> None:
    """Make `registry` the one track_child records into (the session)."""
    global _registry
    _registry = registry


def track_child(process: subprocess.Popen) -> None:
    """Record a child a job handler started; nothing without a registry."""
    registry = _registry
    if registry is None:
        return
    try:
        registry.track(process)
    except Exception:  # noqa: BLE001 - bookkeeping never fails the job
        logger.warning("Could not record child %s", process.pid, exc_info=True)
