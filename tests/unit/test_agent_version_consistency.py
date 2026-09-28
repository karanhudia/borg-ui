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

from app.core.agent_versions import compute_agent_upgrade_status

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


def test_an_agent_from_before_the_borg1_lock_wait_change_is_offered_an_upgrade():
    """#1220 changed the agent's Borg 1 command lines (--lock-wait) without
    moving the version, so a server built from that tree kept telling a 0.1.10
    agent it was up to date and never sent it the fix (#1231). The served
    version is the wheel's, so the pyproject version is the one compared.
    """
    assert (
        compute_agent_upgrade_status(
            reported="0.1.10", desired=None, available=_pyproject_version()
        )
        == "outdated"
    )
