def test_database_discovery_requires_auth(test_client):
    response = test_client.get("/api/source-discovery/databases")

    assert response.status_code in {401, 403}


def test_database_discovery_returns_source_types_and_templates(
    test_client, admin_headers
):
    response = test_client.get("/api/source-discovery/databases", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()

    source_types = {item["id"]: item for item in payload["source_types"]}
    assert source_types["paths"]["enabled"] is True
    assert source_types["database"]["enabled"] is True
    assert source_types["container"]["enabled"] is False

    template_engines = {item["engine"] for item in payload["templates"]}
    assert {"postgresql", "mysql", "mongodb", "redis"}.issubset(template_engines)

    for target in payload["templates"]:
        assert target["source_directories"]
        assert target["pre_backup_script"].startswith("#!/usr/bin/env bash")
        assert target["post_backup_script"].startswith("#!/usr/bin/env bash")
        assert target["script_name_base"]


def test_database_discovery_reports_detected_postgresql(
    test_client, admin_headers, monkeypatch
):
    from app.api import source_discovery

    monkeypatch.setattr(
        source_discovery,
        "_path_exists",
        lambda path: path == "/var/lib/postgresql",
    )
    monkeypatch.setattr(source_discovery, "_is_port_open", lambda port: False)

    response = test_client.get("/api/source-discovery/databases", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()

    assert len(payload["databases"]) == 1
    target = payload["databases"][0]
    assert target["engine"] == "postgresql"
    assert target["status"] == "detected"
    assert target["confidence"] == "medium"
    assert target["service_name"] == "postgresql"
    assert target["source_directories"] == ["/var/lib/postgresql"]
    assert 'systemctl stop "$SERVICE_NAME"' in target["pre_backup_script"]
    assert 'systemctl start "$SERVICE_NAME"' in target["post_backup_script"]
