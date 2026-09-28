"""Relocatable CPython builds for platforms without a usable system Python.

The agent needs Python 3.11 or newer. A Linux distribution provides that; macOS
does not, so the installer there unpacks a python-build-standalone release
under the agent root and creates the virtualenv from it, the way Borg's static
binary reaches a node: a published, checksummed artifact selected by a
manifest the server serves.

The build follows the ``PYTHON_VERSION`` minor in ``docker/runtime-base.env``.
To move to a newer build, run::

    python scripts/refresh_python_runtime_manifest.py

which asks the release API for the newest build of that minor and rewrites
``python_runtimes.json``. ``tests/unit/test_python_runtimes.py`` fails if the
manifest and the pinned minor disagree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

MANIFEST_PATH = Path(__file__).with_name("python_runtimes.json")


class PythonRuntime(NamedTuple):
    """One published build: which machine it runs on, and what it hashes to."""

    platform: str
    arch: str  # as reported by `uname -m`
    asset: str
    sha256: str
    url: str


def _load() -> tuple[dict[str, tuple[PythonRuntime, ...]], str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    runtimes = {
        version: tuple(PythonRuntime(**entry) for entry in entries)
        for version, entries in manifest["runtimes"].items()
    }
    return runtimes, manifest["current"]


PYTHON_RUNTIMES, CURRENT_PYTHON_RUNTIME = _load()


def runtime_table(version: str | None = None) -> str:
    """Render the installer's runtime lookup table.

    Each output line is ``platform arch sha256 url``; the installer picks the
    row of its platform and architecture. An unknown version contributes no
    rows, and the installer then says so instead of installing something else.
    """
    version = CURRENT_PYTHON_RUNTIME if version is None else version
    return "\n".join(
        f"{runtime.platform} {runtime.arch} {runtime.sha256} {runtime.url}"
        for runtime in PYTHON_RUNTIMES.get(version, ())
    )
