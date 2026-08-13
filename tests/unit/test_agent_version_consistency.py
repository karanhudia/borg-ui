"""The agent wheel version must match the package's declared __version__.

The wheel is built from pyproject.toml (`python -m build`), so its filename — and
the version the installer pins as PINNED_AGENT_VERSION — comes from pyproject's
[project] version, not from borg_ui_agent.__version__. Bumping only one drifts
silently: __init__.py read 0.1.3 while the wheel shipped 0.1.2, so a server built
from that tree offered every node an agent a release behind its own code.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def _dunder_version() -> str:
    init = (REPO_ROOT / "agent" / "borg_ui_agent" / "__init__.py").read_text(
        encoding="utf-8"
    )
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.M)
    assert match, "no __version__ in agent/borg_ui_agent/__init__.py"
    return match.group(1)


def test_agent_wheel_version_matches_the_package_version():
    pyproject, dunder = _pyproject_version(), _dunder_version()
    assert pyproject == dunder, (
        f"pyproject.toml pins {pyproject}, but borg_ui_agent.__version__ is "
        f"{dunder}. The built wheel takes the pyproject version, so the installer "
        "would ship an agent that disagrees with the code."
    )
