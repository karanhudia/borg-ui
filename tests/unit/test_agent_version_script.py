"""scripts/agent_version.py decides the agent version at release and on edge.

The orderings are checked with the server's own comparison, since what matters
is whether an enrolled agent is offered the build.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.core.agent_versions import compute_agent_upgrade_status
from scripts.agent_version import (
    INIT,
    PYPROJECT,
    ROOT,
    edge_version,
    read_version,
    release_version,
    write_version,
)


def _status(reported: str, available: str) -> str:
    return compute_agent_upgrade_status(
        reported=reported, desired=None, available=available
    )


def test_release_bumps_the_patch_when_the_agent_changed():
    assert release_version("0.1.21", "0.1.21", agent_changed=True) == "0.1.22"


def test_release_keeps_the_version_when_the_agent_did_not_change():
    assert release_version("0.1.21", "0.1.21", agent_changed=False) == "0.1.21"


def test_release_keeps_a_version_already_moved_since_the_tag():
    assert release_version("0.1.21", "0.1.15", agent_changed=True) == "0.1.21"


def test_release_without_a_previous_tag_keeps_the_version():
    assert release_version("0.1.21", None, agent_changed=True) == "0.1.21"


def test_release_refuses_an_edge_stamped_version():
    with pytest.raises(SystemExit):
        release_version("0.1.21.1412", "0.1.21", agent_changed=True)


def test_edge_sorts_between_its_release_and_the_next():
    edge = edge_version("0.1.21", "1412")
    assert edge == "0.1.21.1412"
    assert _status(reported="0.1.21", available=edge) == "outdated"
    assert _status(reported=edge, available="0.1.22") == "outdated"
    assert _status(reported=edge, available=edge_version("0.1.21", "1413")) == (
        "outdated"
    )


def test_edge_refuses_a_non_numeric_run_number():
    with pytest.raises(SystemExit):
        edge_version("0.1.21", "12a")


def test_write_version_moves_both_files(tmp_path: Path):
    for path in (PYPROJECT, INIT):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / path, tmp_path / path)

    write_version("9.8.7", tmp_path)

    assert read_version(tmp_path) == "9.8.7"
    assert '__version__ = "9.8.7"' in (tmp_path / INIT).read_text()
