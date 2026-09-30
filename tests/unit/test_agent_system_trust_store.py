"""The agent verifies TLS against the machine's trust store.

requests verifies against certifi's bundle, so a self-signed server certificate
that the operator installed with update-ca-certificates satisfied curl and the
agent's websocket (which loads the system store) but not registration or any
other HTTP call (#1272). truststore routes every ssl context through the
system store; it must be in place before the first request, so it goes in at
the CLI entry, not in one client.
"""

from __future__ import annotations

import ssl

import pytest
import truststore

from agent.borg_ui_agent import cli


def test_the_cli_routes_tls_through_the_system_trust_store():
    # Any earlier test that ran the CLI left truststore in place; start clean
    # so this checks main() itself and not that leftover.
    truststore.extract_from_ssl()
    assert ssl.SSLContext is not truststore.SSLContext
    try:
        with pytest.raises(SystemExit):
            cli.main(["--help"])
        assert ssl.SSLContext is truststore.SSLContext
    finally:
        truststore.extract_from_ssl()


def test_the_agent_wheel_declares_truststore():
    """The wheelhouse is built from the declared dependencies; a missing
    declaration would ship an agent that fails at import on the endpoint."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    deps = tomllib.loads((root / "pyproject.toml").read_text())["project"][
        "dependencies"
    ]
    assert any(dep.startswith("truststore") for dep in deps)
    pins = (root / "agent" / "constraints.txt").read_text()
    assert "truststore==" in pins
