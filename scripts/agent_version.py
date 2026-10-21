#!/usr/bin/env python3
"""Move the managed agent's version, so pull requests never have to.

The version lives twice: pyproject.toml's [project] version names the wheel the
server serves and the installer pins, and borg_ui_agent.__version__ is what a
running agent reports. Both are only ever rewritten here.

    python scripts/agent_version.py release    # run by scripts/release.sh
    python scripts/agent_version.py edge 1412  # run by the edge image build

release: when agent/ or pyproject.toml changed since the last v* tag and the
version did not move with them, bump the patch component. A release without
agent changes keeps the version, so enrolled agents are not offered a no-op
upgrade.

edge: stamp the workflow run number as a fourth component (0.1.21.1412). It
sorts after the release it builds on and before the next one, so every edge
build offers enrolled agents its code, which an unchanged version would not
(the server compares the reported version with the served one).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = Path("pyproject.toml")
INIT = Path("agent/borg_ui_agent/__init__.py")
AGENT_PATHS = ["agent/", "pyproject.toml"]

_PYPROJECT_LINE = re.compile(r'^version = "[^"]+"$', re.M)
_INIT_LINE = re.compile(r'^__version__ = "[^"]+"$', re.M)
_RELEASE = re.compile(r"^\d+\.\d+\.\d+$")


def pyproject_version(text: str) -> str:
    return tomllib.loads(text)["project"]["version"]


def read_version(root: Path = ROOT) -> str:
    return pyproject_version((root / PYPROJECT).read_text(encoding="utf-8"))


def write_version(version: str, root: Path = ROOT) -> None:
    for path, pattern, line in (
        (PYPROJECT, _PYPROJECT_LINE, f'version = "{version}"'),
        (INIT, _INIT_LINE, f'__version__ = "{version}"'),
    ):
        text = (root / path).read_text(encoding="utf-8")
        new, count = pattern.subn(line, text)
        if count != 1:
            sys.exit(f"{path}: expected one version line, found {count}")
        (root / path).write_text(new, encoding="utf-8")


def release_version(current: str, at_tag: str | None, agent_changed: bool) -> str:
    """The version the release ships. No previous tag means nothing to compare."""
    if not _RELEASE.fullmatch(current):
        sys.exit(f"agent version {current!r} is not X.Y.Z")
    if at_tag is None or not agent_changed or current != at_tag:
        return current
    major, minor, patch = current.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def edge_version(current: str, run_number: str) -> str:
    if not _RELEASE.fullmatch(current):
        sys.exit(f"agent version {current!r} is not X.Y.Z")
    if not run_number.isdigit():
        sys.exit(f"run number {run_number!r} is not a number")
    return f"{current}.{int(run_number)}"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def _release() -> str:
    current = read_version()
    tag = _git("describe", "--tags", "--abbrev=0", "--match", "v*", "HEAD")
    if tag.returncode != 0:
        return release_version(current, None, False)
    tag_name = tag.stdout.strip()
    at_tag = pyproject_version(_git("show", f"{tag_name}:pyproject.toml").stdout)
    changed = _git("diff", "--quiet", tag_name, "HEAD", "--", *AGENT_PATHS)
    if changed.returncode > 1:
        sys.exit(changed.stderr.strip())
    return release_version(current, at_tag, changed.returncode == 1)


def main(argv: list[str]) -> None:
    if argv[:1] == ["release"] and len(argv) == 1:
        version = _release()
    elif argv[:1] == ["edge"] and len(argv) == 2:
        version = edge_version(read_version(), argv[1])
    else:
        sys.exit("usage: agent_version.py release | edge <run-number>")
    write_version(version)
    print(version)


if __name__ == "__main__":
    main(sys.argv[1:])
