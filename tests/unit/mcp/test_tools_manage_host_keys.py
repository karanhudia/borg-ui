"""trust_host_key confirms every key it pins (phase 4; PR #1585 review)."""

import base64

import pytest

from app.utils.ssh_host_keys import key_fingerprint
from tests.unit.mcp.test_tools_stubbed import run

CONNS = {
    "/api/ssh-keys/connections": {
        "connections": [
            {"id": 4, "host": "backups.example.com", "username": "borg", "port": 22}
        ]
    }
}
HOST = "/api/ssh-keys/connections/4/host-key"
TRUST = f"POST {HOST}/trust"


def _line(kind: str, body: bytes) -> str:
    return f"backups.example.com {kind} {base64.b64encode(body).decode()}"


ED = _line("ssh-ed25519", b"example ed25519 host key")
RSA = _line("ssh-rsa", b"example rsa host key")
RSA_SWAPPED = _line("ssh-rsa", b"another rsa host key")
TWO = f"{ED}\n{RSA}"


def _scan(observed: str) -> dict:
    return {
        "connection_id": 4,
        "host": "backups.example.com",
        "port": 22,
        "status": "unpinned",
        "trusted_fingerprint": None,
        "observed_fingerprint": key_fingerprint(observed),
        "observed_key": observed,
    }


def _routes(observed: str) -> dict:
    return {**CONNS, HOST: _scan(observed), TRUST: _scan(observed)}


ALL = [key_fingerprint(ED), key_fingerprint(RSA)]


@pytest.mark.unit
def test_first_call_lists_every_key_and_trusts_nothing():
    result, api = run(
        "trust_host_key", _routes(TWO), ssh_connection="borg@backups.example.com"
    )
    assert api.posts == []
    for fingerprint in ALL:
        assert fingerprint in result.text
    assert sorted(result.data["fingerprints"]) == sorted(ALL)


@pytest.mark.unit
def test_trusts_when_every_fingerprint_is_confirmed():
    _, api = run(
        "trust_host_key",
        _routes(TWO),
        ssh_connection="borg@backups.example.com",
        fingerprints=ALL,
    )
    assert api.posts == [(f"{HOST}/trust", {"key": TWO})]


@pytest.mark.unit
def test_an_unconfirmed_key_in_an_unchanged_set_is_not_trusted():
    """The finding: confirming only the strongest key must not pin the rest."""
    result, api = run(
        "trust_host_key",
        _routes(TWO),
        ssh_connection="borg@backups.example.com",
        fingerprints=[key_fingerprint(ED)],
    )
    assert api.posts == []
    assert result.is_error
    assert key_fingerprint(RSA) in result.text


@pytest.mark.unit
def test_a_key_that_changed_since_confirmation_is_not_trusted():
    result, api = run(
        "trust_host_key",
        _routes(f"{ED}\n{RSA_SWAPPED}"),
        ssh_connection="borg@backups.example.com",
        fingerprints=ALL,
    )
    assert api.posts == []
    assert result.is_error


@pytest.mark.unit
def test_unreachable_server_trusts_nothing():
    routes = {
        **CONNS,
        HOST: {**_scan(TWO), "observed_key": None, "observed_fingerprint": None},
    }
    result, api = run(
        "trust_host_key", routes, ssh_connection="borg@backups.example.com"
    )
    assert api.posts == []
    assert result.is_error
