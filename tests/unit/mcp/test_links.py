"""Hand-off links into the web UI (plan phase 4, Task 1; spec 5.9)."""

import pytest

from app.mcp import links
from app.mcp.context import ConnectionContext, ToolContext
from app.mcp.levels import Level


def _ctx(base_url="http://borg.example.invalid"):
    conn = ConnectionContext(1, "test", 1, "admin", Level.MANAGE)
    return ToolContext(conn=conn, api=None, base_url=base_url)


@pytest.mark.unit
def test_web_link_encodes_params_and_drops_none():
    url = links.web(_ctx(), "repositories", import_="1", name="My Photos", path=None)
    assert url == "http://borg.example.invalid/repositories?import=1&name=My+Photos"


@pytest.mark.unit
def test_web_link_keeps_base_path():
    url = links.web(_ctx("https://borg.example.invalid/borg"), "cloud-storage", edit=4)
    assert url == "https://borg.example.invalid/borg/cloud-storage?edit=4"


@pytest.mark.unit
@pytest.mark.parametrize("key", ["passphrase", "password", "private_key", "secret"])
def test_web_link_refuses_secret_params(key):
    with pytest.raises(ValueError):
        links.web(_ctx(), "repositories", **{key: "x"})


@pytest.mark.unit
def test_named_links():
    ctx = _ctx()
    assert (
        links.repository(ctx, 7) == "http://borg.example.invalid/repositories?reveal=7"
    )
    assert links.ssh_deploy(ctx, "backups.example.com", "borg", 23) == (
        "http://borg.example.invalid/ssh-connections?deploy=1"
        "&host=backups.example.com&username=borg&port=23"
    )
    assert links.rclone_remote(ctx, 3).endswith("/cloud-storage?edit=3")
    assert links.new_user(ctx, username="sam", role="viewer").endswith(
        "/settings/users?new=1&username=sam&role=viewer"
    )
    assert links.import_repository(ctx, name="Photos", path="/data/example").endswith(
        "/repositories?import=1&name=Photos&path=%2Fdata%2Fexample"
    )


@pytest.mark.unit
def test_base_url_prefers_public_base_url(monkeypatch):
    from starlette.requests import Request

    from app.config import settings

    monkeypatch.setattr(settings, "public_base_url", "https://borg.example.invalid/")
    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "headers": [(b"host", b"internal:8081")],
            "root_path": "/borg",
            "path": "/borg/mcp",
            "client": ("10.0.0.2", 1),
            "server": ("internal", 8081),
            "query_string": b"",
            "method": "POST",
        }
    )
    assert links.base_url(request) == "https://borg.example.invalid/borg"
