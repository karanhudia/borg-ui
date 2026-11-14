"""Shared fixtures for the MCP tests."""

import pytest

from app.database.models import LicensingState


@pytest.fixture
def pro_plan(test_db):
    """An active Pro licence, the way the real gate reads it."""
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="t-mcp", plan="pro", status="active")
        test_db.add(state)
    else:
        state.plan, state.status = "pro", "active"
    test_db.commit()
    return state


@pytest.fixture
def create_connection(test_client, pro_plan):
    """Create an MCP connection over REST; returns (row dict, token)."""

    def create(headers, *, name="Claude on my laptop", level="read", **extra):
        response = test_client.post(
            "/api/settings/mcp/connections",
            json={"name": name, "access_level": level, **extra},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        return body, body["token"]

    return create


ACCEPT = "application/json, text/event-stream"


class McpSession:
    """JSON-RPC over POST /mcp, the way a Streamable HTTP client talks."""

    def __init__(self, client, token, path="/mcp"):
        self.client, self.token, self.path, self._id = client, token, path, 0

    def post(self, method, params=None, headers=None):
        self._id += 1
        return self.client.post(
            self.path,
            json={
                "jsonrpc": "2.0",
                "id": self._id,
                "method": method,
                "params": params or {},
            },
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": ACCEPT,
                "MCP-Protocol-Version": "2025-06-18",
                **(headers or {}),
            },
        )

    def initialize(self, client_name="claude-code", version="1.2.3"):
        response = self.post(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": version},
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["result"]

    def list_tools(self):
        response = self.post("tools/list")
        assert response.status_code == 200, response.text
        return response.json()["result"]["tools"]

    def call(self, name, **arguments):
        response = self.post("tools/call", {"name": name, "arguments": arguments})
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        return {
            "text": "".join(c.get("text", "") for c in result["content"]),
            "data": result.get("structuredContent"),
            "is_error": result.get("isError", False),
        }


@pytest.fixture
def mcp(test_client):
    def connect(token, path="/mcp"):
        return McpSession(test_client, token, path)

    return connect


@pytest.fixture(autouse=True)
def _fresh_auth_cache():
    from app.mcp import auth

    auth.clear_cache()
    yield
    auth.clear_cache()


@pytest.fixture
def scratch_tools():
    """Register throwaway tools for one test, removed afterwards."""
    from app.mcp.registry import REGISTRY

    before = set(REGISTRY)
    yield REGISTRY
    for name in set(REGISTRY) - before:
        del REGISTRY[name]


@pytest.fixture
def seeded(test_db):
    """Two repositories, archives and one failed backup, with no real paths."""
    import uuid
    from datetime import datetime, timedelta

    from app.database.models import Archive, Operation, Repository

    now = datetime.utcnow()
    photos = Repository(
        name="Photos",
        path="/srv/backups/photos",
        borg_version=1,
        last_backup=now - timedelta(hours=3),
        last_check=now - timedelta(days=1),
        last_compact=now - timedelta(days=1),
        total_size="412.6 GB",
        archive_count=2,
        encryption="repokey",
        passphrase="hunter2-passphrase",
    )
    laptop = Repository(
        name="Laptop",
        path="/srv/backups/laptop",
        borg_version=1,
        last_backup=now - timedelta(days=9),
        last_check=now - timedelta(days=1),
        last_compact=now - timedelta(days=1),
        total_size="18.1 GB",
        archive_count=0,
    )
    test_db.add_all([photos, laptop])
    test_db.commit()
    for i in range(2):
        test_db.add(
            Archive(
                repository_id=photos.id,
                borg_id=f"ab{i}",
                name=f"photos-2026-11-1{i}",
                series="photos",
                start=now - timedelta(days=i),
                end=now - timedelta(days=i) + timedelta(minutes=6),
                nfiles=100 + i,
                original_size=10**9,
                deduplicated_size=10**6,
            )
        )
    failed = Operation(
        repository_id=laptop.id,
        kind="backup",
        category="backup",
        run_id=str(uuid.uuid4()),
        status="failed",
        error_message="Failed to create/acquire the lock",
        created_at=now - timedelta(hours=2),
        started_at=now - timedelta(hours=2),
        completed_at=now - timedelta(hours=2) + timedelta(minutes=2),
    )
    test_db.add(failed)
    test_db.commit()
    return {"photos": photos, "laptop": laptop, "failed": failed}


@pytest.fixture
def admin_mcp(mcp, create_connection, admin_headers):
    _, token = create_connection(admin_headers, name="admin laptop", level="read")
    return mcp(token)


@pytest.fixture
def viewer_mcp(mcp, create_connection, auth_headers):
    _, token = create_connection(auth_headers, name="viewer laptop", level="read")
    return mcp(token)


SECRET_VALUES = (
    "hunter2-passphrase",
    "PRIVATE-KEY-BODY-7f3a",
    "tgram://123456:SECRET-BOT-TOKEN/987",
    "SECRET-BOT-TOKEN",
    "SCRIPT-BODY-PASSWORD",
)


@pytest.fixture
def secrets_seeded(seeded, test_db, tmp_path):
    """Rows whose secrets must never reach a tool result."""
    import json as _json

    from app.database.models import (
        BackupPlan,
        NotificationSettings,
        RcloneRemote,
        ScheduledJob,
        Script,
        SSHKey,
    )

    script_file = tmp_path / "notify.sh"
    script_file.write_text(
        "curl -u admin:SCRIPT-BODY-PASSWORD https://example.invalid\n"
    )
    test_db.add_all(
        [
            SSHKey(
                name="nas key",
                key_type="ed25519",
                fingerprint="SHA256:abc",
                public_key="ssh-ed25519 AAAA nas",
                private_key="PRIVATE-KEY-BODY-7f3a",
                is_active=True,
                is_system_key=False,
            ),
            NotificationSettings(
                name="Phone",
                service_url="tgram://123456:SECRET-BOT-TOKEN/987",
                enabled=True,
                notify_on_backup_failure=True,
            ),
            RcloneRemote(
                name="b2",
                provider="b2",
                config_source="managed",
                redacted_config={"account": "***"},
                last_test_status="success",
            ),
            Script(
                name="notify", file_path=str(script_file), description="Ping when done"
            ),
            BackupPlan(
                name="Nightly photos",
                source_directories=_json.dumps(["/local/photos"]),
                cron_expression="0 2 * * *",
                timezone="UTC",
                schedule_enabled=True,
            ),
            ScheduledJob(
                name="Nightly",
                cron_expression="0 3 * * *",
                timezone="UTC",
                repository_id=seeded["photos"].id,
                repository=seeded["photos"].path,
                enabled=True,
            ),
        ]
    )
    test_db.commit()
    return seeded
