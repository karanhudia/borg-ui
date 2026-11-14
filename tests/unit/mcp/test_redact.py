"""Secret scrubbing for tool output (plan Task 5)."""

import pytest

from app.mcp.redact import scrub


@pytest.mark.unit
def test_hides_secret_fields_at_any_depth():
    data = {
        "passphrase": "p1",
        "keys": [{"ssh_private_key": "k1", "name": "laptop"}],
        "token": "t1",
        "nested": {
            "service_url": "tgram://bot/chat",
            "webhook_url": "https://h",
            "key_data": "x",
        },
        "has_passphrase": True,
        "password_set": False,
    }
    out = scrub(data)
    assert out["passphrase"] == "[hidden]"
    assert out["keys"][0] == {"ssh_private_key": "[hidden]", "name": "laptop"}
    assert out["token"] == "[hidden]"
    assert set(out["nested"].values()) == {"[hidden]"}
    assert out["has_passphrase"] is True
    assert out["password_set"] is False


@pytest.mark.unit
def test_strings_lose_url_credentials():
    assert "pw" not in scrub({"url": "ssh://u:pw@host/repo"})["url"]
    assert scrub("plain") == "plain"
    assert scrub(None) is None
    assert scrub(3) == 3
